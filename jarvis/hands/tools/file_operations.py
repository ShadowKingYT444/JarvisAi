"""File operations tool — find files, open files, recent files."""
import asyncio
import logging
import os
import sys
from pathlib import Path
from jarvis.shared.types import ToolResult
logger = logging.getLogger(__name__)

async def find_files(query: str, path: str = "", max_results: int = 10, **kwargs) -> ToolResult:
    """Search for files by name pattern."""
    search_path = Path(path) if path else Path.home()
    if not search_path.exists():
        return ToolResult(success=False, error=f"Path not found: {search_path}")

    loop = asyncio.get_event_loop()

    def _search():
        results = []
        query_lower = query.lower()
        skip_dirs = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'AppData', '.cache'}
        for root, dirs, files in os.walk(search_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                if query_lower in f.lower():
                    full = os.path.join(root, f)
                    try:
                        stat = os.stat(full)
                        results.append({"name": f, "path": full, "size_kb": round(stat.st_size / 1024, 1)})
                    except OSError:
                        results.append({"name": f, "path": full, "size_kb": 0})
                    if len(results) >= max_results:
                        return results
        return results

    results = await loop.run_in_executor(None, _search)

    if not results:
        return ToolResult(success=True, data=[], display_text=f"No files found matching '{query}'.")

    names = [r["name"] for r in results[:5]]
    return ToolResult(success=True, data=results, display_text=f"Found {len(results)} file(s): {', '.join(names)}")

async def open_file(path: str, **kwargs) -> ToolResult:
    """Open a file with its default application."""
    if not Path(path).exists():
        return ToolResult(success=False, error=f"File not found: {path}")
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            await asyncio.create_subprocess_exec("open", path)
        else:
            await asyncio.create_subprocess_exec("xdg-open", path)
        return ToolResult(success=True, display_text=f"Opened {Path(path).name}.")
    except Exception as e:
        return ToolResult(success=False, error=str(e))

async def get_recent_files(count: int = 10, **kwargs) -> ToolResult:
    """Get recently modified files from common user directories."""
    loop = asyncio.get_event_loop()

    def _get_recent():
        home = Path.home()
        search_dirs = [home / "Desktop", home / "Documents", home / "Downloads"]
        files = []
        for d in search_dirs:
            if not d.exists():
                continue
            for f in d.iterdir():
                if f.is_file() and not f.name.startswith('.'):
                    try:
                        files.append({"name": f.name, "path": str(f), "modified": f.stat().st_mtime})
                    except OSError:
                        pass
        files.sort(key=lambda x: x["modified"], reverse=True)
        return files[:count]

    results = await loop.run_in_executor(None, _get_recent)
    names = [r["name"] for r in results[:5]]
    return ToolResult(success=True, data=results, display_text=f"Recent files: {', '.join(names)}")

def register(executor, platform, config):
    executor.register("find_files", find_files)
    executor.register("open_file", open_file)
    executor.register("get_recent_files", get_recent_files)
