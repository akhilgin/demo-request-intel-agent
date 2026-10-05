"""fetch -> filter -> dedup -> enrich -> summarize -> post -> record state."""
import os

from .enrich import build_facts, classify
from .render import llm_prose, render_thread, render_top
from .slack import post_with_thread
from .state import State
from .targets import load_targets


def run(cfg, source, mode="test", dry_run=False, base_dir=".", out=print, poster=post_with_thread):
    """Run once. mode is 'test' (DM, [TEST] prefix, no state writes) or 'live'.

    Returns a list of (record_id, top, detail) for everything that was (or would be) posted.
    """
    def path(p):
        return p if os.path.isabs(p) else os.path.join(base_dir, p)

    targets = load_targets(path(cfg["target_list"]))
    state = State(path(cfg["state_path"]))
    fields = cfg["fields"]

    records = source.demo_requests(fields, cfg.get("lookback_days", 2), cfg.get("limit", 50))
    latest = {}
    for rec in records:  # same email twice: keep the newest (query is CreatedDate DESC)
        latest.setdefault((rec.get("Email") or rec["Id"]).lower(), rec)

    kept, dropped = [], []
    for rec in latest.values():
        hit, reason = classify(rec, targets, cfg.get("internal_domains", []),
                               cfg.get("extra_freemail_domains", []))
        (dropped if reason else kept).append((rec, hit) if not reason else (rec, reason))

    new = [(r, t) for r, t in kept if state.is_new(r["Id"])]
    out(f"{len(records)} demo requests, {len(kept)} target, {len(new)} new, "
        f"{len(dropped)} dropped ({', '.join(sorted({d[1] for d in dropped})) or 'none'})")
    if not new:
        return []  # nothing new: post nothing

    token = os.environ.get(cfg["slack"].get("token_env", "SLACK_BOT_TOKEN"), "")
    channel = cfg["slack"]["live_channel_id"] if mode == "live" else cfg["slack"]["test_user_id"]
    llm_cfg = cfg.get("llm", {})
    posted = []
    for rec, target in new:
        facts = build_facts(rec, target, fields, source, getattr(source, "instance_url", ""),
                            cfg.get("include_campaign_activity", True))
        prose = llm_prose(facts, llm_cfg) if llm_cfg.get("enabled") else ""
        top = render_top(facts)
        detail = render_thread(facts, prose, cfg.get("low_fit_tiers", []))
        if mode != "live":
            top = ":test_tube: *[TEST]* " + top
        if dry_run:
            out("--- top-level ---\n" + top + "\n--- thread ---\n" + detail + "\n")
        else:
            if not token:
                raise RuntimeError("Slack token env var is not set.")
            poster(token, channel, top, detail)
            if mode == "live":  # test posts never mark state, or they would hide the real alert
                state.mark(rec["Id"])
        posted.append((rec["Id"], top, detail))
    return posted
