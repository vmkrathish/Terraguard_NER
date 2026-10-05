"""Village census profile (Census of India 2001 Village Directory) API.

This is exposure/impact-assessment CONTEXT data, not risk data: it never
feeds a risk score or the XGBoost model, and it has no coordinates. See
docs/DATASET_SCHEMA_DIFF.md for why. These endpoints exist so the frontend
(and the RAG assistant, via a structured query template — never raw SQL)
can answer questions like "how many people/households are near this
village" honestly, from real Census figures, with no invented numbers.
"""
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, Query

from app.core.excel_store import (
    CENSUS_REAL_PROVENANCE,
    CENSUS_SYNTHETIC_PROVENANCE,
    Store,
    clean_records,
    get_store,
)
from app.schemas.schemas import VillageCensusProfileOut, VillageCensusSearchResponse

router = APIRouter(prefix="/villages", tags=["village-census"])

_OUT_COLUMNS = [
    "record_id", "state_name", "district_code", "village_name", "village_area_hectares",
    "total_households", "population_total", "population_male", "population_female",
    "st_population_total", "sc_population_total", "education_facility_available",
    "medical_facility_available", "drinking_water_facility_available", "approach_pucca_road",
    "nearest_town_name", "distance_to_town_km", "forest_area_hectares", "main_crop",
    "slope_percent", "elevation_m", "soil_characters", "data_provenance", "source_name",
    "quality_status",
]


def _with_defaults(df: pd.DataFrame) -> pd.DataFrame:
    """Maps the sheet's raw `data_provenance` tag to this API's public
    labels, WITHOUT ever overwriting a genuine value with a fabricated one:

    - A row from the original v1 "Master_Dataset" sheet (no data_provenance
      column of its own) or tagged `real_census_2001` in the v2 expanded
      sheet gets the same constant values this API has always returned for
      real rows: data_provenance="historical", quality_status="verified" —
      unchanged behavior for every real row, before or after the v2
      dataset expansion.
    - A row tagged `synthetic_generated_v1` (the v2 expansion's
      transparently-labeled statistical augmentation — see
      excel_store.py's module docstring) is labeled honestly as such, never
      as "historical"/"verified", so a caller that opts into
      `include_synthetic=true` can never mistake it for real Census data.
    """
    df = df.copy()
    df["source_name"] = "Census of India 2001 - Village Directory"
    # np.where (not `.loc[mask, col] = scalar`) so this also works correctly
    # on a zero-row DataFrame (e.g. an unmatched search) — `.loc` assignment
    # against a boolean mask on an empty frame raises in newer pandas when
    # the target column doesn't exist yet.
    is_synthetic = (df["data_provenance"] == CENSUS_SYNTHETIC_PROVENANCE) if "data_provenance" in df.columns else pd.Series(False, index=df.index)
    df["quality_status"] = np.where(is_synthetic, "synthetic_not_verified_statistical_model", "verified")
    df["data_provenance"] = np.where(is_synthetic, CENSUS_SYNTHETIC_PROVENANCE, "historical")
    for col in ("slope_percent", "elevation_m", "soil_characters"):
        if col not in df.columns:
            df[col] = None
    return df


def _real_rows_only(df: pd.DataFrame) -> pd.DataFrame:
    """Filters to genuine Census-2001 rows — the default everywhere this
    table is read. A row from the original v1 sheet (no data_provenance
    column at all) is real by definition; a v2-expanded row is real only
    when explicitly tagged so. Never the other way around: an unrecognized
    or missing tag is treated as real ONLY when the column is entirely
    absent (old workbook), not when it's present but something unexpected —
    that stays excluded rather than risk quietly including a fabricated row."""
    if "data_provenance" not in df.columns:
        return df
    return df[df["data_provenance"].isin([CENSUS_REAL_PROVENANCE]) | df["data_provenance"].isna()]


@router.get("/census-profile", response_model=VillageCensusSearchResponse)
def search_census_profile(
    state: Optional[str] = Query(None, description="State name, e.g. 'Assam'"),
    village_name: Optional[str] = Query(None, description="Case-insensitive substring match on village name"),
    district_code: Optional[int] = Query(None, description="Census 2001 district code (not the same code space as other TerraGuard tables)"),
    limit: int = Query(20, le=200),
    include_synthetic: bool = Query(
        False,
        description=(
            "If true, also include the dataset's transparently-labeled synthetic villages "
            "(statistically modeled, not real Census 2001 records — see data_provenance/"
            "quality_status on each result). Off by default, so every existing caller keeps "
            "seeing real Census 2001 data only, exactly as before this option existed."
        ),
    ),
    store: Store = Depends(get_store),
):
    """Search Census 2001 village exposure/context records. Returns real
    rows only unless `include_synthetic=true` — if nothing matches,
    `results` is empty and `note` explains why; it never fabricates a
    plausible-looking row, and a synthetic row is always labeled as such,
    never presented as real."""
    df = store.df("village_census_profile")
    if not include_synthetic:
        df = _real_rows_only(df)
    if state:
        df = df[df["state_name"].str.contains(state, case=False, na=False)]
    if village_name:
        df = df[df["village_name"].str.contains(village_name, case=False, na=False)]
    if district_code is not None:
        df = df[df["district_code"] == district_code]

    df = df.sort_values("population_total", ascending=False, na_position="last").head(limit)
    df = _with_defaults(df)

    note = None
    if df.empty:
        note = (
            "No matching Census 2001 village record found in TerraGuard's data. This dataset "
            "covers 7 of the 8 North-Eastern states (Manipur is not included — no Village "
            "Directory file was available for it) and reflects the 2001 census year only."
            + ("" if include_synthetic else " (Synthetic villages were excluded — pass include_synthetic=true to search those too.)")
        )

    records = clean_records(df[_OUT_COLUMNS].to_dict("records"))

    return VillageCensusSearchResponse(
        query={"state": state, "village_name": village_name, "district_code": district_code, "include_synthetic": include_synthetic},
        matched=len(records),
        results=[VillageCensusProfileOut.model_validate(r) for r in records],
        note=note,
    )


@router.get("/census-profile/coverage")
def census_profile_coverage(store: Store = Depends(get_store)):
    """Honest coverage summary — used by the admin dashboard and by the RAG
    assistant's data-availability checks, so nobody has to guess whether a
    state/field is covered before answering a user's question with it.
    `states_covered`/`total_villages` are REAL Census-2001 rows only, so
    this endpoint's numbers never move just because the dataset's v2
    expansion added synthetic rows underneath it — the synthetic count is
    reported separately, honestly, in `synthetic_villages_available`."""
    raw_df = store.df("village_census_profile")
    df = _real_rows_only(raw_df)
    synthetic_count = len(raw_df) - len(df)
    if df.empty:
        states_covered = []
    else:
        grouped = df.groupby("state_name")["population_total"].agg(["count", "sum"]).reset_index()
        grouped = grouped.sort_values("state_name")
        states_covered = [
            {"state_name": r["state_name"], "villages": int(r["count"]),
             "population_total": (None if pd.isna(r["sum"]) else int(r["sum"]))}
            for _, r in grouped.iterrows()
        ]
    return {
        "source": "Census of India 2001 - Village Directory",
        "census_year": 2001,
        "states_covered": states_covered,
        "states_not_covered": ["Manipur"],
        "synthetic_villages_available": synthetic_count,
        "synthetic_villages_note": (
            "These are transparently-labeled, statistically-modeled rows added by the "
            "dataset's v2 expansion — not real villages, excluded from every count above. "
            "Pass include_synthetic=true on /villages/census-profile to search them; every "
            "such result carries data_provenance='synthetic_generated_v1'."
        ) if synthetic_count else None,
        "fields_never_available_in_this_dataset": [
            "geological_data_lithology", "soil_characters", "slope_percent", "elevation_m",
            "rainfall_intensity_mm_per_hr", "rainfall_duration_hr", "realtime_weather_feed_available",
            "sensor_id", "satellite_insar_deformation_rate_mm_yr",
            "drainage_control_structure_present", "retaining_structure_present",
            "community_driven_eng_solution_notes",
        ],
        "has_coordinates": False,
        "used_for_ml_features": False,
        "used_for": "exposure/impact-assessment context only",
    }
