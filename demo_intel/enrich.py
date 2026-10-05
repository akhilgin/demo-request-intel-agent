"""Turn a raw Contact record into a flat facts dict, and build record links."""
from .targets import lookup_target

PLACEHOLDERS = {"", "none", "null", "n/a", "unknown", "-"}


def clean(value):
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s.lower() in PLACEHOLDERS else s


def record_url(instance_url, sobject, record_id):
    """Lightning record link. `instance_url` is your org's base URL (no trailing slash)."""
    if not (instance_url and record_id):
        return ""
    base = instance_url.rstrip("/").replace(".my.salesforce.com", ".lightning.force.com")
    return f"{base}/lightning/r/{sobject}/{record_id}/view"


def _nested(rec, *path):
    cur = rec
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def build_facts(rec, target, cfg_fields, source, instance_url, include_campaigns=True):
    """Collect everything the message needs. `source` provides opps and campaigns."""
    f = cfg_fields
    account_id = clean(rec.get("AccountId"))
    first, last = clean(rec.get("FirstName")), clean(rec.get("LastName"))
    name = clean(rec.get("Name")) or f"{first} {last}".strip()

    opps = []
    if account_id:
        for o in source.open_opportunities(account_id):
            opps.append({
                "name": clean(o.get("Name")), "stage": clean(o.get("StageName")),
                "amount": o.get("Amount"), "type": clean(o.get("Type")),
                "url": record_url(instance_url, "Opportunity", o.get("Id")),
            })
    campaigns = []
    if include_campaigns:
        for m in source.campaign_activity(rec["Id"]):
            cname = clean(_nested(m, "Campaign", "Name"))
            if cname:
                campaigns.append({"name": cname, "status": clean(m.get("Status"))})

    return {
        "id": rec["Id"],
        "name": name,
        "email": clean(rec.get("Email")),
        "title": clean(rec.get("Title")),
        "company": clean(_nested(rec, "Account", "Name")) or target.get("company", ""),
        "tier": target.get("tier", ""),
        "linkedin": clean(rec.get(f.get("linkedin", ""))),
        "account_owner": clean(_nested(rec, "Account", "Owner", "Name")),
        "account_url": record_url(instance_url, "Account", account_id),
        "contact_url": record_url(instance_url, "Contact", rec["Id"]),
        "submitted": clean(rec.get(f.get("demo_date", ""))),
        "attribution": {k: clean(rec.get(f.get(k, ""))) for k in
                        ("source", "medium", "campaign", "term", "landing_page")},
        "open_opps": opps,
        "campaigns": campaigns,
    }


def classify(rec, targets, internal, freemail_extra):
    """Return (target_dict_or_None, drop_reason). Reason is '' when the record is kept."""
    from .domains import is_freemail, is_internal, normalize_domain
    email = clean(rec.get("Email"))
    dom = normalize_domain(email)
    if not dom:
        return None, "no email"
    if is_internal(dom, internal):
        return None, "internal"
    if is_freemail(dom, freemail_extra):
        return None, "freemail"
    hit = lookup_target(dom, targets)
    if not hit:
        return None, "not a target"
    return hit, ""
