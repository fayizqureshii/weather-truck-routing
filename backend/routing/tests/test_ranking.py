from django.test import SimpleTestCase

from routing.services.ranking import explain, sort_key, summarize
from routing.services.risk import Risk

L, M, H, S, N = Risk.LOW, Risk.MODERATE, Risk.HIGH, Risk.SEVERE, Risk.NO_TRAVEL


def route(levels, interval=10.0, hours=10.0):
    miles = [i * interval for i in range(len(levels))]
    return summarize(miles, levels, miles[-1]), hours


class SummarizeTests(SimpleTestCase):
    def test_miles_add_up_to_route_length(self):
        s = summarize([0, 25, 50, 62], [L, H, S, L], 62)
        self.assertAlmostEqual(sum(s.miles_by_level.values()), 62)

    def test_each_checkpoint_owns_nearest_stretch(self):
        s = summarize([0, 10, 20], [L, S, L], 20)
        # middle checkpoint covers miles 5..15
        self.assertAlmostEqual(s.miles_by_level[S], 10)
        self.assertAlmostEqual(s.miles_by_level[L], 10)

    def test_average_risk_is_distance_weighted(self):
        s = summarize([0, 10, 20], [L, H, L], 20)
        self.assertAlmostEqual(s.average_risk, (2 * 10) / 20)
        self.assertEqual(s.max_level, H)


class OrderingTests(SimpleTestCase):
    def rank(self, *routes):
        return sorted(range(len(routes)), key=lambda i: sort_key(*routes[i]))

    def test_fewest_severe_miles_wins_even_if_slower(self):
        fast_severe = route([L, S, L], hours=8)
        slow_high = route([H, H, H], hours=12)
        self.assertEqual(self.rank(fast_severe, slow_high)[0], 1)

    def test_no_travel_is_worse_than_severe(self):
        no_travel = route([L, N, L])
        severe = route([S, S, S])
        self.assertEqual(self.rank(no_travel, severe)[0], 1)

    def test_high_miles_break_severe_ties(self):
        a = route([L, H, H, L])
        b = route([L, H, L, L])
        self.assertEqual(self.rank(a, b)[0], 1)

    def test_average_risk_breaks_high_ties(self):
        a = route([M, M, M])
        b = route([L, M, L])
        self.assertEqual(self.rank(a, b)[0], 1)

    def test_travel_time_breaks_full_ties(self):
        a = route([L, L, L], hours=11)
        b = route([L, L, L], hours=9)
        self.assertEqual(self.rank(a, b)[0], 1)

    def test_explanation_names_deciding_criterion(self):
        (wa, ha), (wb, hb) = route([L, L, L], hours=9), route([L, S, L], hours=8)
        self.assertIn("Severe", explain(wa, ha, wb, hb, "Route B"))
        (wa, ha), (wb, hb) = route([L, L, L], hours=9), route([L, L, L], hours=11)
        self.assertIn("faster", explain(wa, ha, wb, hb, "Route B"))
