// The demo room (?view=demo): pick a reader to look through. Each persona is
// a synthetic run of weekly issues built from a hand-authored catalog of real
// records, with modelled listening statistics and no Spotify anything. It is
// the room for UX testing, demos and screenshots; ?clean=1 drops the badge
// from every view for capture. Capture mode is authoring tooling, so it is
// only offered when the app is not built as the public site.

import { useState } from "react";
import { BracketLink } from "./links.jsx";
import { fdate, fmt } from "../../reader/util.js";

function Thumb({ src }) {
  const [dead, setDead] = useState(false);
  if (dead) return <span className="dr-thumb dr-thumb--none" aria-hidden="true" />;
  return <img className="dr-thumb" src={src} alt="" loading="lazy" decoding="async"
              onError={() => setDead(true)} />;
}

function Card({ p, current, onOpen, clean }) {
  const q = (extra) => `?demo=${p.slug}${extra}${clean ? "&clean=1" : ""}`;
  return (
    <article className={"dr-card" + (current === p.slug ? " is-on" : "")}>
      <div className="dr-covers" aria-hidden="true">
        {(p.covers || []).map((c) => <Thumb key={c} src={c} />)}
      </div>
      <div className="dr-body">
        <h2 className="dr-name">
          {p.name}
          {current === p.slug ? <span className="dr-now">in view</span> : null}
        </h2>
        <p className="dr-persona">{p.persona}</p>
        <p className="dr-blurb">{p.blurb}</p>
        <p className="dr-stats">
          {p.issues} issues · {fdate(p.first_date, { year: false })} to {fdate(p.last_date)}
          {p.history ? <> · {fmt(p.history.plays)} plays, {fmt(Math.round(p.history.hours))} hours since {p.history.since}</> : null}
        </p>
        <p className="dr-lanes">
          {(p.lanes || []).map((l) => (
            <span key={l.id} className="dr-lane" style={{ "--lh": l.hue }} title={`${l.name} (${l.state})`}>
              <i aria-hidden="true" />{l.name}
            </span>
          ))}
        </p>
        {p.latest ? <p className="dr-latest">Latest: {p.latest.title}</p> : null}
        <p className="act">
          <BracketLink href={q("")} onClick={(e) => { e.preventDefault(); onOpen(p.slug); }}>
            Read as {p.name}
          </BracketLink>
          <BracketLink href={q("&view=archive")}>Archive</BracketLink>
          <BracketLink href={q("&view=archive&mode=list")}>List</BracketLink>
        </p>
      </div>
    </article>
  );
}

export default function DemoRoom({ manifest, current, onOpen, onExit, tools = true,
                                   exitLabel = "Back to the live reader", exitHref = "?" }) {
  const personas = (manifest && manifest.personas) || [];
  const [clean, setClean] = useState(false);
  return (
    <section className="demo-room">
      <div className="archive-head">
        <h1 className="archive-title">Demo room</h1>
        <span className="archive-meta">{personas.length} persona{personas.length === 1 ? "" : "s"}</span>
      </div>
      <p className="dr-intro">
        Synthetic readers, each with months of weekly issues, for testing the app and
        showing what it does. Every record in them is real; every listening statistic is
        modelled; no playlist was ever created. Pick one and the whole app reads as that
        person, archive and lane pages included.
      </p>
      {tools ? (
        <p className="dr-switches">
          <button className={"dr-toggle" + (clean ? " is-on" : "")} onClick={() => setClean(!clean)}
                  aria-pressed={clean}>
            {clean ? "[ Capture mode on ]" : "[ Capture mode off ]"}
          </button>
          <span className="dr-hint">
            Capture mode hides the persona badge, for screenshots and video.
          </span>
        </p>
      ) : null}

      {personas.length === 0 ? (
        <p className="archive-empty">
          No personas have been built yet. Run demo/build_demo.py --all to press them.
        </p>
      ) : (
        <div className="dr-grid">
          {personas.map((p) => (
            <Card key={p.slug} p={p} current={current} clean={clean}
                  onOpen={(slug) => onOpen(slug, clean)} />
          ))}
        </div>
      )}

      <p className="act dr-exit">
        <BracketLink href={exitHref} onClick={(e) => { e.preventDefault(); onExit(); }}>
          {exitLabel}
        </BracketLink>
      </p>
    </section>
  );
}
