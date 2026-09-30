/**
 * PERCEPTA SHARED SYNC PROTOCOL TYPES
 */

export type SyncState = "PENDING" | "UPLOADING" | "SYNCED" | "FAILED" | "RETRYING";

export interface SyncRecord {
  sync_id: string;
  entity_type: "INCIDENT" | "EVIDENCE" | "CAMERA" | "ZONE" | "TRIPWIRE";
  entity_id: string;
  source_device_id: string;
  payload: Record<string, any>;
  state: SyncState;
  retry_count: number;
  last_error?: string;
  created_at: string;
  updated_at: string;
}

export interface SyncStatusSummary {
  pending_count: number;
  uploading_count: number;
  synced_count: number;
  failed_count: number;
  is_online: boolean;
  last_sync_timestamp?: string;
}
