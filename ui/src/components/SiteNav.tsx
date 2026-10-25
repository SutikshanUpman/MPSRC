import { Link, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { Logo } from "./Logo";

export function SiteNav() {
  const location = useLocation();
  const path = location.pathname;

  return (
    <header className="marketing-nav">
      <Link className="marketing-brand" to="/" aria-label="Trial of the Nine Realms home">
        <Logo size={30} />
        <span>
          <span className="marketing-brand-kicker">Ragnarok Trial Console</span>
          <strong>Trial of the Nine Realms</strong>
        </span>
      </Link>

      <nav className="marketing-links" aria-label="Public navigation">
        <a className={path === "/" ? "is-active" : ""} href="/#agents">
          The four agents
        </a>
        <a href="/#map">The Runemark map</a>
        <Link className={path === "/how-it-works" ? "is-active" : ""} to="/how-it-works">
          How it works
        </Link>
      </nav>

      <Link className="marketing-cta" to="/app">
        Open the console
      </Link>
    </header>
  );
}

export function MarketingChrome({ children }: { children: ReactNode }) {
  return (
    <div className="marketing-shell">
      <SiteNav />
      <main>{children}</main>
      <footer className="marketing-footer">
        <span className="mono">Trial of the Nine Realms · Runemark pack</span>
        <span>Every number traces to a document. A gap is shown as a gap.</span>
      </footer>
    </div>
  );
}
