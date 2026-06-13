"""Artifact upload + job-row updates against Supabase.

Degrades gracefully: if Supabase env vars are absent (local CLI runs), uploads
become no-ops that just return the local file path and job updates are skipped.
That lets the whole pipeline run end-to-end on a laptop without any cloud account.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

BUCKET = os.environ.get("ARTIFACT_BUCKET", "artifacts")
SIGNED_URL_TTL = 60 * 60 * 24  # 24h — matches the artifact TTL cleanup
JOB_TTL_HOURS = 24

_MIME = {
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".mid": "audio/midi",
    ".midi": "audio/midi", ".pdf": "application/pdf",
    ".musicxml": "application/vnd.recordare.musicxml+xml",
    ".xml": "application/xml", ".txt": "text/plain", ".json": "application/json",
}


def enabled() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"))


def _client():
    from supabase import create_client

    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _mime(path: Path) -> str:
    return _MIME.get(path.suffix.lower(), "application/octet-stream")


def create_job(job_id: str, source_type: str) -> None:
    """Insert a fresh queued job row with a TTL. No-op when Supabase is absent."""
    if not enabled():
        return
    expires = datetime.now(timezone.utc) + timedelta(hours=JOB_TTL_HOURS)
    _client().table("jobs").insert({
        "id": job_id, "status": "queued", "stage": "queued",
        "source_type": source_type, "expires_at": expires.isoformat(),
    }).execute()


def get_job(job_id: str) -> dict | None:
    """Read a job row by id (used by the status endpoint)."""
    if not enabled():
        return None
    res = _client().table("jobs").select("*").eq("id", job_id).limit(1).execute()
    rows = res.data or []
    return rows[0] if rows else None


def update_job(job_id: str, **fields) -> None:
    """Patch a row in the `jobs` table. No-op when Supabase is not configured."""
    if not enabled():
        return
    _client().table("jobs").update(fields).eq("id", job_id).execute()


def upload_artifact(local_path: str | Path, job_id: str) -> str:
    """Upload one file under <job_id>/<name>; return a URL (or local path locally)."""
    path = Path(local_path)
    if not enabled():
        return str(path)
    key = f"{job_id}/{path.name}"
    client = _client()
    bucket = client.storage.from_(BUCKET)
    bucket.upload(
        key, path.read_bytes(),
        {"content-type": _mime(path), "upsert": "true"},
    )
    signed = bucket.create_signed_url(key, SIGNED_URL_TTL)
    return signed.get("signedURL") or signed.get("signedUrl") or signed.get("signed_url")
