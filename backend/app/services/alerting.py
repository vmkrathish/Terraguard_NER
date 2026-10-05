"""
Alert creation + FCM-style dispatch. Works fully without production FCM
credentials via the alert-history/testing interface (notification_history
rows are still created, with status 'simulated').
"""
import datetime as dt
from typing import Optional

from app.core.config import get_settings
from app.core.excel_store import Store, clean_value

settings = get_settings()


def create_alert(
    store: Store,
    alert_type: str,
    severity: str,
    reason: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    state: Optional[str] = None,
    district: Optional[str] = None,
    risk_score: Optional[float] = None,
    affected_area: Optional[str] = None,
    recommended_action: Optional[str] = None,
    risk_zone_id: Optional[int] = None,
) -> dict:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    alert = store.insert("alerts", {
        "alert_type": alert_type,
        "severity": severity,
        "latitude": latitude,
        "longitude": longitude,
        "state": state,
        "district": district,
        "risk_score": risk_score,
        "reason": reason,
        "affected_area": affected_area,
        "recommended_action": recommended_action,
        "status": "active" if alert_type != "test" else "test",
        "created_at": now,
        "risk_zone_id": risk_zone_id,
    })

    dispatch_status = "simulated" if not settings.FCM_SERVER_KEY else "sent"
    store.insert("notification_history", {
        "alert_id": alert["id"],
        "channel": "fcm",
        "recipient": "all_subscribed_devices",
        "status": dispatch_status,
        "payload": {
            "title": f"TerraGuard Alert: {alert['severity'].upper()} — {alert['alert_type']}",
            "body": reason,
            "location": {"lat": latitude, "lon": longitude, "state": state, "district": district},
            "recommended_action": recommended_action,
        },
        "sent_at": None,
        "created_at": now,
    })
    return {k: clean_value(v) for k, v in alert.items()}
