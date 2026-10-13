# Jev Sorter

Sorts loose files into a folder's own subfolders. Jev (TypeSafe System One) judges where each file belongs from its filename. Desktop app (customtkinter) plus a stdlib-only CLI sharing one engine. MIT licensed. Public repo: umarshahzad0001/jev-sorter.

## Layout

| File | Role |
|---|---|
| `jevsorter.py` | Engine and CLI. `plan_folder` (asks Jev, moves nothing) and `apply_moves` (re-checks, moves, logs) are split on purpose: the window previews before applying. `JevError` replaces `SystemExit` so worker threads never die silently. |
| `jevsorter_gui.py` | The window. Worker threads post to a queue that `_poll` drains on the Tk thread. Never touch widgets from a worker. |
| `jevsorter_theme.py` | umarca.com brand tokens as (light, dark) pairs, fonts, pill buttons, `PageTitle`. Follow the `brand` skill. |
| `jevsorter_dialogs.py` | Confirm dialog ("Don't ask me again") and the preset/subfolder checklist. |
| `jevsorter_presets.py` | Starter category packs. Descriptions carry the quality, so keep them specific. |
| `jevsorter_settings.py` | Settings plus key storage: DPAPI on Windows, keyring on macOS and Linux, a 0600 file as last resort. |
| `jevsorter_tray.py` | Tray icon, login item per OS, single-instance socket. |
| `tests/` | `gui_smoke.py` drives the real window against `stub_server.py`. `readme_shots.py` regenerates `docs/screenshots` (Windows only). |

## Run the checks

```bash
py jevsorter.py selftest
py jevsorter_settings.py
py jevsorter_tray.py
py jevsorter_presets.py
py tests/gui_smoke.py          # add a folder path as an argument to save screenshots
```

`build.ps1` runs the first four, then PyInstaller and Inno Setup. `build.sh` does the same for macOS and Linux. Release flow is in the README.

## Rules that matter here

- **Dry run before apply.** Never move a user's real files without showing a preview first. The CLI defaults to a dry run, and the window previews.
- **Never overwrite, never move in-flight files.** Those are code rules, not questions for the model.
- **Test installs must not touch the real install.** The installer's AppId and Run-key name are overridable: build a test installer with `/DAppGuid={{...}` and `/DRunName=JevSorterTest`, install to a temp dir with `/TASKS=`, and clean up with its own `unins000.exe`. A shared AppId once deleted the real install's uninstall entry.
- **Kill test processes by PID, never `Stop-Process -Name JevSorter`.** The user may have their own copy running.
- **Never write the real Windows Run key from tests.** `gui_smoke.py` patches `set_autostart`.
- **Use `JEVSORTER_HOME`, `JEVSORTER_LOG` and `JEVSORTER_NO_KEYRING` in tests** so real settings, history and the keychain are never used. Clear `JEV_API_KEY` too.
- **No em dashes** in any user-facing text, comments, commits or docs (brand rule). Sentence case, plain and specific.
- **Do not publish or tag without being asked.** The release workflow runs on a `v*` tag that matches `pyproject.toml`.

## Platform status

- **Windows:** the most tested (Windows 11). Tray on by default, installer is per-user.
- **Linux:** tested in a `python:3.12` container under Xvfb (self-tests, full GUI smoke, PyInstaller build, frozen launch, `install.sh`). Tray off by default because GNOME has no tray.
- **macOS:** never run on a real Mac. No tray (pystray fights Tk's main loop), the Dock keeps the app alive, fonts load through CoreText via ctypes. Treat every macOS path as unverified.
- **Not code-signed.** SmartScreen and Gatekeeper warn once. The owner chose to leave it unsigned.

## Gotchas

- Hidden frames and rows need `border_width=0`: the theme gives every `CTkFrame` a card border.
- customtkinter scales `geometry()` by the display scale. Size windows from `winfo_screenwidth() / scaling`.
- A `CTkToplevel` closed within about 200 ms can raise `bad window path name` from its delayed focus call. `App.report_callback_exception` swallows that one error.
- `CTkSegmentedButton` has one text colour, so `th.Segmented` recolours per state.
- Screenshots use `tests/shotutil.py` (PrintWindow) so other windows never end up in the image.
- Saved API keys show as a masked value in the box (`KEY_MASK`), never empty and never the real key.
- `build/lib` and `jevsorter.egg-info` are tracked in git by accident. Remove them from the index when committing.

More detail on the packaging and GUI lessons: `D:\Development\Claude Notes\python_gui_packaging_gotchas.md`.
