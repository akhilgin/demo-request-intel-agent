import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from demo_intel.domains import is_freemail, is_internal, normalize_domain
from demo_intel.enrich import build_facts, classify, record_url
from demo_intel.pipeline import run
from demo_intel.render import llm_prose, render_thread, render_top
from demo_intel.sfdc import FixtureSource, build_contact_query, soql_quote
from demo_intel.state import State
from demo_intel.targets import load_targets, lookup_target

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "sample_data", "target_accounts_sample.csv")
FIXTURE = os.path.join(ROOT, "sample_data", "sample_requests.json")


class DomainTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_domain("Jane@WWW.Acme.test"), "acme.test")
        self.assertEqual(normalize_domain("https://www.acme.test/pricing?x=1"), "acme.test")
        self.assertEqual(normalize_domain("  "), "")
        self.assertEqual(normalize_domain(None), "")

    def test_freemail_and_internal(self):
        self.assertTrue(is_freemail("a@gmail.com"))
        self.assertTrue(is_freemail("a@corp-mail.test", extra=["corp-mail.test"]))
        self.assertFalse(is_freemail("a@acme.test"))
        self.assertTrue(is_internal("me@Example.com", ["example.com"]))
        self.assertFalse(is_internal("me@acme.test", ["example.com"]))
        self.assertFalse(is_internal("", ["example.com"]))


class TargetTests(unittest.TestCase):
    def test_lookup(self):
        t = load_targets(CSV)
        self.assertEqual(lookup_target("x@acme.test", t)["tier"], "A")
        self.assertEqual(lookup_target("x@mail.acme.test", t)["tier"], "A")  # subdomain
        self.assertEqual(lookup_target("https://www.globex.test", t)["tier"], "B")
        self.assertIsNone(lookup_target("x@nope.test", t))
        self.assertIsNone(lookup_target("x@test", t))

    def test_classify(self):
        t = load_targets(CSV)
        c = lambda e: classify({"Email": e}, t, ["example.com"], [])[1]
        self.assertEqual(c("a@acme.test"), "")
        self.assertEqual(c("a@gmail.com"), "freemail")
        self.assertEqual(c("a@example.com"), "internal")
        self.assertEqual(c("a@unlisted.test"), "not a target")
        self.assertEqual(c(""), "no email")


class StateTests(unittest.TestCase):
    def test_mark_and_filter(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sub", "s.json")
            s = State(p)
            self.assertEqual(s.filter_new(["a", "b"]), ["a", "b"])
            s.mark("a", now=datetime(2026, 1, 1, tzinfo=timezone.utc))
            s2 = State(p)  # reload from disk
            self.assertEqual(s2.filter_new(["a", "b"]), ["b"])
            with open(p) as f:
                self.assertEqual(json.load(f)["a"], "2026-01-01T00:00:00Z")

    def test_corrupt_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.json")
            with open(p, "w") as f:
                f.write("{not json")
            self.assertTrue(State(p).is_new("x"))


class SoqlTests(unittest.TestCase):
    def test_quote(self):
        self.assertEqual(soql_quote("O'Neil"), "'O\\'Neil'")

    def test_query(self):
        f = {"demo_flag": "Flag__c", "demo_date": "Date__c", "source": "Src__c"}
        q = build_contact_query(f, "2026-01-01", 10)
        self.assertIn("Flag__c = true AND Date__c >= 2026-01-01", q)
        self.assertIn("Src__c", q)
        self.assertTrue(q.endswith("LIMIT 10"))


def cfg_for(tmp):
    with open(os.path.join(ROOT, "config.example.json")) as f:
        cfg = json.load(f)
    cfg["state_path"] = os.path.join(tmp, "state.json")
    cfg["target_list"] = CSV
    return cfg


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.src = FixtureSource(FIXTURE)
        self.cfg = cfg_for(tempfile.gettempdir())
        rec = self.src.data["contacts"][0]
        self.facts = build_facts(rec, {"tier": "A", "company": "Acme Corp"}, self.cfg["fields"],
                                 self.src, self.src.instance_url)

    def test_record_url(self):
        self.assertEqual(record_url("https://x.my.salesforce.com/", "Account", "001"),
                         "https://x.lightning.force.com/lightning/r/Account/001/view")
        self.assertEqual(record_url("", "Account", "001"), "")

    def test_top(self):
        top = render_top(self.facts)
        self.assertIn("Acme Corp", top)
        self.assertIn("`jordan.rivera@acme.test`", top)
        self.assertTrue(top.splitlines()[-1].startswith("`ref:003FAKE"))
        self.assertLessEqual(len(top.splitlines()), 3)

    def test_thread_sections(self):
        t = render_thread(self.facts)
        for s in ("How they got here", "Source: Paid Search", "Open opp:", "$48,000", "Spring Webinar (Attended)"):
            self.assertIn(s, t)

    def test_thread_omits_empty(self):
        rec = self.src.data["contacts"][4]  # Medium is the placeholder "None"
        facts = build_facts(rec, {"tier": "C"}, self.cfg["fields"], self.src, self.src.instance_url)
        t = render_thread(facts, low_fit_tiers=["C"])
        self.assertNotIn("Medium", t)
        self.assertNotIn("None", t.replace("No open opportunity", ""))
        self.assertIn("low fit", t)
        self.assertIn("No open opportunity", t)

    def test_llm_failure_falls_back(self):
        def boom(body, key):
            raise OSError("network down")
        os.environ["ANTHROPIC_API_KEY"] = "test"
        try:
            self.assertEqual(llm_prose(self.facts, {"model": "m"}, post=boom), "")
            ok = lambda body, key: {"content": [{"type": "text", "text": "Short summary."}]}
            self.assertEqual(llm_prose(self.facts, {"model": "m"}, post=ok), "Short summary.")
        finally:
            del os.environ["ANTHROPIC_API_KEY"]


class PipelineTests(unittest.TestCase):
    def test_filters_and_dry_run(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = cfg_for(d)
            out = []
            res = run(cfg, FixtureSource(FIXTURE), dry_run=True, out=out.append)
            self.assertEqual([r[0] for r in res], ["003FAKE000000001", "003FAKE000000005"])
            self.assertTrue(res[0][1].startswith(":test_tube:"))
            self.assertFalse(os.path.exists(cfg["state_path"]))  # dry-run never writes state

    def test_live_posts_once_then_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = cfg_for(d)
            os.environ["SLACK_BOT_TOKEN"] = "x"
            sent = []
            poster = lambda tok, ch, top, det: sent.append((ch, top))
            try:
                first = run(cfg, FixtureSource(FIXTURE), mode="live", poster=poster, out=lambda s: None)
                second = run(cfg, FixtureSource(FIXTURE), mode="live", poster=poster, out=lambda s: None)
            finally:
                del os.environ["SLACK_BOT_TOKEN"]
            self.assertEqual(len(first), 2)
            self.assertEqual(second, [])
            self.assertEqual(len(sent), 2)
            self.assertFalse(sent[0][1].startswith(":test_tube:"))

    def test_test_mode_does_not_mark(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = cfg_for(d)
            os.environ["SLACK_BOT_TOKEN"] = "x"
            try:
                run(cfg, FixtureSource(FIXTURE), mode="test", poster=lambda *a: None, out=lambda s: None)
            finally:
                del os.environ["SLACK_BOT_TOKEN"]
            self.assertTrue(State(cfg["state_path"]).is_new("003FAKE000000001"))


if __name__ == "__main__":
    unittest.main()
