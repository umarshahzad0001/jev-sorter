# Jev Sorter

Sorts loose files into a folder's own subfolders. Jev (TypeSafe System One) judges
which subfolder each file belongs in; the script owns every decision about what
actually moves.

Pure stdlib, so it pulls in no dependencies of its own.

## Prerequisites

- **Python 3.9 or later**, with `pip`.
- **[pipx](https://pipx.pypa.io/)** to install it as an isolated CLI tool, the same
  way you'd install any other command-line program. If you don't have it yet, the
  install commands below cover that too.
- **A Jev API key**, set as the `JEV_API_KEY` environment variable. Get one at
  [typesafe.ai](https://typesafe.ai) — the key is never stored in a file or printed
  by this tool, only read from the environment.

## Install

Run from inside this project folder (the one with `pyproject.toml`).

### Windows (PowerShell)

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
# open a new terminal so the updated PATH takes effect, then:
pipx install .
```

### macOS

```bash
brew install pipx    # or: python3 -m pip install --user pipx
pipx ensurepath
# open a new terminal, then:
pipx install .
```

### Linux

```bash
sudo apt install pipx    # Debian/Ubuntu — or use your distro's package manager
pipx ensurepath
# open a new terminal, then:
pipx install .
```

All three put a `jevsorter` command on your PATH, in its own isolated environment,
runnable from any directory. To pick up code changes: `pipx install . --force`.
To remove it: `pipx uninstall jevsorter`.

### Set the API key

**Windows (PowerShell)** — persists across terminals:
```powershell
setx JEV_API_KEY "your-key-here"
```

**macOS / Linux** — add to your shell profile (`~/.zshrc`, `~/.bashrc`, or similar)
so it persists:
```bash
echo 'export JEV_API_KEY="your-key-here"' >> ~/.zshrc
source ~/.zshrc
```

## Quick start

```bash
cd ~/Downloads
jevsorter propose    # list filenames so you can write categories
jevsorter sort       # DRY RUN - prints decisions, moves nothing
jevsorter sort --apply
jevsorter undo last
```

`propose` and `sort` default to the directory you're standing in. Name folders
explicitly when you want others, and `sort` takes as many as you like:

```bash
jevsorter sort ~/Downloads ~/Documents ~/Study
jevsorter selftest    # assertions, no network, no files touched
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
at 255 options, and one real project folder on this machine holds over 40,000
directories. Each folder is its own independent job, so files never jump between
branches.

It never descends into `node_modules`, `.git`, `.gradle`, `.kotlin`, `venv`,
`__pycache__`, `site-packages`, `.next`, `.terraform`, `.tox`, `$RECYCLE.BIN`,
`System Volume Information`, or any dot-folder.

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
- **Also skipped:** Office lock files (`~$*`), `desktop.ini`, `thumbs.db`, and, on
  Windows, `.lnk` / `.url` shortcuts, which break when you move them.
- **A folder with more than 255 categories is refused**, not quietly shortlisted.
  Shortlisting would hide the real reason files stayed put.
- **Files in use** get logged and skipped rather than crashing the run.
- **Every move is logged**, one run per undo:
  - Windows: `%LOCALAPPDATA%\jevsorter\moves.jsonl`
  - macOS / Linux: `~/jevsorter/moves.jsonl`

  Each line records the choice, confidence and top probabilities. `undo last` (or
  `undo <run-id>`) replays a run backwards, and only restores a file if its original
  path is still free.
- **The API key comes from `JEV_API_KEY` and nowhere else.** It's never stored in a
  config file and never printed.

## Cost

A real 208-file run took 27 seconds and cost about a cent. Jev is $0.042 per million
input tokens and output is free. One request per file, 8 at a time, against a limit
of 1,200 per minute.
