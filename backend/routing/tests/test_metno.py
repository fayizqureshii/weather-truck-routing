from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import SimpleTestCase

from routing.services import metno

START = datetime(2026, 1, 1, 0, tzinfo=timezone.utc)


def step(hours, wind_ms, temp_c, next_1h_mm=None, next_6h_mm=None):
    data = {"instant": {"details": {"wind_speed": wind_ms, "air_temperature": temp_c}}}
    if next_1h_mm is not None:
        data["next_1_hours"] = {"details": {"precipitation_amount": next_1h_mm}}
    if next_6h_mm is not None:
        data["next_6_hours"] = {"details": {"precipitation_amount": next_6h_mm}}
    t = (START + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")
    return {"time": t, "data": data}


def response(*steps):
    return {"properties": {"timeseries": list(steps)}}


class MetNoConversionTests(SimpleTestCase):
    def run_hourly(self, payload, hours):
        with mock.patch.object(metno, "get_json", return_value=payload):
            return metno.hourly((40.0, -100.0), START, START + timedelta(hours=hours))

    def test_units_and_precip_hour_alignment(self):
        out = self.run_hourly(response(step(0, 10, 5, next_1h_mm=25.4), step(1, 20, 5, next_1h_mm=0), step(2, 20, 5)), 2)
        self.assertAlmostEqual(out["wind_speed_10m"][0], 22.37, places=2)
        # Precip falling 00:00–01:00 is stamped at 01:00, like Open-Meteo.
        self.assertEqual(out["rain"][0], 0.0)
        self.assertAlmostEqual(out["rain"][1], 1.0)
        self.assertAlmostEqual(out["temperature_2m"][0], 41.0)

    def test_freezing_precip_counts_as_snow(self):
        out = self.run_hourly(response(step(0, 5, -3, next_1h_mm=2.54), step(1, 5, -3)), 1)
        self.assertEqual(out["rain"][1], 0.0)
        self.assertAlmostEqual(out["snowfall"][1], 1.0)  # 0.1 in liquid at 10:1

    def test_six_hour_steps_are_spread_and_interpolated(self):
        out = self.run_hourly(response(step(0, 0, 5, next_6h_mm=6 * 2.54), step(6, 12, 5)), 6)
        self.assertAlmostEqual(out["wind_speed_10m"][3], 6 * metno.MS_TO_MPH)
        for h in range(1, 7):
            self.assertAlmostEqual(out["rain"][h], 0.1)

    def test_short_forecast_is_an_error(self):
        with self.assertRaises(metno.UpstreamError):
            self.run_hourly(response(step(0, 5, 5), step(1, 5, 5)), 10)
