"""Tenant-Isolated Sandboxed Filesystem Operations."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from app.core.config import settings
from app.core.context import ExecutionContext

# Windows reserved device names that can hang or crash the OS
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

MAX_FILE_READ_BYTES = 50_000  # 50 KB ceiling


class IsolatedFilesystem:
    """Provides sandboxed file operations strictly isolated to the user's jail directory."""

    def __init__(self, base_sandbox_dir: Optional[Path] = None):
        self.base_dir = base_sandbox_dir or (settings.STORAGE_DIR / "sandboxes")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_user_jail(self, user_id: str) -> Path:
        """Return canonical jail directory for a specific user tenant."""
        safe_user = re.sub(r"[^a-zA-Z0-9_\-]", "_", user_id)
        jail = (self.base_dir / safe_user).resolve()
        jail.mkdir(parents=True, exist_ok=True)
        return jail

    def _resolve_safe_path(self, user_id: str, relative_path: str) -> Path:
        """
        Resolve relative path inside user jail and strictly enforce containment.
        Raises PermissionError or ValueError on jailbreak attempt.
        """
        jail = self.get_user_jail(user_id)
        clean_rel = relative_path.replace("\\", "/").strip().lstrip("/")

        # Check for Windows device names in path segments
        for part in Path(clean_rel).parts:
            stem = part.split(".")[0].upper()
            if stem in WINDOWS_RESERVED_NAMES:
                raise PermissionError(f"Access denied: Reserved device name '{part}' is forbidden.")

        target = (jail / clean_rel).resolve()

        # Enforce boundary: target must be inside jail
        try:
            target.relative_to(jail)
        except ValueError:
            raise PermissionError(f"Access denied: Path '{relative_path}' escapes sandbox jail.")

        return target

    def read_file(self, ctx: ExecutionContext, path: str) -> str:
        """Read text file within user jail."""
        target = self._resolve_safe_path(ctx.user_id, path)
        if not target.exists():
            raise FileNotFoundError(f"File '{path}' does not exist.")
        if not target.is_file():
            raise IsADirectoryError(f"Path '{path}' is a directory, not a file.")

        size = target.stat().st_size
        if size > MAX_FILE_READ_BYTES:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                return f.read(MAX_FILE_READ_BYTES) + f"\n... [Truncated {size - MAX_FILE_READ_BYTES} bytes]"

        return target.read_text(encoding="utf-8", errors="replace")

    def write_file(self, ctx: ExecutionContext, path: str, content: str) -> int:
        """Write text file within user jail."""
        target = self._resolve_safe_path(ctx.user_id, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return len(content)

    def list_directory(self, ctx: ExecutionContext, path: str = "") -> List[Dict[str, str]]:
        """List files and folders within user jail."""
        target = self._resolve_safe_path(ctx.user_id, path)
        if not target.exists():
            raise FileNotFoundError(f"Directory '{path}' does not exist.")
        if not target.is_dir():
            raise NotADirectoryError(f"Path '{path}' is not a directory.")

        results = []
        for p in sorted(target.iterdir()):
            results.append({
                "name": p.name,
                "type": "directory" if p.is_dir() else "file",
                "size_bytes": str(p.stat().st_size if p.is_file() else 0),
            })
        return results

    def delete_file(self, ctx: ExecutionContext, path: str) -> bool:
        """Delete file within user jail."""
        target = self._resolve_safe_path(ctx.user_id, path)
        if not target.exists():
            raise FileNotFoundError(f"File '{path}' does not exist.")
        if target.is_dir():
            raise IsADirectoryError(f"Cannot delete directory '{path}' with delete_file.")
        target.unlink()
        return True


# Global default filesystem instance
isolated_fs = IsolatedFilesystem()
