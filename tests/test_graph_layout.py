import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from docket.graph_layout import box_path, box_tree, neighbourhood, scope_dir


def rec(ident, kind="claim", scope=None):
    return {"id": ident, "kind": kind, "scope": scope or []}


class ScopeTests(unittest.TestCase):
    def test_scope_dir(self):
        self.assertEqual(scope_dir("docket/web/**"), ("docket", "web"))
        self.assertEqual(scope_dir("docket/cli/web.py"), ("docket", "cli"))
        self.assertEqual(scope_dir("justfile"), ())
        self.assertEqual(scope_dir("docs/*.md"), ("docs",))

    def test_box_path(self):
        self.assertEqual(box_path(["docket/web/**", "docket/cli/web.py"]), ("docket",))
        self.assertEqual(box_path(["docket/a.py,docs/b.md"]), ())
        self.assertIsNone(box_path([]))
        self.assertEqual(box_path(["justfile"]), ())


class NeighbourhoodTests(unittest.TestCase):
    chain = [("a", "b", "supports"), ("b", "c", "supports"), ("c", "d", "supports")]

    def test_chain_hops(self):
        ids = {"a", "b", "c", "d"}
        self.assertEqual(neighbourhood(self.chain, ids, "a", 1), {"a", "b"})
        self.assertEqual(neighbourhood(self.chain, ids, "a", 2), {"a", "b", "c"})

    def test_follows_edges_both_ways(self):
        ids = {"a", "b", "c", "d"}
        self.assertEqual(neighbourhood(self.chain, ids, "c", 1), {"b", "c", "d"})

    def test_join_costs_no_hop(self):
        edges = [
            ("c1", "d3_set1", "supports"),
            ("d3_set1", "d3", "supports"),
            ("c2", "d3_set2", "supports"),
            ("d3_set2", "d3", "supports"),
        ]
        ids = {"c1", "c2", "d3"}
        self.assertEqual(neighbourhood(edges, ids, "c1", 1), {"c1", "d3"})
        self.assertEqual(neighbourhood(edges, ids, "c1", 2), {"c1", "d3", "c2"})

    def test_unknown_focus(self):
        with self.assertRaisesRegex(ValueError, "nope is not in this selection"):
            neighbourhood(self.chain, {"a"}, "nope", 1)


class BoxTreeTests(unittest.TestCase):
    def test_kind(self):
        entries = [rec("c1", "claim"), rec("d1", "decision"), rec("q1", "question"), rec("c2")]
        root, loose = box_tree(entries, "kind")
        self.assertEqual(loose, [])
        self.assertEqual(
            {k: b.ids for k, b in root.children.items()},
            {
                "claims": ["c1", "c2"],
                "decisions": ["d1"],
                "questions": ["q1"],
            },
        )
        self.assertEqual(root.children["claims"].label, "claims")

    def test_scope_nests_and_merges(self):
        entries = [
            rec("a", scope=["docket/web/**"]),
            rec("b", scope=["docket/cli/x.py"]),
            rec("c", scope=["docket/cli/y.py"]),
            rec("d", scope=["docs/superpowers/specs/a.md"]),
            rec("e"),
            rec("f", scope=["justfile"]),
        ]
        root, loose = box_tree(entries, "scope")
        self.assertEqual(loose, ["e"])
        docket = root.children["docket/"]
        self.assertEqual(docket.label, "docket/")
        self.assertEqual(docket.ids, [])
        self.assertEqual(sorted(docket.children), ["cli/", "web/"])
        self.assertEqual(docket.children["cli/"].ids, ["b", "c"])
        merged = root.children["docs/"]
        self.assertEqual(merged.label, "docs/superpowers/specs/")
        self.assertEqual(merged.ids, ["d"])
        self.assertEqual(root.children["/"].label, "/")
        self.assertEqual(root.children["/"].ids, ["f"])


if __name__ == "__main__":
    unittest.main()
