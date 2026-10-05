"""
Excel-backed data layer — replaces PostgreSQL/PostGIS/pgvector entirely.

TWO workbooks are used, deliberately kept separate:

  1. dataset/SIH26001_Master_Dataset.xlsx — the project's Census of India
     2001 Village Directory workbook. It is treated as READ-ONLY reference
     data (the app never writes to it): its "Expanded_Dataset" sheet
     becomes the `village_census_profile` table, loaded once at startup.
     Mixing this large, citation-worthy source sheet with the app's own
     frequently-mutated live tables in one file would mean every
     alert/report/road-status write rewrites the census sheet too (slower,
     and a real corruption risk to the one sheet that must stay
     byte-for-byte traceable to its original source), so it stays untouched
     in its own file.

     As of the dataset's v2 expansion, "Expanded_Dataset" holds 8,722 real
     Census-2001 rows (byte-identical to the original v1 "Master_Dataset"
     sheet — confirmed column-by-column, not assumed) PLUS 13,083
     transparently-labeled synthetic rows (a 1.5x augmentation, resampled
     from real rows with correlated noise applied only to continuous
     numeric fields — see the workbook's own "Notes_Limitations" and
     "Validation_Report" sheets for the full method and validation). Every
     row carries a `data_provenance` column: "real_census_2001" or
     "synthetic_generated_v1" — a synthetic row's `record_id`/`village_code`/
     `village_name`/`source_file` are also regenerated (`SYN_######`,
     `Synthetic_Village_######`) specifically so it can never be mistaken
     for a real, named village. Every consumer of this table
     (app/api/census.py, app/services/query_router.py's RAG census
     answers) defaults to real rows only — the synthetic rows exist for
     opt-in use (e.g. UI load-testing, future ML-feature-richness
     experiments), never silently blended into what the app presents as
     real Census 2001 data.

  2. dataset/terraguard_data.xlsx — a sibling workbook, one sheet per
     former Postgres table, created (and seeded) by this module the first
     time the app runs if it does not already exist. This is the ONLY file
     the app ever writes to.

On import, `get_store()` lazily loads every sheet of both workbooks into an
in-memory pandas DataFrame kept in the module-level `Store` singleton. All
reads are served from memory. Every mutation:
  (a) validates the change in the caller (routers/services do this),
  (b) updates the in-memory DataFrame,
  (c) persists ALL live-table sheets back to terraguard_data.xlsx atomically
      (write to a temp file in the same directory, then os.replace), guarded
      by a cross-process file lock (`filelock`) so two processes/requests
      can never interleave a write and corrupt the file,
  (d) keeps memory and file in sync, so the next read — even from another
      process that reloads the store — sees the update.

LIMITATION (documented honestly, not hidden): this in-memory-plus-file-lock
design assumes a SINGLE `uvicorn` worker process, as this MVP runs. A
second worker process would hold its own separate in-memory copy that only
picks up another worker's writes on its own next full reload — there is no
cross-process cache invalidation here. Do not run this app with
`--workers > 1` (or multiple gunicorn workers) without adding that.
"""
from __future__ import annotations

import json
import math
import os
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

import pandas as pd
from filelock import FileLock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
# backend/app/core/excel_store.py -> repo root is 4 levels up (core -> app -> backend -> repo)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

DATASET_DIR = os.path.join(_REPO_ROOT, "dataset")
CENSUS_XLSX_PATH = os.environ.get(
    "TERRAGUARD_CENSUS_XLSX", os.path.join(DATASET_DIR, "SIH26001_Master_Dataset.xlsx")
)
LIVE_XLSX_PATH = os.environ.get(
    "TERRAGUARD_LIVE_XLSX", os.path.join(DATASET_DIR, "terraguard_data.xlsx")
)

CENSUS_SHEET = "Expanded_Dataset"
CENSUS_TABLE = "village_census_profile"
# The raw sheet's own tag for a genuine Census-2001 row vs. the transparent
# statistical-augmentation rows added in the dataset's v2 expansion — see
# this module's docstring above and app/api/census.py.
CENSUS_REAL_PROVENANCE = "real_census_2001"
CENSUS_SYNTHETIC_PROVENANCE = "synthetic_generated_v1"

# --- Live table -> sheet name (identical; kept as a constant in case any
# ever needs to differ, e.g. Excel's 31-char sheet-name limit). ------------
LIVE_TABLES = [
    "users",
    "landslide_events",
    "rainfall_records",
    "risk_predictions",
    "risk_zones",
    "field_reports",
    "roads",
    "villages",
    "hospitals",
    "schools",
    "alerts",
    "notification_history",
    "satellite_observations",
    "rag_documents",
    "rag_chunks",
    "data_source_cache",
    "alert_lifecycle_events",
    "alert_acknowledgements",
    "alert_assignments",
]

# Columns that hold JSON-serialized Python objects (dict/list) rather than
# scalars — serialized to a JSON string on save, parsed back to a Python
# object on load, so callers always see real dict/list values in memory.
JSON_COLUMNS: dict[str, list[str]] = {
    "risk_predictions": ["contributing_factors", "rainfall_context"],
    "field_reports": ["photo_ai_analysis"],
    "notification_history": ["payload"],
    "satellite_observations": ["metadata"],
    "rag_chunks": ["embedding", "metadata"],
    "data_source_cache": ["payload"],
}

# Column -> empty-DataFrame dtype, used only when creating a brand-new sheet
# with zero rows so pandas doesn't guess `object` for numeric id columns.
_SCHEMAS: dict[str, dict[str, str]] = {
    "users": {
        "id": "int64", "email": "object", "password_hash": "object", "full_name": "object",
        "role": "object", "is_active": "bool", "created_at": "object",
        "reset_token": "object", "reset_token_expires": "object",
    },
    "landslide_events": {
        "id": "int64", "source_event_id": "object", "source": "object", "state": "object",
        "district": "object", "latitude": "float64", "longitude": "float64",
        "event_date": "object", "event_year": "Int64", "event_month": "Int64",
        "season": "object", "landslide_type": "object", "severity": "object",
        "trigger": "object", "validation_status": "object", "confidence": "object",
        "fatality_count": "Int64", "injury_count": "Int64", "event_title": "object",
        "event_description": "object", "data_provenance": "object", "created_at": "object",
    },
    "rainfall_records": {
        "id": "int64", "state": "object", "district": "object", "year": "Int64",
        "month": "Int64", "rainfall_mm": "float64", "temporal_resolution": "object",
        "source": "object", "data_provenance": "object", "created_at": "object",
    },
    "risk_predictions": {
        "id": "int64", "latitude": "float64", "longitude": "float64", "state": "object",
        "district": "object", "probability": "float64", "risk_score": "float64",
        "risk_level": "object", "contributing_factors": "object", "rainfall_context": "object",
        "model_version": "object", "requested_by": "Int64", "created_at": "object",
    },
    "risk_zones": {
        "id": "int64", "name": "object", "state": "object", "district": "object",
        "latitude": "float64", "longitude": "float64", "radius_m": "float64",
        "risk_score": "float64", "risk_level": "object", "data_provenance": "object",
        "updated_at": "object",
    },
    "field_reports": {
        "id": "int64", "client_report_id": "object", "reporter_name": "object",
        "reporter_contact": "object", "latitude": "float64", "longitude": "float64",
        "incident_type": "object", "description": "object", "severity": "object",
        "photo_path": "object", "photo_ai_analysis": "object", "device_timestamp": "object",
        "server_received_at": "object", "sync_status": "object", "created_at": "object",
    },
    "roads": {
        "id": "int64", "name": "object", "road_type": "object", "state": "object",
        "district": "object", "geom_wkt": "object", "status": "object",
        "blocked_reason": "object", "blocked_since": "object", "data_provenance": "object",
        "updated_at": "object",
    },
    "villages": {
        "id": "int64", "name": "object", "state": "object", "district": "object",
        "latitude": "float64", "longitude": "float64", "population": "Int64",
        "data_provenance": "object", "created_at": "object",
    },
    "hospitals": {
        "id": "int64", "name": "object", "state": "object", "district": "object",
        "latitude": "float64", "longitude": "float64", "data_provenance": "object",
        "created_at": "object",
    },
    "schools": {
        "id": "int64", "name": "object", "state": "object", "district": "object",
        "latitude": "float64", "longitude": "float64", "data_provenance": "object",
        "created_at": "object",
    },
    "alerts": {
        "id": "int64", "alert_type": "object", "severity": "object", "latitude": "float64",
        "longitude": "float64", "state": "object", "district": "object", "risk_score": "float64",
        "reason": "object", "affected_area": "object", "recommended_action": "object",
        "status": "object", "created_at": "object", "risk_zone_id": "Int64",
    },
    "notification_history": {
        "id": "int64", "alert_id": "Int64", "channel": "object", "recipient": "object",
        "status": "object", "payload": "object", "sent_at": "object", "created_at": "object",
    },
    "satellite_observations": {
        "id": "int64", "source": "object", "observation_type": "object", "latitude": "float64",
        "longitude": "float64", "observation_date": "object", "value": "float64",
        "unit": "object", "metadata": "object", "data_provenance": "object", "created_at": "object",
    },
    "rag_documents": {
        "id": "int64", "title": "object", "source": "object", "filepath": "object",
        "content_hash": "object", "ingested_at": "object",
    },
    "rag_chunks": {
        "id": "int64", "document_id": "int64", "chunk_index": "int64", "content": "object",
        "embedding": "object", "metadata": "object", "created_at": "object",
    },
    "data_source_cache": {
        "id": "int64", "source": "object", "grid_lat": "float64", "grid_lon": "float64",
        "param": "object", "payload": "object", "retrieved_at": "object",
    },
    # --- Alert Intelligence Center tables -------------------------------- #
    # Append-only stage log. A stage with no row for a given alert_id is
    # honestly "pending" — never backfilled. See app/services/alert_intelligence.py
    # for the canonical list of valid `stage` values.
    "alert_lifecycle_events": {
        "id": "int64", "alert_id": "Int64", "stage": "object", "occurred_at": "object",
        "note": "object",
    },
    # One row per acknowledgement event. `role` is one of the 4 real/simulated
    # channels (field_officer/authority/admin map to real user accounts;
    # community/emergency_team are honestly-labeled simulation-only channels
    # since this project has no real notification-delivery or community
    # account system).
    "alert_acknowledgements": {
        "id": "int64", "alert_id": "Int64", "role": "object", "acknowledged_by": "object",
        "acknowledged_at": "object",
    },
    "alert_assignments": {
        "id": "int64", "alert_id": "Int64", "assignee_name": "object", "role": "object",
        "assigned_at": "object",
    },
}


def _empty_df(table: str) -> pd.DataFrame:
    schema = _SCHEMAS[table]
    return pd.DataFrame({col: pd.Series(dtype=dtype) for col, dtype in schema.items()})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """In-memory table store backed by two Excel workbooks. Thread-safe for
    a single process via an internal RLock; safe across processes for the
    on-disk write via a `filelock.FileLock` (see module docstring for the
    single-worker limitation this does NOT solve)."""

    def __init__(self, live_path: str = LIVE_XLSX_PATH, census_path: str = CENSUS_XLSX_PATH):
        self.live_path = live_path
        self.census_path = census_path
        self._lock = threading.RLock()
        self._tables: dict[str, pd.DataFrame] = {}
        self._loaded = False

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #
    def load(self) -> None:
        with self._lock:
            if os.path.exists(self.live_path):
                sheets = pd.read_excel(self.live_path, sheet_name=None)
                for table in LIVE_TABLES:
                    df = sheets.get(table)
                    if df is None:
                        df = _empty_df(table)
                    df = self._reconcile_schema(table, df)
                    self._tables[table] = self._decode_json_columns(table, df)
            else:
                os.makedirs(os.path.dirname(self.live_path), exist_ok=True)
                for table in LIVE_TABLES:
                    self._tables[table] = _empty_df(table)
                self._seed_demo_data()
                self.save()

            self._tables[CENSUS_TABLE] = self._load_census()
            self._loaded = True

    def _reconcile_schema(self, table: str, df: pd.DataFrame) -> pd.DataFrame:
        """Adds any schema column missing from a sheet loaded from an older
        workbook (e.g. `alerts.risk_zone_id`, or a brand-new table this
        version added) as an all-null column, rather than raising KeyError
        downstream. Never drops or backfills real data — a genuinely absent
        column stays null, honestly, for existing rows."""
        schema = _SCHEMAS.get(table, {})
        for col, dtype in schema.items():
            if col not in df.columns:
                df[col] = pd.Series([None] * len(df), dtype="object" if dtype == "object" else None)
        return df

    def _load_census(self) -> pd.DataFrame:
        if not os.path.exists(self.census_path):
            return pd.DataFrame()
        try:
            df = pd.read_excel(self.census_path, sheet_name=CENSUS_SHEET)
        except ValueError:
            # Backward compatibility: an older v1 workbook (pre-expansion)
            # only has the original "Master_Dataset" sheet, with no
            # data_provenance column and no synthetic rows at all. Load it
            # as-is rather than crashing the whole app — every consumer
            # already treats a missing data_provenance as "real" (see
            # app/api/census.py's _with_defaults and query_router.py's
            # real-only filters), so this degrades gracefully to
            # real-data-only behavior, identical to how the app behaved
            # before the v2 expansion existed.
            df = pd.read_excel(self.census_path, sheet_name="Master_Dataset")
        return df

    def _decode_json_columns(self, table: str, df: pd.DataFrame) -> pd.DataFrame:
        for col in JSON_COLUMNS.get(table, []):
            if col not in df.columns:
                continue
            df[col] = df[col].apply(_json_loads_or_none)
        return df

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def df(self, table: str) -> pd.DataFrame:
        """Returns a COPY of the table's current DataFrame — callers may
        filter/sort freely without risking mutating the store's own state
        outside of insert/update/delete."""
        self.ensure_loaded()
        with self._lock:
            return self._tables[table].copy(deep=True)

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    def next_id(self, table: str, id_col: str = "id") -> int:
        with self._lock:
            df = self._tables[table]
            if df.empty or df[id_col].isna().all():
                return 1
            return int(pd.to_numeric(df[id_col], errors="coerce").max()) + 1

    def insert(self, table: str, row: dict[str, Any], id_col: str = "id", persist: bool = True) -> dict[str, Any]:
        """Inserts `row` (assigning an auto id if `id_col` is absent/None),
        appends it to the in-memory table, and persists all live tables to
        disk (unless `persist=False`, for batched multi-row inserts —
        remember to call `save()` yourself afterwards)."""
        self.ensure_loaded()
        with self._lock:
            df = self._tables[table]
            row = dict(row)
            if row.get(id_col) in (None, ""):
                row[id_col] = self.next_id(table, id_col)
            new_row = pd.DataFrame([row])
            self._tables[table] = pd.concat([df, new_row], ignore_index=True)
            if persist:
                self.save()
            return row

    def update_where(
        self, table: str, id_col: str, id_val: Any, updates: dict[str, Any], persist: bool = True
    ) -> bool:
        self.ensure_loaded()
        with self._lock:
            df = self._tables[table]
            mask = df[id_col] == id_val
            if not mask.any():
                return False
            matched_idx = df.index[mask]
            for k, v in updates.items():
                if k not in df.columns:
                    df[k] = None
                if isinstance(v, (list, dict)):
                    # A single list/dict value must not be broadcast
                    # element-wise across matched rows by pandas — assign it
                    # as one Python object per matched row instead.
                    for idx in matched_idx:
                        df.at[idx, k] = v
                else:
                    df.loc[mask, k] = v
            self._tables[table] = df
            if persist:
                self.save()
            return True

    def delete_where(self, table: str, id_col: str, id_val: Any, persist: bool = True) -> bool:
        self.ensure_loaded()
        with self._lock:
            df = self._tables[table]
            mask = df[id_col] == id_val
            if not mask.any():
                return False
            self._tables[table] = df.loc[~mask].reset_index(drop=True)
            if persist:
                self.save()
            return True

    def replace_table(self, table: str, df: pd.DataFrame, persist: bool = True) -> None:
        """Wholesale-replaces a table's contents (e.g. a bulk historical-data
        reload script). Used sparingly — most endpoints use insert/update."""
        self.ensure_loaded()
        with self._lock:
            self._tables[table] = df.reset_index(drop=True)
            if persist:
                self.save()

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def save(self) -> None:
        """Atomically persists every live-table sheet to `terraguard_data.xlsx`:
        writes a temp file, then `os.replace`s it into place, guarded by a
        cross-process file lock so two writers can never interleave."""
        with self._lock:
            os.makedirs(os.path.dirname(self.live_path), exist_ok=True)
            lock_path = self.live_path + ".lock"
            with FileLock(lock_path, timeout=30):
                tmp_path = self.live_path[: -len(".xlsx")] + f".tmp-{uuid.uuid4().hex}.xlsx" if self.live_path.endswith(".xlsx") else self.live_path + f".tmp-{uuid.uuid4().hex}"
                with pd.ExcelWriter(tmp_path, engine="openpyxl") as writer:
                    for table in LIVE_TABLES:
                        out = self._encode_json_columns(table, self._tables[table])
                        # Excel sheet names are capped at 31 characters.
                        out.to_excel(writer, sheet_name=table[:31], index=False)
                os.replace(tmp_path, self.live_path)

    def _encode_json_columns(self, table: str, df: pd.DataFrame) -> pd.DataFrame:
        cols = JSON_COLUMNS.get(table, [])
        if not cols:
            return df
        out = df.copy()
        for col in cols:
            if col in out.columns:
                out[col] = out[col].apply(lambda v: json.dumps(v) if v is not None and not _is_nan(v) else None)
        return out

    # ------------------------------------------------------------------ #
    # Demo seed (ported verbatim from the project's own database/seed.sql —
    # every value below already carries data_provenance='demo' in the
    # original SQL and is committed project content, not a new invention).
    # ------------------------------------------------------------------ #
    def _seed_demo_data(self) -> None:
        import bcrypt

        def _hash(pw: str) -> str:
            return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        now = _now_iso()

        self._tables["users"] = pd.DataFrame([
            {"id": 1, "email": "admin@terraguard.demo", "password_hash": _hash("Admin@123"),
             "full_name": "Demo Admin", "role": "admin", "is_active": True, "created_at": now,
             "reset_token": None, "reset_token_expires": None},
            {"id": 2, "email": "authority@terraguard.demo", "password_hash": _hash("Authority@123"),
             "full_name": "Demo District Authority", "role": "authority", "is_active": True,
             "created_at": now, "reset_token": None, "reset_token_expires": None},
            {"id": 3, "email": "field@terraguard.demo", "password_hash": _hash("Field@123"),
             "full_name": "Demo Field Officer", "role": "field_officer", "is_active": True,
             "created_at": now, "reset_token": None, "reset_token_expires": None},
        ])

        villages = [
            ("Rangpo (demo)", "Sikkim", "East Sikkim", 27.1706, 88.5322, 3200),
            ("Mangan (demo)", "Sikkim", "North Sikkim", 27.5122, 88.5322, 2100),
            ("Haflong (demo)", "Assam", "Dima Hasao", 25.1667, 93.0167, 8500),
            ("Tamenglong Town (demo)", "Manipur", "Tamenglong", 25.0333, 93.5000, 4600),
            ("Kohima Village (demo)", "Nagaland", "Kohima", 25.6751, 94.1086, 12000),
            ("Lawngtlai Town (demo)", "Mizoram", "Lawngtlai", 22.5333, 92.9000, 5300),
        ]
        self._tables["villages"] = pd.DataFrame([
            {"id": i + 1, "name": n, "state": s, "district": d, "latitude": lat, "longitude": lon,
             "population": pop, "data_provenance": "demo", "created_at": now}
            for i, (n, s, d, lat, lon, pop) in enumerate(villages)
        ])

        hospitals = [
            ("Rangpo Community Health Centre (demo)", "Sikkim", "East Sikkim", 27.1750, 88.5300),
            ("Haflong Civil Hospital (demo)", "Assam", "Dima Hasao", 25.1700, 93.0200),
            ("Kohima District Hospital (demo)", "Nagaland", "Kohima", 25.6700, 94.1100),
        ]
        self._tables["hospitals"] = pd.DataFrame([
            {"id": i + 1, "name": n, "state": s, "district": d, "latitude": lat, "longitude": lon,
             "data_provenance": "demo", "created_at": now}
            for i, (n, s, d, lat, lon) in enumerate(hospitals)
        ])

        schools = [
            ("Rangpo Govt. Secondary School (demo)", "Sikkim", "East Sikkim", 27.1720, 88.5340),
            ("Haflong Govt. Higher Secondary School (demo)", "Assam", "Dima Hasao", 25.1650, 93.0130),
            ("Tamenglong Govt. School (demo)", "Manipur", "Tamenglong", 25.0350, 93.5050),
        ]
        self._tables["schools"] = pd.DataFrame([
            {"id": i + 1, "name": n, "state": s, "district": d, "latitude": lat, "longitude": lon,
             "data_provenance": "demo", "created_at": now}
            for i, (n, s, d, lat, lon) in enumerate(schools)
        ])

        roads = [
            (1, "NH10 Rangpo-Mangan Link (demo)", "highway", "Sikkim", "East Sikkim",
             [(88.5322, 27.1706), (88.5280, 27.2500), (88.5322, 27.5122)], "open", None, None),
            (2, "Rangpo Alternate Route (demo)", "district_road", "Sikkim", "East Sikkim",
             [(88.5322, 27.1706), (88.5600, 27.2200), (88.5322, 27.5122)], "open", None, None),
            (3, "Haflong-Tamenglong Corridor (demo)", "state_highway", "Assam", "Dima Hasao",
             [(93.0167, 25.1667), (93.2500, 25.0800), (93.5000, 25.0333)], "blocked",
             "Debris flow reported (demo)", now),
        ]
        self._tables["roads"] = pd.DataFrame([
            {"id": rid, "name": n, "road_type": rt, "state": s, "district": d,
             "geom_wkt": _linestring_wkt(coords), "status": status,
             "blocked_reason": reason, "blocked_since": since,
             "data_provenance": "demo", "updated_at": now}
            for rid, n, rt, s, d, coords, status, reason, since in roads
        ])

        risk_zones = [
            ("East Sikkim high-slope corridor (demo)", "Sikkim", "East Sikkim", 27.1706, 88.5322, 6000, 68, "HIGH"),
            ("Dima Hasao corridor (demo)", "Assam", "Dima Hasao", 25.1667, 93.0167, 8000, 81, "CRITICAL"),
            ("Tamenglong hill tract (demo)", "Manipur", "Tamenglong", 25.0333, 93.5000, 5000, 42, "MODERATE"),
        ]
        self._tables["risk_zones"] = pd.DataFrame([
            {"id": i + 1, "name": n, "state": s, "district": d, "latitude": lat, "longitude": lon,
             "radius_m": radius, "risk_score": score, "risk_level": level,
             "data_provenance": "demo", "updated_at": now}
            for i, (n, s, d, lat, lon, radius, score, level) in enumerate(risk_zones)
        ])

        self._tables["field_reports"] = pd.DataFrame([
            {"id": 1, "client_report_id": str(uuid.uuid4()), "reporter_name": "Demo Field Officer",
             "reporter_contact": None, "latitude": 25.1690, "longitude": 93.0180,
             "incident_type": "blocked_road",
             "description": "Road blocked by debris near Haflong-Tamenglong corridor (demo report).",
             "severity": "high", "photo_path": None, "photo_ai_analysis": None,
             "device_timestamp": None, "server_received_at": now, "sync_status": "synced",
             "created_at": now},
        ])

        # Everything else starts empty — landslide_events / rainfall_records
        # are populated by scripts/load_historical_data.py from real source
        # CSVs (not fabricated here), and alerts/notifications/predictions/
        # satellite_observations/rag_*/data_source_cache start empty and
        # fill in as the app is used.
        for table in ("landslide_events", "rainfall_records", "risk_predictions", "alerts",
                      "notification_history", "satellite_observations", "rag_documents",
                      "rag_chunks", "data_source_cache"):
            self._tables[table] = _empty_df(table)


def _linestring_wkt(coords: list[tuple[float, float]]) -> str:
    return "LINESTRING(" + ", ".join(f"{lon} {lat}" for lon, lat in coords) + ")"


def linestring_wkt_to_coords(wkt: str) -> list[tuple[float, float]]:
    """Parses 'LINESTRING(lon lat, lon lat, ...)' back into [(lon, lat), ...]."""
    inner = wkt.strip()
    inner = inner[inner.index("(") + 1 : inner.rindex(")")]
    coords = []
    for pair in inner.split(","):
        lon_s, lat_s = pair.strip().split()
        coords.append((float(lon_s), float(lat_s)))
    return coords


def clean_value(v: Any) -> Any:
    """NaN/NaT (pandas' representation of a missing scalar) -> None; a real
    dict/list (a JSON-decoded column) or any other value passes through
    unchanged. Never calls pd.isna() on a list/dict — pandas returns an
    elementwise array for those, which raises on truthiness."""
    if isinstance(v, (dict, list)):
        return v
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def clean_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: clean_value(v) for k, v in r.items()} for r in records]


def _is_nan(v: Any) -> bool:
    try:
        return isinstance(v, float) and math.isnan(v)
    except Exception:  # noqa: BLE001
        return False


def _json_loads_or_none(v: Any) -> Any:
    if v is None or _is_nan(v):
        return None
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            return None
    return None


# ---------------------------------------------------------------------- #
# Module-level singleton, mirroring the old get_db()/SessionLocal pattern
# so FastAPI `Depends(get_store)` is a drop-in replacement everywhere.
# ---------------------------------------------------------------------- #
_store: Optional[Store] = None
_store_lock = threading.Lock()


def get_store() -> Store:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = Store()
                _store.load()
    return _store


def reset_store_for_tests(live_path: str, census_path: str) -> Store:
    """Test-only helper: points the module-level singleton at a throwaway
    copy of the workbooks so tests never mutate the real project files."""
    global _store
    _store = Store(live_path=live_path, census_path=census_path)
    _store.load()
    return _store


def check_store_ready() -> tuple[bool, str]:
    try:
        store = get_store()
        n = len(store.df(CENSUS_TABLE))
        return True, f"ok ({len(LIVE_TABLES)} live tables + village_census_profile [{n} rows])"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
