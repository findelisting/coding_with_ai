import os
from typing import Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """Return the caller's user id from a Supabase access token (the `sub` claim)."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="unauthorized")
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="auth_not_configured")
    try:
        claims = jwt.decode(
            credentials.credentials, secret, algorithms=["HS256"], audience="authenticated"
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="unauthorized")
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="unauthorized")
    return user_id
