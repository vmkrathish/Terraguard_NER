"""
AI-assisted visual assessment for field-report photos.

This is a lightweight, fully local heuristic (edge density / dark-region
ratio via Pillow) used as the default so the app works without any external
vision API key. It never claims to predict exact failure time — outputs are
always labelled "AI-assisted visual assessment", a coarse signal for a human
reviewer, not a verdict. If external vision AI is unavailable or the image
can't be processed, the app continues functioning and returns a
"not_available" result rather than crashing.
"""
from typing import Any

from PIL import Image, ImageFilter


def analyze_photo(image_path: str, incident_type: str) -> dict[str, Any]:
    try:
        img = Image.open(image_path).convert("L")
        img = img.resize((256, 256))
        edges = img.filter(ImageFilter.FIND_EDGES)
        edge_pixels = list(edges.getdata())
        edge_density = sum(1 for p in edge_pixels if p > 60) / len(edge_pixels)

        dark_pixels = list(img.getdata())
        dark_ratio = sum(1 for p in dark_pixels if p < 70) / len(dark_pixels)

        indicators = []
        if incident_type in ("crack", "slope_movement", "landslide"):
            if edge_density > 0.18:
                indicators.append("high linear-edge density consistent with visible cracking/fissures")
        if incident_type in ("debris", "landslide", "blocked_road"):
            if dark_ratio > 0.35:
                indicators.append("large irregular dark regions consistent with debris/soil deposits")
        if not indicators:
            indicators.append("no strong visual indicators detected by the heuristic model")

        confidence = "low"  # this heuristic is intentionally conservative
        return {
            "status": "ok",
            "label": "AI-assisted visual assessment",
            "incident_type_context": incident_type,
            "indicators": indicators,
            "edge_density": round(edge_density, 3),
            "dark_region_ratio": round(dark_ratio, 3),
            "confidence": confidence,
            "disclaimer": (
                "This is an automated, coarse visual heuristic for triage support only. "
                "It cannot and does not predict exact failure timing, and must not replace "
                "human field assessment."
            ),
        }
    except Exception as exc:  # noqa: BLE001 — must never crash report submission
        return {
            "status": "not_available",
            "label": "AI-assisted visual assessment",
            "message": f"Photo analysis unavailable: {exc}",
        }
