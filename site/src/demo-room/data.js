/** The demo persona manifest. null when no demos have been built. */
export async function loadDemoManifest() {
  try {
    const res = await fetch("/demo/index.json");
    if (!res.ok) return null;
    const j = JSON.parse(await res.text());
    return Array.isArray(j?.personas) && j.personas.length ? j : null;
  } catch {
    return null;
  }
}
