"""Engine CLI — one front door for the whole pipeline.

    python3 -m engine model            # build taste model + revival pools
    python3 -m engine harvest          # gather candidates from all sources
    python3 -m engine verify           # zero-play verification rounds
    python3 -m engine select           # ranked selection proposal
    python3 -m engine issue --n 1 --no-llm [--copy PATH] [--in DIR] [--date D]
    python3 -m engine all [issue options]

Upstream stages are dispatched lazily by shelling out to
``python3 -m engine.<module>`` from the project root, so a stage that is
not built yet fails only its own subcommand with a clear message instead
of breaking the CLI at import time. ``issue`` calls the editorial writer
directly. ``all`` runs the stages in order and stops at the first failure.
"""

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# First existing module wins. Only model/harvest/select entry points are
# fixed by CONTRACTS.md; verify's is probed among likely names.
STAGES = {
    "model": ["engine.model.build_taste_model"],
    "harvest": ["engine.harvest.run_harvest"],
    "verify": ["engine.verify.run_verify", "engine.verify.zero_play",
               "engine.verify.verify", "engine.verify.main"],
    "select": ["engine.select.select_issue"],
}


def _find_module(candidates):
    for mod in candidates:
        try:
            if importlib.util.find_spec(mod) is not None:
                return mod
        except (ImportError, ModuleNotFoundError):
            continue
    return None


def _run_stage(name):
    mod = _find_module(STAGES[name])
    if mod is None:
        print(f"engine {name}: stage not built yet — tried "
              f"{', '.join(STAGES[name])}", file=sys.stderr)
        return 3
    proc = subprocess.run([sys.executable, "-m", mod], cwd=str(PROJECT_ROOT))
    return proc.returncode


def _issue_argv(args):
    argv = ["--n", str(args.n)]
    if args.no_llm:
        argv.append("--no-llm")
    if args.copy:
        argv += ["--copy", args.copy]
    if args.in_dir:
        argv += ["--in", args.in_dir]
    if args.date:
        argv += ["--date", args.date]
    return argv


def _run_issue(args):
    from engine.editorial import writer  # own module; safe to import
    return writer.main(_issue_argv(args))


def _add_issue_args(sp):
    sp.add_argument("--n", type=int, default=1, help="issue number")
    sp.add_argument("--no-llm", dest="no_llm", action="store_true",
                    help="template prose only (receipts joined plainly)")
    sp.add_argument("--copy", help="prose overrides JSON for the writer")
    sp.add_argument("--in", dest="in_dir",
                    help="writer input dir (default: out/)")
    sp.add_argument("--date", help="issue date YYYY-MM-DD (default: today)")


def main(argv=None):
    p = argparse.ArgumentParser(prog="engine", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("model", help="build out/taste-model.json + revival pools")
    sub.add_parser("harvest", help="gather out/candidates-raw.json")
    sub.add_parser("verify", help="zero-play verification")
    sub.add_parser("select", help="rank out/selection-proposal.json")
    _add_issue_args(sub.add_parser("issue", help="write issues/issue-NNN.json"))
    _add_issue_args(sub.add_parser("all", help="run every stage in order"))
    args = p.parse_args(argv)

    if args.cmd in STAGES:
        return _run_stage(args.cmd)
    if args.cmd == "issue":
        return _run_issue(args)
    # all
    for name in ("model", "harvest", "verify", "select"):
        rc = _run_stage(name)
        if rc:
            print(f"engine all: stopped at '{name}' (exit {rc})",
                  file=sys.stderr)
            return rc
    return _run_issue(args)


if __name__ == "__main__":
    sys.exit(main())
