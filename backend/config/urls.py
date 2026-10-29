from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.urls import include, path, re_path


def health(_request):
    return JsonResponse({"status": "ok"})


def spa_index(_request):
    """Serve the built React app for any non-API path (assets are served by WhiteNoise)."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        return HttpResponse(
            "Frontend not built. Run `npm run build` in frontend/, or use the Vite dev server.",
            status=404,
            content_type="text/plain",
        )
    return HttpResponse(index.read_text(), content_type="text/html")


urlpatterns = [
    path("api/health", health),
    path("api/", include("routing.urls")),
    re_path(r"^(?!api/).*$", spa_index),
]
