"""Versioned, reviewable business metric definitions stored in a local JSON file."""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    name: str
    description: str
    calculation: str
    source: str
    grain: str
    owner: str
    filters: str = ""
    status: str = "draft"
    version: int = 1
    updated_at: str = ""


class MetricCatalog:
    """Keep all versions; only an explicitly approved definition is authoritative."""

    def __init__(self, definitions: list[MetricDefinition] | None = None):
        self.definitions = list(definitions or [])

    def add(self, *, key: str, name: str, description: str, calculation: str,
            source: str, grain: str, owner: str, filters: str = "", status: str = "draft") -> MetricDefinition:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
            raise ValueError("Metric key must use lowercase letters, numbers, and underscores")
        if status not in {"draft", "approved"}:
            raise ValueError("Status must be draft or approved")
        if not all(v.strip() for v in (name, description, calculation, source, grain, owner)):
            raise ValueError("Name, meaning, calculation, source, grain, and owner are required")
        version = max((d.version for d in self.definitions if d.key == key), default=0) + 1
        metric = MetricDefinition(key, name.strip(), description.strip(), calculation.strip(), source.strip(),
                                  grain.strip(), owner.strip(), filters.strip(), status, version,
                                  datetime.now(timezone.utc).isoformat())
        self.definitions.append(metric)
        return metric

    def latest(self, key: str, *, approved_only: bool = False) -> MetricDefinition | None:
        matching = [d for d in self.definitions if d.key == key and (not approved_only or d.status == "approved")]
        return max(matching, key=lambda d: d.version, default=None)

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"format_version": 1, "metrics": [asdict(d) for d in self.definitions]}, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "MetricCatalog":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("format_version") != 1 or not isinstance(data.get("metrics"), list):
            raise ValueError("Unsupported metric dictionary format")
        return cls([MetricDefinition(**item) for item in data["metrics"]])
