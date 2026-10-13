## Download

| System | File | Notes |
|---|---|---|
| Windows 10/11 (64-bit) | `JevSorter-Setup-<version>.exe` | Per-user install, no admin prompt. |
| macOS (Apple Silicon) | `JevSorter-<version>-macos-arm64.dmg` | Drag to Applications. |
| Linux (x86-64) | `JevSorter-<version>-linux-x86_64.tar.gz` | Unpack, then run `./install.sh`. |

`SHA256SUMS.txt` lists a checksum for each file.

## First run

The builds are not code-signed yet, so each system warns once:

- **Windows:** SmartScreen shows "Windows protected your PC". Click **More info**, then **Run anyway**.
- **macOS:** open the app, and if it is blocked go to **System Settings, Privacy & Security** and choose **Open Anyway**. Or run `xattr -dr com.apple.quarantine /Applications/JevSorter.app`.
- **Linux:** no prompt.

Then open **Settings**, paste your Jev API key (or point it at your own server), and sort a folder from the **Sort** page.

## What's in this release

