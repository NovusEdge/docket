import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from docket import corrections, features, merge_driver, migrate, reviews  # noqa: E402
from docket.ledger import make_record, read  # noqa: E402


def claim(ident, text, **kwargs):
    return make_record("claim", text, state="accepted", author="t", record_id=ident, **kwargs)


def write(path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def decision(ident, text, **kwargs):
    return make_record(
        "decision",
        text,
        state="adopted",
        choice="Cache",
        alternatives=["No cache"],
        rationale="Reads dominate",
        author="t",
        record_id=ident,
        **kwargs,
    )


def v2(records):
    return [dict(r, schema=2) for r in records]


def upgraded(records):
    """What a schema-2 ledger holds after `docket migrate`."""
    return migrate.renumber_step(v2(records))[0]


def features_event(ident, slug, schema, **fields):
    made = features.make_event("start", slug, text=slug, paths=["src/**"], ts="t", **fields)
    return dict(made, id=ident, schema=schema)


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.base, self.ours, self.theirs = (self.tmp / n for n in ("O", "A", "B"))

    def test_disjoint_tails_merge_and_existing_lines_keep_their_bytes(self):
        shared = [claim("c1", "Shared")]
        write(self.base, shared)
        write(self.ours, shared + [claim("c2", "Ours")])
        write(self.theirs, shared + [claim("c2", "Theirs", supports=[["c1"]])])
        before = self.ours.read_text(encoding="utf-8")
        self.assertEqual(merge_driver.run(self.base, self.ours, self.theirs), 0)
        after = self.ours.read_text(encoding="utf-8")
        self.assertTrue(after.startswith(before))
        merged = read(self.ours)
        self.assertEqual([r["id"] for r in merged], ["c1", "c2", "c3"])
        self.assertEqual(merged[2]["text"], "Theirs")

    def test_an_incoming_correction_of_a_shared_record_merges(self):
        shared = [claim("c1", "Shared")]
        fix = corrections.make("c1", {"scope": ["a.py"]}, author="t")
        fix["id"] = "c1.1"
        write(self.base, shared)
        write(self.ours, shared + [claim("c2", "Ours")])
        write(self.theirs, shared + [fix])
        self.assertEqual(merge_driver.run(self.base, self.ours, self.theirs), 0)
        self.assertEqual(read(self.ours)[-1]["id"], "c1.1")

    def test_both_sides_superseding_one_record_leaves_conflict_markers(self):
        shared = [claim("c1", "Shared")]
        write(self.base, shared)
        write(self.ours, shared + [claim("c2", "Ours", supersedes=["c1"])])
        write(self.theirs, shared + [claim("c2", "Theirs", supersedes=["c1"])])
        self.assertEqual(merge_driver.run(self.base, self.ours, self.theirs), 1)
        self.assertIn("<<<<<<<", self.ours.read_text(encoding="utf-8"))

    def test_a_refusal_leaves_markers_even_when_the_text_merges_cleanly(self):
        records = [claim("c1", "One"), claim("c2", "Two"), claim("c3", "Three")]
        write(self.base, records)
        edited = [records[0], claim("c2", "Two, reworded"), records[2]]
        write(self.ours, edited)
        decision = make_record(
            "decision",
            "Build the cache layer on the second record",
            state="adopted",
            choice="Cache",
            alternatives=["No cache"],
            rationale="Reads dominate and the second record shows the cost",
            author="t",
            record_id="d1",
            supports=[["c2"]],
        )
        write(self.theirs, records + [decision])
        self.assertEqual(merge_driver.run(self.base, self.ours, self.theirs), 1)
        self.assertIn("<<<<<<<", self.ours.read_text(encoding="utf-8"))

    def test_an_unreadable_theirs_leaves_conflict_markers(self):
        shared = [claim("c1", "Shared")]
        write(self.base, shared)
        write(self.ours, shared + [claim("c2", "Ours")])
        self.theirs.write_text(json.dumps(shared[0]) + "\n{not json\n", encoding="utf-8")
        self.assertEqual(merge_driver.run(self.base, self.ours, self.theirs), 1)
        self.assertIn("<<<<<<<", self.ours.read_text(encoding="utf-8"))

    def test_no_lock_file_appears_beside_the_inputs(self):
        shared = [claim("c1", "Shared")]
        write(self.base, shared)
        write(self.ours, shared)
        write(self.theirs, shared + [claim("c2", "Theirs")])
        merge_driver.run(self.base, self.ours, self.theirs)
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["A", "B", "O"])

    def test_feature_stores_merge_with_colliding_ids_renumbered(self):
        def start(ident, slug):
            event = features.make_event("start", slug, text=slug, paths=["src/**"], ts="t")
            return dict(event, id=ident)

        shared = [start("f1", "shared")]
        write(self.base, shared)
        write(self.ours, shared + [start("f2", "ours")])
        write(self.theirs, shared + [start("f2", "theirs")])
        self.assertEqual(merge_driver.run(self.base, self.ours, self.theirs), 0)
        merged = features.read(self.ours)
        self.assertEqual(
            [(e["id"], e["slug"]) for e in merged][1:], [("f2", "ours"), ("f3", "theirs")]
        )
        self.assertEqual(merge_driver.run(self.base, self.ours, self.theirs), 0)
        self.assertEqual(len(features.read(self.ours)), 3)

    def test_feature_stores_that_both_open_one_slug_conflict(self):
        def start(ident):
            return dict(features.make_event("start", "same", text="x", paths=["a/**"]), id=ident)

        write(self.base, [])
        write(self.ours, [start("f1")])
        write(self.theirs, [dict(start("f1"), text="y")])
        self.assertEqual(merge_driver.run(self.base, self.ours, self.theirs), 1)
        self.assertIn("<<<<<<<", self.ours.read_text(encoding="utf-8"))

    def test_an_empty_base_merges_two_new_ledgers(self):
        self.base.write_text("", encoding="utf-8")
        write(self.ours, [claim("c1", "Ours")])
        write(self.theirs, [claim("c1", "Theirs")])
        self.assertEqual(merge_driver.run(self.base, self.ours, self.theirs), 0)
        self.assertEqual([r["text"] for r in read(self.ours)], ["Ours", "Theirs"])


class CrossMigrationTests(unittest.TestCase):
    """Two branches that each ran `docket migrate`, from a schema-2 BASE.

    Schema-2 ids are one global sequence: c1 d2 c3. After the migration they
    are per kind: c1 d1 c2.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.base, self.ours, self.theirs = (self.tmp / n for n in ("O", "A", "B"))
        self.shared = [
            claim("c1", "Shared premise"),
            decision("d2", "Cache layer sits behind reads", supports=[["c1"]]),
        ]

    def run_driver(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = merge_driver.run(self.base, self.ours, self.theirs)
        return code, err.getvalue()

    def ids(self):
        return [r["id"] for r in read(self.ours)]

    def test_both_sides_migrated_separately_merge_without_duplicates(self):
        write(self.base, v2(self.shared))
        write(self.ours, upgraded(self.shared + [claim("c3", "Ours only")]))
        write(self.theirs, upgraded(self.shared + [claim("c3", "Theirs only")]))
        before = self.ours.read_text(encoding="utf-8")
        self.assertEqual(self.run_driver()[0], 0)
        self.assertTrue(self.ours.read_text(encoding="utf-8").startswith(before))
        merged = read(self.ours)
        self.assertEqual(self.ids(), ["c1", "d1", "c2", "c3"])
        # One old id on two records, one per branch.
        self.assertEqual([merged[2]["migrated_from"], merged[3]["migrated_from"]], ["c3", "c3"])
        self.assertEqual([merged[2]["text"], merged[3]["text"]], ["Ours only", "Theirs only"])
        once = self.ours.read_text(encoding="utf-8")
        self.assertEqual(self.run_driver()[0], 0)
        self.assertEqual(self.ours.read_text(encoding="utf-8"), once)

    def test_a_correction_and_a_review_of_a_shared_record_merge_once(self):
        fix = corrections.make("d2", {"scope": ["a.py"]}, author="t")
        fix["id"] = "d2.1"
        look = reviews.make("d2", author="t")
        look["id"] = "d2.r1"
        look["grounds"] = {"c1": "c1"}
        write(self.base, v2(self.shared))
        write(self.ours, upgraded(self.shared + [claim("c3", "Ours only")]))
        write(self.theirs, upgraded(self.shared + [fix, look]))
        self.assertEqual(self.run_driver()[0], 0)
        merged = read(self.ours)
        self.assertEqual(self.ids(), ["c1", "d1", "c2", "d1.1", "d1.r1"])
        self.assertEqual(merged[3]["corrects"], "d1")
        self.assertEqual((merged[4]["reviews"], merged[4]["grounds"]), ("d1", {"c1": "c1"}))
        once = self.ours.read_text(encoding="utf-8")
        self.assertEqual(self.run_driver()[0], 0)
        self.assertEqual(self.ours.read_text(encoding="utf-8"), once)

    def test_a_branch_that_merged_main_before_the_migration_merges_back_without_duplicates(self):
        base = [claim("c1", "Shared premise")]
        main = base + [decision("d2", "Cache layer sits behind reads", supports=[["c1"]])]
        branch = base + [claim("c2", "Branch only")]
        # A schema-2 `docket rebase` appended main's decision to the branch
        # under the next global id, d3.
        branch = branch + [dict(main[1], id="d3")]
        branch = branch + [claim("c4", "Cites the cache", supports=[["d3"]])]
        write(self.base, v2(base))
        write(self.ours, upgraded(main))
        write(self.theirs, upgraded(branch))
        self.assertEqual(self.run_driver()[0], 0)
        merged = read(self.ours)
        self.assertEqual(self.ids(), ["c1", "d1", "c2", "c3"])
        self.assertEqual([r["text"] for r in merged][2:], ["Branch only", "Cites the cache"])
        self.assertEqual(merged[3]["supports"], [["d1"]])
        once = self.ours.read_text(encoding="utf-8")
        self.assertEqual(self.run_driver()[0], 0)
        self.assertEqual(self.ours.read_text(encoding="utf-8"), once)

    def test_ours_migrated_and_theirs_not_is_refused_with_markers(self):
        write(self.base, v2(self.shared))
        write(self.ours, upgraded(self.shared) + [claim("c2", "Ours only")])
        write(self.theirs, v2(self.shared + [claim("c3", "Theirs only")]))
        code, err = self.run_driver()
        self.assertEqual(code, 1)
        self.assertIn("<<<<<<<", self.ours.read_text(encoding="utf-8"))
        self.assertIn("the other branch's ledger is schema 2", err)
        self.assertIn("docket migrate", err)

    def test_theirs_migrated_and_ours_not_is_refused_with_markers(self):
        write(self.base, v2(self.shared))
        write(self.ours, v2(self.shared + [claim("c3", "Ours only")]))
        write(self.theirs, upgraded(self.shared) + [claim("c2", "Theirs only")])
        code, err = self.run_driver()
        self.assertEqual(code, 1)
        self.assertIn("<<<<<<<", self.ours.read_text(encoding="utf-8"))
        self.assertIn("this branch's ledger is schema 2", err)

    def test_an_unreadable_base_is_refused_with_markers(self):
        for label, content in (
            ("non-UTF-8", b'{"id":"c1"}\n\xff\xfe\n'),
            ("non-object", b"[1, 2]\n"),
            ("non-object after a record", json.dumps(claim("c1", "x")).encode() + b"\n7\n"),
        ):
            with self.subTest(label):
                self.base.write_bytes(content)
                write(self.ours, [claim("c1", "Ours")])
                write(self.theirs, [claim("c1", "Theirs")])
                code, _ = self.run_driver()
                self.assertEqual(code, 1)
                self.assertIn("<<<<<<<", self.ours.read_text(encoding="utf-8"))

    def test_an_unreadable_base_beside_feature_stores_is_refused_with_markers(self):
        good = json.dumps(features_event("f1", "shared", 2)).encode()
        for label, content in (
            ("non-UTF-8", good + b"\n\xff\xfe\n"),
            ("non-object", good + b"\n[1]\n"),
        ):
            with self.subTest(label):
                self.base.write_bytes(content)
                write(self.ours, [features_event("f1", "ours", 2)])
                write(self.theirs, [features_event("f1", "theirs", 2)])
                code, _ = self.run_driver()
                self.assertEqual(code, 1)
                self.assertIn("<<<<<<<", self.ours.read_text(encoding="utf-8"))

    def test_a_schema_2_base_with_a_non_object_line_is_refused_with_markers(self):
        self.base.write_bytes(json.dumps(v2(self.shared)[0]).encode() + b"\n[1]\n")
        write(self.ours, upgraded(self.shared))
        write(self.theirs, upgraded(self.shared))
        code, _ = self.run_driver()
        self.assertEqual(code, 1)
        self.assertIn("<<<<<<<", self.ours.read_text(encoding="utf-8"))

    def test_an_empty_base_still_merges_two_migrated_ledgers(self):
        self.base.write_text("", encoding="utf-8")
        write(self.ours, [claim("c1", "Ours")])
        write(self.theirs, [claim("c1", "Theirs")])
        self.assertEqual(self.run_driver()[0], 0)
        self.assertEqual(self.ids(), ["c1", "c2"])

    def test_features_base_at_schema_1_matches_its_migrated_copy(self):
        # ours archived the old feature; theirs still carries it, migrated.
        # A strict key would see a new event and resurrect it.
        old = features_event("f1", "old", 1, include=["d2"], keys={"d2": "a" * 12})
        migrated = dict(old, schema=2, include=["d1"], keys={"d1": "b" * 12})
        write(self.base, [old])
        write(self.ours, [features_event("f1", "ours", 2)])
        write(self.theirs, [migrated, features_event("f2", "theirs", 2)])
        self.assertEqual(self.run_driver()[0], 0)
        merged = features.read(self.ours)
        self.assertEqual([(e["id"], e["slug"]) for e in merged], [("f1", "ours"), ("f2", "theirs")])

    def test_one_feature_event_carried_by_both_sides_under_different_ids_merges_once(self):
        # A pre-migration features merge copied the event across verbatim; each
        # branch's migration then mapped its include through its own ledger.
        ours_copy = features_event("f1", "shared", 2, include=["d1"], keys={"d1": "a" * 12})
        theirs_copy = dict(ours_copy, include=["d2"], keys={"d2": "a" * 12})
        write(self.base, [features_event("f1", "shared", 1, include=["d3"])])
        write(self.ours, [ours_copy])
        write(self.theirs, [theirs_copy, features_event("f2", "theirs", 2)])
        self.assertEqual(self.run_driver()[0], 0)
        merged = features.read(self.ours)
        self.assertEqual(
            [(e["id"], e["slug"]) for e in merged], [("f1", "shared"), ("f2", "theirs")]
        )
        self.assertEqual(merged[0]["include"], ["d1"])

    def test_features_sides_at_different_schemas_are_refused_with_markers(self):
        for ours_schema, theirs_schema in ((1, 2), (2, 1), (1, 1)):
            write(self.base, [features_event("f1", "shared", 1)])
            write(self.ours, [features_event("f1", "shared", ours_schema)])
            write(
                self.theirs,
                [
                    features_event("f1", "shared", theirs_schema),
                    features_event("f2", "t", theirs_schema),
                ],
            )
            code, err = self.run_driver()
            self.assertEqual(code, 1, (ours_schema, theirs_schema))
            self.assertIn("<<<<<<<", self.ours.read_text(encoding="utf-8"))
            self.assertIn("features file is schema 1", err)
            self.assertIn("docket migrate", err)

    def test_a_schema_1_ledger_side_is_refused_too(self):
        write(self.base, v2(self.shared))
        write(self.ours, upgraded(self.shared))
        write(self.theirs, [dict(r, schema=1) for r in self.shared])
        code, err = self.run_driver()
        self.assertEqual(code, 1)
        self.assertIn("<<<<<<<", self.ours.read_text(encoding="utf-8"))
        self.assertIn("schema 1", err)


DOCKET = str(ROOT / "bin" / "docket")


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class GitTests(unittest.TestCase):
    """Real git, with the driver registered by absolute path to this checkout."""

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.repo)
        self.env = {**os.environ, "DOCKET_HOME": str(self.repo / ".home")}
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        (self.repo / ".gitattributes").write_text(".docket/ledger.jsonl merge=docket\n")
        self.docket("init")
        # After init: from Task 3 on, init registers the PATH form, and this
        # test must run this checkout's docket.
        self.git("config", "merge.docket.driver", f"{DOCKET} merge-driver %O %A %B")
        self.docket("claim", "Shared", "--state", "accepted")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")

    def git(self, *args, check=True):
        return subprocess.run(
            ["git", *args],
            cwd=self.repo,
            env=self.env,
            capture_output=True,
            text=True,
            check=check,
        )

    def docket(self, *args):
        return subprocess.run(
            [DOCKET, *args],
            cwd=self.repo,
            env=self.env,
            capture_output=True,
            text=True,
            check=True,
        )

    def record(self, text, message):
        self.docket("claim", text, "--state", "accepted")
        self.git("commit", "-qam", message)

    def ledger(self):
        return read(self.repo / ".docket" / "ledger.jsonl")

    def texts(self):
        return [r["text"] for r in self.ledger()]

    def test_merge_of_two_recording_branches_is_clean(self):
        self.git("checkout", "-qb", "topic")
        self.record("Topic claim", "topic")
        self.git("checkout", "-q", "main")
        self.record("Main claim", "main")
        self.assertEqual(self.git("merge", "-q", "--no-edit", "topic").returncode, 0)
        self.assertEqual(self.texts(), ["Shared", "Main claim", "Topic claim"])
        self.assertEqual(self.docket("check").returncode, 0)

    def test_repeated_merges_in_both_directions_never_duplicate(self):
        self.git("checkout", "-qb", "topic")
        self.record("Topic one", "t1")
        self.git("checkout", "-q", "main")
        self.record("Main one", "m1")
        self.git("merge", "-q", "--no-edit", "topic")
        self.git("checkout", "-q", "topic")
        self.git("merge", "-q", "--no-edit", "main")
        self.record("Topic two", "t2")
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--no-edit", "topic")
        texts = self.texts()
        self.assertEqual(len(texts), len(set(texts)), texts)
        self.assertEqual(set(texts), {"Shared", "Topic one", "Main one", "Topic two"})

    def test_rebase_onto_a_recording_main_is_clean(self):
        self.git("checkout", "-qb", "topic")
        self.record("Topic claim", "topic")
        self.git("checkout", "-q", "main")
        self.record("Main claim", "main")
        self.git("checkout", "-q", "topic")
        self.assertEqual(self.git("rebase", "-q", "main").returncode, 0)
        self.assertEqual(self.texts(), ["Shared", "Main claim", "Topic claim"])

    def test_cherry_pick_appends_only_the_picked_commit(self):
        self.git("checkout", "-qb", "topic")
        self.record("Topic one", "t1")
        self.record("Topic two", "t2")
        self.record("Topic three", "t3")
        picked = self.git("rev-parse", "HEAD~1").stdout.strip()
        self.git("checkout", "-q", "main")
        self.record("Main claim", "main")
        self.assertEqual(self.git("cherry-pick", picked).returncode, 0)
        self.assertEqual(self.texts(), ["Shared", "Main claim", "Topic two"])

    def test_a_feature_include_follows_its_record_through_a_renumbering_merge(self):
        with (self.repo / ".gitattributes").open("a") as f:
            f.write(".docket/features.jsonl merge=docket\n")
        self.git("commit", "-qam", "attributes")
        self.git("checkout", "-qb", "topic")
        self.docket("claim", "Topic claim", "--state", "accepted")
        self.docket("feature", "start", "work", "--text", "Work", "--path", "src/**")
        self.docket("feature", "amend", "work", "--include", "c2")
        self.git("add", "-A")
        self.git("commit", "-qm", "topic")
        self.git("checkout", "-q", "main")
        self.docket("feature", "start", "other", "--text", "Other", "--path", "lib/**")
        self.record("Main claim", "main")
        self.git("add", "-A")
        self.git("commit", "-qm", "main feature")
        self.assertEqual(self.git("merge", "-q", "--no-edit", "topic").returncode, 0)
        self.assertEqual(self.texts(), ["Shared", "Main claim", "Topic claim"])
        check = subprocess.run(
            [DOCKET, "check"], cwd=self.repo, env=self.env, capture_output=True, text=True
        )
        self.assertEqual(check.returncode, 1, check.stdout)
        self.assertIn("c2 -> c3", check.stdout)
        self.docket("feature", "remap")
        shown = json.loads(self.docket("feature", "show", "work", "--json").stdout)
        self.assertEqual(shown["include"], ["c3"])
        self.assertEqual(self.docket("check").returncode, 0)

    def test_without_the_config_git_reports_a_conflict(self):
        # The whole section: a lone merge.docket.name makes git abort the merge
        # ("lacks command line") instead of reporting a conflict.
        self.git("config", "--remove-section", "merge.docket", check=False)
        self.git("checkout", "-qb", "topic")
        self.record("Topic claim", "topic")
        self.git("checkout", "-q", "main")
        self.record("Main claim", "main")
        self.assertNotEqual(self.git("merge", "--no-edit", "topic", check=False).returncode, 0)
        text = (self.repo / ".docket" / "ledger.jsonl").read_text(encoding="utf-8")
        self.assertIn("<<<<<<<", text)
