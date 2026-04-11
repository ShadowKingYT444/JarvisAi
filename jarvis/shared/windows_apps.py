"""Windows application discovery helpers."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_UNINSTALL_ROOTS = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
    r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)


def _iter_uninstall_entries():
    try:
        import winreg
    except ImportError:
        return

    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for root in _UNINSTALL_ROOTS:
            try:
                with winreg.OpenKey(hive, root) as handle:
                    count = winreg.QueryInfoKey(handle)[0]
                    for index in range(count):
                        try:
                            subkey_name = winreg.EnumKey(handle, index)
                            with winreg.OpenKey(handle, subkey_name) as subkey:
                                try:
                                    display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                except OSError:
                                    display_name = ""
                                try:
                                    install_location = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                                except OSError:
                                    install_location = ""
                                try:
                                    display_icon = winreg.QueryValueEx(subkey, "DisplayIcon")[0]
                                except OSError:
                                    display_icon = ""
                                yield {
                                    "display_name": str(display_name),
                                    "install_location": str(install_location),
                                    "display_icon": str(display_icon),
                                }
                        except OSError:
                            continue
            except OSError:
                continue


def find_app_path(*display_names: str, exe_names: list[str] | None = None) -> Path | None:
    """Find an installed Windows application executable."""
    exe_names = exe_names or []

    for exe_name in exe_names:
        located = shutil.which(exe_name)
        if located:
            return Path(located)

    lowered = [name.lower() for name in display_names]
    for entry in _iter_uninstall_entries():
        display_name = entry["display_name"].lower()
        if not any(name in display_name for name in lowered):
            continue

        display_icon = entry["display_icon"].split(",")[0].strip().strip('"')
        if display_icon and Path(display_icon).exists():
            return Path(display_icon)

        install_location = entry["install_location"].strip().strip('"')
        if install_location:
            install_dir = Path(install_location)
            for exe_name in exe_names:
                candidate = install_dir / exe_name
                if candidate.exists():
                    return candidate
            for candidate in install_dir.glob("*.exe"):
                return candidate

    common_roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
        Path(os.environ.get("ProgramFiles", "")),
        Path(os.environ.get("ProgramFiles(x86)", "")),
    ]
    for root in common_roots:
        if not root.exists():
            continue
        for display_name in display_names:
            direct = root / display_name
            if direct.exists():
                for exe_name in exe_names:
                    candidate = direct / exe_name
                    if candidate.exists():
                        return candidate

    return None


def find_chrome_path() -> Path | None:
    return find_app_path("Google Chrome", exe_names=["chrome.exe", "chrome"])


def find_obsidian_path() -> Path | None:
    return find_app_path("Obsidian", exe_names=["Obsidian.exe", "obsidian"])


def find_warp_path() -> Path | None:
    return find_app_path("Warp", exe_names=["Warp.exe", "warp.exe", "warp"])
