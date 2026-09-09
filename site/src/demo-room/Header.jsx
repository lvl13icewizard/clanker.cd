// The header is a zone, not a bar: liquid glass that fades out. Two
// masked backdrop-filter layers (blur + saturation lift, strongest at the
// top, gone by the bottom) under a frosted white tint that fades with
// them, so content dissolves into bright glass as it scrolls under rather
// than smearing grey. The only chrome is the brand: the clanker's head
// and the wordmark, one click back to the front door, the same on every
// page. In a demo, a quiet pair on the right: the persona's name leads to
// the picker, and [ Leave ] drops the demo for the front door. ?clean=1
// removes both.

import { plainClick } from "../../reader/util.js";

export default function Header({ onHome, badge }) {
  return (
    <header className="mast">
      <span className="mast-blur b1" aria-hidden="true" />
      <span className="mast-blur b2" aria-hidden="true" />
      <span className="mast-tint" aria-hidden="true" />
      <a className="mast-brand" href="?" aria-label="clanker.cd home"
         onClick={(e) => { if (!plainClick(e) || !onHome) return; e.preventDefault(); onHome(e); }}>
        <img src="/brand/head-96.png" alt="" width="96" height="96" />
        <span>clanker.cd</span>
      </a>
      {badge ? (
        <span className="mast-demo">
          <a className="mast-badge" href={badge.href} title={badge.title}
             onClick={(e) => { if (!plainClick(e)) return; e.preventDefault(); badge.onClick(e); }}>
            <span className="mb-dot" aria-hidden="true" />
            <span className="mb-name">{badge.label}</span>
            <span className="mb-tag">demo</span>
          </a>
          <a className="mast-leave" href={badge.leaveHref} title="Leave the demo"
             onClick={(e) => { if (!plainClick(e)) return; e.preventDefault(); badge.onLeave(e); }}>
            [ Leave ]
          </a>
        </span>
      ) : null}
    </header>
  );
}
