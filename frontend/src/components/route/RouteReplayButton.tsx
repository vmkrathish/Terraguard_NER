/** Route Replay (spec section 17) — re-reveals the same already-calculated
 * polyline from source to destination. This is a re-reveal only: it never
 * implies live vehicle movement, and clicking it simply bumps the parent's
 * `replayToken`, which `RouteMap`'s existing reveal animation (also used on
 * first render) restarts. No separate animation loop is created or left
 * running here. */
export default function RouteReplayButton({ onReplay }: { onReplay: () => void }) {
  return (
    <button type="button" className="btn btn-ghost route-replay-btn" onClick={onReplay}>
      ↻ Replay route animation
    </button>
  );
}
