"""
Unit and Integration Tests for API Gateway Authentication, RBAC, and Security.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, Depends

from backend.config import get_settings
from backend.gateway.auth import (
    User,
    UserRole,
    create_access_token,
    decode_access_token,
    verify_password,
    get_password_hash,
)
from backend.gateway.dependencies import get_current_user, require_role
from backend.main import create_app


@pytest.mark.asyncio
async def test_password_hashing_and_verification():
    """Verify password hashing creates verifiable one-way hashes."""
    plain = "DutyOfficerSecret2026"
    hashed = get_password_hash(plain)
    assert hashed != plain
    assert verify_password(plain, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


@pytest.mark.asyncio
async def test_jwt_token_generation_and_decoding():
    """Verify JWT tokens encode and decode user claims reliably."""
    payload = {"sub": "test_operator", "role": "operator", "callsign": "Alpha-1"}
    token = create_access_token(payload)
    assert isinstance(token, str)

    decoded = decode_access_token(token)
    assert decoded["sub"] == "test_operator"
    assert decoded["role"] == "operator"
    assert decoded["callsign"] == "Alpha-1"
    assert "exp" in decoded


@pytest.mark.asyncio
async def test_gateway_login_endpoint_success():
    """Verify POST /api/auth/token succeeds with valid credentials."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/auth/token",
            json={"username": "operator", "password": "operator123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["username"] == "operator"
        assert data["user"]["role"] == "operator"


@pytest.mark.asyncio
async def test_gateway_login_endpoint_invalid_credentials():
    """Verify POST /api/auth/token rejects wrong passwords."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/auth/token",
            json={"username": "operator", "password": "wrong_password"},
        )
        assert resp.status_code == 401
        assert "Incorrect username or password" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_gateway_demo_token_endpoint():
    """Verify GET /api/auth/demo-token provides instant evaluation token."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/auth/demo-token")
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["callsign"] == "Duty Officer Alpha"


@pytest.mark.asyncio
async def test_rbac_role_enforcement_allowed():
    """Verify user with matching role is allowed access."""
    test_app = FastAPI()

    @test_app.get("/admin-only")
    async def admin_route(
        user: User = Depends(require_role([UserRole.ADMIN, UserRole.COMMANDER])),
    ):
        return {"authorized": True, "callsign": user.callsign}

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = create_access_token({"sub": "commander", "role": "commander"})
        resp = await client.get("/admin-only", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["authorized"] is True


@pytest.mark.asyncio
async def test_rbac_role_enforcement_forbidden():
    """Verify user with unprivileged role is rejected with 403 Forbidden."""
    test_app = FastAPI()

    @test_app.get("/commander-only")
    async def commander_route(
        user: User = Depends(require_role([UserRole.COMMANDER])),
    ):
        return {"authorized": True}

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = create_access_token({"sub": "operator", "role": "operator"})
        resp = await client.get("/commander-only", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403
        assert "Access forbidden" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_demo_mode_fallback_when_unauthenticated():
    """Verify DEMO_MODE=True returns default Duty Officer when no token is passed."""
    settings = get_settings()
    original_demo_mode = settings.DEMO_MODE
    try:
        settings.DEMO_MODE = True
        test_app = FastAPI()

        @test_app.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"user": user.username, "callsign": user.callsign}

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/protected")
            assert resp.status_code == 200
            assert resp.json()["user"] == "operator"
            assert resp.json()["callsign"] == "Duty Officer Alpha"
    finally:
        settings.DEMO_MODE = original_demo_mode


@pytest.mark.asyncio
async def test_strict_auth_rejection_when_demo_mode_disabled():
    """Verify DEMO_MODE=False rejects unauthenticated requests with 401."""
    settings = get_settings()
    original_demo_mode = settings.DEMO_MODE
    try:
        settings.DEMO_MODE = False
        test_app = FastAPI()

        @test_app.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"user": user.username}

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/protected")
            assert resp.status_code == 401
            assert "Authentication credentials required" in resp.json()["detail"]
    finally:
        settings.DEMO_MODE = original_demo_mode
