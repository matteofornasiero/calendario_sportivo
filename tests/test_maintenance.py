"""Test senza rete per passaggi di stagione e monitor di salute."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import aggiorna_calendario as calendar
from monitor_salute import EXPECTED_SOURCES, diagnose


def race_payload(year):
    return {"MRData": {"RaceTable": {"Races": [{
        "season": str(year), "round": "1", "raceName": "Test Grand Prix",
        "date": f"{year}-05-01", "time": "14:00:00Z",
        "Circuit": {"circuitName": "Circuit", "Location": {"locality": "Roma", "country": "Italia"}}
    }]}}}


class SeasonTransitionTests(unittest.TestCase):
    @patch.object(calendar, "get_json")
    def test_future_f1_season_preloaded_in_autumn(self, get_json):
        get_json.side_effect = lambda url: race_payload(2027 if "/2027.json" in url else 2026)
        now = datetime(2026, 10, 11, tzinfo=timezone.utc)
        events = calendar.fetch_f1_calendar_window(now)
        self.assertEqual({event["id"] for event in events}, {"f1-2026-1-Race", "f1-2027-1-Race"})
        self.assertEqual(get_json.call_count, 2)

    @patch.object(calendar, "get_json")
    def test_unpublished_next_f1_season_does_not_break_current(self, get_json):
        def fake(url):
            if "/2027.json" in url:
                raise RuntimeError("404 calendario futuro")
            return race_payload(2026)
        get_json.side_effect = fake
        events = calendar.fetch_f1_calendar_window(datetime(2026, 10, 11, tzinfo=timezone.utc))
        self.assertEqual(len(events), 1)
        self.assertIn("2026", events[0]["id"])

    @patch.object(calendar, "get_json")
    def test_previous_f1_season_available_in_january(self, get_json):
        get_json.side_effect = lambda url: race_payload(2026 if "/2026.json" in url else 2027)
        events = calendar.fetch_f1_calendar_window(datetime(2027, 1, 15, tzinfo=timezone.utc))
        self.assertEqual(len(events), 2)

    @patch.object(calendar, "fetch_f1_standings")
    def test_early_season_shows_previous_f1_standings(self, fetch):
        fetch.side_effect = [ValueError("not yet available"), [{"name": "Driver", "points": "200"}]]
        rows, season = calendar.fetch_f1_standings_with_rollover(2027, 2)
        self.assertEqual(season, 2026)
        self.assertEqual(len(rows), 1)
        self.assertEqual(fetch.call_args_list[1].args[0], 2026)

    @patch.object(calendar, "fetch_f1_standings", side_effect=ValueError("missing"))
    def test_missing_standings_during_active_season_is_error(self, fetch):
        with self.assertRaises(ValueError):
            calendar.fetch_f1_standings_with_rollover(2027, 7)

    @patch.object(calendar, "fetch_espn_calendar")
    def test_nfl_offseason_uses_last_valid_calendar(self, fetch):
        fetch.side_effect = [ValueError("future schedule missing"), [{"id": "nfl-last"}]]
        rows, season = calendar.fetch_nfl_calendar_with_rollover(2027, 4)
        self.assertEqual(season, 2026)
        self.assertEqual(rows[0]["id"], "nfl-last")
        self.assertEqual(fetch.call_args_list[-1].args[2], 2026)

    @patch.object(calendar, "fetch_espn_calendar")
    def test_new_nfl_schedule_is_preferred(self, fetch):
        fetch.return_value = [{"id": "nfl-next"}]
        rows, season = calendar.fetch_nfl_calendar_with_rollover(2027, 5)
        self.assertEqual((rows[0]["id"], season), ("nfl-next", 2027))
        fetch.assert_called_once()


class CalendarQualityTests(unittest.TestCase):
    def test_short_core_feed_rejected(self):
        with self.assertRaisesRegex(ValueError, "troppo corto"):
            calendar.check_calendar_quality("seriea", [{"date": "2026-11-18"}], datetime(2026, 11, 17, tzinfo=timezone.utc))

    def test_no_upcoming_matches_during_regular_season_rejected(self):
        historical = [{"date": "2026-04-01"}] * 380
        with self.assertRaisesRegex(ValueError, "prossimi 45 giorni"):
            calendar.check_calendar_quality("seriea", historical, datetime(2026, 11, 17, tzinfo=timezone.utc))

    def test_winter_f1_calendar_without_upcoming_races_is_valid(self):
        historical = [{"date": "2026-11-01"}] * 115
        calendar.check_calendar_quality("f1", historical, datetime(2026, 12, 17, tzinfo=timezone.utc))

    def test_valid_core_feed_accepted(self):
        events = [{"date": "2026-11-19"}] * 380
        calendar.check_calendar_quality("seriea", events, datetime(2026, 11, 17, tzinfo=timezone.utc))


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 17, 10, tzinfo=timezone.utc)
        self.meta = {
            "generatedAt": self.now.isoformat(),
            "sources": {k: {"status": "ok", "updatedAt": self.now.isoformat()} for k in EXPECTED_SOURCES},
        }

    def test_recent_data_is_healthy(self):
        self.assertEqual(diagnose(self.meta, self.now), [])

    def test_missing_cron_updates_are_detected(self):
        self.meta["generatedAt"] = (self.now - timedelta(hours=17)).isoformat()
        self.assertTrue(any("16 ore" in error for error in diagnose(self.meta, self.now)))

    def test_transient_source_errors_do_not_raise_incident(self):
        self.meta["sources"]["nazionale"] = {
            "status": "error", "updatedAt": (self.now - timedelta(hours=24)).isoformat(), "error": "timeout"}
        self.assertEqual(diagnose(self.meta, self.now), [])

    def test_persistent_source_errors_raise_incident(self):
        self.meta["sources"]["nazionale"] = {
            "status": "error", "updatedAt": (self.now - timedelta(hours=72)).isoformat(), "error": "HTTP 403"}
        self.assertTrue(any("nazionale" in error for error in diagnose(self.meta, self.now)))

    def test_missing_sources_are_detected(self):
        self.meta["sources"].pop("nfl")
        self.assertTrue(any("nfl" in error for error in diagnose(self.meta, self.now)))

    def test_summer_cups_can_be_missing(self):
        summer = self.now.replace(month=7)
        self.meta["generatedAt"] = summer.isoformat()
        self.meta["sources"]["supercoppa"] = {"status": "error", "updatedAt": None, "error": "offseason"}
        self.assertEqual(diagnose(self.meta, summer), [])


if __name__ == "__main__":
    unittest.main()
