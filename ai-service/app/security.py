import hmac

from fastapi import Depends, Header, HTTPException

from .config import Settings, get_settings


def require_secret(
    x_ai_service_secret: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Internal endpoints are only callable by the Express backend."""
    expected = settings.ai_service_secret
    if not expected or not x_ai_service_secret or not hmac.compare_digest(
        x_ai_service_secret, expected
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing service secret")
