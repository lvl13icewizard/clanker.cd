import { useEffect, useRef, useState } from "react";
import ListeningRoom from "./ListeningRoom.jsx";

export const REPO_URL = "github.com/lvl13icewizard/clanker.cd";
const REPO = `https://${REPO_URL}`;

const SECTIONS = [
  ["Singles Rack", "songs from artists you have never played", "singles"],
  ["Album of the Week", "one record, front to back", "album"],
  ["Mixes", "radio shows and DJ sets from NTS, KEXP and Boiler Room", "mixes"],
  [
    "Second Chances",
    "songs you played hard once and dropped, albums you barely opened",
    "second",
  ],
  ["Critics Desk", "acclaimed records you never got to", "critics"],
  ["Catalog Room", "an artist you love, an album you never played", "catalog"],
  ["New This Week", "new releases from artists deep in your library", "new"],
  [
    "The Ledger",
    "last week's picks, graded by what you actually played",
    "ledger",
  ],
];

const LISTENERS = [
  {
    slug: "andrew",
    name: "Andrew",
    issues: 18,
    title: "Glass Field",
    blurb:
      "Eleven years across ambient, instrumental hip hop, loop-digger rap and a late-arriving house habit. Eighteen issues, one lane burning out, another growing into the gap.",
  },
  {
    slug: "electronic",
    name: "Mara",
    issues: 13,
    title: "Night Ferry",
    blurb:
      "Deep electronic: dub techno, UK bass, jungle, long ambient records. Thirteen issues, and a hard-techno phase that ended the way they do.",
  },
  {
    slug: "altindie",
    name: "June",
    issues: 11,
    title: "Late Summer",
    blurb:
      "Post-punk, shoegaze, slowcore, a quiet folk streak. Eleven issues of guitars in every weather.",
  },
  {
    slug: "pop",
    name: "Tasha",
    issues: 9,
    title: "Curtain Call",
    blurb:
      "Pop, played straight and taken seriously. Nine issues where every discovery is one honest step sideways.",
  },
];

function Icon({ name, ...props }) {
  const paths = {
    singles: (
      <>
        <path d="M8 17V5l11-2v12M8 8l11-2" />
        <ellipse cx="5" cy="17" rx="3" ry="2" />
        <ellipse cx="16" cy="15" rx="3" ry="2" />
      </>
    ),
    album: (
      <>
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <circle cx="12" cy="12" r="5" />
        <circle cx="12" cy="12" r=".8" />
      </>
    ),
    mixes: (
      <>
        <path d="M4 14v-2a8 8 0 0 1 16 0v2" />
        <rect x="3" y="12" width="4" height="8" rx="2" />
        <rect x="17" y="12" width="4" height="8" rx="2" />
      </>
    ),
    second: (
      <>
        <path d="M4 10a8 8 0 1 1 0 5M4 4v6h6" />
      </>
    ),
    critics: (
      <>
        <path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z" />
      </>
    ),
    catalog: (
      <>
        <path d="M4 4v16M8 4v16M12 4v16M16 5l5 14" />
      </>
    ),
    new: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M7 3v4M17 3v4M3 11h18M12 14v4M10 16h4" />
      </>
    ),
    ledger: (
      <>
        <path d="M4 20V5M4 20h17M9 15v-4M14 15V7M19 15v-7" />
      </>
    ),
    copy: (
      <>
        <rect x="8" y="8" width="12" height="12" rx="2" />
        <path d="M15 8V4H4v11h4" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    play: <path d="m8 5 11 7-11 7Z" />,
    pause: (
      <>
        <path d="M8 5v14M16 5v14" />
      </>
    ),
    external: (
      <>
        <path d="M8 5H4v15h15v-4M12 4h8v8M10 14 20 4" />
      </>
    ),
    down: <path d="m6 9 6 6 6-6" />,
  };
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.45"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {paths[name]}
    </svg>
  );
}

function Brand() {
  return (
    <a className="lp-brand" href="/" aria-label="clanker.cd home">
      <img src="/brand/head-96.png" width="38" height="38" alt="" />
      <span>clanker.cd</span>
    </a>
  );
}

function Pressing() {
  const [open, setOpen] = useState(false);
  return (
    <figure className={`lp-pressing${open ? " is-open" : ""}`}>
      <div className="lp-object">
        <button
          className="lp-disc"
          type="button"
          onClick={() => setOpen(!open)}
          aria-label={
            open
              ? "Slide the disc back into its sleeve"
              : "Slide the disc out of its sleeve"
          }
          aria-pressed={open}
        >
          <span className="lp-disc-label">clanker.cd</span>
          <span className="lp-disc-number">018</span>
          <span className="lp-disc-hub" />
        </button>
        <a
          className="lp-sleeve"
          href="?demo=andrew&view=latest"
          aria-label="Read Glass Field, Andrew’s demo issue 018"
        >
          <img
            src="/demo/andrew/cover-018-plain.jpg"
            width="640"
            height="640"
            alt=""
            fetchpriority="high"
          />
          <div className="lp-sleeve-top">
            <span>clanker.cd</span>
            <span>Issue 018</span>
          </div>
          <div className="lp-sleeve-title">
            Last
            <br />
            Light
          </div>
          <div className="lp-sleeve-bottom">
            <span>A journal for Andrew</span>
            <span>15.08.26</span>
          </div>
        </a>
        <img
          className="lp-hero-bot"
          src="/brand/pose-hero.png"
          width="470"
          height="490"
          alt="The clanker robot, proudly holding a freshly pressed compact disc."
          fetchpriority="high"
        />
      </div>
      <figcaption>
        <span>From Andrew’s demo, issue 018</span>
        <button
          type="button"
          className="lp-text-link"
          onClick={() => setOpen(!open)}
          aria-pressed={open}
        >
          {open ? "[ Slide it back ]" : "[ Slide out the disc ]"}
        </button>
      </figcaption>
    </figure>
  );
}

function IssuePreview() {
  const [failed, setFailed] = useState(false);
  const [paused, setPaused] = useState(false);
  const video = useRef(null);
  const toggle = () => {
    const element = video.current;
    if (!element) return;
    if (element.paused) {
      element.play().catch(() => {});
      setPaused(false);
    } else {
      element.pause();
      setPaused(true);
    }
  };
  // Respect reduced motion: start on the poster, play only when asked.
  const still =
    typeof window !== "undefined" &&
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  return (
    <div className="lp-inside">
      <div className="lp-film-card">
        <div className="lp-film">
          <video
            ref={video}
            src="/brand/film/saturday.mp4"
            poster="/brand/film/saturday-poster.jpg"
            autoPlay={!still}
            loop
            muted
            playsInline
            preload="metadata"
            aria-label="A thirty-second film: the press runs on a Saturday morning, the issue and its companion playlist arrive."
            onError={() => setFailed(true)}
            onPause={() => setPaused(true)}
            onPlay={() => setPaused(false)}
          />
          {!failed && (
            <button
              type="button"
              className={`lp-film-toggle${paused ? " is-paused" : ""}`}
              onClick={toggle}
              aria-pressed={!paused}
              aria-label={paused ? "Play the film" : "Pause the film"}
            >
              {paused ? "Play" : "Pause"}
            </button>
          )}
        </div>
        {failed && (
          <p className="lp-film-caption">
            <span className="lp-film-status">The film could not load.</span>
          </p>
        )}
      </div>
      <ul className="lp-sections" aria-label="The eight sections of an issue">
        {SECTIONS.map(([name, desc, icon]) => (
          <li key={name} className="lp-section-tab">
            <Icon name={icon} />
            <span>
              <b>{name}</b>
              <span>{desc}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Listener({ listener }) {
  const { slug, name, issues, title, blurb } = listener;
  return (
    <a className="lp-listener" href={`?demo=${slug}`}>
      <div className="lp-cover-stack" aria-hidden="true">
        {[2, 1, 0].map((offset) => (
          <div
            key={offset}
            className={`lp-mini-sleeve lp-mini-sleeve-${offset}`}
          >
            <img
              src={`/demo/${slug}/cover-${String(issues - offset).padStart(3, "0")}-plain.jpg`}
              width="640"
              height="640"
              alt=""
              loading="lazy"
            />
            {offset === 0 && (
              <>
                <div className="lp-mini-top">
                  <span>clanker.cd</span>
                  <span>{String(issues).padStart(3, "0")}</span>
                </div>
                <span className="lp-mini-title">{title}</span>
                <span className="lp-mini-bottom">A journal for {name}</span>
              </>
            )}
          </div>
        ))}
      </div>
      <div className="lp-listener-title">
        <h3>{name}</h3>
        <span>{issues} issues</span>
      </div>
      <p>{blurb}</p>
      <span className="lp-text-link">[ Read as {name} ]</span>
    </a>
  );
}

function Setup() {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(false);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(REPO);
      setCopied(true);
      setError(false);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 2400);
    } catch {
      setError(true);
    }
  };
  return (
    <section className="lp-setup" id="run-it" aria-labelledby="lp-setup-title">
      <div className="lp-setup-copy">
        <h2 id="lp-setup-title">
          Point your
          <br /> clanker at this
        </h2>
        <p>clanker.cd is open source and runs entirely on your machine.</p>
        <ol className="lp-setup-steps">
          <li>
            <h3>Get your listening history</h3>
            <p>
              Open{" "}
              <a
                href="https://www.spotify.com/account/privacy/"
                target="_blank"
                rel="noreferrer"
              >
                Spotify’s data settings
              </a>{" "}
              and request <strong>Extended streaming history</strong>, which
              covers the lifetime of your account. Download the files when
              they’re ready.
            </p>
          </li>
          <li>
            <h3>Hand it to your clanker</h3>
            <p>
              Give your coding agent the downloaded history files and the
              repository link. Ask it to build your own clanker.cd.
            </p>
          </li>
        </ol>
        <a
          className="lp-text-link"
          href={`${REPO}#readme`}
          target="_blank"
          rel="noreferrer"
        >
          [ Read the README ] <Icon name="external" width="14" height="14" />
        </a>
      </div>
      <div className="lp-handoff">
        <div className="lp-repo-box">
          <p>Tell your agent:</p>
          <div className="lp-repo-line">
            <a href={REPO} target="_blank" rel="noreferrer">
              github.com/
              <br />
              <strong>lvl13icewizard/clanker.cd</strong>
            </a>
            <button
              type="button"
              onClick={copy}
              aria-label="Copy repository URL"
            >
              <Icon name={copied ? "check" : "copy"} />
              <span>{copied ? "Copied" : "Copy"}</span>
            </button>
          </div>
          <div className="lp-build-mine">
            “Build me mine.”
            <span aria-live="polite" className="lp-copy-status">
              {error
                ? "Select the repository link above to copy it."
                : copied
                  ? "Repository URL copied."
                  : ""}
            </span>
          </div>
        </div>
        <div className="lp-hands">
          <p>
            Prefer hands? The README walks through setup and your first issue.
            Bring your own robot for the prose, or let the template write it
            plain.
          </p>
          <img
            src="/brand/pose-study.png"
            width="286"
            height="320"
            alt="The clanker inspecting a compact disc with a magnifying glass."
            loading="lazy"
          />
        </div>
      </div>
    </section>
  );
}

export default function Landing() {
  useEffect(() => {
    document.title = "clanker.cd | A personalized music journal";
  }, []);
  return (
    <div className="frontdoor" id="top">
      <a className="lp-skip" href="#lp-main">
        Skip to content
      </a>
      <header className="lp-header lp-width">
        <Brand />
        <nav aria-label="Main navigation">
          <a href="#inside">Inside an issue</a>
          <a href="#demos">The demos</a>
          <a href="#run-it">[ Run it yourself ]</a>
        </nav>
      </header>
      <main id="lp-main">
        <section className="lp-hero lp-width" aria-labelledby="lp-hero-title">
          <div className="lp-hero-copy">
            <h1 id="lp-hero-title">
              A personalized
              <br className="lp-desktop-break" /> music journal,
              <br className="lp-desktop-break" /> pressed by
              <br className="lp-desktop-break" /> your robot.
            </h1>
            <p className="lp-hero-description">
              clanker.cd reads your entire Spotify streaming history and presses
              you an issue of new music every Saturday. No accounts, no uploads,
              no servers.
            </p>
            <div className="lp-hero-actions">
              <a className="lp-button" href="?demo=andrew&view=latest">
                Read a demo issue <Icon name="album" width="17" height="17" />
              </a>
              <a className="lp-text-link" href="#run-it">
                [ Run it yourself ]
              </a>
            </div>
          </div>
          {new URLSearchParams(window.location.search).get("hero") === "cd" ? (
            <Pressing />
          ) : (
            <ListeningRoom />
          )}
        </section>
        <section
          className="lp-content lp-width"
          id="inside"
          aria-labelledby="lp-inside-title"
        >
          <div className="lp-section-intro">
            <h2 id="lp-inside-title">
              What comes
              <br /> off the press
            </h2>
            <p>
              Each issue is 8 written sections, a companion playlist, and a
              cover generated from that week’s own album art. Pressed every
              Saturday from your entire listening history.
            </p>
          </div>
          <IssuePreview />
        </section>
        <section
          className="lp-demos lp-width"
          id="demos"
          aria-labelledby="lp-demos-title"
        >
          <div className="lp-section-intro">
            <h2 id="lp-demos-title">Read the demos</h2>
            <p>
              Four demo listeners, months of issues each. Every record is real,
              every number is consistent, nothing personal is published.
            </p>
          </div>
          <div className="lp-listeners">
            {LISTENERS.map((listener) => (
              <Listener key={listener.slug} listener={listener} />
            ))}
          </div>
        </section>
        <div className="lp-width">
          <Setup />
        </div>
      </main>
      <footer className="lp-footer lp-width">
        <Brand />
        <a href={REPO} target="_blank" rel="noreferrer">
          [ GitHub ]
        </a>
        <a href="#top">[ Back to top ]</a>
      </footer>
    </div>
  );
}
