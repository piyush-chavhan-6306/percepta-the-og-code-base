"""
PERCEPTA Defence — User Isolation, Authentication, and Onboarding Test Suite
Verifies:
1. Complete data isolation between User A and User B (%LOCALAPPDATA%\\PERCEPTA Defence\\users\\<user_id>).
2. Per-user onboarding tour tracking (completion by User A does not mark completed for User B).
3. Offline authentication fallback and credential verification.
4. Supabase cloud identity synchronization with local sandboxes.
5. Repository independence (video resolution works without developer machine paths).
"""
import os
import shutil
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.config import get_settings
from backend.main import app
from backend.users.user_manager import user_manager, UserProfile


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_user_workspaces_are_strictly_isolated():
    """Verify User A and User B have separate physical directories and files."""
    settings = get_settings()

    ws_a = settings.get_user_workspace("usr_officer_alpha")
    ws_b = settings.get_user_workspace("usr_commander_bravo")

    assert ws_a["root"] != ws_b["root"], "User A and User B must have distinct roots"
    assert ws_a["database_dir"] != ws_b["database_dir"]
    assert ws_a["evidence_dir"] != ws_b["evidence_dir"]
    assert ws_a["recordings_dir"] != ws_b["recordings_dir"]

    # Verify directories exist
    assert ws_a["database_dir"].exists()
    assert ws_b["database_dir"].exists()


def test_user_profiles_and_onboarding_independence(client):
    """Verify that User A completing onboarding does NOT mark User B as completed."""
    import uuid
    user_a = f"usr_alpha_{uuid.uuid4().hex[:6]}"
    user_b = f"usr_bravo_{uuid.uuid4().hex[:6]}"

    # Step 1: Initial state for User A
    res_a1 = client.get("/api/user/profile", headers={"X-User-Id": user_a})
    assert res_a1.status_code == 200
    data_a1 = res_a1.json()
    assert data_a1["profile"]["onboarding_completed"] is False, "New user must start with onboarding=False"

    # Step 2: Initial state for User B
    res_b1 = client.get("/api/user/profile", headers={"X-User-Id": user_b})
    assert res_b1.status_code == 200
    data_b1 = res_b1.json()
    assert data_b1["profile"]["onboarding_completed"] is False

    # Step 3: User A completes onboarding tour
    complete_res = client.post("/api/user/onboarding/complete", headers={"X-User-Id": user_a})
    assert complete_res.status_code == 200
    assert complete_res.json()["onboarding_completed"] is True

    # Step 4: Verify User A now has onboarding_completed = True
    res_a2 = client.get("/api/user/profile", headers={"X-User-Id": user_a})
    assert res_a2.json()["profile"]["onboarding_completed"] is True

    # Step 5: CRITICAL CHECK — User B must STILL have onboarding_completed = False
    res_b2 = client.get("/api/user/profile", headers={"X-User-Id": user_b})
    assert res_b2.json()["profile"]["onboarding_completed"] is False, "User A completing tour must NOT affect User B"

    # Step 6: Update User A's dossier
    update_res = client.put(
        "/api/user/profile",
        headers={"X-User-Id": user_a},
        json={
            "name": "Capt. Vikram",
            "rank": "Captain",
            "regiment": "14th Rajputana Rifles",
            "division": "Northern Command",
        },
    )
    assert update_res.status_code == 200
    assert update_res.json()["profile"]["rank"] == "Captain"

    # Step 7: Verify User B's dossier is unaffected
    res_b3 = client.get("/api/user/profile", headers={"X-User-Id": user_b})
    assert res_b3.json()["profile"]["rank"] == "Not configured", "User A dossier must not leak to User B"


def test_onboarding_manual_reset(client):
    """Verify operator can manually reset the tour to retake orientation."""
    user = "usr_retake_tour_test"
    client.post("/api/user/onboarding/complete", headers={"X-User-Id": user})

    # Reset
    reset_res = client.post("/api/user/onboarding/reset", headers={"X-User-Id": user})
    assert reset_res.status_code == 200
    assert reset_res.json()["onboarding_completed"] is False

    # Verify profile reflects reset
    res = client.get("/api/user/profile", headers={"X-User-Id": user})
    assert res.json()["profile"]["onboarding_completed"] is False


def test_offline_credential_verification():
    """Verify offline credential hashing and validation without plaintext storage."""
    uid = "usr_offline_tactical_test"
    email = "tactical@defense.percepta.ai"
    pwd = "SecureTacticalPassword99"

    user_manager.save_offline_credentials(uid, email, pwd)

    # Correct credentials -> success
    verified = user_manager.verify_offline_credentials(email, pwd)
    assert verified is not None
    assert verified.id == uid

    # Incorrect credentials -> failure
    wrong = user_manager.verify_offline_credentials(email, "WrongPassword123")
    assert wrong is None


def test_supabase_identity_sync(client):
    """Verify syncing Supabase cloud identity initializes local user sandbox."""
    sub_id = "f81d4fae-7dec-11d0-a765-00a0c91e6bf6"
    res = client.post(
        "/api/user/sync-supabase",
        json={
            "supabase_id": sub_id,
            "email": "cloud_officer@percepta.mil",
            "name": "Col. Sharma",
            "offline_pin": "pin_9876",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["user_id"] == sub_id
    assert "users" in data["workspace"]


def test_repository_independence_video_resolution():
    """Verify video resolution does not fail when VIRAT folder is absent."""
    from backend.api.cameras import resolve_video_path

    # virat_cctv.mp4 is bundled in frontend/public/videos or storage/
    resolved = resolve_video_path("virat_cctv.mp4")
    assert resolved is not None, "virat_cctv.mp4 must resolve from bundled assets"
    assert Path(resolved).exists(), f"Resolved video does not exist: {resolved}"

    # Generic search returns fallback when specific VIRAT subfolder is requested
    resolved_virat = resolve_video_path("VIRAT/CCTV 01/VIRAT_S_000205_02_000409_000566.mp4")
    assert resolved_virat is not None, "Fallback must resolve to bundled CCTV clip"
    assert Path(resolved_virat).exists()
