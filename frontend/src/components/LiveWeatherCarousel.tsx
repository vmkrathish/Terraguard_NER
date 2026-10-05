import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { LiveWeatherResponse, LiveWeatherState } from "../types";

// How long each state stays on screen before advancing — the user asked
// for "2 to 2.5 seconds", so we land in the middle of that window.
const ROTATE_MS = 2200;
// Live conditions go stale fast; re-poll the backend well inside its own
// 15-minute cache window so this never hammers Open-Meteo, but still
// reflects a fresh fetch each dashboard visit.
const REFRESH_MS = 5 * 60 * 1000;

const CATEGORY_ICON: Record<string, string> = {
  clear: "☀️",
  cloudy: "☁️",
  fog: "🌫️",
  rain: "🌧️",
  storm: "⛈️",
  snow: "❄️",
};

function outlookLine(entry: LiveWeatherState): string {
  const category = entry.condition_category;
  if (category === "rain" || category === "storm") {
    const total = entry.precipitation_sum_today_mm;
    if (total !== undefined && total !== null) {
      return total > 0.1
        ? `Rainfall expected today: ~${total.toFixed(1)} mm`
        : "Rain nearby, but little accumulation expected today";
    }
    return "Rain in the forecast for today";
  }
  // Sunny/clear/cloudy — describe the heat outlook instead.
  const high = entry.temperature_max_today_c;
  const now = entry.temperature_c;
  if (high !== undefined && high !== null && now !== undefined && now !== null) {
    if (high - now > 0.5) {
      return `Expected to warm up to ~${high.toFixed(1)}°C later today`;
    }
    return `Today's high: ~${high.toFixed(1)}°C`;
  }
  return "No further outlook available";
}

export default function LiveWeatherCarousel() {
  const [states, setStates] = useState<LiveWeatherState[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const indexRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      api
        .get<LiveWeatherResponse>("/weather/live-states")
        .then((res) => {
          if (cancelled) return;
          setStates(res.data.states);
          setError(null);
        })
        .catch((e) => {
          if (cancelled) return;
          setError(e.message || "Could not reach the weather service");
        });
    };
    load();
    const refreshTimer = window.setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(refreshTimer);
    };
  }, []);

  useEffect(() => {
    if (!states || states.length === 0) return;
    const rotateTimer = window.setInterval(() => {
      indexRef.current = (indexRef.current + 1) % states.length;
      setActiveIndex(indexRef.current);
    }, ROTATE_MS);
    return () => window.clearInterval(rotateTimer);
  }, [states]);

  return (
    <div className="card admin-panel-card live-weather-widget">
      <h3>Live weather — North-East states</h3>

      {error && !states && <p className="table-empty">Weather service unavailable right now: {error}</p>}
      {!error && !states && <p className="table-empty">Loading live weather…</p>}

      {states && states.length > 0 && (
        <>
          {(() => {
            const entry = states[activeIndex % states.length];
            const category = entry.condition_category;
            const icon = category ? CATEGORY_ICON[category] : "❓";
            return (
              <div key={entry.state} className={`weather-carousel-frame weather-cat-${category || "unknown"}`}>
                <div className="weather-carousel-header">
                  <span className="weather-carousel-icon" aria-hidden="true">
                    {icon}
                  </span>
                  <div>
                    <div className="weather-carousel-state">{entry.state}</div>
                    <div className="weather-carousel-city">{entry.city}</div>
                  </div>
                </div>

                {entry.status === "ok" ? (
                  <>
                    <div className="weather-carousel-body">
                      <div className="weather-carousel-temp">
                        {entry.temperature_c !== undefined ? `${entry.temperature_c.toFixed(1)}°C` : "—"}
                      </div>
                      <div className="weather-carousel-condition">{entry.condition_label}</div>
                    </div>
                    <div className="weather-carousel-outlook">{outlookLine(entry)}</div>
                  </>
                ) : (
                  <p className="table-empty">{entry.message || "Live data unavailable for this state right now."}</p>
                )}

                {/* per-state category animation, CSS-only — see index.css .weather-cat-* rules */}
                {category === "rain" && (
                  <div className="weather-anim weather-anim-rain" aria-hidden="true">
                    {Array.from({ length: 8 }).map((_, i) => (
                      <span key={i} className="rain-drop" style={{ animationDelay: `${i * 0.12}s`, left: `${i * 12 + 4}%` }} />
                    ))}
                  </div>
                )}
                {category === "clear" && <div className="weather-anim weather-anim-sun" aria-hidden="true" />}
                {category === "storm" && <div className="weather-anim weather-anim-storm" aria-hidden="true" />}
              </div>
            );
          })()}

          <div className="weather-carousel-dots">
            {states.map((s, i) => (
              <span key={s.state} className={`weather-carousel-dot ${i === activeIndex % states.length ? "active" : ""}`} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
