from datetime import datetime, timedelta, timezone

from rest_framework import serializers

from .services.weather import MAX_FORECAST_DAYS

INTERVAL_CHOICES = (10, 25, 50)
MAX_LOAD_LB = 80_000  # US federal gross vehicle weight limit


class LocationField(serializers.Field):
    """Either free text to geocode, or a {name, lat, lon} object picked from suggestions."""

    def to_internal_value(self, data):
        if isinstance(data, str):
            if not data.strip():
                raise serializers.ValidationError("Enter a location.")
            return data.strip()
        if isinstance(data, dict):
            try:
                lat, lon = float(data["lat"]), float(data["lon"])
            except (KeyError, TypeError, ValueError):
                raise serializers.ValidationError("Location needs numeric lat and lon.")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise serializers.ValidationError("Coordinates out of range.")
            return {"name": str(data.get("name") or ""), "lat": lat, "lon": lon}
        raise serializers.ValidationError("Location must be text or {name, lat, lon}.")

    def to_representation(self, value):
        return value


def validate_departure(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise serializers.ValidationError("Departure must include a timezone offset.")
    now = datetime.now(timezone.utc)
    if value < now - timedelta(hours=1):
        raise serializers.ValidationError("Departure can't be in the past.")
    if value > now + timedelta(days=MAX_FORECAST_DAYS - 3):
        raise serializers.ValidationError(
            f"Departure must be within {MAX_FORECAST_DAYS - 3} days so the trip stays inside the forecast."
        )
    return value.astimezone(timezone.utc)


class PlanRequestSerializer(serializers.Serializer):
    origin = LocationField()
    destination = LocationField()
    departure = serializers.DateTimeField(validators=[validate_departure])
    load_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)
    interval_miles = serializers.ChoiceField(choices=INTERVAL_CHOICES, default=25)


class HeatmapRequestSerializer(serializers.Serializer):
    cells = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2),
        min_length=1,
        max_length=1000,
    )
    start = serializers.DateTimeField(validators=[validate_departure])
    load_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)
