"""Message rendering (Slack mrkdwn) and the optional LLM prose summary.

The template is the default and always works. The LLM, when enabled, only writes
one short prose paragraph from the structured facts. It never decides what posts.
"""
import json
import os
import urllib.request


def _link(text, url):
    return f"<{url}|{text}>" if url else text


def _money(amount):
    try:
        return f"${float(amount):,.0f}"
    except (TypeError, ValueError):
        return ""


def render_top(facts, low_fit_tiers=()):
    badge = f" (Tier {facts['tier']})" if facts["tier"] else ""
    lines = [f":dart: *Target demo request: {_link(facts['company'] or 'Unknown company', facts['account_url'])}*{badge}"]
    who = " · ".join(x for x in (facts["name"], facts["title"], f"`{facts['email']}`" if facts["email"] else "") if x)
    lines.append(who)
    lines.append(f"`ref:{facts['id']}`")
    return "\n".join(lines)


def render_thread(facts, prose="", low_fit_tiers=()):
    out = []
    if prose:
        out.append(prose)
        out.append("")
    if facts["tier"] and facts["tier"] in set(low_fit_tiers):
        out.append(f"> :warning: On the target list but low fit (Tier {facts['tier']}). Triage accordingly.")
        out.append("")
    head = []
    if facts["linkedin"]:
        head.append(_link("LinkedIn", facts["linkedin"]))
    if facts["account_owner"]:
        head.append(f"Account owner: {facts['account_owner']}")
    if head:
        out.append(" · ".join(head))
        out.append("")

    a = facts["attribution"]
    parts = [f"{label}: {a[k]}" for k, label in
             (("source", "Source"), ("medium", "Medium"), ("campaign", "Campaign"), ("term", "Term")) if a.get(k)]
    tail = []
    if a.get("landing_page"):
        tail.append(f"Landing page: {a['landing_page']}")
    if facts["submitted"]:
        tail.append(f"Submitted: {facts['submitted']}")
    if parts or tail:
        out.append("*How they got here*")
        if parts:
            out.append(" · ".join(parts))
        if tail:
            out.append(" · ".join(tail))
        out.append("")

    if facts["campaigns"]:
        out.append("*Recent activity*")
        for c in facts["campaigns"]:
            out.append(f"• {c['name']}" + (f" ({c['status']})" if c["status"] else ""))
        out.append("")

    crm = [_link("Account", facts["account_url"])] if facts["account_url"] else []
    for o in facts["open_opps"]:
        bits = [x for x in (o["stage"], _money(o["amount"]), f"({o['type']})" if o["type"] else "") if x]
        crm.append("Open opp: " + _link(o["name"] or "Opportunity", o["url"]) + (" · " + " · ".join(bits) if bits else ""))
    if not facts["open_opps"] and crm:
        crm.append("No open opportunity")
    if crm:
        out.append("*CRM*")
        out.append(" · ".join(crm))
    return "\n".join(out).rstrip()


def llm_prose(facts, llm_cfg, post=None):
    """Return a short factual paragraph from the Anthropic Messages API, or '' on any error."""
    key = os.environ.get(llm_cfg.get("api_key_env", "ANTHROPIC_API_KEY"), "")
    if not key:
        return ""
    allowed = {k: facts[k] for k in ("name", "title", "company", "tier", "account_owner",
                                     "attribution", "open_opps", "campaigns", "submitted")}
    prompt = ("Write 2 or 3 plain sentences summarizing this inbound demo request for a sales rep. "
              "Use only the facts in the JSON. No advice, no speculation, no marketing language. "
              "If a fact is missing, leave it out.\n\n" + json.dumps(allowed, default=str))
    body = {"model": llm_cfg.get("model", "claude-sonnet-5-5"),
            "max_tokens": int(llm_cfg.get("max_tokens", 400)),
            "messages": [{"role": "user", "content": prompt}]}
    try:
        send = post or _post_anthropic
        resp = send(body, key)
        return "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text").strip()
    except Exception:
        return ""


def _post_anthropic(body, key):
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)
