from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


class SeenStore:
    """Persists a set of string keys (e.g. profile URLs) for resume/checkpoint."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._seen: set[str] = set()
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                self._seen = {str(item) for item in raw}
            elif isinstance(raw, dict) and "seen" in raw:
                self._seen = {str(item) for item in raw["seen"]}

    def __contains__(self, key: str) -> bool:
        return key in self._seen

    def add(self, key: str) -> None:
        self._seen.add(key)

    def update(self, keys: Iterable[str]) -> None:
        self._seen.update(keys)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"seen": sorted(self._seen)}
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    @property
    def size(self) -> int:
        return len(self._seen)
