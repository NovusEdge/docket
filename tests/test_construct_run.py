"""The two-pass driver, with the provider call injected."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from docket.construct import client, run


class SchemaShapeTests(unittest.TestCase):
    """Both schemas travel with `"strict": True`.

    Strict mode requires every property listed in `required` and
    `additionalProperties: false`. A schema that misses either is refused by the
    endpoint, and no fake caller would ever notice.
    """

    def objects(self, node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                yield node
            for value in node.values():
                yield from self.objects(value)
        elif isinstance(node, list):
            for value in node:
                yield from self.objects(value)

    def test_every_property_is_required(self):
        for schema in (run.EXTRACT_SCHEMA, run.LINK_SCHEMA):
            for node in self.objects(schema):
                self.assertEqual(set(node.get("properties", {})),
                                 set(node.get("required", [])), node)

    def test_no_object_admits_extra_properties(self):
        for schema in (run.EXTRACT_SCHEMA, run.LINK_SCHEMA):
            for node in self.objects(schema):
                self.assertIs(node.get("additionalProperties"), False, node)


class FakeCaller:
    """Stands in for the provider. Records what it was asked."""

    def __init__(self, extract_reply=None, link_reply=None):
        self.extract_reply = extract_reply or {"records": []}
        self.link_reply = link_reply or {"edges": []}
        self.prompts = []

    def __call__(self, prompt, schema):
        self.prompts.append(prompt)
        # Identity, never a property name: dispatching on the schema's contents
        # would couple every test to the schema's internals.
        if schema is run.LINK_SCHEMA:
            return self.link_reply
        return self.extract_reply


def doc(root, name, body):
    path = Path(root) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


class PathSpellingTests(unittest.TestCase):
    """A record's key and its git date both hinge on the path's spelling.

    An absolute path argument would otherwise restage every record as new, and
    make every git-date lookup miss, which silently disables supersession.
    """

    def test_an_absolute_path_records_the_repository_relative_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "docs").mkdir()
            doc(root, "docs/one.md", "# one\n\nClaim: a\n")
            caller = FakeCaller({"records": [
                {"kind": "claim", "text": "A", "choice": "", "anchor": "Claim: a",
                 "rationale": "", "scope": []}]})
            got, _ = run.two_pass([str(root / "docs")], caller=caller, root=root)
            self.assertEqual(got[0]["source"]["path"], "docs/one.md")

    def test_derives_the_root_from_the_documents_own_repository(self):
        # Reading another project's history is the main case, so the root cannot
        # be the working directory. Without this, paths stay absolute and a
        # different spelling on the next run restages every record.
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp).resolve() / "other"
            (other / "docs").mkdir(parents=True)
            subprocess.run(["git", "-C", str(other), "init", "-q"], check=True)
            doc(other, "docs/one.md", "# one\n\nClaim: a\n")
            subprocess.run(["git", "-C", str(other), "add", "docs/one.md"], check=True)
            caller = FakeCaller({"records": [
                {"kind": "claim", "text": "A", "choice": "", "anchor": "Claim: a",
                 "rationale": "", "scope": []}]})
            got, _ = run.two_pass([str(other / "docs")], caller=caller)
            self.assertEqual(got[0]["source"]["path"], "docs/one.md")

    def test_two_spellings_of_one_document_give_one_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            doc(root, "one.md", "# one\n\nClaim: a\n")
            reply = {"records": [
                {"kind": "claim", "text": "A", "choice": "", "anchor": "Claim: a",
                 "rationale": "", "scope": []}]}
            absolute, _ = run.two_pass([str(root / "one.md")],
                                       caller=FakeCaller(reply), root=root)
            relative, _ = run.two_pass([str(root / "./one.md")],
                                       caller=FakeCaller(reply), root=root)
            self.assertEqual(absolute[0]["key"], relative[0]["key"])


class FailedRunTests(unittest.TestCase):
    """A run where nothing worked must not report success.

    A bad key took 60 documents to 60 identical 401s, and construct printed
    "staged 0 proposals" and exited 0.
    """

    def docs(self, tmp, count=3):
        for index in range(count):
            doc(tmp, f"d{index}.md", f"# {index}\n\nClaim: a{index}\n")

    def test_refuses_a_run_where_every_document_failed(self):
        def boom(*_args, **_kwargs):
            raise RuntimeError("upstream said no")

        with tempfile.TemporaryDirectory() as tmp:
            self.docs(tmp)
            with self.assertRaises(run.RunError) as caught:
                run.two_pass([tmp], caller=boom, untracked=True, sleep=lambda _s: None)
            self.assertIn("3", str(caught.exception))

    def test_keeps_a_run_where_one_document_failed(self):
        seen = []

        def flaky(prompt, schema):
            seen.append(prompt)
            if "d1.md" in prompt:
                raise RuntimeError("upstream said no")
            return {"records": [{"kind": "claim", "text": "A", "choice": "",
                                 "anchor": "Claim: a0", "rationale": "",
                                 "scope": [], "confidence": "high"}]}

        with tempfile.TemporaryDirectory() as tmp:
            self.docs(tmp, count=2)
            got, report = run.two_pass([tmp], caller=flaky, untracked=True,
                                       sleep=lambda _s: None)
            self.assertEqual(len(got), 1)
            self.assertTrue(any("d1.md" in line for line in report))

    def test_an_authentication_failure_stops_the_run(self):
        # One 401 settles the question for every remaining document. Repeating
        # it 60 times spends 60 calls to learn what the first one said.
        calls = []

        def unauthorized(*_args, **_kwargs):
            calls.append(1)
            raise client.ClientError("401 Missing Authentication header")

        with tempfile.TemporaryDirectory() as tmp:
            self.docs(tmp, count=20)
            with self.assertRaises(client.ClientError):
                run.two_pass([tmp], caller=unauthorized, jobs=2, untracked=True,
                             sleep=lambda _s: None)
            self.assertLess(len(calls), 20)


class DiscoveryTests(unittest.TestCase):
    def test_reads_every_markdown_file_under_a_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc(tmp, "a/one.md", "# one\n")
            doc(tmp, "a/two.md", "# two\n")
            doc(tmp, "a/skip.txt", "not markdown")
            self.assertEqual(len(run.documents([str(Path(tmp) / "a")])), 2)

    def test_skips_a_document_git_does_not_track(self):
        # 326 of 891 proposals in the first real run came from untracked
        # documents: scratch, drafts, and another tool's output.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            doc(root, "kept.md", "# kept\n")
            doc(root, "scratch.md", "# scratch\n")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "kept.md"], cwd=root, check=True)
            names = [p.name for p in run.documents([str(root)])]
            self.assertEqual(names, ["kept.md"])

    def test_reads_an_untracked_document_when_asked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            doc(root, "scratch.md", "# scratch\n")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            names = [p.name for p in run.documents([str(root)], untracked=True)]
            self.assertEqual(names, ["scratch.md"])

    def test_reads_everything_outside_a_repository(self):
        # No git, no tracking to filter on. Refusing every document there would
        # make construct useless on a plain directory of notes.
        with tempfile.TemporaryDirectory() as tmp:
            doc(tmp, "one.md", "# one\n")
            self.assertEqual(len(run.documents([tmp])), 1)

    def test_excludes_a_path_segment_by_default(self):
        # 582 of 891 proposals came from an archive/ path, 304 of them from a
        # directory named 2026-06-stale-audit.
        with tempfile.TemporaryDirectory() as tmp:
            doc(tmp, "live/one.md", "# one\n")
            doc(tmp, "archive/old.md", "# old\n")
            names = [p.name for p in run.documents([tmp])]
            self.assertEqual(names, ["one.md"])

    def test_reads_an_excluded_path_when_the_exclusion_is_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc(tmp, "archive/old.md", "# old\n")
            self.assertEqual(len(run.documents([tmp], exclude=())), 1)

    def test_excludes_only_a_whole_segment(self):
        # archived-designs/ is not archive/.
        with tempfile.TemporaryDirectory() as tmp:
            doc(tmp, "archived-designs/one.md", "# one\n")
            self.assertEqual(len(run.documents([tmp])), 1)

    def test_reads_a_named_file_the_filters_would_have_dropped(self):
        # Naming one document is an explicit instruction, never a walk.
        with tempfile.TemporaryDirectory() as tmp:
            path = doc(tmp, "archive/old.md", "# old\n")
            self.assertEqual(run.documents([str(path)]), [path])

    def test_accepts_a_single_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = doc(tmp, "one.md", "# one\n")
            self.assertEqual(run.documents([str(path)]), [path])

    def test_skips_a_path_that_does_not_exist(self):
        self.assertEqual(run.documents(["/nowhere/at/all"]), [])

    def test_returns_a_stable_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc(tmp, "b.md", "x")
            doc(tmp, "a.md", "x")
            names = [p.name for p in run.documents([tmp])]
            self.assertEqual(names, sorted(names))


class ExtractPassTests(unittest.TestCase):
    SOURCE = "# Title\n\nDate: 2026-06-18\n\n**Decision:** keep the ledger local\n"

    def reply(self, **over):
        record = {"kind": "decision", "text": "Where does the ledger live?",
                  "choice": "Local", "anchor": "Decision: keep the ledger local",
                  "rationale": "because", "scope": ["docket/**"]}
        record.update(over)
        return {"records": [record]}

    def one_doc(self, tmp, body=None):
        return doc(tmp, "context/d.md", body or self.SOURCE)

    def test_stages_a_record_the_model_returned(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.one_doc(tmp)
            caller = FakeCaller(self.reply())
            got, _ = run.two_pass([tmp], caller=caller)
            self.assertEqual(len(got), 1)
            self.assertEqual(got[0]["text"], "Where does the ledger live?")

    def test_carries_the_confidence_the_model_reported(self):
        # Review order ranks by confidence. A run that never asks for it stages
        # every record at the default and leaves the sort with nothing to do.
        with tempfile.TemporaryDirectory() as tmp:
            self.one_doc(tmp)
            caller = FakeCaller(self.reply(confidence="high"))
            got, _ = run.two_pass([tmp], caller=caller)
            self.assertEqual(got[0]["confidence"], "high")

    def test_falls_back_to_low_when_the_confidence_is_not_a_known_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.one_doc(tmp)
            caller = FakeCaller(self.reply(confidence="certain"))
            got, _ = run.two_pass([tmp], caller=caller)
            self.assertEqual(got[0]["confidence"], "low")

    def test_asks_the_model_what_confidence_means(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.one_doc(tmp)
            caller = FakeCaller(self.reply())
            run.two_pass([tmp], caller=caller)
            self.assertIn("confidence", caller.prompts[0])

    def test_resolves_the_document_date_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.one_doc(tmp)
            got, _ = run.two_pass([tmp], caller=FakeCaller(self.reply()))
            self.assertEqual(got[0]["source"]["date"], "2026-06-18")

    def test_records_the_line_the_anchor_matched(self):
            with tempfile.TemporaryDirectory() as tmp:
                self.one_doc(tmp)
                got, _ = run.two_pass([tmp], caller=FakeCaller(self.reply()))
                self.assertEqual(got[0]["line"], 5)

    def test_drops_a_record_whose_anchor_is_nowhere_in_the_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.one_doc(tmp)
            caller = FakeCaller(self.reply(anchor="Decision: something invented"))
            got, report = run.two_pass([tmp], caller=caller)
            self.assertEqual(got, [])
            self.assertTrue(any("anchor" in line for line in report))

    def test_drops_a_scope_entry_that_does_not_address_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.one_doc(tmp)
            caller = FakeCaller(self.reply(scope=["a long prose description here"]))
            got, _ = run.two_pass([tmp], caller=caller)
            self.assertEqual(got[0]["scope"], [])

    def test_drops_a_record_the_schema_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.one_doc(tmp)
            caller = FakeCaller(self.reply(kind="opinion"))
            got, report = run.two_pass([tmp], caller=caller)
            self.assertEqual(got, [])
            self.assertTrue(report)

    def test_reports_the_anchor_match_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.one_doc(tmp)
            _, report = run.two_pass([tmp], caller=FakeCaller(self.reply()))
            self.assertTrue(any("anchors" in line for line in report))

    def test_sends_the_document_body_to_the_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.one_doc(tmp)
            caller = FakeCaller(self.reply())
            run.two_pass([tmp], caller=caller)
            self.assertIn("keep the ledger local", caller.prompts[0])


class LinkPassTests(unittest.TestCase):
    SOURCE_A = "# A\n\nDate: 2026-01-01\n\nClaim: state must be sanitized\n"
    SOURCE_B = "# B\n\nDate: 2026-06-01\n\nDecision: tier the audit by layer\n"

    def replies(self, edges):
        return FakeCaller(link_reply={"edges": edges})

    def build(self, tmp, caller):
        doc(tmp, "a.md", self.SOURCE_A)
        doc(tmp, "b.md", self.SOURCE_B)

        def per_doc(prompt, schema):
            if schema is run.LINK_SCHEMA:
                return caller.link_reply
            if "sanitized" in prompt:
                return {"records": [{"kind": "claim", "text": "State must be sanitized",
                                     "choice": "", "anchor": "Claim: state must be sanitized",
                                     "rationale": "", "scope": []}]}
            return {"records": [{"kind": "decision", "text": "How is audit checked?",
                                 "choice": "Tiered", "anchor": "Decision: tier the audit by layer",
                                 "rationale": "", "scope": []}]}

        return run.two_pass([tmp], caller=per_doc)

    def test_applies_a_support_edge_across_two_documents(self):
        # The whole reason pass 2 exists: a per-document call cannot see this.
        with tempfile.TemporaryDirectory() as tmp:
            got, _ = self.build(tmp, self.replies(
                [{"kind": "supports", "from": "p2", "to": "p1"}]))
            by_kind = {p["kind"]: p for p in got}
            self.assertEqual(by_kind["decision"]["supports"],
                             [[by_kind["claim"]["key"]]])

    def test_drops_an_edge_the_local_rules_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            got, report = self.build(tmp, self.replies(
                [{"kind": "supersedes", "from": "p2", "to": "p1"}]))
            self.assertTrue(any("supersedes" in line for line in report))
            self.assertTrue(all(not p["supersedes"] for p in got))

    def test_skips_the_link_pass_for_a_single_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc(tmp, "a.md", self.SOURCE_A)
            caller = FakeCaller({"records": [
                {"kind": "claim", "text": "State must be sanitized", "choice": "",
                 "anchor": "Claim: state must be sanitized", "rationale": "", "scope": []}]})
            run.two_pass([tmp], caller=caller)
            # One extraction prompt, no linking prompt: there is nothing to link.
            self.assertEqual(len(caller.prompts), 1)


class LinkBatchTests(unittest.TestCase):
    def test_links_in_batches_and_reports_how_many(self):
        with tempfile.TemporaryDirectory() as tmp:
            for n in range(6):
                doc(tmp, f"d{n}.md", f"# d{n}\n\nClaim: number {n}\n")
            calls = []

            def caller(prompt, schema):
                if schema is run.LINK_SCHEMA:
                    calls.append(prompt)
                    return {"edges": []}
                n = prompt.split("Claim: number ")[1][0]
                return {"records": [{"kind": "claim", "text": f"Number {n}", "choice": "",
                                     "anchor": f"Claim: number {n}", "rationale": "",
                                     "scope": []}]}

            _, report = run.two_pass([tmp], caller=caller, batch=2)
            self.assertEqual(len(calls), 3)
            self.assertTrue(any("3 batches" in line for line in report))

    def test_a_contradiction_is_staged_as_a_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc(tmp, "a.md", "# a\n\nClaim: latency is 200ms\n")
            doc(tmp, "b.md", "# b\n\nClaim: latency is under 50ms\n")

            def caller(prompt, schema):
                if schema is run.LINK_SCHEMA:
                    return {"edges": [{"kind": "contradicts", "from": "p1", "to": "p2"}]}
                text = "latency is 200ms" if "200ms" in prompt else "latency is under 50ms"
                return {"records": [{"kind": "claim", "text": text.capitalize(), "choice": "",
                                     "anchor": f"Claim: {text}", "rationale": "", "scope": []}]}

            got, report = run.two_pass([tmp], caller=caller)
            questions = [p for p in got if p["kind"] == "question"]
            self.assertEqual(len(questions), 1)
            self.assertIn("200ms", questions[0]["text"])
            self.assertTrue(any("question" in line for line in report))


class DryRunTests(unittest.TestCase):
    def test_reads_no_document_and_calls_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc(tmp, "a.md", "# a\n")
            caller = FakeCaller()
            got, report = run.two_pass([tmp], caller=caller, dry_run=True)
            self.assertEqual(got, [])
            self.assertEqual(caller.prompts, [])
            self.assertTrue(any("1 document" in line for line in report))


class RetryTests(unittest.TestCase):
    """One call per document across a pool, so a 429 is expected.

    Without a retry the whole document's records are lost to one rate limit.
    """

    def source(self, tmp):
        doc(tmp, "a.md", "# a\n\nClaim: one\n")
        return {"records": [{"kind": "claim", "text": "One", "choice": "",
                             "anchor": "Claim: one", "rationale": "", "scope": []}]}

    def test_retries_a_rate_limited_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            reply = self.source(tmp)
            tries = {"n": 0}

            def limited(prompt, schema):
                tries["n"] += 1
                if tries["n"] < 3:
                    raise RuntimeError("429 Too Many Requests")
                return reply

            got, _ = run.two_pass([tmp], caller=limited, sleep=lambda s: None)
            self.assertEqual(len(got), 1)
            self.assertEqual(tries["n"], 3)

    def test_waits_longer_between_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.source(tmp)
            waits = []

            def limited(prompt, schema):
                raise RuntimeError("429 rate limited")

            # The only document fails, so the run refuses. The backoff it made
            # on the way there is what this checks.
            with self.assertRaises(run.RunError):
                run.two_pass([tmp], caller=limited, sleep=waits.append)
            self.assertTrue(waits)
            self.assertEqual(waits, sorted(waits))

    def test_gives_up_after_the_last_attempt_and_reports_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.source(tmp)

            def limited(prompt, schema):
                raise RuntimeError("429 rate limited")

            with self.assertRaises(run.RunError) as caught:
                run.two_pass([tmp], caller=limited, sleep=lambda s: None)
            self.assertIn("every document failed", str(caught.exception))

    def test_does_not_retry_an_error_that_is_not_a_rate_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.source(tmp)
            tries = {"n": 0}

            def broken(prompt, schema):
                tries["n"] += 1
                raise RuntimeError("400 malformed schema")

            with self.assertRaises(run.RunError):
                run.two_pass([tmp], caller=broken, sleep=lambda s: None)
            self.assertEqual(tries["n"], 1)


class FailureTests(unittest.TestCase):
    def test_no_documents_is_an_error_naming_the_paths(self):
        with self.assertRaises(run.RunError):
            run.two_pass(["/nowhere"], caller=FakeCaller())

    def test_one_document_failing_does_not_lose_the_others(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc(tmp, "good.md", "# g\n\nClaim: one\n")
            doc(tmp, "bad.md", "# b\n\nClaim: two\n")

            def flaky(prompt, schema):
                if "two" in prompt:
                    raise RuntimeError("provider said no")
                return {"records": [{"kind": "claim", "text": "One", "choice": "",
                                     "anchor": "Claim: one", "rationale": "", "scope": []}]}

            got, report = run.two_pass([tmp], caller=flaky)
            self.assertEqual(len(got), 1)
            self.assertTrue(any("bad.md" in line for line in report))


if __name__ == "__main__":
    unittest.main()
