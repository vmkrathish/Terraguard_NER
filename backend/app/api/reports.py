import datetime as dt
import os
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.config import get_settings
from app.core.excel_store import Store, clean_records, get_store
from app.services.photo_analysis import analyze_photo
from app.schemas.schemas import (
    FieldReportOut, ReportSyncRequest, ReportSyncResponse, ReportSyncResult,
)

router = APIRouter(tags=["reports"])
settings = get_settings()

VALID_INCIDENT_TYPES = {"crack", "slope_movement", "landslide", "blocked_road", "debris", "flooding", "other"}


@router.get("/reports", response_model=list[FieldReportOut])
def list_reports(limit: int = 200, store: Store = Depends(get_store)):
    df = store.df("field_reports").sort_values("created_at", ascending=False, na_position="last").head(limit)
    cols = ["id", "client_report_id", "reporter_name", "latitude", "longitude", "incident_type",
            "description", "severity", "photo_path", "photo_ai_analysis", "sync_status", "created_at"]
    records = df[cols].to_dict("records") if not df.empty else []
    return clean_records(records)


@router.post("/reports", response_model=FieldReportOut)
async def submit_report(
    latitude: float = Form(...),
    longitude: float = Form(...),
    incident_type: str = Form(...),
    description: str | None = Form(None),
    severity: str = Form("unknown"),
    reporter_name: str | None = Form(None),
    client_report_id: str | None = Form(None),
    photo: UploadFile | None = File(None),
    store: Store = Depends(get_store),
):
    if incident_type not in VALID_INCIDENT_TYPES:
        raise HTTPException(status_code=422, detail=f"incident_type must be one of {sorted(VALID_INCIDENT_TYPES)}")

    photo_path = None
    ai_analysis = None
    if photo is not None:
        if photo.content_type not in settings.allowed_mime_types:
            raise HTTPException(status_code=415, detail=f"Unsupported image type: {photo.content_type}")
        contents = await photo.read()
        if len(contents) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Photo exceeds max upload size")
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}_{os.path.basename(photo.filename or 'upload')}"
        photo_path = os.path.join(settings.UPLOAD_DIR, safe_name)
        with open(photo_path, "wb") as f:
            f.write(contents)
        ai_analysis = analyze_photo(photo_path, incident_type)

    crid = client_report_id or str(uuid.uuid4())
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    existing = store.df("field_reports")
    existing = existing[existing["client_report_id"] == crid]
    if not existing.empty:
        # ON CONFLICT (client_report_id) DO UPDATE SET description = EXCLUDED.description
        store.update_where("field_reports", "client_report_id", crid, {"description": description})
        row = store.df("field_reports")
        row = row[row["client_report_id"] == crid].iloc[0].to_dict()
        return clean_records([row])[0]

    row = {
        "client_report_id": crid, "reporter_name": reporter_name, "reporter_contact": None,
        "latitude": latitude, "longitude": longitude, "incident_type": incident_type,
        "description": description, "severity": severity, "photo_path": photo_path,
        "photo_ai_analysis": ai_analysis, "device_timestamp": None,
        "server_received_at": now, "sync_status": "synced", "created_at": now,
    }
    inserted = store.insert("field_reports", row)
    return clean_records([inserted])[0]


@router.post("/reports/sync", response_model=ReportSyncResponse)
def sync_reports(payload: ReportSyncRequest, store: Store = Depends(get_store)):
    """Idempotent sync for the offline field-report queue: re-submitting the
    same client_report_id never creates a duplicate row."""
    results = []
    for item in payload.reports:
        if item.incident_type not in VALID_INCIDENT_TYPES:
            continue
        crid = str(item.client_report_id)
        existing = store.df("field_reports")
        existing = existing[existing["client_report_id"] == crid]
        if not existing.empty:
            results.append(ReportSyncResult(client_report_id=item.client_report_id, status="already_synced", server_id=int(existing.iloc[0]["id"])))
            continue

        now = dt.datetime.now(dt.timezone.utc).isoformat()
        row = {
            "client_report_id": crid, "reporter_name": item.reporter_name,
            "reporter_contact": item.reporter_contact, "latitude": item.latitude, "longitude": item.longitude,
            "incident_type": item.incident_type, "description": item.description, "severity": item.severity,
            "photo_path": None, "photo_ai_analysis": None,
            "device_timestamp": item.device_timestamp.isoformat() if item.device_timestamp else None,
            "server_received_at": now, "sync_status": "synced", "created_at": now,
        }
        inserted = store.insert("field_reports", row)
        results.append(ReportSyncResult(client_report_id=item.client_report_id, status="created", server_id=int(inserted["id"])))

    return ReportSyncResponse(results=results)
