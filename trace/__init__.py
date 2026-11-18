"""Persistent step records."""
import json
from datetime import datetime, timezone
from pathlib import Path


class TraceWriter:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, record):
        record = {'ts': datetime.now(timezone.utc).isoformat(), **record}
        with self.path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
