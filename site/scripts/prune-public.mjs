// The public build ships demo data only. Everything personal under
// dist/issues — real issues, covers, palettes, lane meta, the release
// calendar — is removed after the build; the synthetic fixture stays so
// the app's no-data paths keep working. Demo datasets and brand assets
// are public by design and stay.
import { readdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const dist = new URL("../dist/issues", import.meta.url).pathname;
let removed = 0;
let kept = 0;
for (const name of readdirSync(dist)) {
  if (name === "issue-000.json") { kept++; continue; }
  rmSync(join(dist, name), { recursive: true, force: true });
  removed++;
}
// Say out loud that there are no personal issues here, rather than leaving
// the app to discover it by missing 48 files it will never find.
writeFileSync(join(dist, "index.json"), JSON.stringify({ issues: [] }) + "\n");
writeFileSync(join(dist, "lanes.json"), JSON.stringify({ lanes: [] }) + "\n");

// The live pose set is the personal app's: robots holding the week's disc.
// The public site's robots hold the standard disc, so the live set never ships.
const live = new URL("../dist/brand/live", import.meta.url).pathname;
rmSync(live, { recursive: true, force: true });

console.log(`public prune: removed ${removed} personal file(s) from dist/issues, kept ${kept} (the fixture); dropped brand/live`);
const left = readdirSync(dist).sort();
const want = ["index.json", "issue-000.json", "lanes.json"];
if (left.length !== want.length || want.some((n, i) => left[i] !== n)) {
  console.error("prune check failed:", left);
  process.exit(1);
}
