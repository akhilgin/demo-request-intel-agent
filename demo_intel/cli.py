"""Command line entry point: python -m demo_intel [--live] [--dry-run] [--fixture FILE]"""
import argparse
import json
import os
import sys

from .pipeline import run
from .sfdc import FixtureSource, SalesforceSource


def main(argv=None):
    p = argparse.ArgumentParser(prog="demo_intel", description=__doc__)
    p.add_argument("--config", default="config.json")
    p.add_argument("--live", action="store_true", help="post to the live channel and record dedup state (default is TEST: DM, no state)")
    p.add_argument("--dry-run", action="store_true", help="print messages instead of posting")
    p.add_argument("--fixture", help="read requests from a JSON file instead of Salesforce (offline)")
    p.add_argument("--lookback-days", type=int, help="override config lookback_days")
    a = p.parse_args(argv)

    cfg_path = a.config if os.path.exists(a.config) else "config.example.json"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    if a.lookback_days:
        cfg["lookback_days"] = a.lookback_days
    base = os.path.dirname(os.path.abspath(cfg_path))

    if a.fixture:
        source = FixtureSource(a.fixture)
        a.dry_run = True  # fixtures never post or write state
    else:
        source = SalesforceSource(cfg["salesforce"])
    try:
        run(cfg, source, mode="live" if a.live else "test", dry_run=a.dry_run, base_dir=base)
    except Exception as e:  # fail loudly, never guess data
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0
