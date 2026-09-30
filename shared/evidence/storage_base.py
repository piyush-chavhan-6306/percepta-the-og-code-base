"""
PERCEPTA SHARED EVIDENCE STORAGE ABSTRACTION
Provides decoupled, provider-agnostic storage interfaces for forensic evidence,
snapshots, clips, and recordings with SHA-256 integrity verification and configurable retention.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class EvidenceMetadata:
    def __init__(
        self,
        evidence_id: str,
        incident_id: str,
        camera_id: str,
        file_path: str,
        file_size_bytes: int,
        sha256_hash: str,
        is_permanent_evidence: bool = True,
        timestamp: Optional[str] = None,
        retention_expires_at: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ):
        self.evidence_id = evidence_id
        self.incident_id = incident_id
        self.camera_id = camera_id
        self.file_path = file_path
        self.file_size_bytes = file_size_bytes
        self.sha256_hash = sha256_hash
        self.is_permanent_evidence = is_permanent_evidence
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.retention_expires_at = retention_expires_at
        self.extra_metadata = extra_metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "incident_id": self.incident_id,
            "camera_id": self.camera_id,
            "file_path": self.file_path,
            "file_size_bytes": self.file_size_bytes,
            "sha256_hash": self.sha256_hash,
            "is_permanent_evidence": self.is_permanent_evidence,
            "timestamp": self.timestamp,
            "retention_expires_at": self.retention_expires_at,
            "extra_metadata": self.extra_metadata,
        }


class EvidenceStorage(ABC):
    """Abstract base class for forensic evidence and video storage."""

    @abstractmethod
    async def store_evidence(
        self,
        evidence_id: str,
        incident_id: str,
        camera_id: str,
        data: bytes,
        extension: str = "jpg",
        is_permanent: bool = True,
        retention_hours: Optional[int] = None,
    ) -> EvidenceMetadata:
        """Store evidence bytes and return its metadata with SHA-256 checksum."""
        pass

    @abstractmethod
    async def retrieve_evidence(self, file_path: str) -> Optional[bytes]:
        """Retrieve raw evidence bytes by path."""
        pass

    @abstractmethod
    async def verify_integrity(self, file_path: str, expected_sha256: str) -> bool:
        """Verify that the stored file's SHA-256 matches the expected forensic hash."""
        pass

    @abstractmethod
    async def purge_expired_recordings(self, max_retention_hours: int) -> int:
        """
        Purge expired temporary surveillance recordings while strictly protecting
        permanent forensic incident evidence. Returns number of purged files.
        """
        pass


class LocalEvidenceStorage(EvidenceStorage):
    """Local filesystem implementation for Offline deployments and Edge buffer."""

    def __init__(self, base_directory: str = "./storage"):
        self.base_dir = Path(base_directory)
        self.evidence_dir = self.base_dir / "evidence"
        self.recordings_dir = self.base_dir / "recordings"
        self.snapshots_dir = self.base_dir / "snapshots"
        self.clips_dir = self.base_dir / "clips"
        
        for d in (self.evidence_dir, self.recordings_dir, self.snapshots_dir, self.clips_dir):
            d.mkdir(parents=True, exist_ok=True)

    async def store_evidence(
        self,
        evidence_id: str,
        incident_id: str,
        camera_id: str,
        data: bytes,
        extension: str = "jpg",
        is_permanent: bool = True,
        retention_hours: Optional[int] = None,
    ) -> EvidenceMetadata:
        target_dir = self.evidence_dir if is_permanent else self.recordings_dir
        filename = f"{incident_id}_{evidence_id}.{extension}"
        file_path = target_dir / filename

        # Write data
        with open(file_path, "wb") as f:
            f.write(data)

        sha256 = hashlib.sha256(data).hexdigest()
        expires_at = None
        if retention_hours and not is_permanent:
            exp = datetime.now(timezone.utc) + timedelta(hours=retention_hours)
            expires_at = exp.isoformat()

        meta = EvidenceMetadata(
            evidence_id=evidence_id,
            incident_id=incident_id,
            camera_id=camera_id,
            file_path=str(file_path.as_posix()),
            file_size_bytes=len(data),
            sha256_hash=sha256,
            is_permanent_evidence=is_permanent,
            retention_expires_at=expires_at,
        )
        return meta

    async def retrieve_evidence(self, file_path: str) -> Optional[bytes]:
        p = Path(file_path)
        if not p.is_file():
            return None
        with open(p, "rb") as f:
            return f.read()

    async def verify_integrity(self, file_path: str, expected_sha256: str) -> bool:
        data = await self.retrieve_evidence(file_path)
        if data is None:
            return False
        return hashlib.sha256(data).hexdigest().lower() == expected_sha256.lower()

    async def purge_expired_recordings(self, max_retention_hours: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_retention_hours)
        purged = 0
        
        # Only inspect recordings_dir (never evidence_dir)
        for item in self.recordings_dir.glob("*"):
            if item.is_file():
                mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
                if mtime < cutoff:
                    try:
                        item.unlink()
                        purged += 1
                    except OSError:
                        pass
        return purged
