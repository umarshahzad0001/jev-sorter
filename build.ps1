# Builds dist\JevSorter\JevSorter.exe, then dist\JevSorter-Setup-<version>.exe (Windows).
# Needs: py -m pip install customtkinter pyinstaller pillow pystray ; Inno Setup 6 (winget install JRSoftware.InnoSetup)
# Set $env:PYTHON to use an interpreter other than the `py` launcher (CI does).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = if ($env:PYTHON) { $env:PYTHON } else { "py" }
$version = (Select-String -Path pyproject.toml -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
& $py jevsorter.py selftest | Select-Object -Last 1
foreach ($t in "jevsorter_settings.py", "jevsorter_tray.py", "jevsorter_presets.py") {
    & $py $t
    if ($LASTEXITCODE) { throw "$t failed" }
}

Remove-Item -Recurse -Force build\gui, dist -ErrorAction SilentlyContinue
& $py -m PyInstaller --noconfirm --clean --windowed --onedir --name JevSorter `
    --icon "$PSScriptRoot\jevsorter.ico" --add-data "$PSScriptRoot\jevsorter.ico;." --add-data "$PSScriptRoot\assets;assets" `
    --add-data "$PSScriptRoot\licenses;licenses" --add-data "$PSScriptRoot\LICENSE;." --add-data "$PSScriptRoot\THIRD_PARTY_NOTICES.md;." `
    --collect-data customtkinter --hidden-import pystray._win32 `
    --workpath build\gui --specpath build\gui "$PSScriptRoot\jevsorter_gui.py"
if ($LASTEXITCODE) { throw "PyInstaller failed" }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found" }
& $iscc "/DAppVersion=$version" installer.iss
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Get-ChildItem dist\JevSorter-Setup-*.exe | Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
