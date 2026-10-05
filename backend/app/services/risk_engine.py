"""
Risk engine: loads the pre-trained model artifact (never retrains per
request), builds the feature row for a query, returns probability / risk
score / risk level, and produces an explanation (SHAP where reliable, safe
feature-importance fallback otherwise — explanation failure never crashes
prediction).
"""
import json
import math
import os
import warnings
from functools import lru_cache
from typing import Any, Optional

import joblib
import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.core.native_init_lock import NATIVE_INIT_LOCK

settings = get_settings()

NUMERIC_FEATURES = [
    "historical_landslide_count", "historical_landslide_density",
    "rainfall_month_actual_mm", "rainfall_month_climatology_mm",
    "month_sin", "month_cos", "rainfall_departure_pct",
    "spatial_features_available", "rainfall_actual_available",
    "rainfall_climatology_available", "lat_lon_available",
]
CATEGORICAL_FEATURES = ["state"]


class RiskEngineUnavailable(Exception):
    pass


@lru_cache
def _load_artifacts():
    model_path = os.path.join(settings.MODEL_DIR, "risk_model.joblib")
    meta_path = os.path.join(settings.MODEL_DIR, "model_metadata.json")
    if not os.path.exists(model_path):
        raise RiskEngineUnavailable(
            f"Model artifact not found at {model_path}. Run `python scripts/train_model.py` first."
        )
    # See app/core/native_init_lock.py: hold the lock only around the
    # `import xgboost` line — that's the single moment XGBoost's bundled
    # OpenMP runtime actually initializes. joblib.load() itself (which
    # deserializes the pipeline/model — fast, no native re-init once
    # xgboost is already imported) runs outside the lock so a concurrent
    # embedding-model load is never blocked longer than a native import.
    with NATIVE_INIT_LOCK:
        import xgboost  # noqa: F401
    pipe = joblib.load(model_path)
    metadata = {}
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            metadata = json.load(f)
    return pipe, metadata


@lru_cache
def _load_anomaly_artifact():
    """Loads the pre-trained 'Unknown Trigger Hunter' IsolationForest artifact
    (scripts/train_model.py), if present. Returns None (never raises) when
    the artifact is missing — anomaly detection is a bonus signal on top of
    the real risk prediction, and its absence must never break
    /risk/predict."""
    anomaly_path = os.path.join(settings.MODEL_DIR, "anomaly_model.joblib")
    if not os.path.exists(anomaly_path):
        return None
    try:
        return joblib.load(anomaly_path)
    except Exception:  # noqa: BLE001 — bonus signal must never crash prediction
        return None


def score_anomaly(
    rainfall_month_actual_mm: Optional[float],
    rainfall_departure_pct: Optional[float],
    month_sin: Optional[float],
    month_cos: Optional[float],
    historical_landslide_count: Optional[float],
    historical_landslide_density: Optional[float],
) -> Optional[dict]:
    """Live per-query anomaly score from the pre-trained IsolationForest
    artifact. Never retrains; never invents a score. Returns None if the
    artifact isn't available or scoring fails for any reason."""
    artifact = _load_anomaly_artifact()
    if artifact is None:
        return None
    try:
        model = artifact["model"]
        imputer = artifact["imputer"]
        features = artifact["features"]
        values = {
            "rainfall_month_actual_mm": rainfall_month_actual_mm,
            "rainfall_departure_pct": rainfall_departure_pct,
            "month_sin": month_sin,
            "month_cos": month_cos,
            "historical_landslide_count": historical_landslide_count,
            "historical_landslide_density": historical_landslide_density,
        }
        X = pd.DataFrame([{f: values[f] for f in features}])[features]
        X_imputed = imputer.transform(X)
        anomaly_score = -model.score_samples(X_imputed)[0]  # higher = more anomalous, matches training script
        is_anomaly = bool(model.predict(X_imputed)[0] == -1)
        return {
            "is_anomaly": is_anomaly,
            "anomaly_score": round(float(anomaly_score), 4),
            "method": "isolation_forest",
            "note": (
                "Anomaly does not confirm a landslide cause — it flags this combination of "
                "rainfall/historical-activity features as statistically unusual relative to "
                "the training data."
            ),
        }
    except Exception:  # noqa: BLE001 — bonus signal must never crash prediction
        return None


def get_model_metrics() -> dict[str, Any]:
    """Returns the saved evaluation metrics for the currently-selected model
    (from model_metadata.json, written by scripts/train_model.py) — real
    numbers computed on a held-out test set, never invented. Includes
    accuracy/precision/recall/F1/ROC-AUC/PR-AUC (this is a binary
    classifier, so those are the metrics used for model selection) plus
    R²/MAE of predicted probability vs. actual outcome (a probability-
    calibration view, not a substitute for the classification metrics —
    see metrics_note)."""
    _, metadata = _load_artifacts()
    selected = metadata.get("selected_model")
    return {
        "selected_model": selected,
        "metrics": (metadata.get("metrics_by_candidate") or {}).get(selected),
        "metrics_by_candidate": metadata.get("metrics_by_candidate"),
        "metrics_note": metadata.get("metrics_note"),
        "train_rows": metadata.get("train_rows"),
        "test_rows": metadata.get("test_rows"),
        "version": metadata.get("version"),
    }


def risk_level_for_score(score: float) -> str:
    if score <= settings.RISK_LOW_MAX:
        return "LOW"
    if score <= settings.RISK_MODERATE_MAX:
        return "MODERATE"
    if score <= settings.RISK_HIGH_MAX:
        return "HIGH"
    return "CRITICAL"


def build_feature_row(
    state: Optional[str],
    observation_month: Optional[int],
    rainfall_month_actual_mm: Optional[float],
    rainfall_month_climatology_mm: Optional[float] = None,
    historical_landslide_count: Optional[float] = None,
    historical_landslide_density: Optional[float] = None,
    lat_lon_available: bool = True,
) -> pd.DataFrame:
    month = observation_month
    month_sin = math.sin(2 * math.pi * month / 12.0) if month else np.nan
    month_cos = math.cos(2 * math.pi * month / 12.0) if month else np.nan

    departure_pct = np.nan
    if rainfall_month_actual_mm is not None and rainfall_month_climatology_mm:
        departure_pct = (
            (rainfall_month_actual_mm - rainfall_month_climatology_mm)
            / rainfall_month_climatology_mm
            * 100.0
        )

    row = {
        "historical_landslide_count": historical_landslide_count,
        "historical_landslide_density": historical_landslide_density,
        "rainfall_month_actual_mm": rainfall_month_actual_mm,
        "rainfall_month_climatology_mm": rainfall_month_climatology_mm,
        "month_sin": month_sin,
        "month_cos": month_cos,
        "rainfall_departure_pct": departure_pct,
        "spatial_features_available": int(historical_landslide_count is not None),
        "rainfall_actual_available": int(rainfall_month_actual_mm is not None),
        "rainfall_climatology_available": int(rainfall_month_climatology_mm is not None),
        "lat_lon_available": int(lat_lon_available),
        "state": state or "unknown",
    }
    return pd.DataFrame([row])[NUMERIC_FEATURES + CATEGORICAL_FEATURES]


def explain_prediction(pipe, X: pd.DataFrame) -> tuple[list[dict], str]:
    """Returns (contributing_factors, method). Never raises — falls back safely."""
    try:
        import shap

        pre = pipe.named_steps["preprocess"]
        clf = pipe.named_steps["clf"]
        Xt = pre.transform(X)
        if hasattr(Xt, "toarray"):
            Xt = Xt.toarray()
        feature_names = pre.get_feature_names_out()

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            explainer = shap.TreeExplainer(clf)
            shap_values = explainer.shap_values(Xt)

        if isinstance(shap_values, list):  # binary clf may return [class0, class1]
            shap_values = shap_values[-1]
        values = np.asarray(shap_values)[0]

        order = np.argsort(-np.abs(values))[:5]
        factors = [
            {
                "feature": str(feature_names[i]),
                "contribution": float(values[i]),
                "direction": "increases_risk" if values[i] > 0 else "decreases_risk",
            }
            for i in order
        ]
        return factors, "shap"
    except Exception:  # noqa: BLE001 — explanation must never crash prediction
        try:
            clf = pipe.named_steps["clf"]
            pre = pipe.named_steps["preprocess"]
            feature_names = pre.get_feature_names_out()
            importances = getattr(clf, "feature_importances_", None)
            if importances is None:
                return [], "unavailable"
            order = np.argsort(-importances)[:5]
            factors = [
                {
                    "feature": str(feature_names[i]),
                    "contribution": float(importances[i]),
                    "direction": "increases_risk",
                }
                for i in order
            ]
            return factors, "feature_importance_fallback"
        except Exception:  # noqa: BLE001
            return [], "unavailable"


def predict_risk(**kwargs) -> dict[str, Any]:
    pipe, metadata = _load_artifacts()
    X = build_feature_row(**kwargs)
    probability = float(pipe.predict_proba(X)[0, 1])
    risk_score = round(probability * 100, 1)
    risk_level = risk_level_for_score(risk_score)
    factors, method = explain_prediction(pipe, X)

    # Same month_sin/month_cos/departure_pct formulas as build_feature_row()
    # above, recomputed here (rather than threading them back out of
    # build_feature_row) so score_anomaly() can reuse the exact values the
    # main model just saw — smallest diff for wiring in the existing,
    # never-retrained "Unknown Trigger Hunter" IsolationForest artifact.
    month = kwargs.get("observation_month")
    month_sin = math.sin(2 * math.pi * month / 12.0) if month else np.nan
    month_cos = math.cos(2 * math.pi * month / 12.0) if month else np.nan
    rainfall_actual = kwargs.get("rainfall_month_actual_mm")
    rainfall_climatology = kwargs.get("rainfall_month_climatology_mm")
    departure_pct = np.nan
    if rainfall_actual is not None and rainfall_climatology:
        departure_pct = (rainfall_actual - rainfall_climatology) / rainfall_climatology * 100.0

    environmental_anomaly = score_anomaly(
        rainfall_month_actual_mm=rainfall_actual,
        rainfall_departure_pct=departure_pct,
        month_sin=month_sin,
        month_cos=month_cos,
        historical_landslide_count=kwargs.get("historical_landslide_count"),
        historical_landslide_density=kwargs.get("historical_landslide_density"),
    )

    return {
        "probability": round(probability, 4),
        "risk_score": risk_score,
        "risk_level": risk_level,
        "contributing_factors": factors,
        "explainability_method": method,
        "model_version": metadata.get("selected_model", "unknown"),
        "environmental_anomaly": environmental_anomaly,
    }
