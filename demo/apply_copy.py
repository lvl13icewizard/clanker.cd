"""Apply a written-copy batch to a catalog, through a lint gate.

Input: a JSON file {"entries": [{"path": [...], "text": "..."}]} whose paths
point at prose fields inside demo/catalogs/<slug>.json. Only fields that are
currently null are written; anything else is refused. Every text passes the
same bans the validator and VOICE.md enforce (digits, em dashes, streaming
diction, runaway length) or it is left null and reported.

Run:  python3 demo/apply_copy.py <slug> <entries.json>
"""

import json
import re
import sys
from pathlib import Path

BANS = re.compile(r"\d|—|\bbanger\b|\bslaps\b|for fans of|\bcurated\b|"
                  r"\belevate\b|sonic journey", re.I)
PROSE = ("why", "note", "intro", "dek")


def main():
    slug, entries_path = sys.argv[1], sys.argv[2]
    cp = Path(__file__).parent / "catalogs" / f"{slug}.json"
    cat = json.loads(cp.read_text())
    entries = json.loads(Path(entries_path).read_text())["entries"]
    applied, rejected, skipped = 0, [], []
    for e in entries:
        path, text = e["path"], (e.get("text") or "").strip()
        if not text or path[-1] not in PROSE:
            skipped.append(path)
            continue
        if BANS.search(text) or len(re.findall(r"[.!?]", text)) > 3 or len(text) > 420:
            rejected.append((path, text[:80]))
            continue
        node = cat
        try:
            for k in path[:-1]:
                node = node[k]
            if node.get(path[-1]) is not None:
                skipped.append(path)
                continue
            node[path[-1]] = text
            applied += 1
        except (KeyError, IndexError, TypeError):
            skipped.append(path)
    cp.write_text(json.dumps(cat, indent=1, ensure_ascii=False) + "\n")
    print(f"{slug}: applied {applied}, rejected {len(rejected)}, skipped {len(skipped)}")
    for path, frag in rejected[:12]:
        print(f"  REJECT {'/'.join(map(str, path))}: {frag!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
