import datetime as dt
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from app.core.excel_store import Store, clean_records, get_store
from app.services import geo_utils
from app.services.chain_reaction import analyze_chain_reaction
from app.services.rainfall_shock import get_climatology
from app.services.risk_engine import RiskEngineUnavailable, get_model_metrics, predict_risk
from app.schemas.schemas import (
    RiskPredictRequest,
    RiskPredictResponse,
    RiskWhatIfRequest,
    RiskWhatIfResponse,
)

router = APIRouter(tags=["risk"])


def _nearby_historical_stats(store: Store, lat: float, lon: float, radius_m: float = 20000):
    df = store.df("landslide_events")
    if df.empty:
        return 0, 0.0
    nearby = geo_utils.within_radius(df, lat, lon, radius_m)
    count = len(nearby)
    density = count / (3.14159 * (radius_m / 1000) ** 2) if count else 0.0
    return count, density


@router.get("/risk/model-metrics")
def model_metrics():
    """Real evaluation metrics for the currently-loaded risk model, computed
    on a held-out test set by scripts/train_model.py — never invented."""
    try:
        return get_model_metrics()
    except RiskEngineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/risk")
def list_recent_risk_predictions(limit: int = 20, store: Store = Depends(get_store)):
    df = store.df("risk_predictions").sort_values("created_at", ascending=False, na_position="last").head(limit)
    cols = ["id", "latitude", "longitude", "state", "district", "probability", "risk_score",
            "risk_level", "model_version", "created_at"]
    records = clean_records(df[cols].to_dict("records")) if not df.empty else []
    return {"predictions": records}


@router.post("/risk/predict", response_model=RiskPredictResponse)
def predict(payload: RiskPredictRequest, store: Store = Depends(get_store)):
    hist_count, hist_density = _nearby_historical_stats(store, payload.latitude, payload.longitude)

    climatology = None
    if payload.state and payload.observation_month:
        climatology = get_climatology(store, payload.state, payload.district, payload.observation_month)

    try:
        result = predict_risk(
            state=payload.state,
            observation_month=payload.observation_month,
            rainfall_month_actual_mm=payload.rainfall_month_actual_mm,
            rainfall_month_climatology_mm=climatology,
            historical_landslide_count=hist_count,
            historical_landslide_density=hist_density,
            lat_lon_available=True,
        )
    except RiskEngineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    store.insert("risk_predictions", {
        "latitude": payload.latitude, "longitude": payload.longitude,
        "state": payload.state, "district": payload.district,
        "probability": result["probability"], "risk_score": result["risk_score"],
        "risk_level": result["risk_level"],
        "contributing_factors": result["contributing_factors"],
        "rainfall_context": {
            "rainfall_month_actual_mm": payload.rainfall_month_actual_mm,
            "rainfall_month_climatology_mm": climatology,
        },
        "model_version": result["model_version"],
        "requested_by": None,
        "created_at": now,
    })

    # A prediction was, until now, only ever written to risk_predictions —
    # the GIS Map (and route optimizer) only read risk_zones, so a new
    # HIGH/CRITICAL prediction never actually appeared anywhere else in the
    # app. Surfacing it as a real risk_zone (tagged data_provenance='derived')
    # is what makes "check a new location, see it reflected on the map"
    # actually true. LOW/MODERATE predictions are not persisted as zones.
    if result["risk_level"] in ("HIGH", "CRITICAL"):
        store.insert("risk_zones", {
            "name": f"Predicted {result['risk_level'].title()} zone"
            + (f" ({payload.district or payload.state})" if (payload.district or payload.state) else ""),
            "state": payload.state, "district": payload.district,
            "latitude": payload.latitude, "longitude": payload.longitude,
            "radius_m": 5000, "risk_score": result["risk_score"], "risk_level": result["risk_level"],
            "data_provenance": "derived", "updated_at": now,
        })

    try:
        chain_reaction = analyze_chain_reaction(store, payload.latitude, payload.longitude)
    except Exception:  # noqa: BLE001 — chain-reaction lookup must never break prediction
        chain_reaction = None

    return RiskPredictResponse(
        probability=result["probability"],
        risk_score=result["risk_score"],
        risk_level=result["risk_level"],
        contributing_factors=result["contributing_factors"],
        explainability_method=result["explainability_method"],
        rainfall_context={
            "rainfall_month_actual_mm": payload.rainfall_month_actual_mm,
            "rainfall_month_climatology_mm": climatology,
            "historical_landslide_count_20km": hist_count,
        },
        model_version=result["model_version"],
        disclaimer=(
            "This is a modelled estimate based on historical data and configurable thresholds; "
            "risk levels are not scientifically validated boundaries and should support, not replace, "
            "official disaster-management judgment."
        ),
        chain_reaction_impact=chain_reaction,
        environmental_anomaly=result.get("environmental_anomaly"),
    )


@router.post("/risk/predict/what-if", response_model=RiskWhatIfResponse)
def predict_what_if(payload: RiskWhatIfRequest, store: Store = Depends(get_store)):
    """Pure read-only what-if computation — reuses the exact same
    predict_risk() model/code path as /risk/predict, called twice (actual
    rainfall, then scenario rainfall), but NEVER writes to `risk_predictions`
    or `risk_zones`. Mirrors the existing /alerts/simulate precedent
    (app/services/alert_intelligence.py::simulate_scenario)."""
    hist_count, hist_density = _nearby_historical_stats(store, payload.latitude, payload.longitude)

    climatology = None
    if payload.state and payload.observation_month:
        climatology = get_climatology(store, payload.state, payload.district, payload.observation_month)

    try:
        chain_reaction = analyze_chain_reaction(store, payload.latitude, payload.longitude)
    except Exception:  # noqa: BLE001 — chain-reaction lookup must never break prediction
        chain_reaction = None

    disclaimer = (
        "This is a modelled estimate based on historical data and configurable thresholds; "
        "risk levels are not scientifically validated boundaries and should support, not replace, "
        "official disaster-management judgment."
    )

    def _run(rainfall_value: Optional[float]) -> RiskPredictResponse:
        try:
            result = predict_risk(
                state=payload.state,
                observation_month=payload.observation_month,
                rainfall_month_actual_mm=rainfall_value,
                rainfall_month_climatology_mm=climatology,
                historical_landslide_count=hist_count,
                historical_landslide_density=hist_density,
                lat_lon_available=True,
            )
        except RiskEngineUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return RiskPredictResponse(
            probability=result["probability"],
            risk_score=result["risk_score"],
            risk_level=result["risk_level"],
            contributing_factors=result["contributing_factors"],
            explainability_method=result["explainability_method"],
            rainfall_context={
                "rainfall_month_actual_mm": rainfall_value,
                "rainfall_month_climatology_mm": climatology,
                "historical_landslide_count_20km": hist_count,
            },
            model_version=result["model_version"],
            disclaimer=disclaimer,
            chain_reaction_impact=chain_reaction,
            environmental_anomaly=result.get("environmental_anomaly"),
        )

    baseline = _run(payload.rainfall_month_actual_mm)
    scenario = _run(payload.rainfall_month_actual_mm_scenario)

    rainfall_change_pct = None
    if payload.rainfall_month_actual_mm is not None and payload.rainfall_month_actual_mm:
        rainfall_change_pct = (
            (payload.rainfall_month_actual_mm_scenario - payload.rainfall_month_actual_mm)
            / payload.rainfall_month_actual_mm
            * 100.0
        )

    return RiskWhatIfResponse(
        baseline=baseline,
        scenario=scenario,
        rainfall_change_pct=rainfall_change_pct,
        risk_score_change=scenario.risk_score - baseline.risk_score,
    )
