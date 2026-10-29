import math

from django.test import SimpleTestCase

from routing.services.risk import (
    Risk,
    assess,
    classify_rain,
    classify_snow,
    classify_wind,
    risk_score,
)


class ThresholdTests(SimpleTestCase):
    def test_wind_bands(self):
        cases = [(0, Risk.LOW), (24.9, Risk.LOW), (25, Risk.MODERATE), (34.9, Risk.MODERATE),
                 (35, Risk.HIGH), (44.9, Risk.HIGH), (45, Risk.SEVERE), (54.9, Risk.SEVERE),
                 (55, Risk.NO_TRAVEL), (80, Risk.NO_TRAVEL)]
        for mph, expected in cases:
            with self.subTest(mph=mph):
                self.assertEqual(classify_wind(mph), expected)

    def test_rain_bands(self):
        cases = [(0, Risk.LOW), (0.099, Risk.LOW), (0.10, Risk.MODERATE), (0.25, Risk.HIGH),
                 (0.49, Risk.HIGH), (0.50, Risk.SEVERE), (1.00, Risk.SEVERE), (1.01, Risk.NO_TRAVEL)]
        for rate, expected in cases:
            with self.subTest(rate=rate):
                self.assertEqual(classify_rain(rate), expected)

    def test_snow_bands(self):
        cases = [(0, Risk.LOW), (0.49, Risk.LOW), (0.5, Risk.MODERATE), (1.0, Risk.HIGH),
                 (2.0, Risk.SEVERE), (3.0, Risk.SEVERE), (3.01, Risk.NO_TRAVEL)]
        for rate, expected in cases:
            with self.subTest(rate=rate):
                self.assertEqual(classify_snow(rate), expected)


class LoadRuleTests(SimpleTestCase):
    def test_55_mph_is_no_travel_for_any_load(self):
        self.assertEqual(assess(55, 0, 0, load_lb=0).level, Risk.NO_TRAVEL)

    def test_45_to_54_mph_with_heavy_load_is_no_travel(self):
        self.assertEqual(assess(50, 0, 0, load_lb=30_001).level, Risk.NO_TRAVEL)
        self.assertEqual(assess(50, 0, 0, load_lb=30_000).level, Risk.SEVERE)

    def test_35_to_44_mph_with_very_heavy_load_is_severe(self):
        self.assertEqual(assess(40, 0, 0, load_lb=40_001).level, Risk.SEVERE)
        self.assertEqual(assess(40, 0, 0, load_lb=40_000).level, Risk.HIGH)

    def test_load_does_not_change_low_wind(self):
        self.assertEqual(assess(20, 0, 0, load_lb=80_000).level, Risk.LOW)

    def test_escalation_is_explained(self):
        reasons = assess(40, 0, 0, load_lb=45_000).reasons
        self.assertTrue(any("escalated from High" in r for r in reasons))


class CombinedTests(SimpleTestCase):
    def test_overall_level_is_worst_component(self):
        a = assess(wind_mph=30, rain_in_hr=0.6, snow_in_hr=0, load_lb=10_000)
        self.assertEqual(a.wind, Risk.MODERATE)
        self.assertEqual(a.rain, Risk.SEVERE)
        self.assertEqual(a.level, Risk.SEVERE)

    def test_score_floor_matches_level(self):
        for wind in (0, 12, 25, 34.9, 35, 44, 45, 54.9, 55, 70):
            for rain in (0, 0.1, 0.3, 1.0, 1.2):
                for snow in (0, 0.7, 2.5, 3.5):
                    for load in (10_000, 35_000, 45_000):
                        level = assess(wind, rain, snow, load).level
                        score = risk_score(wind, rain, snow, load)
                        with self.subTest(wind=wind, rain=rain, snow=snow, load=load):
                            self.assertEqual(math.floor(score), int(level))
