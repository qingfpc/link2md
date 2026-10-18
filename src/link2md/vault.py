"""Write notes into an Obsidian vault and remember URLs that were already saved."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from link2md.config import AppConfig
from link2md.errors import ConfigError
from link2md.filenames import safe_filename
from link2md.urls import canonical_url

_INDEX_NAME = ".link2md-index.json"
_SOURCE_RE = re.compile(r"^source_url:\s*(.+)\s*$", re.MULTILINE)


class Vault:
    def __init__(self, config: AppConfig) -> None:
        root = (config.vault.path or "").strip()
        if not root:
            raise ConfigError(
                "还没有配置 Obsidian 仓库路径。请在配置里填写 vault.path，或设置环境变量 LINK2MD_VAULT。"
            )
        self.root = Path(root).expanduser()
        self.notes_dir = self.root / config.vault.notes_dir
        self.attachments_dir = self.root / config.vault.attachments_dir
        self.index_path = self.notes_dir / _INDEX_NAME

    def find(self, url: str) -> Path | None:
        key = canonical_url(url)
        indexed = self._read_index().get("items", {}).get(key, {})
        relative = indexed.get("path")
        if relative:
            path = self.notes_dir / relative
            if path.is_file():
                return path
        if not self.notes_dir.is_dir():
            return None
        for path in sorted(self.notes_dir.glob("*.md")):
            found = _front_matter_url(path)
            if found and canonical_url(found) == key:
                return path
        return None

    def write(self, *, canonical: str, title: str, markdown: str, existing: Path | None) -> Path:
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        if existing is not None:
            path = existing
        else:
            path = self.notes_dir / safe_filename(title, canonical)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(markdown, encoding="utf-8")
        os.replace(temporary, path)
        self._remember(canonical, path)
        return path

    def attachment_dir(self, note_path: Path) -> Path:
        return self.attachments_dir / note_path.stem

    def _remember(self, canonical: str, path: Path) -> None:
        data = self._read_index()
        items = data.setdefault("items", {})
        items[canonical] = {"path": path.name}
        data["version"] = 1
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.index_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.index_path)

    def _read_index(self) -> dict:
        if not self.index_path.is_file():
            return {"version": 1, "items": {}}
        try:
            loaded = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"version": 1, "items": {}}
        if not isinstance(loaded, dict):
            return {"version": 1, "items": {}}
        loaded.setdefault("items", {})
        return loaded


def _front_matter_url(path: Path) -> str | None:
    try:
        head = path.read_text(encoding="utf-8")[:4000]
    except OSError:
        return None
    if not head.startswith("---"):
        return None
    end = head.find("\n---", 3)
    block = head[:end] if end != -1 else head
    match = _SOURCE_RE.search(block)
    if not match:
        return None
    raw = match.group(1).strip()
    if raw.startswith(("'", '"')):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw.strip("'\"")
    return raw
