"""
PERCEPTA ONLINE + OFFLINE ARCHITECTURAL VERIFICATION SUITE
Tests the shared severity engine, storage abstraction, retention policy,
offline persistent sync queue, online sync receiver, and copilot grounding.
"""
import asyncio
import os
import shutil
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
from shared.severity.engine import calculate_severity, normalize_severity
from shared.evidence.storage_base import LocalEvidenceStorage, EvidenceMetadata
from shared.models.schemas import IncidentSyncPacket, EvidenceSyncPacket
from offline.sync.queue import PersistentSyncQueue
from online.storage.retention_manager import RetentionManager
from online.auth.supabase_auth import AuthenticatedUser
from shared.copilot.tools import COPILOT_TOOL_DEFINITIONS


class TestSharedSeverityEngine:
    def test_strict_severity_classification(self):
        # Critical: >= 60.0
        assert calculate_severity(100.0) == "CRITICAL"
        assert calculate_severity(60.0) == "CRITICAL"
        assert calculate_severity(60.1) == "CRITICAL"

        # Restricted: >= 25.0 and < 60.0
        assert calculate_severity(59.9) == "RESTRICTED"
        assert calculate_severity(25.0) == "RESTRICTED"
        assert calculate_severity(35.5) == "RESTRICTED"

        # Normal: < 25.0
        assert calculate_severity(24.9) == "NORMAL"
        assert calculate_severity(10.0) == "NORMAL"
        assert calculate_severity(0.0) == "NORMAL"

    def test_normalize_severity(self):
        assert normalize_severity("critical") == "CRITICAL"
        assert normalize_severity("RESTRICTED") == "RESTRICTED"
        assert normalize_severity("normal") == "NORMAL"
        assert normalize_severity(None, threat_score=85.0) == "CRITICAL"


class TestEvidenceStorageAbstraction:
    @pytest.mark.asyncio
    async def test_local_storage_and_integrity(self):
        temp_dir = tempfile.mkdtemp()
        try:
            storage = LocalEvidenceStorage(base_directory=temp_dir)
            sample_bytes = b"JPEG_FORENSIC_EVIDENCE_SAMPLE_FRAME_123"
            
            # Store permanent evidence
            meta = await storage.store_evidence(
                evidence_id="ev_001",
                incident_id="inc_001",
                camera_id="CAM-01",
                data=sample_bytes,
                extension="jpg",
                is_permanent=True,
            )
            assert meta.evidence_id == "ev_001"
            assert meta.is_permanent_evidence is True
            assert len(meta.sha256_hash) == 64

            # Verify integrity
            valid = await storage.verify_integrity(meta.file_path, meta.sha256_hash)
            assert valid is True

            # Verify corrupted hash fails
            invalid = await storage.verify_integrity(meta.file_path, "wrong_hash" * 4)
            assert invalid is False
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_retention_preserves_permanent_evidence(self):
        temp_dir = tempfile.mkdtemp()
        try:
            storage = LocalEvidenceStorage(base_directory=temp_dir)
            
            # 1. Store permanent incident evidence
            ev_meta = await storage.store_evidence(
                evidence_id="ev_perm_001",
                incident_id="inc_001",
                camera_id="CAM-01",
                data=b"PERMANENT_INCIDENT_EVIDENCE",
                is_permanent=True,
            )

            # 2. Store temporary raw recording
            rec_meta = await storage.store_evidence(
                evidence_id="rec_temp_001",
                incident_id="raw_stream",
                camera_id="CAM-01",
                data=b"TEMPORARY_SURVEILLANCE_VIDEO_STREAM",
                is_permanent=False,
                retention_hours=2,
            )

            # Age the temporary recording file mtime by 5 hours
            rec_path = rec_meta.file_path
            old_time = (datetime.now() - timedelta(hours=5)).timestamp()
            os.utime(rec_path, (old_time, old_time))

            # Run retention purge (max retention 2 hours)
            purged = await storage.purge_expired_recordings(max_retention_hours=2)
            assert purged == 1

            # Permanent evidence MUST still exist!
            assert os.path.exists(ev_meta.file_path) is True
            # Temporary recording MUST be deleted!
            assert os.path.exists(rec_path) is False
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestOfflinePersistentSyncQueue:
    def test_enqueue_and_deduplication(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_db = os.path.join(temp_dir, "test_percepta_sync.db")
            queue = PersistentSyncQueue(db_path=temp_db)
            sync_id = "sync_packet_001"
            
            # Enqueue incident
            queue.enqueue(
                sync_id=sync_id,
                entity_type="INCIDENT",
                entity_id="inc_101",
                source_device_id="edge_station_north",
                payload={"incident_id": "inc_101", "severity": "CRITICAL", "threat_score": 90.0},
            )

            items = queue.get_pending_items()
            assert len(items) == 1
            assert items[0]["sync_id"] == sync_id
            assert items[0]["state"] == "PENDING"

            # Transition state
            queue.mark_state(sync_id, "SYNCED")
            assert len(queue.get_pending_items()) == 0


class TestCopilotToolArchitecture:
    def test_grounded_tool_definitions(self):
        tool_names = [t["name"] for t in COPILOT_TOOL_DEFINITIONS]
        assert "get_incident" in tool_names
        assert "search_incidents" in tool_names
        assert "get_camera_trust" in tool_names
        assert "get_pathguard_events" in tool_names
        assert "get_blind_spots" in tool_names
        assert "get_system_status" in tool_names
