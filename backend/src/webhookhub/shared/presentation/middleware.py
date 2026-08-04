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

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("x-request-id", request_id)
            await send(message)

        await self.app(scope, receive, send_with_request_id)


def _validated_request_id(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError):
        return str(uuid4())
