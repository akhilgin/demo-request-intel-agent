"""Minimal Salesforce REST client (SOQL only, read-only) plus an offline fixture source.

Auth, in order:
  1. env vars named in config (default SF_INSTANCE_URL + SF_ACCESS_TOKEN)
  2. the Salesforce CLI: `sf org display --target-org <alias> --json`
Nothing is ever written to Salesforce.
"""
import json
import os
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


def soql_quote(value):
    """Escape a string for use inside a SOQL single-quoted literal."""
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def build_contact_query(fields, since_date, limit):
    f = fields
    cols = ["Id", "FirstName", "LastName", "Name", "Email", "Title", "AccountId",
            "Account.Name", "Account.Owner.Name", "CreatedDate", f["demo_date"]]
    for key in ("linkedin", "source", "medium", "campaign", "term", "landing_page"):
        if f.get(key):
            cols.append(f[key])
    return (f"SELECT {', '.join(cols)} FROM Contact "
            f"WHERE {f['demo_flag']} = true AND {f['demo_date']} >= {since_date} "
            f"ORDER BY CreatedDate DESC LIMIT {int(limit)}")


def since_date(lookback_days, now=None):
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d")


class SalesforceSource:
    def __init__(self, cfg):
        self.cfg = cfg
        self.version = cfg.get("api_version", "v60.0")
        self.instance_url, self.token = self._auth()

    def _auth(self):
        url = os.environ.get(self.cfg.get("instance_url_env", "SF_INSTANCE_URL"))
        tok = os.environ.get(self.cfg.get("access_token_env", "SF_ACCESS_TOKEN"))
        if url and tok:
            return url.rstrip("/"), tok
        org = self.cfg.get("sf_cli_org")
        if not org:
            raise RuntimeError("No Salesforce auth: set env vars or sf_cli_org in config.")
        res = subprocess.run(["sf", "org", "display", "--target-org", org, "--json"],
                             capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Salesforce CLI auth failed: {res.stderr.strip()}")
        data = json.loads(res.stdout)["result"]
        return data["instanceUrl"].rstrip("/"), data["accessToken"]

    def query(self, soql):
        url = f"{self.instance_url}/services/data/{self.version}/query?" + \
            urllib.parse.urlencode({"q": soql})
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r).get("records", [])

    # --- the four reads the pipeline needs ---
    def demo_requests(self, fields, lookback_days, limit):
        return self.query(build_contact_query(fields, since_date(lookback_days), limit))

    def open_opportunities(self, account_id):
        return self.query(
            "SELECT Id, Name, StageName, Amount, Type FROM Opportunity "
            f"WHERE AccountId = {soql_quote(account_id)} AND IsClosed = false "
            "ORDER BY CreatedDate DESC LIMIT 5")

    def campaign_activity(self, contact_id):
        return self.query(
            "SELECT Campaign.Name, Status, FirstRespondedDate FROM CampaignMember "
            f"WHERE ContactId = {soql_quote(contact_id)} ORDER BY CreatedDate DESC LIMIT 5")


class FixtureSource:
    """Offline stand-in that reads a JSON file shaped like the SOQL results."""

    instance_url = "https://example.my.salesforce.test"

    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            self.data = json.load(f)

    def demo_requests(self, fields, lookback_days, limit):
        return self.data.get("contacts", [])[:limit]

    def open_opportunities(self, account_id):
        return self.data.get("opportunities", {}).get(account_id, [])

    def campaign_activity(self, contact_id):
        return self.data.get("campaign_activity", {}).get(contact_id, [])
