"""Regressioni per la fonte Nazionale e per il comportamento con feed vuoto."""
import unittest
from unittest.mock import patch

import aggiorna_calendario as calendar


class ItalySourceTests(unittest.TestCase):
    @patch.object(calendar, "get_json")
    def test_uses_documented_free_api_key(self, get_json):
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

    @patch.object(calendar, "get_json", return_value={"events": []})
    def test_empty_feed_is_not_marked_as_updated(self, get_json):
        with self.assertRaisesRegex(ValueError, "Nessuna partita"):
            calendar.fetch_italy()


if __name__ == "__main__":
    unittest.main()
