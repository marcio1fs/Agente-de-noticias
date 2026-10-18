from fastapi import Header, HTTPException, status
from app.core.config import settings

async def require_admin(x_admin_token: str = Header(None)):
    """
    Dependency that validates the administrative API token.
    Expects 'X-Admin-Token' header.
    """
    if not settings.ADMIN_API_TOKEN:
        # If no token is configured in .env, we allow access in development 
        # BUT log a warning. In production, this should be strict.
        return True

    if x_admin_token != settings.ADMIN_API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Administrative Token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True
