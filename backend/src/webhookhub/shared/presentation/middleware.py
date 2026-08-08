import json
import logging
from collections import Counter, defaultdict
from time import perf_counter
from uuid import UUID, uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_headers = Headers(scope=scope)
        request_id = _validated_request_id(request_headers.get("x-request-id", ""))
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("x-request-id", request_id)
            await send(message)

        await self.app(scope, receive, send_with_request_id)


class HttpObservabilityMiddleware:
    def __init__(self, app: ASGIApp, metrics: "HttpMetrics") -> None:
        self.app = app
        self.metrics = metrics
        self.logger = logging.getLogger("webhookhub.http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        status_code = 500

        async def observe(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, observe)
        finally:
            duration = perf_counter() - started
            route = scope.get("route")
            path = getattr(route, "path", "unmatched")
            method = scope["method"]
            self.metrics.observe(method, path, status_code, duration)
            self.logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": scope.get("state", {}).get("request_id"),
                        "method": method,
                        "path": path,
                        "status_code": status_code,
                        "duration_ms": round(duration * 1000, 2),
                    },
                    separators=(",", ":"),
                )
            )


class HttpMetrics:
    def __init__(self) -> None:
        self.requests: Counter[tuple[str, str, int]] = Counter()
        self.duration_seconds: defaultdict[tuple[str, str], float] = defaultdict(float)

    def observe(self, method: str, path: str, status_code: int, duration: float) -> None:
        self.requests[(method, path, status_code)] += 1
        self.duration_seconds[(method, path)] += duration

    def render(self) -> str:
        lines = [
            "# HELP webhookhub_http_requests_total Total HTTP requests.",
            "# TYPE webhookhub_http_requests_total counter",
        ]
        for (method, path, status), count in sorted(self.requests.items()):
            labels = f'method="{method}",path="{path}",status="{status}"'
            lines.append(f"webhookhub_http_requests_total{{{labels}}} {count}")
        lines.extend(
            [
                "# HELP webhookhub_http_request_duration_seconds_total Total request duration.",
                "# TYPE webhookhub_http_request_duration_seconds_total counter",
            ]
        )
        for (method, path), duration in sorted(self.duration_seconds.items()):
            labels = f'method="{method}",path="{path}"'
            lines.append(
                f"webhookhub_http_request_duration_seconds_total{{{labels}}} {duration:.9f}"
            )
        return "\n".join(lines) + "\n"


def _validated_request_id(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError):
        return str(uuid4())
