"""Thin New This Week notes to the contract's density band.

All-speaking release rows read busy; the house wants a third to two
thirds. Deterministic: keeps every other note (seeded by position), so
reruns are stable and the kept set never reshuffles.

Run:  python3 demo/thin_release_notes.py <slug>
"""

import json
import sys
from pathlib import Path


def main():
    slug = sys.argv[1]
    cp = Path(__file__).parent / "catalogs" / f"{slug}.json"
    cat = json.loads(cp.read_text())
    rows = cat.get("releases") or []
    noted = [r for r in rows if r.get("note")]
    kept = 0
    for i, r in enumerate(noted):
        if i % 2 == 1:
            r["note"] = None
        else:
            kept += 1
    cp.write_text(json.dumps(cat, indent=1, ensure_ascii=False) + "\n")
    print(f"{slug}: kept {kept} of {len(noted)} release notes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
