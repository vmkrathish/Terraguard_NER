const CHECKLIST_ITEMS = [
  "Checking distance",
  "Evaluating risk exposure",
  "Checking blocked roads",
  "Applying emergency constraints",
];

/** Shown only while the single real `/route/optimize` request is in flight
 * (controlled entirely by the `loading` prop — this component holds no
 * timer of its own). Each row's appearance is staggered purely with a CSS
 * transition-delay for visual polish; the whole checklist unmounts the
 * instant the real response (or error) arrives, never waiting on an
 * artificial timer. */
export default function AnalyzingChecklist() {
  return (
    <ul className="route-checklist" aria-label="Route calculation in progress">
      {CHECKLIST_ITEMS.map((item, i) => (
        <li key={item} className="route-checklist-item" style={{ transitionDelay: `${i * 90}ms` }}>
          <span className="route-checklist-spinner" aria-hidden="true" />
          {item}
        </li>
      ))}
    </ul>
  );
}
