from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from routing.services import geo
from routing.services.routing import Route, corridor_grid, sample_every
from routing.services.weather import Forecast


def straight_route(miles=100.0, mph=50.0, n=200):
    """A due-north route of `miles` length at constant speed."""
    end = geo.offset_point((40.0, -100.0), 0, miles)
    coords = [geo.interpolate((40.0, -100.0), end, i / n) for i in range(n + 1)]
    seg_miles = [geo.haversine_miles(a, b) for a, b in zip(coords, coords[1:])]
    return Route(coords=coords, seg_miles=seg_miles, seg_hours=[m / mph for m in seg_miles], summary="")


class SamplingTests(SimpleTestCase):
    def test_checkpoints_every_interval_including_endpoints(self):
        points = sample_every(straight_route(100), 25)
        self.assertEqual([round(p.mile) for p in points], [0, 25, 50, 75, 100])

    def test_eta_follows_route_speed(self):
        points = sample_every(straight_route(100, mph=50), 10)
        for p in points:
            self.assertAlmostEqual(p.hours, p.mile / 50, places=3)

    def test_short_final_leg_kept(self):
        points = sample_every(straight_route(57), 25)
        self.assertEqual([round(p.mile) for p in points], [0, 25, 50, 57])

    def test_corridor_grid_is_bounded(self):
        grid = corridor_grid([straight_route(800)], max_cells=240)
        self.assertTrue(0 < len(grid["cells"]) <= 240)
        for row, col, lat, lon in grid["cells"]:
            self.assertTrue(0 <= row < grid["rows"] and 0 <= col < grid["cols"])
            self.assertTrue(grid["south"] <= lat <= grid["north"])
            self.assertTrue(grid["west"] <= lon <= grid["east"])


class ForecastLookupTests(SimpleTestCase):
    def setUp(self):
        self.start = datetime(2026, 1, 1, 0, tzinfo=timezone.utc)
        self.fc = Forecast(self.start, {
            "wind_speed_10m": [10, 30, 50],
            "wind_gusts_10m": [15, 35, 55],
            "rain": [0, 0.2, 0.6],  # rain[h] is the total for hour (h-1, h]
            "snowfall": [0, 0, 0],
            "temperature_2m": [30, 32, 34],
            "weather_code": [0, 61, 63],
        })

    def test_wind_is_interpolated(self):
        c = self.fc.at(self.start + timedelta(minutes=30))
        self.assertAlmostEqual(c.wind_mph, 20)

    def test_precip_uses_hour_in_progress(self):
        c = self.fc.at(self.start + timedelta(hours=1, minutes=15))
        self.assertAlmostEqual(c.rain_in_hr, 0.6)

    def test_exact_hour(self):
        c = self.fc.at(self.start + timedelta(hours=1))
        self.assertAlmostEqual(c.wind_mph, 30)
        self.assertAlmostEqual(c.rain_in_hr, 0.2)
