import React, { useEffect, useRef, useState } from "react";
import {
  displayTitle as title,
  fdate,
  pad,
  issueCover,
  spotifyUrl,
  spotifyId,
  MODULE_NAMES as names,
  LANES,
} from "./util.js";

const descriptions = {
  singles_rack: "New names, familiar connections.",
  front_to_back: "One record. All the way through.",
  the_mix: "Let someone else take the controls.",
  revival_desk: "The songs you left behind.",
  critics_desk: "Acclaimed records still waiting for you.",
  catalog_room: "Further into an artist you already love.",
  new_this_week: "The next arrivals in your orbit.",
  ledger: "What actually made it into your week.",
};
// One reader, two datasets. The personal build reads /issues as its owner's
// edition; the public site reads /demo/<slug> as a persona's, and the slug
// rides on every link so the whole app stays inside that persona.
const demoSlug = () => new URLSearchParams(location.search).get("demo");
const isClean = () => new URLSearchParams(location.search).get("clean") === "1";
const carry = () => {
  const d = demoSlug();
  const c = isClean() ? "&clean=1" : "";
  return (d ? `&demo=${encodeURIComponent(d)}` : "") + c;
};
const link = (view, extra = "") => `?view=${view}${extra}${carry()}`;
const baseFor = () => (demoSlug() ? `/demo/${demoSlug()}` : "/issues");
const readRoute = () => {
  const p = new URLSearchParams(location.search);
  let view = p.get("view") || (p.has("n") ? "issue" : "home");
  if (view === "lane") view = "lanes"; // the first reader's spelling
  return { view, n: Number(p.get("n")) || null, lane: p.get("lane") };
};
const hrefIssue = (issue, hash = "") =>
  `?view=issue&n=${issue.issue}${carry()}${hash}`;
const WORDS = [
  "zero",
  "one",
  "two",
  "three",
  "four",
  "five",
  "six",
  "seven",
  "eight",
  "nine",
  "ten",
  "eleven",
  "twelve",
  "thirteen",
  "fourteen",
  "fifteen",
  "sixteen",
  "seventeen",
  "eighteen",
  "nineteen",
  "twenty",
];
const words = (n) =>
  Number.isInteger(n) && n >= 0 && n <= 20 ? WORDS[n] : String(n);
const external = { target: "_blank", rel: "noreferrer" };
// Spotify links go to the desktop app first. A plain click hands the
// spotify: URI to the OS; if nothing takes it within a moment (no app
// installed, or the scheme blocked) the web player opens in a new tab
// instead. Modified clicks and middle clicks stay ordinary links.
const APP_WAIT_MS = 1400;
const spotifyKind = (url) =>
  (/open\.spotify\.com\/(track|album|playlist|artist)\//.exec(url || "") ||
    [])[1];

/** The desk's row of issues. Scrolls sideways once the collection outgrows
 *  the desk, with a chevron at whichever edge has more behind it. */
function Shelf({ selected, children }) {
  const ref = useRef(null);
  const [edges, setEdges] = useState({ left: false, right: false });
  const measure = () => {
    const el = ref.current;
    if (!el) return;
    const max = el.scrollWidth - el.clientWidth;
    setEdges({ left: el.scrollLeft > 2, right: el.scrollLeft < max - 2 });
  };
  useEffect(() => {
    measure();
    const el = ref.current;
    if (!el) return undefined;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    el.addEventListener("scroll", measure, { passive: true });
    return () => { ro.disconnect(); el.removeEventListener("scroll", measure); };
  }, [children]);
  useEffect(() => {
    const el = ref.current;
    const hit = el?.querySelector(`[data-issue="${selected}"]`);
    if (hit) hit.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
  }, [selected]);
  const nudge = (dir) => ref.current?.scrollBy({ left: dir * ref.current.clientWidth * 0.6, behavior: "smooth" });
  return (
    <div className={`shelf-scroller${edges.left ? " has-left" : ""}${edges.right ? " has-right" : ""}`}>
      <button type="button" className="shelf-edge left" aria-label="Earlier issues" onClick={() => nudge(-1)} tabIndex={edges.left ? 0 : -1}>
        <svg viewBox="0 0 12 20" aria-hidden="true"><path d="M10 2 2 10l8 8" /></svg>
      </button>
      <div className="mini-shelf" aria-label="Choose an issue" ref={ref}>{children}</div>
      <button type="button" className="shelf-edge right" aria-label="Later issues" onClick={() => nudge(1)} tabIndex={edges.right ? 0 : -1}>
        <svg viewBox="0 0 12 20" aria-hidden="true"><path d="m2 2 8 8-8 8" /></svg>
      </button>
    </div>
  );
}

function spotifyProps(href) {
  const kind = spotifyKind(href);
  const id = kind && spotifyId(href);
  if (!id) return { href, ...external };
  const app = `spotify:${kind}:${id}`;
  const onClick = (e) => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey)
      return;
    e.preventDefault();
    const t = setTimeout(
      () => window.open(href, "_blank", "noopener"),
      APP_WAIT_MS,
    );
    const taken = () => clearTimeout(t);
    document.addEventListener(
      "visibilitychange",
      () => {
        if (document.hidden) taken();
      },
      { once: true },
    );
    window.addEventListener("blur", taken, { once: true });
    window.location.assign(app);
  };
  return { href, ...external, onClick, title: "Opens the Spotify app" };
}
const getSaved = (key) => {
  try {
    return localStorage.getItem(`reader-concept:${key}`);
  } catch {
    return null;
  }
};
const save = (key, value) => {
  try {
    localStorage.setItem(`reader-concept:${key}`, value);
  } catch {
    /* Reading works without storage. */
  }
};
function Icon({ name = "arrow", size = 18 }) {
  const paths = {
    arrow: "M4 12h16m-6-6 6 6-6 6",
    external: "M7 17 17 7M7 7h10v10",
    play: "m8 5 11 7-11 7Z",
    close: "m6 6 12 12M6 18 18 6",
    headphones:
      "M4 14v-3a8 8 0 0 1 16 0v3M4 12h3v8H4a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2Zm16 0h-3v8h3a2 2 0 0 0 2-2v-4a2 2 0 0 0-2-2Z",
    book: "M3 4h7l2 2 2-2h7v15h-7l-2 2-2-2H3ZM12 6v15",
    search: "M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] || paths.arrow} />
    </svg>
  );
}
function Art({ src, label = "", className = "" }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  return (
    <div className={`art ${className}`}>
      {src && !failed ? (
        <img
          src={src}
          alt={label}
          loading="lazy"
          onError={() => setFailed(true)}
        />
      ) : (
        <div className="art-fallback">
          <span className="record-ring" />
          <span>{label || "clanker.cd"}</span>
        </div>
      )}
    </div>
  );
}
function Cover({ issue, plain = false }) {
  return (
    <Art
      src={issueCover(issue, plain ? "plain" : "text")}
      label={`${title(issue)} — Issue ${pad(issue.issue)}`}
    />
  );
}
function Pill({ children, href, onClick, active }) {
  return href ? (
    <a
      className={`pill ${active ? "active" : ""}`}
      href={href}
      onClick={onClick}
    >
      {children}
    </a>
  ) : (
    <button
      className={`pill ${active ? "active" : ""}`}
      onClick={onClick}
      aria-pressed={active}
    >
      {children}
    </button>
  );
}
// A mix can mirror to several players; say which one each link opens.
function listenLabel(url) {
  const host = (() => {
    try {
      return new URL(url).hostname.replace(/^(www|m)\./, "");
    } catch {
      return "";
    }
  })();
  if (/youtu\.?be/.test(host)) return "Watch on YouTube";
  if (host.endsWith("soundcloud.com")) return "Listen on SoundCloud";
  if (host.endsWith("mixcloud.com")) return "Listen on Mixcloud";
  if (host.endsWith("hearthis.at")) return "Listen on hearthis";
  return "Listen to mix";
}
function LinkOut({ href, children = "Open in Spotify", className = "" }) {
  return href ? (
    <a className={`text-link ${className}`} {...spotifyProps(href)}>
      {children}
      <Icon name="external" size={15} />
    </a>
  ) : null;
}
function Lane({ id, lanes }) {
  const lane = lanes.find((l) => l.id === id);
  return id ? (
    <a
      className="lane-tag"
      href={link("lanes", `&lane=${encodeURIComponent(id)}`)}
    >
      <i style={{ background: `hsl(${LANES[id] || 200} 35% 45%)` }} />
      {lane?.name || id.replaceAll("-", " ")}
    </a>
  ) : null;
}
function Item({ item, lanes, kind = "track", feature = false }) {
  const url = spotifyUrl(item, kind);
  return (
    <article className={`music-entry ${feature ? "feature-entry" : ""}`}>
      <div className="entry-art">
        {url ? (
          <a {...spotifyProps(url)} aria-label={`Listen to ${item.title}`}>
            <Art
              src={item.cover_url}
              label={`${item.artist || item.show || ""} — ${item.title || item.episode || ""}`}
            />
            <span className="art-play">
              <Icon name="play" size={17} />
            </span>
          </a>
        ) : (
          <Art
            src={item.cover_url}
            label={item.artist || item.show || item.title}
          />
        )}
      </div>
      <div className="entry-copy">
        <div className="entry-heading">
          <div className="entry-meta">
            <Lane id={item.cluster} lanes={lanes} />
            {item.score != null && (
              <span className="score">
                {Number(item.score).toFixed(1)} <small>Pitchfork</small>
              </span>
            )}
          </div>
          <h3>{item.artist || item.show}</h3>
          {(item.title || (item.episode && item.episode !== item.show)) && (
            <p className="record-title">
              {item.title || item.episode}
              {item.year && <span className="muted"> ({item.year})</span>}
            </p>
          )}
          {item.plays != null && (
            <p className="small muted">
              {item.plays} {item.plays === 1 ? "play" : "plays"}
              {item.last_played && ` · last ${fdate(item.last_played)}`}
            </p>
          )}
          {item.station && (
            <p className="small muted">
              {item.station}
              {item.date && ` · ${fdate(item.date)}`}
            </p>
          )}
        </div>
        {item.why && <p className="prose">{item.why}</p>}
        {item.critics &&
          Object.entries(item.critics).map(
            ([key, critic]) =>
              critic && (
                <div className="critic-note" key={key}>
                  {critic.dek && <p>“{critic.dek}”</p>}
                  <LinkOut href={critic.url}>
                    {key === "pitchfork" ? "Pitchfork" : "Fantano"}{" "}
                    {critic.score || critic.rating}
                    {critic.bnm ? " · Best New Music" : ""}
                  </LinkOut>
                </div>
              ),
          )}
        <div className="entry-links">
          <LinkOut href={url} />
          {!url && (
            <LinkOut href={item.url}>
              {item.show ? "Open broadcast" : "Read the review"}
            </LinkOut>
          )}
          {(item.listen_urls || []).map((url) => (
            <LinkOut key={url} href={url}>
              {listenLabel(url)}
            </LinkOut>
          ))}
        </div>
      </div>
    </article>
  );
}
function Section({ mod, i, issue, lanes }) {
  let content;
  switch (mod.type) {
    case "front_to_back":
      content = (
        <Item
          feature
          kind="album"
          lanes={lanes}
          item={{
            ...mod.album,
            why: mod.why,
            cluster: mod.cluster,
            critics: mod.critics,
            receipts: mod.receipts,
          }}
        />
      );
      break;
    case "singles_rack":
    case "revival_desk":
      content = (
        <div className={mod.type === "revival_desk" ? "rediscover-list" : ""}>
          {mod.tracks?.map((t, j) => (
            <Item key={j} item={t} lanes={lanes} />
          ))}
        </div>
      );
      break;
    case "critics_desk":
      content = (
        <>
          {mod.albums?.map((a, j) => (
            <Item key={j} item={a} lanes={lanes} kind="album" />
          ))}
        </>
      );
      break;
    case "the_mix":
      content = mod.mixes?.map((m, j) => (
        <Item key={j} item={m} lanes={lanes} />
      ));
      break;
    case "catalog_room":
      content = (
        <>
          <h3 className="catalog-artist">{mod.artist}</h3>
          <p className="prose">{mod.why}</p>
          <div className="catalog-shelf">
            {mod.unheard?.map((a, j) => (
              <div key={j}>
                <Art src={a.cover_url} label={a.title} />
                <h3>{a.title}</h3>
                <p className="small muted">{a.year}</p>
              </div>
            ))}
          </div>
          <p className="small muted">{mod.heard_note}</p>
        </>
      );
      break;
    case "new_this_week":
      content = (
        <>
          {!mod.releases?.length && (
            <p className="muted">No new releases in your orbit this week.</p>
          )}
          <ReleaseRows rows={mod.releases || []} />
          <a className="text-link" href={link("releases")}>
            All releases <Icon />
          </a>
        </>
      );
      break;
    case "ledger":
      content = (
        <>
          <p className="prose">{mod.verdict}</p>
          <div className="ledger-columns">
            {[true, false].map((played) => (
              <div key={String(played)}>
                <h3>
                  {played ? "Made it into rotation" : "Still waiting"}{" "}
                  <span>
                    {mod.rows?.filter((r) => !!r.played === played).length || 0}
                  </span>
                </h3>
                {mod.rows
                  ?.filter((r) => !!r.played === played)
                  .map((r, j) => (
                    <div className="ledger-row" key={j}>
                      <i className={played ? "played" : ""} />
                      <div>
                        {r.label}
                        <p className="small muted">
                          {played
                            ? `${r.plays} ${r.plays === 1 ? "play" : "plays"}`
                            : names[r.module] || r.module}
                        </p>
                      </div>
                    </div>
                  ))}
              </div>
            ))}
          </div>
        </>
      );
      break;
    default:
      content = <p>This section is not supported in this concept yet.</p>;
  }
  return (
    <section className={`issue-section section-${mod.type}`} id={`s${i + 1}`}>
      <header className="section-heading">
        <span>{String(i + 1).padStart(2, "0")}</span>
        <div>
          <h2>{names[mod.type] || mod.type}</h2>
          <p>{descriptions[mod.type]}</p>
        </div>
      </header>
      {mod.intro && <p className="section-intro">{mod.intro}</p>}
      {content}
    </section>
  );
}
function Home({ issues, lanes, who }) {
  const [selected, setSelected] = useState(issues[0].issue);
  const issue = issues.find((i) => i.issue === selected) || issues[0];
  const latest = issues[0];
  const album = latest.modules.find((m) => m.type === "front_to_back")?.album;
  return (
    <>
      <div className="welcome">
        <div>
          <h1>Welcome back, {who.name}.</h1>
        </div>
        <img src="/brand/pose-listen.png" alt="" />
      </div>
      <section className="desk-hero">
        <div className="desk-note">
          <p className="issue-stamp">
            {issue.issue === latest.issue
              ? "Latest issue"
              : `Issue ${pad(issue.issue)}`}
          </p>
          <h2>{title(issue)}</h2>
          <p className="desk-date">{fdate(issue.date, { full: true })}</p>
          <p className="desk-dek">{issue.dek}</p>
          <div className="hero-actions">
            <a className="primary" href={hrefIssue(issue)}>
              Read this issue <Icon />
            </a>
            <LinkOut href={issue.companion_playlist?.spotify_url}>
              Put the playlist on
            </LinkOut>
          </div>
          <p className="small muted hero-foot">
            {issue.modules.length} sections to read ·{" "}
            {issue.companion_playlist?.track_count || 0} tracks to keep you
            company
          </p>
        </div>
        <div className="sleeve-desk">
          <div className="sleeve-stage">
            <div className="desk-disc" />
            <a className="hero-sleeve" href={hrefIssue(issue)}>
              <Cover issue={issue} />
            </a>
          </div>
          <Shelf selected={selected}>
            {issues.map((iss) => (
              <button
                key={iss.issue}
                data-issue={iss.issue}
                aria-label={`Select ${title(iss)}`}
                aria-pressed={selected === iss.issue}
                onClick={() => setSelected(iss.issue)}
              >
                <Cover issue={iss} />
                <span>{pad(iss.issue)}</span>
              </button>
            ))}
          </Shelf>
          <p className="shelf-caption">Your collection, one week at a time.</p>
        </div>
      </section>
      <section className="home-inside">
        <div className="section-top">
          <h2>In this week’s issue</h2>
          <a href={hrefIssue(latest)} className="text-link">
            Read from the beginning <Icon />
          </a>
        </div>
        <div className="inside-grid">
          <a
            href={`${hrefIssue(latest)}#s${latest.modules.findIndex((m) => m.type === "front_to_back") + 1}`}
            className="album-preview"
          >
            <Art src={album?.cover_url} label={album?.title} />
            <div>
              <p className="small muted">Album of the Week</p>
              <h3>{album?.artist}</h3>
              <p>{album?.title}</p>
              <span className="text-link">
                Settle into the record <Icon />
              </span>
            </div>
          </a>
          <div className="contents-preview">
            {latest.modules
              .filter((m) => m.type !== "front_to_back")
              .slice(0, 4)
              .map((m) => (
                <a
                  key={m.type}
                  href={`${hrefIssue(latest)}#s${latest.modules.indexOf(m) + 1}`}
                >
                  <div>
                    <h3>{names[m.type]}</h3>
                    <p>
                      {m.type === "singles_rack"
                        ? m.tracks
                            ?.slice(0, 3)
                            .map((t) => t.artist)
                            .join(", ")
                        : m.type === "catalog_room"
                          ? m.artist
                          : descriptions[m.type]}
                    </p>
                  </div>
                  <Icon />
                </a>
              ))}
          </div>
        </div>
      </section>
      <div className="home-bottom">
        <div>
          <h2>Elsewhere in your listening.</h2>
          <p className="muted">Your lanes, and the records on the way.</p>
        </div>
        <a href={link("lanes")} className="text-link">
          Explore your {lanes.length} lanes <Icon />
        </a>
        <a href={link("releases")} className="text-link">
          See what’s coming <Icon />
        </a>
      </div>
    </>
  );
}
function Reader({ issue, issues, lanes, focus, setFocus }) {
  const [current, setCurrent] = useState("s1");
  const [resume] = useState(() => getSaved(`position:${issue.issue}`));
  useEffect(() => {
    const update = () => {
      const sections = [...document.querySelectorAll(".issue-section")];
      let active = sections[0]?.id;
      sections.forEach((s) => {
        if (s.getBoundingClientRect().top < 180) active = s.id;
      });
      if (active) {
        setCurrent(active);
        if (window.scrollY > 300) save(`position:${issue.issue}`, active);
      }
    };
    window.addEventListener("scroll", update, { passive: true });
    const timer = setTimeout(() => {
      if (location.hash)
        document.getElementById(location.hash.slice(1))?.scrollIntoView();
      update();
    }, 100);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("scroll", update);
    };
  }, [issue]);
  const activeIndex = issue.modules.findIndex(
    (m, i) => `s${i + 1}` === current,
  );
  const next = issues[issues.indexOf(issue) + 1];
  return (
    <>
      <div className="reader-top">
        <a href={link("archive")} className="text-link">
          Collection / Issue {pad(issue.issue)}
        </a>
        <button
          className="text-link"
          onClick={() => setFocus(!focus)}
          aria-pressed={focus}
        >
          <Icon name="book" />
          {focus ? "Exit reading focus" : "Reading focus"}
        </button>
      </div>
      <div className={`reader-layout ${focus ? "focused" : ""}`}>
        <aside className="chapter-rail">
          <p className="small muted">In this issue</p>
          <nav aria-label="Issue contents">
            {issue.modules.map((m, i) => (
              <a
                key={i}
                href={`#s${i + 1}`}
                aria-current={current === `s${i + 1}` ? "location" : undefined}
              >
                <span>{String(i + 1).padStart(2, "0")}</span>
                {names[m.type]}
              </a>
            ))}
          </nav>
          <div className="rail-progress">
            <span
              style={{
                width: `${((activeIndex + 1) / issue.modules.length) * 100}%`,
              }}
            />
          </div>
          <p className="small muted">
            Section {activeIndex + 1} of {issue.modules.length}
          </p>
          <a className="small text-link" href="#issue-title">
            Back to the top ↑
          </a>
        </aside>
        <div className="reading-column">
          <header className="issue-front" id="issue-title">
            <h1>{title(issue)}</h1>
            <p className="issue-dek">{issue.dek}</p>
            {/* The listening rail carries the issue and date, but it is
                hidden under 1000px — this line takes over there. */}
            <p className="issue-date">
              Issue {pad(issue.issue)} · {fdate(issue.date, { full: true })}
            </p>
            {resume && resume !== "s1" && (
              <div className="reading-start">
                <a className="text-link" href={`#${resume}`}>
                  Continue at{" "}
                  {names[issue.modules[Number(resume.slice(1)) - 1]?.type]}{" "}
                  <Icon />
                </a>
              </div>
            )}
          </header>
          {issue.modules.map((m, i) => (
            <Section key={i} mod={m} i={i} issue={issue} lanes={lanes} />
          ))}
          <footer className="issue-end">
            <img src="/brand/head-96.png" alt="" />
            <h2>That’s this week’s pressing.</h2>
            <p className="muted">
              Keep listening. We’ll meet you here for the next one.
            </p>
            <div className="hero-actions">
              <a className="primary" href={link("archive")}>
                Back to your collection <Icon />
              </a>
              {next && (
                <a className="text-link" href={hrefIssue(next)}>
                  Previous issue
                </a>
              )}
            </div>
          </footer>
        </div>
        <aside className="listening-rail">
          <Cover issue={issue} />
          <p className="small muted">
            Issue {pad(issue.issue)} · {fdate(issue.date, { full: true })}
          </p>
          <h3>A soundtrack for the read.</h3>
          <p className="small muted">
            {issue.companion_playlist?.track_count || 0} tracks, in the order of
            the issue.
          </p>
          {issue.companion_playlist?.spotify_url && (
            <a
              className="primary"
              {...spotifyProps(issue.companion_playlist.spotify_url)}
            >
              <Icon name="headphones" />
              Open in Spotify
            </a>
          )}
        </aside>
      </div>
    </>
  );
}
function Archive({ issues }) {
  const [mode, setMode] = useState("shelf");
  const [query, setQuery] = useState("");
  const shown = issues.filter((i) =>
    (i.title + " " + i.dek).toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <>
      <PageHeading
        title="Your collection."
        description="A little further into your taste, every week. All your issues live here."
      />
      <div className="toolbar">
        <p className="muted">{issues.length} issues on the shelf</p>
        <div className="segmented">
          <Pill active={mode === "shelf"} onClick={() => setMode("shelf")}>
            Sleeves
          </Pill>
          <Pill active={mode === "list"} onClick={() => setMode("list")}>
            List
          </Pill>
        </div>
        <Search value={query} onChange={setQuery} placeholder="Find an issue" />
      </div>
      <div className={`archive-${mode}`}>
        {shown.map((iss) => (
          <a className="archive-item" key={iss.issue} href={hrefIssue(iss)}>
            <div className="archive-art">
              <Cover issue={iss} />
            </div>
            <div className="archive-copy">
              <p className="small muted">
                Issue {pad(iss.issue)} <span>{fdate(iss.date)}</span>
              </p>
              <h2>{title(iss)}</h2>
              <p className="archive-dek">{iss.dek}</p>
              <span className="text-link">
                Read issue <Icon />
              </span>
            </div>
          </a>
        ))}
      </div>
      {!shown.length && (
        <p className="empty">
          No issues match “{query}”. Try a title or artist from the weekly note.
        </p>
      )}
      {/* The shelf speaks for itself once it has a few issues on it. */}
      {issues.length < 4 && (
        <p className="collection-note">
          {issues.length === 1
            ? "The first of many. Your collection has begun."
            : "No rush to fill the shelf. These are yours to come back to."}
        </p>
      )}
    </>
  );
}
function PageHeading({ title: heading, description }) {
  return (
    <header className="page-heading">
      <h1>{heading}</h1>
      <p>{description}</p>
    </header>
  );
}
function Search({ value, onChange, placeholder }) {
  return (
    <label className="search">
      <Icon name="search" size={17} />
      <input
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button aria-label="Clear search" onClick={() => onChange("")}>
          <Icon name="close" size={15} />
        </button>
      )}
    </label>
  );
}
function Lanes({ lanes, issues, selected }) {
  const [id, setId] = useState(selected || lanes[0]?.id);
  useEffect(() => {
    if (selected) setId(selected);
  }, [selected]);
  const lane = lanes.find((l) => l.id === id) || lanes[0];
  if (!lane)
    return (
      <p className="empty">
        Your listening lanes will appear here once they’re ready.
      </p>
    );
  const picks = issues.flatMap((issue) =>
    issue.modules.flatMap((m, i) => {
      const items =
        m.tracks ||
        m.albums ||
        m.mixes ||
        (m.album ? [{ ...m.album, cluster: m.cluster }] : []);
      return items
        .filter((t) => t.cluster === lane.id)
        .map((t) => ({ ...t, issue, section: i + 1 }));
    }),
  );
  return (
    <>
      <PageHeading
        title="Follow your ears."
        description="The neighborhoods in your listening. Familiar names, unexpected connections, and a way into every issue."
      />
      <div className="lanes-layout">
        <nav className="lane-list" aria-label="Listening lanes">
          {lanes.map((l) => (
            <button
              key={l.id}
              aria-pressed={lane.id === l.id}
              onClick={() => {
                setId(l.id);
                history.replaceState(
                  null,
                  "",
                  link("lanes", `&lane=${encodeURIComponent(l.id)}`),
                );
              }}
            >
              <i style={{ background: `hsl(${LANES[l.id] || 200} 35% 45%)` }} />
              <span>{l.name}</span>
              <small>{Math.round(l.hours)}h</small>
            </button>
          ))}
        </nav>
        <section className="lane-detail">
          <div className="lane-summary">
            <p className="small muted">
              {lane.state === "active" ? "In rotation" : lane.state} ·{" "}
              {lane.members} artists
            </p>
            <h2>{lane.name}</h2>
            <p>{lane.description}</p>
          </div>
          <h3 className="subheading">The familiar company</h3>
          <div className="artist-list">
            {lane.top?.map((a) => (
              <div key={a.artist}>
                <span>{a.artist}</span>
                <div className="artist-bar">
                  <i
                    style={{
                      width: `${(a.plays / Math.max(...lane.top.map((x) => x.plays))) * 100}%`,
                      background: `hsl(${LANES[lane.id] || 200} 25% 63%)`,
                    }}
                  />
                </div>
                <small>{a.plays.toLocaleString()} plays</small>
              </div>
            ))}
          </div>
          <h3 className="subheading">
            From your issues <span className="muted">{picks.length}</span>
          </h3>
          <div className="lane-picks">
            {picks.map((p, i) => (
              <a key={i} href={`${hrefIssue(p.issue)}#s${p.section}`}>
                <Art src={p.cover_url} label="" />
                <div>
                  <h4>{p.artist || p.show}</h4>
                  <p>{p.title || p.episode}</p>
                  <small>
                    Issue {pad(p.issue.issue)} · {title(p.issue)}
                  </small>
                </div>
                <Icon />
              </a>
            ))}
          </div>
          {!picks.length && (
            <p className="empty">
              No picks from this lane yet. Its artists are already part of your
              listening history.
            </p>
          )}
        </section>
      </div>
    </>
  );
}
function ReleaseRows({ rows }) {
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  return (
    <div className="release-rows">
      {rows.map((r, i) => (
        <div className="release-row" key={i}>
          <span className="release-date">
            {fdate(r.release_date, { year: false })}
          </span>
          <Art src={r.cover_url} label={r.artist} />
          <div className="release-copy">
            <h3>{r.artist}</h3>
            <p>{r.title}</p>
            <small className="muted">
              {r.release_type}
              {r.release_date > today ? " · Upcoming" : ""}
            </small>
            {r.note && <p className="release-note">{r.note}</p>}
          </div>
          <LinkOut
            href={
              spotifyUrl(r, "album") ||
              `https://open.spotify.com/search/${encodeURIComponent(`${r.artist} ${r.title}`)}`
            }
          >
            Spotify
          </LinkOut>
        </div>
      ))}
    </div>
  );
}
function Releases({ rows }) {
  const [kind, setKind] = useState("all");
  const [query, setQuery] = useState("");
  const filtered = rows.filter(
    (r) =>
      (kind === "all" || r.release_type === kind) &&
      (r.artist + " " + r.title).toLowerCase().includes(query.toLowerCase()),
  );
  const months = [
    ...new Set(filtered.map((r) => r.release_date?.slice(0, 7) || "")),
  ]
    .sort()
    .reverse();
  return (
    <>
      <PageHeading
        title="On the horizon. On repeat."
        description="New releases from the artists already in your listening, with a little room for what’s next."
      />
      <div className="toolbar">
        <div className="segmented">
          {["all", "album", "ep", "single"].map((k) => (
            <Pill key={k} active={kind === k} onClick={() => setKind(k)}>
              {
                {
                  all: "All releases",
                  album: "Albums",
                  ep: "EPs",
                  single: "Singles",
                }[k]
              }
            </Pill>
          ))}
        </div>
        <Search
          value={query}
          onChange={setQuery}
          placeholder="Find an artist or release"
        />
      </div>
      <div className="releases-layout">
        <div>
          {months.map((m) => (
            <section className="release-month" key={m}>
              <h2>
                {m
                  ? new Date(`${m}-01T12:00:00`).toLocaleDateString("en-US", {
                      month: "long",
                      year: "numeric",
                    })
                  : "Undated"}
              </h2>
              <ReleaseRows
                rows={filtered.filter(
                  (r) => (r.release_date?.slice(0, 7) || "") === m,
                )}
              />
            </section>
          ))}
          {!filtered.length && (
            <p className="empty">
              No releases match these filters. Try another artist or release
              type.
            </p>
          )}
        </div>
        <aside className="calendar-note">
          <Icon name="headphones" size={28} />
          <h3>Already in your orbit.</h3>
          <p>
            Each issue brings you what’s fresh that week. This is the whole
            shelf, including the things you might have missed.
          </p>
        </aside>
      </div>
    </>
  );
}
export default function App({ reader = { name: "Andrew", since: 2015 } }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [route, setRoute] = useState(readRoute);
  const [focus, setFocus] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const json = async (p) => {
      const r = await fetch(p);
      if (!r.ok) throw Error(`Could not load ${p}`);
      return r.json();
    };
    const optional = (p, fallback) => json(p).catch(() => fallback);
    (async () => {
      try {
        const base = baseFor();
        const idx = await json(`${base}/index.json`);
        const [issues, lanes, releases, demos] = await Promise.all([
          Promise.all(
            idx.issues.map((x) => json(`${base}/issue-${pad(x.issue)}.json`)),
          ),
          optional(`${base}/lanes.json`, {}),
          // Personas carry no release calendar; the page simply stays out
          // of the navigation when there is nothing to show.
          optional(`${base}/releases.json`, {}),
          demoSlug() ? optional("/demo/index.json", {}) : {},
        ]);
        const persona = (demos.personas || []).find(
          (x) => x.slug === demoSlug(),
        );
        if (!cancelled)
          setData({
            issues: issues.sort((a, b) => b.issue - a.issue),
            lanes: lanes.lanes || [],
            releases: releases.releases || [],
            // Whose edition this is: the persona's when reading a demo,
            // the owner's otherwise.
            who: persona
              ? {
                  name: persona.name,
                  since: Number(persona.history?.since) || null,
                  demo: true,
                }
              : { ...reader, demo: false },
          });
      } catch (e) {
        if (!cancelled) setError(e.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    const nav = () => {
      setRoute(readRoute());
      if (location.hash) {
        requestAnimationFrame(() =>
          document.getElementById(location.hash.slice(1))?.scrollIntoView(),
        );
      } else {
        window.scrollTo({ top: 0, behavior: "instant" });
      }
    };
    window.addEventListener("popstate", nav);
    const click = (e) => {
      const a = e.target.closest("a");
      if (
        !a ||
        a.target ||
        e.defaultPrevented ||
        e.button !== 0 ||
        e.metaKey ||
        e.ctrlKey ||
        e.shiftKey ||
        e.altKey
      )
        return;
      const u = new URL(a.href);
      if (
        u.origin !== location.origin ||
        !u.search ||
        u.pathname !== location.pathname
      )
        return;
      if (u.search === location.search && u.hash) return;
      e.preventDefault();
      history.pushState(null, "", u);
      setRoute(readRoute());
      setFocus(false);
      window.scrollTo({ top: 0, behavior: "instant" });
    };
    document.addEventListener("click", click);
    return () => {
      document.removeEventListener("click", click);
      window.removeEventListener("popstate", nav);
    };
  }, []);
  useEffect(() => {
    if (!data) return;
    const issue =
      data.issues.find((i) => i.issue === route.n) || data.issues[0];
    const page =
      route.view === "issue" || route.view === "latest"
        ? title(issue)
        : {
            home: "Your listening desk",
            archive: "Your collection",
            lanes: "Your listening lanes",
            releases: "Release calendar",
          }[route.view] || "Your listening desk";
    document.title = `${page} · ${data.who?.demo ? `${data.who.name} demo · ` : ""}clanker.cd`;
  }, [route, data]);
  if (error)
    return (
      <main className="loading">
        <h1>The issues couldn’t be loaded.</h1>
        <p>{error}</p>
        <button className="primary" onClick={() => location.reload()}>
          Try again
        </button>
      </main>
    );
  if (!data)
    return (
      <main className="loading">
        <img src="/brand/head-96.png" alt="" />
        <p>Setting out your records…</p>
      </main>
    );
  if (!data.issues.length)
    return (
      <main className="loading">
        <h1>Your first pressing is on its way.</h1>
        <p>Your listening desk will be ready when your first issue arrives.</p>
      </main>
    );
  const { issues, lanes, releases, who } = data;
  const years = who.since ? new Date().getFullYear() - who.since : null;
  const clean = isClean();
  const issue = issues.find((i) => i.issue === route.n) || issues[0];
  const reading = ["issue", "latest"].includes(route.view);
  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="site-header">
        <div className="header-inner">
          <a className="brand" href="?">
            <img src="/brand/head-96.png" alt="" />
            clanker.cd
          </a>
          <nav aria-label="Main navigation">
            {[
              ["home", "Your desk"],
              ["issue", "Latest issue"],
              ["archive", "Collection"],
              ["lanes", "Your lanes"],
              ["releases", "Releases"],
            ]
              .filter(([v]) => v !== "releases" || releases.length)
              .map(([v, label]) => (
                <a
                  key={v}
                  href={v === "issue" ? hrefIssue(issues[0]) : link(v)}
                  aria-current={
                    (
                      v === "issue"
                        ? reading && issue.issue === issues[0].issue
                        : v === "archive"
                          ? route.view === v ||
                            (reading && issue.issue !== issues[0].issue)
                          : route.view === v
                    )
                      ? "page"
                      : undefined
                  }
                >
                  {label}
                </a>
              ))}
          </nav>
          <span className="profile">
            <span>{who.name.slice(0, 1)}</span>
            {who.demo && !clean ? (
              <a href="?view=demo" title="Pick another demo persona">
                {who.name}’s edition <em>demo</em>
              </a>
            ) : (
              `${who.name}’s edition`
            )}
            {who.demo && !clean && (
              <a className="leave" href="?" title="Leave the demo">
                Leave demo
              </a>
            )}
          </span>
        </div>
      </header>
      <main
        id="main"
        className={`page ${reading ? "reader-page" : ""}`}
        key={`${route.view}:${route.n}`}
        tabIndex="-1"
      >
        {reading ? (
          <Reader
            key={issue.issue}
            issue={issue}
            issues={issues}
            lanes={lanes}
            focus={focus}
            setFocus={setFocus}
          />
        ) : route.view === "archive" ? (
          <Archive issues={issues} />
        ) : route.view === "lanes" ? (
          <Lanes lanes={lanes} issues={issues} selected={route.lane} />
        ) : route.view === "releases" ? (
          <Releases rows={releases} />
        ) : (
          <Home issues={issues} lanes={lanes} who={who} />
        )}
      </main>
      <footer className="site-footer">
        <span>clanker.cd</span>
        <p>
          {years
            ? `Pressed weekly from ${words(years)} years of listening.`
            : "Pressed weekly from your listening."}
        </p>
      </footer>
    </>
  );
}
