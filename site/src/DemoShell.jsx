// The demo room: the persona picker, in the chrome it was designed in
// (site/src/demo-room, lifted from the first reader before it was archived).
// Opening a persona is a full navigation into the approved reader
// (site/reader), not a client route.
import { useEffect, useState } from "react";
import "./demo-room/demo-room.css";
import Header from "./demo-room/Header.jsx";
import DemoRoom from "./demo-room/DemoRoom.jsx";
import { loadDemoManifest } from "./demo-room/data.js";

export default function DemoShell() {
  const [manifest, setManifest] = useState(null);
  useEffect(() => {
    document.title = "Demo room · clanker.cd";
    loadDemoManifest().then(setManifest);
  }, []);
  const current = new URLSearchParams(location.search).get("demo");
  return (
    <div className="board">
      <a className="skip" href="#main">
        Skip to the personas
      </a>
      <Header onHome={() => location.assign("?")} />
      <main id="main">
        <DemoRoom
          manifest={manifest}
          current={current}
          tools={false}
          exitLabel="Back to the landing"
          exitHref="?"
          onExit={() => location.assign("?")}
          onOpen={(slug, clean) =>
            location.assign(
              `?demo=${encodeURIComponent(slug)}${clean ? "&clean=1" : ""}`,
            )
          }
        />
      </main>
    </div>
  );
}
