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

from docket import corrections, features, merge_driver  # noqa: E402
from docket.ledger import make_record, read  # noqa: E402


def claim(ident, text, **kwargs):
    return make_record("claim", text, state="accepted", author="t", record_id=ident, **kwargs)


def write(path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


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
