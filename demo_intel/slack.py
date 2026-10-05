"""Slack posting via chat.postMessage (bot token). Top-level message, then a thread reply."""
import json
import urllib.request


def _call(token, payload):
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage", data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if not data.get("ok"):
        raise RuntimeError(f"Slack error: {data.get('error')}")
    return data


def post_with_thread(token, channel, top, detail):
    """Post `top`, then `detail` in its thread. Returns the top-level message ts."""
    first = _call(token, {"channel": channel, "text": top, "unfurl_links": False})
    _call(token, {"channel": channel, "thread_ts": first["ts"], "text": detail, "unfurl_links": False})
    return first["ts"]
