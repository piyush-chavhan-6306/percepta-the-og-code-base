"""
PERCEPTA Defence — User Management & Onboarding API
Exposes endpoints for user profiles, isolated workspace status, onboarding completion,
and offline/online credential synchronization.
"""
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from backend.users.user_manager import user_manager, UserProfile

router = APIRouter(prefix="/api/user", tags=["User & Identity"])


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    callsign: Optional[str] = None
    role: Optional[str] = None
    rank: Optional[str] = None
    regiment: Optional[str] = None
    division: Optional[str] = None
    organization: Optional[str] = None
    official_contact: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None


class SyncSupabaseRequest(BaseModel):
    supabase_id: str
    email: str
    name: Optional[str] = None
    access_token: Optional[str] = None
    offline_pin: Optional[str] = None


class UserProfileResponse(BaseModel):
    success: bool
    profile: UserProfile
    workspace_path: str


def _get_active_user_id(x_user_id: Optional[str] = Header(None)) -> str:
    """Extracts user identity from header or defaults to offline operator."""
    if x_user_id and x_user_id.strip():
        return x_user_id.strip()
    return "usr_operator"


@router.get("/profile", response_model=UserProfileResponse)
async def get_current_profile(x_user_id: Optional[str] = Header(None)):
    """Fetch the isolated profile for the active user."""
    uid = _get_active_user_id(x_user_id)
    profile = user_manager.get_user_profile(uid)
    if not profile:
        # Create baseline profile for new user
        email = f"{uid.replace('usr_', '')}@defense.percepta.ai"
        profile = user_manager.create_or_update_profile(
            user_id=uid,
            email=email,
            name=uid.replace("usr_", "").capitalize(),
            onboarding_completed=False,
        )

    ws = user_manager.get_workspace(uid)
    return UserProfileResponse(
        success=True,
        profile=profile,
        workspace_path=str(ws["root"]),
    )


@router.put("/profile", response_model=UserProfileResponse)
async def update_current_profile(
    body: UpdateProfileRequest,
    x_user_id: Optional[str] = Header(None),
):
    """Update profile attributes for active user."""
    uid = _get_active_user_id(x_user_id)
    profile = user_manager.get_user_profile(uid)
    email = profile.email if profile else f"{uid}@defense.percepta.ai"

    updated = user_manager.create_or_update_profile(
        user_id=uid,
        email=email,
        name=body.name,
        callsign=body.callsign,
        role=body.role,
        rank=body.rank,
        regiment=body.regiment,
        division=body.division,
        organization=body.organization,
        official_contact=body.official_contact,
        preferences=body.preferences,
    )
    ws = user_manager.get_workspace(uid)
    return UserProfileResponse(
        success=True,
        profile=updated,
        workspace_path=str(ws["root"]),
    )


@router.post("/onboarding/complete")
async def mark_onboarding_completed(x_user_id: Optional[str] = Header(None)):
    """Mark onboarding tour completed specifically for the current user."""
    uid = _get_active_user_id(x_user_id)
    profile = user_manager.set_onboarding_completed(uid, completed=True)
    return {
        "success": True,
        "user_id": uid,
        "onboarding_completed": profile.onboarding_completed,
        "message": "Onboarding completed successfully.",
    }


@router.post("/onboarding/reset")
async def reset_onboarding(x_user_id: Optional[str] = Header(None)):
    """Reset onboarding tour so the user can retake the tour manually."""
    uid = _get_active_user_id(x_user_id)
    profile = user_manager.set_onboarding_completed(uid, completed=False)
    return {
        "success": True,
        "user_id": uid,
        "onboarding_completed": profile.onboarding_completed,
        "message": "Onboarding tour reset. Will display on next navigation.",
    }


@router.post("/sync-supabase")
async def sync_supabase_identity(body: SyncSupabaseRequest):
    """
    Synchronizes cloud Supabase user identity with a dedicated local user sandbox.
    Caches authentication credentials locally for offline continuity.
    """
    uid = body.supabase_id
    profile = user_manager.get_user_profile(uid)
    is_new_user = profile is None

    profile = user_manager.create_or_update_profile(
        user_id=uid,
        email=body.email,
        name=body.name or body.email.split("@")[0].capitalize(),
        onboarding_completed=False if is_new_user else None,
    )

    if body.offline_pin:
        user_manager.save_offline_credentials(uid, body.email, body.offline_pin)

    ws = user_manager.get_workspace(uid)
    return {
        "success": True,
        "user_id": uid,
        "is_new_user": is_new_user,
        "onboarding_completed": profile.onboarding_completed,
        "workspace": str(ws["root"]),
    }


@router.get("/users")
async def list_local_users():
    """List known local users for offline switching."""
    users = user_manager.list_all_local_users()
    return {"success": True, "users": users}
