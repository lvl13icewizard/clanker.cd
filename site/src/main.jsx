import React, { Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import Landing from "./Landing.jsx";
import "./landing.css";

// Three surfaces, each with its own stylesheet loaded only when it renders:
// the landing (bare, or view=landing|home), the demo room (view=demo), and
// the approved reader (site/reader) for everything else — a persona's
// dataset when ?demo=<slug> is set, the owner's /issues otherwise.
const Reader = lazy(() =>
  import("../reader/App.jsx").then(async (m) => {
    await import("../reader/styles.css");
    return m;
  }),
);
const DemoShell = lazy(() => import("./DemoShell.jsx"));
const query = new URLSearchParams(location.search);
const view = query.get("view");
const isDemoRoom = view === "demo";
const isLanding =
  !isDemoRoom &&
  !query.has("demo") &&
  !query.has("n") &&
  (!view || view === "landing" || view === "home");

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {isLanding ? (
      <Landing />
    ) : (
      <Suspense fallback={<p className="page-status">Opening the demo…</p>}>
        {isDemoRoom ? <DemoShell /> : <Reader />}
      </Suspense>
    )}
  </React.StrictMode>,
);
