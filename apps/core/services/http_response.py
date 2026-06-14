from typing import Any, Optional

from django.http import JsonResponse


def json_error(msg: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"status": "error", "message": msg}, status=status)


def json_ok(extra: Optional[dict[str, Any]] = None) -> JsonResponse:
    resp: dict[str, Any] = {"status": "ok"}
    if extra:
        resp.update(extra)
    return JsonResponse(resp)
