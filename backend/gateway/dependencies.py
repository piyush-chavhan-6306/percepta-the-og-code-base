"""
Border Intelligence Gateway Security Dependencies.
Provides FastAPI dependency injectors for JWT validation, RBAC role enforcement, and WebSocket auth.
"""
from typing import Callable, List, Optional
from fastapi import Depends, HTTPException, Query, Security, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import get_settings
from backend.gateway.auth import MOCK_USERS_DB, User, UserRole, decode_access_token

# Optional HTTP Bearer security scheme (auto_error=False allows graceful DEMO_MODE fallback)
security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
) -> User:
    """
    Extract and validate the current authenticated user from the Authorization header.
    When DEMO_MODE=True and no token is provided, safely returns default Duty Officer persona.
    """
    settings = get_settings()

    if credentials and credentials.credentials:
        payload = decode_access_token(credentials.credentials)
        username = payload.get("sub")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload missing subject identifier",
            )
        user_record = MOCK_USERS_DB.get(username)
        if not user_record:
            # Synthetic user representation from token claims
            return User(
                username=username,
                callsign=payload.get("callsign", "Field Operator"),
                role=UserRole(payload.get("role", "operator")),
                is_active=True,
                assigned_sector="Sector Alpha",
            )
        return User(
            username=user_record["username"],
            callsign=user_record["callsign"],
            role=user_record["role"],
            is_active=user_record["is_active"],
            assigned_sector=user_record["assigned_sector"],
        )

    # DEMO_MODE Fallback
    if settings.DEMO_MODE:
        default_user = MOCK_USERS_DB["operator"]
        return User(
            username=default_user["username"],
            callsign=default_user["callsign"],
            role=default_user["role"],
            is_active=default_user["is_active"],
            assigned_sector=default_user["assigned_sector"],
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication credentials required. (Pass 'Authorization: Bearer <token>' or enable DEMO_MODE)",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(allowed_roles: List[UserRole]) -> Callable:
    """
    Role-Based Access Control (RBAC) dependency factory.
    Enforces that the current authenticated user possesses one of the specified roles.
    """

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        # Admin has superuser override on all role-gated routes
        if current_user.role == UserRole.ADMIN:
            return current_user

        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: User role '{current_user.role.value}' is not authorized. Requires one of: {[r.value for r in allowed_roles]}",
            )
        return current_user

    return role_checker


async def validate_ws_token(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
) -> Optional[User]:
    """
    Validate authentication token for WebSocket handshakes.
    Supports ?token=<jwt> query parameter or DEMO_MODE fallback.
    """
    settings = get_settings()
    if token:
        try:
            payload = decode_access_token(token)
            username = payload.get("sub", "ws_operator")
            return User(
                username=username,
                callsign=payload.get("callsign", "WebSocket Monitor"),
                role=UserRole(payload.get("role", "operator")),
                is_active=True,
            )
        except Exception:
            if not settings.DEMO_MODE:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return None

    if settings.DEMO_MODE:
        default_user = MOCK_USERS_DB["operator"]
        return User(
            username=default_user["username"],
            callsign=default_user["callsign"],
            role=default_user["role"],
            is_active=default_user["is_active"],
        )

    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    return None
