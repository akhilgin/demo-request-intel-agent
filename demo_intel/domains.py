"""Domain normalization and the filter lists (freemail, internal)."""

FREEMAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "hotmail.com",
    "outlook.com", "live.com", "msn.com", "aol.com", "icloud.com", "me.com",
    "mac.com", "proton.me", "protonmail.com", "gmx.com", "mail.com", "zoho.com",
    "yandex.com", "qq.com", "163.com", "126.com", "hey.com", "pm.me",
})


def normalize_domain(value):
    """Return a bare lowercase domain from an email, URL, or domain string.

    'Jane@WWW.Acme.test' -> 'acme.test'; 'https://www.acme.test/x' -> 'acme.test'.
    """
    d = (value or "").strip().lower()
    if not d:
        return ""
    if "@" in d:
        d = d.rsplit("@", 1)[-1]
    d = d.split("//")[-1].split("/")[0].split("?")[0].split(":")[0].strip(".")
    if d.startswith("www."):
        d = d[4:]
    return d


def is_freemail(domain, extra=()):
    d = normalize_domain(domain)
    return d in FREEMAIL_DOMAINS or d in {normalize_domain(x) for x in extra}


def is_internal(domain, internal_domains=()):
    d = normalize_domain(domain)
    return bool(d) and d in {normalize_domain(x) for x in internal_domains}
