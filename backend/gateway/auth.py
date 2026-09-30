"""
Border Intelligence Gateway Authentication & JWT Management.
Provides password hashing, JWT issuance and verification, and authentication REST endpoints.
"""
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["Gateway Auth"])

# Password hashing context (supporting bcrypt and pbkdf2_sha256)
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")


class UserRole(str, Enum):
    OPERATOR = "operator"
    COMMANDER = "commander"
    AUDITOR = "auditor"
    ADMIN = "admin"


class User(BaseModel):
    username: str
    callsign: str
    role: UserRole
    is_active: bool = True
    assigned_sector: str = "Sector Alpha"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: User


class LoginRequest(BaseModel):
    username: str
    password: str


# Pre-configured baseline users for border command post operations
MOCK_USERS_DB = {
    "operator": {
        "username": "operator",
        "hashed_password": pwd_context.hash("operator123"),
        "callsign": "Duty Officer Alpha",
        "role": UserRole.OPERATOR,
        "is_active": True,
        "assigned_sector": "Sector Alpha",
    },
    "commander": {
        "username": "commander",
        "hashed_password": pwd_context.hash("commander123"),
        "callsign": "Sector Commander Bravo",
        "role": UserRole.COMMANDER,
        "is_active": True,
        "assigned_sector": "All Sectors",
    },
    "auditor": {
        "username": "auditor",
        "hashed_password": pwd_context.hash("auditor123"),
        "callsign": "Forensic Inspector",
        "role": UserRole.AUDITOR,
        "is_active": True,
        "assigned_sector": "Forensics & Audit",
    },
    "admin": {
        "username": "admin",
        "hashed_password": pwd_context.hash("admin123"),
        "callsign": "HQ Chief Administrator",
        "role": UserRole.ADMIN,
        "is_active": True,
        "assigned_sector": "Headquarters Command",
    },
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Compute password hash."""
    return pwd_context.hash(password)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create signed JWT access token."""
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_EXPIRY_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired credentials: {str(exc)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(credentials: LoginRequest):
    """Authenticate user credentials and issue signed JWT access token."""
    user_record = MOCK_USERS_DB.get(credentials.username.lower())
    if not user_record or not verify_password(credentials.password, user_record["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = User(
        username=user_record["username"],
        callsign=user_record["callsign"],
        role=user_record["role"],
        is_active=user_record["is_active"],
        assigned_sector=user_record["assigned_sector"],
    )

    settings = get_settings()
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role.value, "callsign": user.callsign}
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in_minutes=settings.JWT_EXPIRY_MINUTES,
        user=user,
    )


@router.get("/demo-token", response_model=TokenResponse)
async def get_demo_token():
    """Retrieve pre-signed operator token for zero-friction evaluation and testing."""
    user_record = MOCK_USERS_DB["operator"]
    user = User(
        username=user_record["username"],
        callsign=user_record["callsign"],
        role=user_record["role"],
        is_active=user_record["is_active"],
        assigned_sector=user_record["assigned_sector"],
    )
    settings = get_settings()
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role.value, "callsign": user.callsign}
    )
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in_minutes=settings.JWT_EXPIRY_MINUTES,
        user=user,
    )
