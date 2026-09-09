// The bracketed text action the demo room uses. It only intercepts plain
// left clicks, so cmd/ctrl/middle clicks open in a new tab like any link.
import { plainClick } from "../../reader/util.js";

export function BracketLink({ href, children, onClick, className = "", ariaLabel }) {
  const external = /^https?:/.test(href || "");
  return (
    <a className={`blink ${className}`} href={href}
       onClick={onClick ? (e) => { if (plainClick(e)) onClick(e); } : undefined}
       target={external ? "_blank" : undefined}
       rel={external ? "noreferrer" : undefined}
       aria-label={ariaLabel}>
      [ {children} ]{external ? <span className="sr-only"> (opens in a new tab)</span> : null}
    </a>
  );
}
