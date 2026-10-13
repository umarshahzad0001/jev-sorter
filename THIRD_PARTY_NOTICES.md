# Third-party notices

Jev Sorter is released under the [MIT License](LICENSE). The installers and archives also contain the third-party software below. Each one keeps its own license, and the full text is in the `licenses` folder that ships with the app.

## Fonts

| Font | Copyright | License | Text |
|---|---|---|---|
| Plus Jakarta Sans | Copyright 2020 The Plus Jakarta Sans Project Authors (https://github.com/tokotype/PlusJakartaSans) | SIL Open Font License 1.1 | `licenses/OFL-PlusJakartaSans.txt` |
| Caveat | Copyright 2014 The Caveat Project Authors (https://github.com/googlefonts/caveat) | SIL Open Font License 1.1 | `licenses/OFL-Caveat.txt` |

Both fonts reach the app as static weights cut from the variable fonts published by their authors (Plus Jakarta Sans at 400, 600, 700 and 800, Caveat at 700). The family names were adjusted per weight so each can be addressed by name. Neither font declares a Reserved Font Name. The fonts are bundled with the app and are not sold on their own, as the license requires.

## Python libraries bundled in the app

| Package | License | Text |
|---|---|---|
| customtkinter (Tom Schimansky) | MIT | `licenses/MIT-customtkinter.txt` |
| darkdetect (Alberto Sottile) | BSD-3-Clause | `licenses/BSD-3-Clause-darkdetect.txt` |
| Pillow | MIT-CMU (HPND), plus the licenses of the libraries inside its wheels | `licenses/MIT-CMU-Pillow.txt` |
| pystray (Moses Palmér), Windows and Linux builds | LGPL-3.0 | `licenses/LGPL-3.0-pystray.txt`, `licenses/GPL-3.0-pystray.txt` |
| keyring and its dependencies, macOS and Linux builds | MIT, BSD and Apache-2.0 | in each package's `dist-info` folder inside the app |

### pystray (LGPL-3.0)

pystray is used unmodified. Its source is at https://github.com/moses-palmer/pystray. In the Windows and Linux builds it is an ordinary Python package inside the app folder (`_internal/pystray`), so you can replace it with another build of the same version. The LGPL applies to pystray only and does not change the license of Jev Sorter. The macOS build leaves pystray out.

## Runtime and build tools

- **Python and Tcl/Tk** are bundled by PyInstaller. Python is under the [PSF License](https://docs.python.org/3/license.html), and Tcl/Tk under its [BSD-style license](https://www.tcl-lang.org/software/tcltk/license.html).
- **PyInstaller** builds the executables. Its bootloader is GPL-2.0-or-later with an exception that lets the programs it produces use any license, so it places no condition on Jev Sorter.
- **Inno Setup** builds the Windows installer. It places no condition on the installers it produces.

## The Jev API

Jev is a model from TypeSafe. Jev Sorter calls its API, and your use of that API is covered by TypeSafe's own terms.
