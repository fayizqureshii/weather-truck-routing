import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import HeatmapRequestSerializer, PlanRequestSerializer
from .services import geocoding, planner
from .services.http import UpstreamError
from .services.routing import NoRouteFound

logger = logging.getLogger(__name__)


def _error(message: str, code: int) -> Response:
    return Response({"error": message}, status=code)


class GeocodeView(APIView):
    def get(self, request):
        query = request.query_params.get("q", "")
        if len(query.strip()) < 2:
            return Response({"results": []})
        try:
            places = geocoding.search(query, limit=6)
        except UpstreamError:
            logger.exception("Geocoding failed")
            return _error("Location search is temporarily unavailable.", status.HTTP_502_BAD_GATEWAY)
        return Response({"results": [p.as_dict() for p in places]})


class PlanView(APIView):
    def post(self, request):
        s = PlanRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        try:
            origin = geocoding.resolve(data["origin"])
            destination = geocoding.resolve(data["destination"])
            result = planner.plan_trip(
                planner.TripRequest(
                    origin=origin,
                    destination=destination,
                    departure=data["departure"],
                    load_lb=data["load_lb"],
                    interval_miles=float(data["interval_miles"]),
                )
            )
        except (geocoding.LocationNotFound, NoRouteFound, ValueError) as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except UpstreamError:
            logger.exception("Trip planning failed upstream")
            return _error(
                "A routing or weather service is temporarily unavailable. Please try again.",
                status.HTTP_502_BAD_GATEWAY,
            )
        return Response(result)


class HeatmapView(APIView):
    def post(self, request):
        s = HeatmapRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        cells = [(float(lat), float(lon)) for lat, lon in data["cells"]]
        try:
            result = planner.heatmap(cells, data["start"], data["load_lb"])
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except UpstreamError:
            logger.exception("Heatmap weather fetch failed")
            return _error("The weather service is temporarily unavailable.", status.HTTP_502_BAD_GATEWAY)
        return Response(result)
