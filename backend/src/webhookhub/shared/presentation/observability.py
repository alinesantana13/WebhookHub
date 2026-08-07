from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from webhookhub.bootstrap.config import Settings, get_settings

router = APIRouter(tags=["observability"])
optional_bearer = HTTPBearer(auto_error=False)


@router.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
async def metrics(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(optional_bearer)],
) -> PlainTextResponse:
    if settings.metrics_token and (
        credentials is None or credentials.credentials != settings.metrics_token
    ):
        return PlainTextResponse("Unauthorized", status_code=401)
    return PlainTextResponse(request.app.state.http_metrics.render())
