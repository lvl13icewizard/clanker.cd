"""Apply a prose copy document to an EXISTING issue, in place.

The writer builds an issue from the selection in out/, so re-running it to
change a sentence risks changing the picks. This applies copy (the same
structure writer --copy takes: title, dek, masthead_note, modules with why /
intro / verdict / tracks[].why / mixes[].why / albums[].why /
releases[].note) onto issues/issue-NNN.json as it stands, runs the same
new_this_week note pairing and the same validator, and writes the result
back to issues/ and site/public/issues/. Picks, receipts, covers and rows
are untouched; only prose moves.

Run:  PYTHONPATH=<root> python3 -m engine.editorial.recopy --n 2 --copy out/copy-002-v2.json
"""

import argparse
import json
import sys
from pathlib import Path

from ..lib.config import load_config
from . import validate as V
from .writer import _align_copy, _load_json, _merge, guard_copy


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, required=True, help="issue number")
    ap.add_argument("--copy", required=True, help="prose copy JSON")
    args = ap.parse_args(argv)
    cfg = load_config()
    name = f"issue-{args.n:03d}.json"
    path = Path(cfg["ISSUES_DIR"]) / name
    if not path.exists():
        print(f"recopy: {path} not found", file=sys.stderr)
        return 2
    doc = json.loads(path.read_text())
    copy_doc = _load_json(args.copy)
    if copy_doc is None:
        print(f"recopy: --copy {args.copy} missing or unreadable", file=sys.stderr)
        return 2
    out_dir = Path(cfg["OUT_DIR"])
    proposal = _load_json(out_dir / "selection-proposal.json") or {}
    model = _load_json(out_dir / "taste-model.json")
    notes = []
    have = {m.get("type") for m in doc.get("modules") or []}
    for m in copy_doc.get("modules") or []:
        if isinstance(m, dict) and m.get("type") not in have:
            notes.append(f"module type {m.get('type')!r} not in the issue; ignored")
    aligned = _align_copy(copy_doc, doc["modules"], proposal, model, doc.get("date"), notes)
    safe, guard_errors = guard_copy(doc, aligned, notes)
    if guard_errors:
        for e in guard_errors:
            print(f"IDENTITY: {e}", file=sys.stderr)
        print(f"recopy: issue {args.n:03d} REJECTED, the copy is not prose-only; nothing written",
              file=sys.stderr)
        return 1
    new = _merge(doc, safe)
    gen = new.setdefault("generated", {})
    gen["llm"] = True
    gen["notes"] = list(gen.get("notes") or []) + [f"recopy: {x}" for x in notes]
    errors = V.validate_issue(new)
    if errors:
        for e in errors:
            print(f"VALIDATION: {e}", file=sys.stderr)
        print(f"recopy: issue {args.n:03d} REJECTED, {len(errors)} violation(s); nothing written",
              file=sys.stderr)
        return 1
    body = json.dumps(new, indent=2, ensure_ascii=False) + "\n"
    path.write_text(body)
    (Path(cfg["SITE_ISSUES_DIR"]) / name).write_text(body)
    print(f"recopy: issue {args.n:03d} updated ({len(notes)} note(s))")
    for x in notes:
        print(f"  note: {x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
