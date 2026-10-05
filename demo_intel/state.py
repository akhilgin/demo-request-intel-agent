"""Deterministic dedup state: a JSON file of {record_id: iso_utc_posted}.

The lookback window is wide on purpose (it tolerates delays); this file is what
prevents re-posting. It is the only source of truth for "already posted".
"""
import json
import os
from datetime import datetime, timezone


class State:
    def __init__(self, path):
        self.path = path
        self.data = {}
        try:
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.data = {}

    def is_new(self, record_id):
        return record_id not in self.data

    def filter_new(self, ids):
        return [i for i in ids if self.is_new(i)]

    def mark(self, record_id, now=None):
        stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.data.setdefault(record_id, stamp)
        self.save()

    def save(self):
        folder = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(folder, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)
