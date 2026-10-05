import { useEffect, useRef, useState, type ReactNode } from "react";
import logo from "../../assets/logo-icon.png";

export default function AuthLayout({ children }: { children: ReactNode }) {
  const pageOneRef = useRef<HTMLElement>(null);
  const pageTwoRef = useRef<HTMLElement>(null);
  const pageThreeRef = useRef<HTMLElement>(null);
  const [activePage, setActivePage] = useState(1);
  const [automaticTransitionPaused, setAutomaticTransitionPaused] = useState(false);

  useEffect(() => {
    const pages = [pageOneRef.current, pageTwoRef.current, pageThreeRef.current].filter(Boolean) as HTMLElement[];
    const observer = new IntersectionObserver(
      (entries) => {
        const visiblePage = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visiblePage) setActivePage(Number(visiblePage.target.getAttribute("data-page")));
      },
      { threshold: [0.55, 0.75] },
    );

    pages.forEach((page) => observer.observe(page));
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (automaticTransitionPaused || (activePage !== 1 && activePage !== 2)) return;
    const timer = window.setTimeout(() => goTo(activePage + 1), 2000);
    return () => window.clearTimeout(timer);
  }, [activePage, automaticTransitionPaused]);

  function goTo(page: number) {
    const target = [pageOneRef.current, pageTwoRef.current, pageThreeRef.current][page - 1];
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="auth-experience">
      <section
        ref={pageOneRef}
        data-page="1"
        className="auth-screen auth-screen-hero"
        onClick={() => goTo(2)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") goTo(2);
        }}
        role="button"
        tabIndex={0}
        aria-label="Continue to the next page"
      >
        <div className="auth-hero">
          <div className="hero-content-group">
            <div className="hero-brand">
              <img src={logo} alt="TerraGuard NER" />
              <strong>
                Terra<span>Guard</span> NER
              </strong>
            </div>

            <div className="hero-copy">
              <span className="hero-tag">MONITOR · PREDICT · PROTECT</span>
              <h2>Landslide early warning for North East India.</h2>
              <p>
                Predict risk, detect rainfall shocks, trace chain-reaction impact on roads and
                villages, and coordinate field response — all in one console built on real
                historical data for the NER region.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section
        ref={pageTwoRef}
        data-page="2"
        className="auth-screen auth-screen-terrain"
        onClick={() => goTo(3)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") goTo(3);
        }}
        role="button"
        tabIndex={0}
        aria-label="Continue to login"
      >
        <div className="terrain-content">
          <span className="hero-tag">TERRAGUARD NER · FIELD INTELLIGENCE</span>
          <h2>See the terrain before it moves.</h2>
          <p>Understand changing risk, rainfall shocks, and landslide signals before they become an emergency.</p>
        </div>
      </section>

      <section ref={pageThreeRef} data-page="3" className="auth-screen auth-screen-login">
        <div className="auth-panel">
          <div className="auth-card">
            <div className="mobile-brand">
              <img src={logo} alt="TerraGuard NER" />
              <strong>
                Terra<span>Guard</span> NER
              </strong>
            </div>
            {children}
          </div>
        </div>
        <button
          className="auth-back-top"
          onClick={(event) => {
            event.stopPropagation();
            setAutomaticTransitionPaused(true);
            goTo(1);
          }}
        >
          Back to Top ↑
        </button>
      </section>

    </div>
  );
}
