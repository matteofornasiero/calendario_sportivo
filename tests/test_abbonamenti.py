"""Verifica i calendari iCalendar: compatibilità e aggiornamenti senza churn."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from aggiorna_calendario import write_data
from genera_abbonamenti import (calendar_teams, competition, generate, previous_events,
                                serialize, slug, uid)


class CalendarSubscriptionsTests(unittest.TestCase):
    def setUp(self):
        self.clock = datetime(2026, 11, 17, 10, tzinfo=timezone.utc)
        self.match = {
            "id": "football-123", "sport": "seriea", "date": "2026-11-21",
            "time": "20:45", "timeConfirmed": True, "startUtc": "2026-11-21T19:45:00Z",
            "title": "Napoli - Torino", "home": "Napoli", "away": "Torino",
            "loc": "Giornata 12", "venue": "Maradona, Napoli", "status": "TIMED",
            "homeScore": None, "awayScore": None,
        }

    def test_correct_utc_dates_and_escaped_text(self):
        e = dict(self.match, venue="Stadio, Napoli; Italia")
        source = serialize("Torino", [e], timestamp=self.clock)
        self.assertIn("BEGIN:VCALENDAR\r\n", source)
        self.assertIn("DTSTART:20261121T194500Z", source)
        self.assertIn("DTEND:20261121T214500Z", source)
        self.assertIn("LOCATION:Stadio\\, Napoli\\; Italia", source)
        self.assertIn("REFRESH-INTERVAL;VALUE=DURATION:PT12H", source)
        self.assertTrue(all(len(line.encode("utf-8")) <= 75 for line in source.split("\r\n")))

    def test_uid_stays_stable_when_match_moves(self):
        first = serialize("Torino", [self.match], timestamp=self.clock)
        moved = dict(self.match, startUtc="2026-11-22T19:45:00Z", date="2026-11-22")
        second = serialize("Torino", [moved], first, self.clock.replace(day=18))
        self.assertIn("DTSTART:20261122T194500Z", second)
        self.assertEqual(uid(self.match), uid(moved))
        self.assertIn("SEQUENCE:1", second)
        self.assertIn("DTSTAMP:20261117T100000Z", second)
        self.assertIn("LAST-MODIFIED:20261118T100000Z", second)

    def test_same_events_do_not_rewrite_file_every_two_hours(self):
        before = serialize("Torino", [self.match], timestamp=self.clock)
        after = serialize("Torino", [self.match], before, self.clock.replace(hour=12))
        self.assertEqual(before, after)
        self.assertEqual(len(previous_events(after)), 1)

    def test_unknown_time_is_all_day_and_marked_provisional(self):
        provisional = dict(self.match, time="", timeConfirmed=False, startUtc=None)
        content = serialize("Torino", [provisional], timestamp=self.clock)
        self.assertIn("DTSTART;VALUE=DATE:20261121", content)
        self.assertIn("DTEND;VALUE=DATE:20261122", content)
        self.assertIn("orario da confermare", content)

    def test_cancellation_has_correct_status(self):
        cancelled = dict(self.match, status="CANCELLED")
        content = serialize("Torino", [cancelled], timestamp=self.clock)
        self.assertIn("STATUS:CANCELLED", content)

    def test_separate_competitions_and_teams(self):
        self.assertEqual(competition(dict(self.match, loc="Coppa Italia")), "coppa")
        self.assertEqual(competition(dict(self.match, loc="Supercoppa")), "supercoppa")
        self.assertEqual(competition(dict(self.match, loc="Giornata 1")), "seriea")
        self.assertEqual(slug("Fenerbahçe"), "fenerbahce")
        self.assertEqual(calendar_teams(dict(self.match, away="TBD")), ["Napoli"])

    def test_generate_public_catalog_and_single_team_calendar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = [self.match,
                dict(self.match, id="football-124", title="Napoli - Atalanta",
                     home="Napoli", away="Atalanta", date="2026-11-22",
                     startUtc="2026-11-22T19:45:00Z"),
                dict(self.match, id="cup-12", title="Torino - Roma", home="Torino",
                     away="Roma", loc="Coppa Italia", date="2026-12-02",
                     startUtc="2026-12-02T20:00:00Z")]
            data = root / "dati.js"
            write_data(data, events, {}, {"schemaVersion": 2})
            listing = generate(data, root / "calendari", self.clock)
            self.assertIn("Torino", [item["name"] for item in listing["teams"]])
            self.assertIn("Coppa Italia", [item["name"] for item in listing["competitions"]])
            torino = (root / "calendari/squadra/torino.ics").read_text()
            napoli = (root / "calendari/squadra/napoli.ics").read_text()
            seriea = (root / "calendari/competizione/seriea.ics").read_text()
            coppa = (root / "calendari/competizione/coppa.ics").read_text()
            self.assertEqual(torino.count("BEGIN:VEVENT"), 2)
            self.assertEqual(napoli.count("BEGIN:VEVENT"), 2)
            self.assertEqual(seriea.count("BEGIN:VEVENT"), 2)
            self.assertEqual(coppa.count("BEGIN:VEVENT"), 1)
            saved = json.loads((root / "calendari/catalogo.json").read_text())
            self.assertEqual(saved["schemaVersion"], 1)
            self.assertTrue(all(item["path"].startswith("calendari/") for item in saved["teams"]))
            self.assertTrue(all(item["path"].endswith(".ics") for item in saved["competitions"]))
            initial = (root / "calendari/squadra/torino.ics").read_bytes()
            generate(data, root / "calendari", self.clock.replace(hour=12))
            self.assertEqual(initial, (root / "calendari/squadra/torino.ics").read_bytes())


if __name__ == "__main__":
    unittest.main()
