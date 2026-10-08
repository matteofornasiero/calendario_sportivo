import contextlib
import copy
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import aggiorna_calendario as app


def football_match(status="TIMED", date="2026-11-12T19:45:00Z"):
    return {"id": 1, "utcDate": date, "status": status, "matchday": 12,
            "homeTeam": {"name": "Torino", "crest": ""}, "awayTeam": {"name": "Roma", "crest": ""},
            "score": {"fullTime": {"home": 2, "away": 1}}}


class UpdaterTests(unittest.TestCase):
    def test_unconfirmed_football_midnight_is_not_two_am(self):
        event = app.parse_football_matches({"matches": [football_match("SCHEDULED", "2026-08-22T00:00:00Z")]}, "seriea")[0]
        self.assertEqual(event["date"], "2026-08-22")
        self.assertEqual(event["time"], "")
        self.assertFalse(event["timeConfirmed"])
        self.assertIsNone(event["startUtc"])
        self.assertIsNone(event["homeScore"])

    def test_rome_uses_winter_and_summer_offsets(self):
        self.assertEqual(app.timestamp_clock("2026-08-22T19:00:00Z")["time"], "21:00")
        self.assertEqual(app.timestamp_clock("2026-11-12T19:45:00Z")["time"], "20:45")
        self.assertEqual(app.timestamp_clock("2026-10-25T00:30:00Z")["time"], "02:30")
        self.assertEqual(app.timestamp_clock("2026-10-25T01:30:00Z")["time"], "02:30")

    def test_local_day_rolls_over(self):
        event = app.timestamp_clock("2026-12-31T23:15Z")
        self.assertEqual((event["date"], event["time"]), ("2027-01-01", "00:15"))

    def test_postponements_and_finished_results(self):
        events = app.parse_football_matches({"matches": [football_match("POSTPONED"), football_match("FINISHED")]}, "seriea")
        self.assertEqual(events[0]["status"], "POSTPONED")
        self.assertFalse(events[0]["timeConfirmed"])
        self.assertEqual((events[1]["homeScore"], events[1]["awayScore"]), (2, 1))

    def test_f1_uses_actual_sessions_not_saturday_at_four(self):
        race = {"season": "2026", "round": "2", "date": "2026-03-15", "time": "07:00:00Z", "raceName": "Chinese Grand Prix",
                "Qualifying": {"date": "2026-03-14", "time": "07:00:00Z"},
                "Sprint": {"date": "2026-03-14", "time": "03:00:00Z"}}
        events = app.parse_f1_calendar({"MRData": {"RaceTable": {"Races": [race]}}})
        qualifying = next(event for event in events if event["title"].startswith("Qualifiche:"))
        self.assertEqual(qualifying["time"], "08:00")
        self.assertEqual(len(events), 3)
        self.assertTrue(any(event["title"].startswith("Sprint:") for event in events))

    def test_missing_f1_time_is_unconfirmed(self):
        race = {"season": "2026", "round": "1", "date": "2026-03-08", "raceName": "GP"}
        event = app.parse_f1_calendar({"MRData": {"RaceTable": {"Races": [race]}}})[0]
        self.assertEqual(event["time"], "")

    def test_espn_filters_season_and_keeps_unknown_time(self):
        event = {"id": "12", "date": "2027-01-11T00:00Z", "season": {"year": 2026, "type": 3},
                 "competitions": [{"date": "2027-01-11T00:00Z", "timeValid": False,
                     "competitors": [{"homeAway": "home", "team": {"displayName": "Denver Broncos"}},
                                     {"homeAway": "away", "team": {"displayName": "Buffalo Bills"}}]}]}
        other_season = copy.deepcopy(event)
        other_season["season"]["year"] = 2027
        result = app.parse_espn_events({"events": [event, other_season]}, "nfl", 2026)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["isTop"])
        self.assertEqual(result[0]["time"], "")

    def test_espn_fetches_next_year_and_removes_duplicates(self):
        event = app.parse_football_matches({"matches": [football_match()]}, "seriea")[0]
        with patch.object(app, "get_json", return_value={"events": []}) as request, patch.object(app, "parse_espn_events", return_value=[event]):
            result = app.fetch_espn_calendar("football/nfl", "nfl", 2026)
        self.assertEqual(len(result), 1)
        urls = [call.args[0] for call in request.call_args_list]
        self.assertIn("dates=2027", urls[1])
        self.assertNotIn("20260901-20270228", urls[0])

    def test_football_standings_keep_real_points(self):
        table = {"type": "TOTAL", "table": [{"position": 1, "team": {"name": "Torino"}, "playedGames": 5,
                 "won": 4, "draw": 1, "lost": 0, "points": 13, "goalDifference": 7}]}
        with patch.object(app, "get_json", return_value={"standings": [table]}):
            row = app.fetch_football_standings("CL")[0]
        self.assertEqual((row["points"], row["played"]), (13, 5))

    def test_partial_failure_preserves_source_and_timestamp(self):
        old_event = {**app.timestamp_clock("2026-10-10T18:00:00Z"), "id": "old-nfl", "title": "NFL", "sport": "nfl"}
        old_stamp = "2026-10-07T08:00:00+00:00"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dati.js"
            app.write_data(path, [old_event], {"nfl": {"divisions": {"AFC West": []}}},
                           {"schemaVersion": 2, "sources": {"nfl": {"updatedAt": old_stamp, "status": "ok"}}})
            def data(url, authenticated=False):
                if "/competitions/SA/matches" in url:
                    return {"matches": [football_match()]}
                raise RuntimeError("Fonte di prova non disponibile")
            with patch.object(app, "get_json", side_effect=data), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = app.update(path, datetime(2026, 10, 8, tzinfo=timezone.utc))
            events, _, meta = app.load_previous(path)
            self.assertEqual(code, 1)
            self.assertIn(old_event, events)
            self.assertEqual(meta["sources"]["nfl"]["updatedAt"], old_stamp)
            self.assertEqual(meta["sources"]["nfl"]["status"], "error")
            self.assertTrue(meta["partial"])

    def test_total_failure_does_not_overwrite_legacy_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dati.js"
            original = 'window.calendarData = [];\nwindow.standingsData = {};'
            path.write_text(original, encoding="utf-8")
            with patch.object(app, "get_json", side_effect=RuntimeError("Offline")), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    app.update(path)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_invalid_dates_do_not_replace_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dati.js"
            path.write_text("original", encoding="utf-8")
            with self.assertRaises(ValueError):
                app.write_data(path, [{"date": "not-a-date", "title": "Bad"}], {}, {})
            self.assertEqual(path.read_text(encoding="utf-8"), "original")

    def test_json_with_semicolons_and_html_roundtrips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dati.js"
            event = {"date": "2026-10-08", "time": "", "title": "Team; <script>"}
            app.write_data(path, [event], {}, {})
            self.assertNotIn("<script>", path.read_text(encoding="utf-8"))
            self.assertEqual(app.load_previous(path)[0], [event])


if __name__ == "__main__":
    unittest.main()
