import importlib.util
import unittest

spec = importlib.util.spec_from_file_location("laliga", "laliga-report-server.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CardReportTests(unittest.TestCase):
    def fixture(self, events):
        return {"match": {"id": 1, "slug": "test", "season": {"opta_id": "2026"},
                "competition": {"slug": "primera-division"}, "date": "2026-08-30T17:30:00+00:00",
                "gameweek": {"week": 3}, "status": "FullTime", "home_score": 3, "away_score": 1,
                "home_team": {"id": 26, "nickname": "Deportivo"},
                "away_team": {"id": 18, "nickname": "Valencia"}}, "events": events}

    def card(self, kind, second, player="Player", team=26):
        return {"id": second, "minute": 92, "second": second, "clock": "90+3",
                "match_event_kind": {"collection": "booking", "name": kind},
                "lineup": {"team": {"id": team}, "person": {"name": player}}}

    def test_two_bookings_in_same_display_minute(self):
        result = module.extract_match(self.fixture([self.card("Second Yellow", 53), self.card("Yellow", 31)]))
        self.assertEqual(result["date"], "2026-08-31")
        self.assertEqual(result["time"], "01:30")
        self.assertEqual(result["events"][0]["first"], "90+3")
        self.assertEqual(result["events"][0]["second"], "90+3")

    def test_does_not_borrow_opponent_booking(self):
        result = module.extract_match(self.fixture([self.card("Yellow", 31, team=18), self.card("Second Yellow", 53)]))
        self.assertIsNone(result["events"][0]["first"])

    def test_straight_red_and_overturned_second_yellow_not_included(self):
        self.assertIsNone(module.extract_match(self.fixture([self.card("Yellow", 31), self.card("Red", 53)])))
        self.assertIsNone(module.extract_match(self.fixture([])))

    def test_wrong_season_is_rejected(self):
        fixture = self.fixture([])
        fixture["match"]["season"]["opta_id"] = "2027"
        with self.assertRaises(ValueError):
            module.extract_match(fixture)

    def test_rank_ties_and_zero_exclusion(self):
        players = [{"name": n, "playerId": n, "yellow": y} for n, y in [("a", 3), ("b", 3), ("c", 1), ("d", 0)]]
        self.assertEqual([r["rank"] for r in module.rank_players(players, "yellow")], [1, 1, 3])


if __name__ == "__main__":
    unittest.main()
