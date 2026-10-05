"""Target account list: a CSV with at least `domain` and `tier` columns."""
import csv

from .domains import normalize_domain


def load_targets(path):
    """Return {normalized_domain: {"tier": str, "company": str}}."""
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            dom = normalize_domain(row.get("domain", ""))
            if dom:
                out[dom] = {"tier": row.get("tier", ""), "company": row.get("company", "")}
    return out


def lookup_target(email_or_domain, targets):
    """Match a domain; if no exact hit, retry with leading subdomains stripped.

    'mail.acme.test' matches 'acme.test'. Returns the target dict or None.
    """
    dom = normalize_domain(email_or_domain)
    labels = dom.split(".")
    while len(labels) >= 2:
        hit = targets.get(".".join(labels))
        if hit:
            return hit
        labels = labels[1:]
    return None
