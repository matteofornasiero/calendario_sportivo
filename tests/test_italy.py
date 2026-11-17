"""Regressioni per le fonti Nazionale e il calendario di Formula 1."""
import unittest
from datetime import datetime
from unittest.mock import patch

import aggiorna_calendario as calendar


class ItalySourceTests(unittest.TestCase):
    @patch.object(calendar, "get_json")
    def test_uses_documented_free_api_key_as_fallback(self, get_json):
        get_json.return_value = {"events": [{
            "idEvent": "match-123",
            "dateEvent": "2026-12-01",
            "strTime": "19:00:00",
            "strHomeTeam": "Italy",
            "strAwayTeam": "France",
            "strLeague": "Nations League",
        }]}
        fixtures = calendar.fetch_italy()
        self.assertIn("/api/v1/json/123/eventsnext.php", get_json.call_args.args[0])
        self.assertEqual(len(fixtures), 1)
        self.assertEqual(fixtures[0]["sport"], "nazionale")
        self.assertTrue(fixtures[0]["timeConfirmed"])
        self.assertIn("Italia", fixtures[0]["title"])

    @patch.object(calendar, "get_json")
    def test_espn_includes_away_matches_when_available(self, get_json):
        now = datetime.now(calendar.ROME)
        season = now.year if now.month >= 7 else now.year - 1
        get_json.return_value = {"events": [{
            "id": "national-1",
            "date": f"{season}-12-01T20:00:00Z",
            "season": {"year": season, "type": 2},
            "competitions": [{
                "date": f"{season}-12-01T20:00:00Z",
                "timeValid": True,
                "competitors": [
                    {"homeAway": "home", "team": {"displayName": "France", "logo": ""}},
                    {"homeAway": "away", "team": {"displayName": "Italy", "logo": ""}}
                ],
                "status": {"type": {"name": "STATUS_SCHEDULED", "state": "pre"}}
            }]
        }]}
        fixtures = calendar.fetch_italy()
        get_json.assert_called_once()
        self.assertIn("uefa.nations/teams/162/schedule", get_json.call_args.args[0])
        self.assertEqual(len(fixtures), 1)
        self.assertEqual(fixtures[0]["away"], "Italy")
        self.assertTrue(fixtures[0]["timeConfirmed"])

    @patch.object(calendar, "get_json", return_value={"events": []})
    def test_empty_feed_is_not_marked_as_updated(self, get_json):
        with self.assertRaisesRegex(ValueError, "Nessuna partita"):
            calendar.fetch_italy()


class FormulaOneStatusTests(unittest.TestCase):
    def test_past_session_does_not_remain_scheduled(self):
        payload = {"MRData": {"RaceTable": {"Races": [{
            "season": "2001", "round": "1", "raceName": "Test Grand Prix",
            "date": "2001-05-01", "time": "14:00:00Z",
            "Circuit": {"circuitName": "Circuit", "Location": {"locality": "Roma", "country": "Italia"}}
        }]}}}
        events = calendar.parse_f1_calendar(payload)
        self.assertEqual(events[0]["status"], "PAST")
        self.assertEqual(events[0]["sport"], "f1")


if __name__ == "__main__":
    unittest.main()
