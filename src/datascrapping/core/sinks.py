from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable, Mapping, Sequence


def sanitize_filename(name: str, max_length: int = 100) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return cleaned[:max_length] or "untitled"


class MarkdownSink:
    """Writes article markdown files with optional YAML front matter."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        title: str,
        source: str,
        body: str,
        dry_run: bool = False,
    ) -> Path:
        path = self.directory / f"{sanitize_filename(title)}.md"
        content = f"---\ntitle: {title}\nsource: {source}\n---\n\n{body}"
        if not dry_run:
            path.write_text(content, encoding="utf-8")
        return path


class CsvSink:
    """Appends row dicts to a CSV file, writing the header once."""

    def __init__(
        self,
        path: Path,
        fieldnames: Sequence[str],
    ) -> None:
        self.path = path
        self.fieldnames = list(fieldnames)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = self.path.exists() and self.path.stat().st_size > 0

    def write_rows(
        self,
        rows: Iterable[Mapping[str, object]],
        dry_run: bool = False,
    ) -> int:
        count = 0
        if dry_run:
            return sum(1 for _ in rows)

        with self.path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames)
            if not self._initialized:
                writer.writeheader()
                self._initialized = True
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in self.fieldnames})
                count += 1
        return count
