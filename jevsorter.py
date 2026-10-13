#!/usr/bin/env python3
"""
jevsorter - sort loose files into a folder's own subfolders, using Jev
(TypeSafe System One) to judge which subfolder each file belongs in.

Dry run by default. Nothing moves without --apply.

    jevsorter propose DIR              list filenames, draft categories
    jevsorter sort DIR [DIR ...]       DRY RUN unless --apply
    jevsorter undo [last | <run-id>]   reverse a run
    jevsorter selftest                 built-in assertions, no network
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
KEY_ENV = "JEV_API_KEY"
PRICE_PER_M_INPUT = 0.042  # USD; output tokens are free


class JevError(Exception):
    """A problem the user must fix (bad key, bad config). Raised instead of
    SystemExit so GUI worker threads do not die silently; main() prints it."""


def summarize_usage(usage_sink: list) -> tuple[int, int, float]:
    """(input_tokens, output_tokens, cost_usd) totaled across a run's requests."""
    in_tok = sum(u.get("input_tokens", 0) for u in usage_sink)
    out_tok = sum(u.get("output_tokens", 0) for u in usage_sink)
    return in_tok, out_tok, in_tok * PRICE_PER_M_INPUT / 1_000_000

# Choice caps at 255 options; state + longest question caps at 32k tokens.
MAX_OPTIONS = 255
CRITERIA_CHAR_BUDGET = 24_000
EXAMPLES_PER_FOLDER = 5
WORKERS = 8  # rate limit is 1200 req/min, so this is nowhere near it

CONFIG_NAME = ".jevsorter.json"
STAY = "__stay__"
STAY_DESC = (
    "The file does not clearly belong in any of the other listed folders, "
    "or it is already sitting in the folder that suits it best. "
    "Leave it exactly where it is."
)

# Never descend into these. They are not excluded from being *candidate*
# folders, because a folder the user named explicitly may legitimately contain
# one (D:\Softwares has a real 'build'). Descending is the expensive mistake:
# D:\Development alone holds 41,649 directories, nearly all of them below these.
SKIP_DIRS = {
    "node_modules", ".git", ".gradle", ".kotlin", "venv", ".venv",
    "__pycache__", "site-packages", ".next", ".terraform", ".tox",
    "$recycle.bin", "system volume information",
}

# In-flight downloads. Moving one of these is the way this tool destroys data.
PARTIAL_EXTS = {
    ".crdownload", ".part", ".partial", ".tmp", ".download",
    ".!ut", ".opdownload", ".aria2",
}
# Shortcuts break when moved; .url likewise.
SKIP_EXTS = {".lnk", ".url"}
SKIP_NAMES = {"desktop.ini", "thumbs.db", ".ds_store", CONFIG_NAME.lower()}


# --------------------------------------------------------------------------
# log
# --------------------------------------------------------------------------

def app_dir() -> Path:
    """Where settings and the move log live: the platform's per-user data folder."""
    override = os.environ.get("JEVSORTER_HOME")
    if override:
        return Path(override)
    home = Path.home()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    return base / "jevsorter"


def open_path(path: Path) -> None:
    """Show a folder in the system file manager."""
    import subprocess
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


def log_path() -> Path:
    override = os.environ.get("JEVSORTER_LOG")
    if override:
        return Path(override)
    legacy = Path.home() / "jevsorter" / "moves.jsonl"  # where 0.1 wrote it on macOS and Linux
    if sys.platform != "win32" and legacy.exists() and not (app_dir() / "moves.jsonl").exists():
        return legacy
    return app_dir() / "moves.jsonl"


def append_log(record: dict) -> None:
    p = log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_log() -> list[dict]:
    p = log_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # a torn last line should not break undo
    return out


# --------------------------------------------------------------------------
# scanning
# --------------------------------------------------------------------------

def skippable_file(p: Path, min_age: int, now: float | None = None) -> str | None:
    """Return the reason this file must not be touched, or None."""
    name = p.name
    if name.lower() in SKIP_NAMES:
        return "system file"
    if name.startswith("~$"):
        return "office lock file"
    suffix = p.suffix.lower()
    if suffix in PARTIAL_EXTS:
        return "partial download"
    if suffix in SKIP_EXTS:
        return "shortcut"
    try:
        age = (now if now is not None else time.time()) - p.stat().st_mtime
    except OSError:
        return "unreadable"
    if age < min_age:
        return f"too fresh ({int(age)}s)"
    return None


def loose_files(folder: Path, min_age: int) -> list[Path]:
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return []
    return [
        p for p in entries
        if p.is_file() and skippable_file(p, min_age) is None
    ]


def subfolders(folder: Path) -> list[Path]:
    """Immediate subfolders that can serve as categories."""
    try:
        entries = sorted(folder.iterdir())
    except OSError:
        return []
    return [p for p in entries if p.is_dir() and not p.name.startswith(".")]


def descendable(folder: Path) -> bool:
    return folder.name.lower() not in SKIP_DIRS and not folder.name.startswith(".")


def collect_jobs(root: Path, recursive: bool, max_depth: int) -> list[Path]:
    """Folders to sort. Each sorts its own loose files into its own subfolders."""
    jobs = [root]
    if not recursive:
        return jobs
    frontier = [(root, 0)]
    while frontier:
        folder, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        for sub in subfolders(folder):
            if not descendable(sub):
                continue
            jobs.append(sub)
            frontier.append((sub, depth + 1))
    return jobs


# --------------------------------------------------------------------------
# criteria
# --------------------------------------------------------------------------

def load_config(folder: Path) -> dict[str, str] | None:
    cfg = folder / CONFIG_NAME
    if not cfg.exists():
        return None
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise JevError(f"{cfg}: cannot read categories file: {exc}")
    cats = data.get("categories")
    if not isinstance(cats, dict) or not cats:
        raise JevError(f"{cfg}: expected a non-empty 'categories' object")
    return {str(k): str(v) for k, v in cats.items()}


def build_criteria(folder: Path, config: dict[str, str] | None) -> dict:
    """
    Criteria for one folder. From .jevsorter.json if present, else from the
    folder's existing subfolders described by what already lives in them.
    """
    if config is not None:
        criteria: dict = {name: desc for name, desc in config.items()}
    else:
        criteria = {}
        for sub in subfolders(folder):
            # A category folder can hold only subfolders. Saying it is "empty"
            # in that case tells the model something false and loses the best
            # evidence it has, so describe it by what it does contain.
            examples, nested = [], []
            try:
                for child in sorted(sub.iterdir()):
                    if child.is_file() and len(examples) < EXAMPLES_PER_FOLDER:
                        examples.append(child.name)
                    elif child.is_dir() and len(nested) < EXAMPLES_PER_FOLDER:
                        nested.append(child.name)
            except OSError:
                pass
            if examples or nested:
                desc = {"folder": sub.name}
                if examples:
                    desc["files_already_in_it"] = examples
                if nested:
                    desc["subfolders_it_contains"] = nested
                criteria[sub.name] = desc
            else:
                criteria[sub.name] = f"The folder named {sub.name!r} (currently empty)."

    # Budget guard: drop the example filenames before anything else.
    if len(json.dumps(criteria, ensure_ascii=False)) > CRITERIA_CHAR_BUDGET:
        criteria = {
            k: (f"The folder named {k!r}." if isinstance(v, dict) else v)
            for k, v in criteria.items()
        }

    criteria[STAY] = STAY_DESC
    return criteria


# --------------------------------------------------------------------------
# Jev
# --------------------------------------------------------------------------

def api_key() -> str:
    key = os.environ.get(KEY_ENV)
    if not key:
        raise JevError(
            f"{KEY_ENV} is not set.\n"
            f"Set it as a user environment variable, then open a new terminal:\n"
            f'    setx {KEY_ENV} "your-key-here"'
        )
    return key


def jev_choice(state: dict, criteria: dict, key: str | None, timeout: int = 60,
              usage_sink: list | None = None, url: str = API_URL,
              model: str = MODEL) -> dict:
    payload = {
        "state": state,
        "model": model,
        "questions": {
            "folder": {
                "type": "choice",
                "instructions": (
                    "Which of the listed folders does this file belong in? "
                    "Judge from the file's name, extension and size; the name "
                    "is usually the strongest evidence. Pick a folder only when "
                    "the file plainly belongs there."
                ),
                "criteria": criteria,
            }
        },
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key:  # a local server may not need one
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)

    delay = 1.0
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if usage_sink is not None:
                usage_sink.append(data.get("usage", {}))  # list.append is thread-safe
            return data["answers"]["folder"]
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise JevError("401 Unauthorized: the API key was rejected.")
            if exc.code in (429, 529) and attempt < 2:
                time.sleep(delay)
                delay *= 4
                continue
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < 2:
                time.sleep(delay)
                delay *= 4
                continue
            raise RuntimeError(f"network error: {exc}") from exc
    raise RuntimeError("unreachable")


def file_state(path: Path, current_folder: str | None) -> dict:
    st = path.stat()
    state = {
        "name": path.name,
        "ext": path.suffix.lower(),
        "size_bytes": st.st_size,
        "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
    }
    if current_folder is not None:
        state["current_folder"] = current_folder
    return state


# --------------------------------------------------------------------------
# moving
# --------------------------------------------------------------------------

def unique_dest(dst: Path) -> Path:
    """Never overwrite. name.ext -> name (1).ext -> name (2).ext ..."""
    if not dst.exists():
        return dst
    n = 1
    while True:
        cand = dst.with_name(f"{dst.stem} ({n}){dst.suffix}")
        if not cand.exists():
            return cand
        n += 1


def move(src: Path, dst: Path) -> Path:
    """Move without ever clobbering. Returns the path actually used."""
    dst = unique_dest(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(src, dst)  # on Windows this raises rather than overwriting
    except OSError:
        shutil.move(str(src), str(dst))
    return dst


# --------------------------------------------------------------------------
# the sort itself
# --------------------------------------------------------------------------

class Decision:
    def __init__(self, path: Path, choice: str, confidence: float,
                 probabilities: dict, reason: str = ""):
        self.path = path
        self.choice = choice
        self.confidence = confidence
        self.probabilities = probabilities
        self.reason = reason


def decide_target(dec: Decision, current: str | None, args) -> str | None:
    """The chosen folder name, or None to leave the file alone."""
    if dec.choice == STAY or dec.choice == current:
        return None
    if dec.confidence < args.min_confidence:
        return None
    if current is not None:
        p_new = dec.probabilities.get(dec.choice, 0.0)
        p_cur = dec.probabilities.get(current, 0.0)
        if p_new <= p_cur + args.margin:
            return None  # ties go to staying put
    return dec.choice


@dataclass
class Proposal:
    """One file's verdict. target is None when the file stays put."""
    folder: Path            # the folder whose categories were used
    path: Path
    current: str | None     # subfolder it already sits in (--resort), else None
    choice: str = ""
    confidence: float = 0.0
    probabilities: dict = field(default_factory=dict)
    target: str | None = None
    error: str | None = None


@dataclass
class FolderPlan:
    folder: Path
    proposals: list = field(default_factory=list)
    categories: list = field(default_factory=list)  # destination names
    status: str = ""        # why the folder was skipped, else ""


def plan_folder(folder: Path, args, key: str | None, classify=None,
                usage_sink: list | None = None, skip: set | None = None,
                progress=None, cancel: threading.Event | None = None,
                url: str = API_URL, model: str = MODEL) -> FolderPlan:
    """Ask Jev about one folder's files. Moves nothing."""
    skip = skip if skip is not None else set()
    classify = classify or (
        lambda state, criteria: jev_choice(state, criteria, key, url=url,
                                           model=model, usage_sink=usage_sink)
    )
    plan = FolderPlan(folder)
    config = load_config(folder)
    subs = subfolders(folder)
    criteria = build_criteria(folder, config)

    plan.categories = [k for k in criteria if k != STAY]
    n_options = len(plan.categories)
    if n_options == 0:
        plan.status = f"no categories (no subfolders, no {CONFIG_NAME})"
        return plan
    if n_options > MAX_OPTIONS - 1:
        plan.status = (f"{n_options} categories exceeds the {MAX_OPTIONS}-option "
                       f"limit - refused (shortlisting would hide why files stayed put)")
        return plan

    targets: list[tuple[Path, str | None]] = [
        (p, None) for p in loose_files(folder, args.min_age)
    ]
    if args.resort:
        for sub in subs:
            for p in loose_files(sub, args.min_age):
                targets.append((p, sub.name))
    targets = [(p, c) for p, c in targets if p not in skip]

    def work(item):
        path, current = item
        prop = Proposal(folder, path, current)
        if cancel is not None and cancel.is_set():
            prop.error = "cancelled"
            return prop
        try:
            ans = classify(file_state(path, current), criteria)
            prop.choice = ans["choice"]
            prop.confidence = float(ans.get("confidence", 0.0))
            prop.probabilities = ans.get("probabilities", {})
            prop.target = decide_target(
                Decision(path, prop.choice, prop.confidence, prop.probabilities),
                current, args)
        except JevError:
            raise  # bad key etc.: every file would fail the same way
        except Exception as exc:  # one bad file must not end the run
            prop.error = str(exc)
        return prop

    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(work, t) for t in targets]
        try:
            for fut in as_completed(futures):
                plan.proposals.append(fut.result())
                done += 1
                if progress:
                    progress(done, len(targets))
        except BaseException:
            for f in futures:
                f.cancel()
            raise
    plan.proposals.sort(key=lambda r: (str(r.path.parent), r.path.name.lower()))
    return plan


@dataclass
class MoveResult:
    proposal: Proposal
    dst: Path | None = None
    error: str | None = None


def apply_moves(proposals, run_id: str, min_age: int = 0,
                model: str = MODEL) -> list[MoveResult]:
    """Move approved proposals and log each. Re-checks every file first: a
    preview can be minutes old and the file may be growing or gone by now."""
    results = []
    for prop in proposals:
        res = MoveResult(prop)
        results.append(res)
        if not prop.target:
            continue
        why = (skippable_file(prop.path, min_age) if prop.path.exists()
               else "file no longer exists")
        if why:
            res.error = f"skipped: {why}"
            continue
        try:
            res.dst = move(prop.path, prop.folder / prop.target / prop.path.name)
        except OSError as exc:
            res.error = f"could not move (in use?): {exc}"
            continue
        append_log({
            "run_id": run_id,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "src": str(prop.path),
            "dst": str(res.dst),
            "choice": prop.choice,
            "confidence": prop.confidence,
            "top_probabilities": dict(sorted(
                prop.probabilities.items(), key=lambda kv: -kv[1])[:3]),
            "model": model,
            "dry_run": False,
        })
    return results


def sort_folder(folder: Path, args, key: str, run_id: str,
                classify=None, already_moved: set | None = None,
                usage_sink: list | None = None, url: str = API_URL,
                model: str = MODEL) -> tuple[int, int]:
    """CLI path: plan one folder, print verdicts, move them under --apply."""
    already_moved = already_moved if already_moved is not None else set()
    plan = plan_folder(folder, args, key, classify=classify, usage_sink=usage_sink,
                       skip=already_moved, url=url, model=model)
    if plan.status:
        print(f"  {folder}: {plan.status} - skipped")
        return (0, 0)
    if not plan.proposals:
        return (0, 0)
    print(f"  {folder}  ({len(plan.proposals)} files, {len(plan.categories)} categories)")

    moved = 0
    for prop in plan.proposals:
        if prop.error:
            print(f"    {prop.path.name}  -> ERROR: {prop.error}")
            continue
        print(f"    {prop.path.name}  ->  {prop.target or 'STAY'}  "
              f"(conf {prop.confidence:.2f})")
        if not prop.target:
            continue
        if not args.apply:
            moved += 1
            continue
        res = apply_moves([prop], run_id, model=model)[0]
        if res.error:
            print(f"      {res.error}")
            continue
        already_moved.add(res.dst)
        moved += 1
    return (moved, len(plan.proposals))


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_propose(args) -> int:
    folder = Path(args.dir).resolve()
    if not folder.is_dir():
        raise SystemExit(f"{folder} is not a folder")

    files = loose_files(folder, 0)
    exts: dict[str, int] = {}
    for p in files:
        exts[p.suffix.lower() or "(none)"] = exts.get(p.suffix.lower() or "(none)", 0) + 1

    print(f"{folder}: {len(files)} loose files\n")
    print("Extensions:")
    for ext, n in sorted(exts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}  {ext}")
    print("\nFilenames:")
    for p in files:
        print(f"  {p.name}")

    print(f"\nJev returns typed judgments, not generated text - it cannot invent")
    print(f"category names. Read the list above, then write {folder / CONFIG_NAME}:")
    print(json.dumps(
        {"categories": {"Example Category": "One line saying what belongs here."}},
        indent=2))
    print("Nothing was created or moved.")
    return 0


def cmd_sort(args) -> int:
    roots = []
    for d in args.dirs:
        p = Path(d).resolve()
        if not p.is_dir():
            raise SystemExit(f"{p} is not a folder")
        roots.append(p)

    # Both at once judges the same file twice: once as a resort candidate of the
    # parent (current_folder set, --margin applies) and once as a loose file of
    # the subfolder's own job (current_folder None, so --margin does not). The
    # second pass could move it on threshold alone. They do one level of the same
    # work anyway, so run them separately.
    if args.recursive and args.resort:
        raise SystemExit(
            "--recursive and --resort cannot be combined: a file inside a "
            "subfolder would be judged twice, and the second pass loses the "
            "--margin protection that keeps already-filed files put.\n"
            "Run them as two passes instead:\n"
            "    jevsorter sort DIR --resort      (re-file one level down)\n"
            "    jevsorter sort DIR --recursive   (sort each folder's own files)"
        )

    key = api_key()

    while True:
        run_id = uuid.uuid4().hex[:12]
        already_moved: set = set()
        total_moved = total_seen = 0
        usage_sink: list = []

        jobs: list[Path] = []
        for root in roots:
            jobs.extend(collect_jobs(root, args.recursive, args.max_depth))

        mode = "APPLY" if args.apply else "DRY RUN"
        print(f"[{mode}] run {run_id}: {len(jobs)} folder(s)"
              + (" --resort" if args.resort else ""))

        for folder in jobs:
            m, s = sort_folder(folder, args, key, run_id,
                               already_moved=already_moved, usage_sink=usage_sink)
            total_moved += m
            total_seen += s

        verb = "moved" if args.apply else "would move"
        print(f"\n{verb} {total_moved} of {total_seen} files.")
        if not args.apply and total_moved:
            print("Re-run with --apply to actually move them.")
        if args.apply and total_moved:
            print(f"Undo with:  jevsorter undo {run_id}")

        if usage_sink:
            in_tok, out_tok, cost = summarize_usage(usage_sink)
            print(f"Jev usage: {in_tok:,} input + {out_tok:,} output tokens "
                  f"across {len(usage_sink)} requests  (~${cost:.4f})")

        if not args.every:
            return 0
        print(f"\nsleeping {args.every} min ... (Ctrl+C to stop)\n")
        time.sleep(args.every * 60)


def list_runs() -> list[dict]:
    """Past runs, newest first: {run_id, ts, count}."""
    runs: dict[str, dict] = {}
    for r in read_log():
        if r.get("dry_run"):
            continue
        run = runs.setdefault(r["run_id"], {"run_id": r["run_id"], "ts": r.get("ts", ""), "count": 0})
        run["count"] += 1
    return list(reversed(list(runs.values())))


def undo_run(run_id: str) -> tuple[int, list[str]]:
    """Reverse one run. Returns (restored, per-file messages)."""
    batch = [r for r in read_log() if not r.get("dry_run") and r.get("run_id") == run_id]
    if not batch:
        raise JevError(f"no run {run_id!r} in {log_path()}")
    restored, lines = 0, []
    for rec in reversed(batch):
        src, dst = Path(rec["src"]), Path(rec["dst"])
        if not dst.exists():
            lines.append(f"skip (gone):     {dst}")
            continue
        if src.exists():
            lines.append(f"skip (occupied): {src}")
            continue
        try:
            src.parent.mkdir(parents=True, exist_ok=True)
            os.rename(dst, src)
            restored += 1
            lines.append(f"{dst.name}  ->  {src.parent}")
        except OSError as exc:
            lines.append(f"FAILED {dst}: {exc}")
    return restored, lines


def cmd_undo(args) -> int:
    runs = list_runs()
    if not runs:
        print("Nothing to undo.")
        return 0
    run_id = runs[0]["run_id"] if args.run == "last" else args.run
    n = next((r["count"] for r in runs if r["run_id"] == run_id), 0)
    print(f"Undoing run {run_id} ({n} moves)")
    restored, lines = undo_run(run_id)
    for line in lines:
        print(f"  {line}")
    print(f"\nrestored {restored} of {n} files.")
    return 0


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------

def cmd_selftest(args) -> int:
    import tempfile
    from types import SimpleNamespace

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # keep the real move log clean
        os.environ["JEVSORTER_LOG"] = str(root / "moves.jsonl")

        old = time.time() - 9999

        # --- unique_dest never clobbers -----------------------------------
        (root / "a.txt").write_text("x")
        assert unique_dest(root / "a.txt").name == "a (1).txt"
        (root / "a (1).txt").write_text("x")
        assert unique_dest(root / "a.txt").name == "a (2).txt"
        assert unique_dest(root / "nope.txt").name == "nope.txt"
        for n in ("a.txt", "a (1).txt"):
            os.utime(root / n, (old, old))

        # --- file skip rules ----------------------------------------------
        for name in ["real.pdf", "half.crdownload", "~$lock.xlsx",
                     "desktop.ini", "short.lnk", "fresh.pdf"]:
            p = root / name
            p.write_text("x")
            if name != "fresh.pdf":
                os.utime(p, (old, old))
        assert skippable_file(root / "real.pdf", 30) is None
        assert skippable_file(root / "half.crdownload", 30) == "partial download"
        assert skippable_file(root / "~$lock.xlsx", 30) == "office lock file"
        assert skippable_file(root / "desktop.ini", 30) == "system file"
        assert skippable_file(root / "short.lnk", 30) == "shortcut"
        assert "too fresh" in skippable_file(root / "fresh.pdf", 30)

        names = {p.name for p in loose_files(root, 30)}
        assert names == {"real.pdf", "a.txt", "a (1).txt"}, names

        # --- recursion skip list and depth cap ----------------------------
        deep = root / "proj"
        (deep / "node_modules" / "pkg").mkdir(parents=True)
        (deep / "src" / "inner" / "deeper").mkdir(parents=True)
        jobs = collect_jobs(root, recursive=True, max_depth=3)
        assert not any("node_modules" in str(j) for j in jobs), jobs
        assert deep / "src" / "inner" in jobs
        assert deep / "src" / "inner" / "deeper" not in jobs, "max_depth ignored"
        assert collect_jobs(root, recursive=False, max_depth=3) == [root]

        # --- >255 categories is refused, not truncated --------------------
        big = root / "big"
        big.mkdir()
        for i in range(260):
            (big / f"c{i:03d}").mkdir()
        (big / "loose.pdf").write_text("x")
        os.utime(big / "loose.pdf", (old, old))
        args_ns = SimpleNamespace(min_age=30, min_confidence=0.6, margin=0.15,
                                  apply=False, resort=False)
        moved, seen = sort_folder(big, args_ns, "k", "run",
                                  classify=lambda s, c: 1 / 0)  # must never be called
        assert (moved, seen) == (0, 0), "a 260-folder job should be refused"

        # --- criteria carry example filenames, plus the catch-all ---------
        work = root / "work"
        (work / "Invoices").mkdir(parents=True)
        (work / "Invoices" / "inv_001.pdf").write_text("x")
        (work / "Notes").mkdir()
        crit = build_criteria(work, None)
        assert crit["Invoices"]["files_already_in_it"] == ["inv_001.pdf"]
        assert STAY in crit and len(crit) == 3
        # a folder holding only subfolders must not be called "empty"
        (work / "Archive" / "2024").mkdir(parents=True)
        crit = build_criteria(work, None)
        assert crit["Archive"]["subfolders_it_contains"] == ["2024"], crit["Archive"]
        assert "empty" not in json.dumps(crit["Archive"])

        # --- .jevsorter.json overrides the folder listing -------------------
        (work / CONFIG_NAME).write_text(json.dumps(
            {"categories": {"Invoices": "bills", "Contracts": "signed docs"}}))
        crit = build_criteria(work, load_config(work))
        assert set(crit) == {"Invoices", "Contracts", STAY}
        assert crit["Contracts"] == "signed docs"

        # --- decide_target: threshold, catch-all, resort margin -----------
        a = SimpleNamespace(min_confidence=0.6, margin=0.15)
        d = Decision(root, "Invoices", 0.9, {"Invoices": 0.9, "Notes": 0.1})
        assert decide_target(d, None, a) == "Invoices"
        assert decide_target(Decision(root, "Invoices", 0.4, {}), None, a) is None
        assert decide_target(Decision(root, STAY, 0.99, {}), None, a) is None
        # already filed, and the new folder only just edges it out -> stay put
        near = Decision(root, "Notes", 0.9, {"Notes": 0.52, "Invoices": 0.48})
        assert decide_target(near, "Invoices", a) is None, "margin ignored"
        clear = Decision(root, "Notes", 0.9, {"Notes": 0.90, "Invoices": 0.05})
        assert decide_target(clear, "Invoices", a) == "Notes"
        assert decide_target(clear, "Notes", a) is None, "same folder should stay"

        # --- end to end: sort, then undo, with a stubbed model ------------
        box = root / "box"
        (box / "Reports").mkdir(parents=True)
        (box / "Reports" / "keep.txt").write_text("x")
        src = box / "q3_report.pdf"
        src.write_text("x")
        os.utime(src, (old, old))

        stub = lambda s, c: {"choice": "Reports", "confidence": 0.95,
                             "probabilities": {"Reports": 0.95, STAY: 0.05}}
        run = "selftest-" + uuid.uuid4().hex[:8]
        sort_args = SimpleNamespace(min_age=30, min_confidence=0.6, margin=0.15,
                                    apply=True, resort=False)
        moved, _ = sort_folder(box, sort_args, "k", run, classify=stub)
        assert moved == 1
        assert not src.exists() and (box / "Reports" / "q3_report.pdf").exists()

        cmd_undo(SimpleNamespace(run=run))
        assert src.exists(), "undo did not restore the file"
        assert not (box / "Reports" / "q3_report.pdf").exists()
        assert (box / "Reports" / "keep.txt").exists(), "undo touched a bystander"

        # --- --recursive + --resort is refused (it double-judges files) ----
        try:
            cmd_sort(SimpleNamespace(dirs=[str(box)], recursive=True, resort=True,
                                     apply=False, max_depth=3, every=0, min_age=30,
                                     min_confidence=0.6, margin=0.15))
            raise AssertionError("--recursive --resort should be refused")
        except SystemExit as exc:
            assert "judged twice" in str(exc), exc

        # --- usage totals math, without a network call ---------------------
        fake = [{"input_tokens": 1200, "output_tokens": 30},
                {"input_tokens": 800, "output_tokens": 20}]
        in_tok, out_tok, cost = summarize_usage(fake)
        assert (in_tok, out_tok) == (2000, 50)
        assert abs(cost - 2000 * 0.042 / 1_000_000) < 1e-12

        # --- bare 'sort' / 'propose' mean the current directory -----------
        # This one guards a destructive default: if it ever regressed to
        # something other than cwd, --apply would move the wrong files.
        # --- per-user data folder follows each platform's convention ---------
        kept = {k: os.environ.pop(k, None) for k in ("JEVSORTER_HOME", "JEVSORTER_LOG", "XDG_DATA_HOME", "LOCALAPPDATA")}
        real_platform = sys.platform
        try:
            sys.platform = "darwin"
            assert app_dir() == Path.home() / "Library" / "Application Support" / "jevsorter"
            sys.platform = "linux"
            assert app_dir() == Path.home() / ".local" / "share" / "jevsorter"
            os.environ["XDG_DATA_HOME"] = "/x"
            assert app_dir() == Path("/x") / "jevsorter"
            sys.platform = "win32"
            os.environ["LOCALAPPDATA"] = "C:/L"
            assert app_dir() == Path("C:/L") / "jevsorter"
            os.environ["JEVSORTER_HOME"] = "/h"
            assert app_dir() == Path("/h"), "JEVSORTER_HOME must win everywhere"
        finally:
            sys.platform = real_platform
            for k in kept:
                os.environ.pop(k, None)
            os.environ.update({k: v for k, v in kept.items() if v is not None})

        parser = build_parser()
        assert parser.parse_args(["sort"]).dirs == ["."]
        assert parser.parse_args(["sort", "X", "Y"]).dirs == ["X", "Y"]
        assert parser.parse_args(["propose"]).dir == "."
        assert parser.parse_args(["propose", "X"]).dir == "X"

    print("selftest OK")
    return 0


# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="jevsorter",
        description="Sort loose files into a folder's own subfolders using Jev.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("propose", help="list filenames so categories can be drafted")
    p.add_argument("dir", nargs="?", default=".",
                   help="folder to inspect (default: the current directory)")
    p.set_defaults(func=cmd_propose)

    p = sub.add_parser("sort", help="sort folders (dry run unless --apply)")
    p.add_argument("dirs", nargs="*", default=["."], metavar="DIR",
                   help="folders to sort (default: the current directory)")
    p.add_argument("--apply", action="store_true",
                   help="actually move files; without this nothing moves")
    p.add_argument("--recursive", action="store_true",
                   help="also sort each subfolder into its own subfolders")
    p.add_argument("--max-depth", type=int, default=3, dest="max_depth")
    p.add_argument("--resort", action="store_true",
                   help="also reconsider files already inside subfolders")
    p.add_argument("--every", type=int, default=0, metavar="N",
                   help="re-scan every N minutes instead of exiting")
    p.add_argument("--min-age", type=int, default=30, dest="min_age")
    p.add_argument("--min-confidence", type=float, default=0.6,
                   dest="min_confidence")
    p.add_argument("--margin", type=float, default=0.15,
                   help="--resort only: how much a new folder must beat the current")
    p.set_defaults(func=cmd_sort)

    p = sub.add_parser("undo", help="reverse a run")
    p.add_argument("run", nargs="?", default="last")
    p.set_defaults(func=cmd_undo)

    p = sub.add_parser("selftest", help="run built-in assertions")
    p.set_defaults(func=cmd_selftest)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    # Ctrl+C is handled here, not under __main__, so the installed console
    # script behaves the same as running the file directly.
    try:
        return args.func(args)
    except JevError as exc:
        print(exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
