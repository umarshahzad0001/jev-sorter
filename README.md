# Jev Sorter

Sorts loose files into a folder's own subfolders. Jev (TypeSafe System One) judges
which subfolder each file belongs in; the script owns every decision about what
actually moves.

Pure stdlib, so it pulls in no dependencies.

## Install

```bash
uv tool install .
```

That puts a real `jevsorter` executable on your PATH, so it runs from any directory
in any shell. `pipx install .` works the same way if you'd rather use that.

Edited the code? Reinstall with `uv tool install . --force`, or install once with
`--editable` and skip the step from then on. To remove it: `uv tool uninstall jevsorter`.

You'll also need `JEV_API_KEY` set as a user environment variable:

```bash
setx JEV_API_KEY "your-key-here"
```

## Quick start

```bash
cd D:\Downloads
jevsorter propose    # list filenames so you can write categories
jevsorter sort       # DRY RUN - prints decisions, moves nothing
jevsorter sort --apply
jevsorter undo last
```

`propose` and `sort` default to the directory you're standing in. Name folders
explicitly when you want others, and `sort` takes as many as you like:

```bash
jevsorter sort D:\Downloads D:\Documents D:\Study
jevsorter selftest   # assertions, no network, no files touched
```

## How it decides

For each file it sends one Choice question to Jev carrying the file's name,
extension, size and modified date. The options are your categories plus `__stay__`,
meaning leave it alone. Jev returns a probability for every option and a confidence
score.

A file moves only when the chosen option is a real folder and confidence is at or
above `--min-confidence` (default 0.6). Everything else stays exactly where it is.
There's no `_Review` folder, because that's just a second pile to sort.

It reads filenames, not file contents. It won't open a PDF or a Word document.

## Categories

Two sources, in order:

1. **`.jevsorter.json` in the folder.** The good option. Folders named here get
   created on first use, and only under `--apply`.
2. **The folder's existing subfolders**, used when there's no `.jevsorter.json`. Each
   one is described to Jev by up to 5 filenames already sitting inside it.

```json
{
  "categories": {
    "Invoices": "Issued sales and purchase invoices carrying a reference number.",
    "Screenshots": "Screenshot_*, IMG_*, and other loose images."
  }
}
```

Descriptions do most of the work here. Measured on real files:
`COOLX_General_Ledger_to_31-07-2026.xlsx` scored 0.47 against a bare empty folder
called "Client Work" and stayed put. The same file scored **0.98** once that folder
had a one-line description of what Coolx work actually looks like. So if files are
staying put that shouldn't, write better descriptions before you touch the threshold.

## Options for `sort`

| Flag | Default | What it does |
|---|---|---|
| `--apply` | off | Actually move files. Without it, nothing moves. |
| `--recursive` | off | Also sort each subfolder into *its own* subfolders. |
| `--max-depth` | 3 | How far `--recursive` descends. |
| `--resort` | off | Also reconsider files already filed in subfolders. |
| `--every N` | off | Re-scan every N minutes instead of exiting. |
| `--min-age` | 30 | Skip files modified in the last N seconds. |
| `--min-confidence` | 0.6 | Below this, leave the file alone. |
| `--margin` | 0.15 | `--resort` only: how much a new folder must beat the current one. |

### `--recursive` sorts each folder into its own subfolders

It doesn't build one flat list of every folder in the tree, and it can't: Choice caps
at 255 options, and `D:\Development` alone holds 41,649 directories. Each folder is
its own independent job, so files never jump between branches.

It never descends into `node_modules`, `.git`, `.gradle`, `.kotlin`, `venv`,
`__pycache__`, `site-packages`, `.next`, `.terraform`, `.tox`, `$RECYCLE.BIN`, or
any dot-folder.

The folder list is taken before anything moves, so a category folder created during
this run isn't itself sorted until the next one. Run it twice if you care.

`--recursive` and `--resort` can't be combined, and the script will tell you so. A
file inside a subfolder would get judged twice, and the second pass loses the
`--margin` protection. Run them as two separate passes.

### `--resort` is the one that can undo your filing

Normal runs only touch files sitting loose in a folder, and anything already filed is
never moved. `--resort` reconsiders filed files too, which is useful right after you
add a category and risky everywhere else. A file only leaves its current folder when
confidence clears the threshold *and* the new folder beats the current one by
`--margin`. Ties stay put.

Dry-run it first. Always.

## Safety

- **Dry run is the default.** Moving requires typing `--apply`.
- **It never overwrites.** Collisions become `name (1).ext`, `name (2).ext`.
- **In-flight downloads are skipped** (`.crdownload`, `.part`, `.partial`, `.tmp`,
  `.download`, `.opdownload`, `.aria2`), along with anything modified in the last
  `--min-age` seconds. That's a code rule, never a question put to the model.
- **Also skipped:** Office lock files (`~$*`), `desktop.ini`, `thumbs.db`, and
  `.lnk` / `.url` shortcuts, which break when you move them.
- **A folder with more than 255 categories is refused**, not quietly shortlisted.
  Shortlisting would hide the real reason files stayed put.
- **Files in use** get logged and skipped rather than crashing the run.
- **Every move is logged** to `%LOCALAPPDATA%\jevsorter\moves.jsonl` with the choice,
  confidence and top probabilities. `undo last` (or `undo <run-id>`) replays a run
  backwards, and only restores a file if its original path is still free.
- **The API key comes from `JEV_API_KEY` and nowhere else.** It's never stored in a
  config file and never printed.

## Cost

A real 208-file run took 27 seconds and cost about a cent. Jev is $0.042 per million
input tokens and output is free. One request per file, 8 at a time, against a limit
of 1,200 per minute.
