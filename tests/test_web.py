import argparse
import contextlib
import http.client
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from docket import ROOT
from docket.web.server import BadRequest, make_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.body = {"dot": "digraph docket {}", "records": [], "title": "t"}
        self.seen = []

        def payload(params):
            self.seen.append(params)
            if params.get("group") == "bad":
                raise BadRequest("group must be none, kind or scope")
            return json.dumps({**self.body, "params": params}).encode()

        self.server = make_server(payload, 0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def get(self, path, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path, headers=headers or {})
        resp = conn.getresponse()
        return resp.status, dict(resp.getheaders()), resp.read()

    def test_the_page_is_served(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b"<html", body)

    def test_the_renderer_is_served(self):
        status, _, body = self.get("/viz-global.js")
        self.assertEqual(status, 200)
        self.assertIn(b"Viz.js", body[:200])

    def test_the_graph_carries_an_etag_and_a_match_gets_304(self):
        status, headers, body = self.get("/api/graph")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["dot"], "digraph docket {}")
        etag = headers["ETag"]
        status, _, body = self.get("/api/graph", {"If-None-Match": etag})
        self.assertEqual((status, body), (304, b""))

    def test_the_query_reaches_the_payload_as_a_dict(self):
        status, _, _ = self.get("/api/graph?group=scope&hops=3&hops=4")
        self.assertEqual(status, 200)
        self.assertEqual(self.seen[-1], {"group": "scope", "hops": "3"})
        self.get("/api/graph")
        self.assertEqual(self.seen[-1], {})

    def test_a_bad_request_is_a_quiet_400_with_its_text(self):
        err = io.StringIO()
        with redirect_stderr(err):
            status, headers, body = self.get("/api/graph?group=bad")
        self.assertEqual(status, 400)
        self.assertIn("text/plain", headers["Content-Type"])
        self.assertEqual(body, b"group must be none, kind or scope")
        self.assertEqual(err.getvalue(), "")

    def test_different_params_give_different_etags(self):
        _, first, _ = self.get("/api/graph?group=kind")
        _, second, _ = self.get("/api/graph?group=scope")
        self.assertNotEqual(first["ETag"], second["ETag"])

    def test_a_changed_payload_changes_the_etag(self):
        _, first, _ = self.get("/api/graph")
        self.body["records"] = [{"id": "c1"}]
        status, second, _ = self.get("/api/graph", {"If-None-Match": first["ETag"]})
        self.assertEqual(status, 200)
        self.assertNotEqual(first["ETag"], second["ETag"])

    def test_a_foreign_host_is_refused(self):
        status, _, body = self.get("/api/graph", {"Host": f"evil.example:{self.port}"})
        self.assertEqual(status, 403)
        self.assertNotIn(b"digraph", body)

    def test_localhost_by_name_is_allowed(self):
        status, _, _ = self.get("/api/graph", {"Host": f"localhost:{self.port}"})
        self.assertEqual(status, 200)

    def test_paths_outside_the_route_list_are_404(self):
        for path in ("/../ledger.jsonl", "/server.py", "/vendor/NOTICE", "/nope", "/index.html"):
            self.assertEqual(self.get(path)[0], 404, path)

    def test_a_taken_port_falls_back_to_a_free_one(self):
        other = make_server(lambda params: b"{}", self.port)
        try:
            self.assertNotEqual(other.server_address[1], self.port)
        finally:
            other.server_close()

    def test_a_failing_payload_is_a_500_and_the_server_lives(self):
        def boom(params):
            raise ValueError("ledger unreadable")

        server = make_server(boom, 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        err = io.StringIO()
        try:
            with redirect_stderr(err):
                for _ in range(2):
                    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                    conn.request("GET", "/api/graph")
                    resp = conn.getresponse()
                    self.assertEqual(resp.status, 500)
                    self.assertIn(b"ledger unreadable", resp.read())
            self.assertIn("docket: web: ledger unreadable", err.getvalue())
        finally:
            server.shutdown()
            server.server_close()

    def test_a_client_that_hangs_up_leaves_no_traceback(self):
        err = io.StringIO()
        with redirect_stderr(err):
            for exc in (BrokenPipeError(32, "Broken pipe"), ConnectionResetError(104, "reset")):
                try:
                    raise exc
                except OSError:
                    self.server.handle_error(None, ("127.0.0.1", 1))
        self.assertEqual(err.getvalue(), "")

    def test_any_other_handler_error_still_prints(self):
        err = io.StringIO()
        with redirect_stderr(err):
            try:
                raise KeyError("real bug")
            except KeyError:
                self.server.handle_error(None, ("127.0.0.1", 1))
        self.assertIn("real bug", err.getvalue())


class ImportCostTests(unittest.TestCase):
    def test_importing_the_cli_does_not_load_the_server(self):
        code = "import sys, docket.cli; sys.exit('http.server' in sys.modules)"
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())


class WebCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(
            ["git", "-C", str(self.root), "init", "-b", "main"], check=True, capture_output=True
        )
        (self.root / ".docket").mkdir()
        (self.root / ".docket" / "ledger.jsonl").write_text("", encoding="utf-8")
        self.procs = []

    def tearDown(self):
        for proc in self.procs:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
            proc.stdout.close()
        self.tmp.cleanup()

    def start(self, port=0, browser="true", stderr=subprocess.DEVNULL):
        env = {
            **os.environ,
            "BROWSER": browser,
            "DISPLAY": os.environ.get("DISPLAY", ":0"),
            "DOCKET_NO_UPDATE_CHECK": "1",
            "DOCKET_HOME": str(self.root / "home"),
        }
        argv = [sys.executable, str(ROOT / "bin" / "docket"), "graph", "--web"]
        if port is not None:
            argv += ["--port", str(port)]
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=stderr, env=env, cwd=self.root)
        self.procs.append(proc)
        return proc

    def first_line(self, proc):
        box = []
        reader = threading.Thread(target=lambda: box.append(proc.stdout.readline()), daemon=True)
        reader.start()
        reader.join(timeout=10)
        if not box:
            self.fail("URL line never arrived (stdout not flushed?)")
        return box[0].decode()

    def test_the_url_is_the_first_line_through_a_pipe(self):
        proc = self.start()
        line = self.first_line(proc)
        self.assertRegex(line, r"^http://127\.0\.0\.1:\d+/\n$")
        port = int(line.rsplit(":", 1)[1].rstrip("/\n"))
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/graph")
        data = json.loads(conn.getresponse().read())
        self.assertIn("dot", data)
        self.assertIn("records", data)
        proc.terminate()
        self.assertEqual(proc.wait(timeout=5), 0)

    def graph(self, query):
        env = {**os.environ, "DOCKET_NO_UPDATE_CHECK": "1", "DOCKET_HOME": str(self.root / "home")}
        docket = [sys.executable, str(ROOT / "bin" / "docket")]
        for text, link, scope in (
            ("a", [], "src/a.py"),
            ("b", ["--supports", "c1"], "src/b.py"),
            ("c", ["--supports", "c2"], "docs/x.md"),
        ):
            subprocess.run(
                [*docket, "claim", text, "--scope", scope, *link],
                cwd=self.root,
                env=env,
                check=True,
                capture_output=True,
            )
        proc = self.start()
        line = self.first_line(proc)
        port = int(line.rsplit(":", 1)[1].rstrip("/\n"))
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/graph" + query)
        resp = conn.getresponse()
        return resp.status, resp.read().decode()

    def test_bad_layout_parameters_are_400(self):
        for query in ("?group=x", "?hops=abc", "?hops=0", "?hops=9", "?focus=nope"):
            status, body = self.graph(query)
            self.assertEqual(status, 400, query)
            self.assertNotIn("Traceback", body)

    def test_group_scope_boxes_the_graph(self):
        status, body = self.graph("?group=scope")
        self.assertEqual(status, 200)
        self.assertIn("subgraph cluster_", json.loads(body)["dot"])

    def test_focus_marks_the_node_and_keeps_every_record(self):
        status, body = self.graph("?focus=c1&hops=1")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("focus", data["dot"])
        self.assertEqual(len(data["records"]), 3)

    def test_the_browser_s_own_output_stays_off_the_terminal(self):
        # A browser launched by webbrowser inherits our stdout and stderr, so
        # Chrome's GPU and extension warnings used to land in the terminal.
        script = self.root / "noisy-browser"
        marker = self.root / "browser-ran"
        script.write_text(
            f'#!/bin/sh\necho browser-out\necho browser-err >&2\ntouch "{marker}"\n',
            encoding="utf-8",
        )
        script.chmod(0o755)
        proc = self.start(browser=str(script), stderr=subprocess.PIPE)
        self.assertRegex(self.first_line(proc), r"^http://127\.0\.0\.1:\d+/\n$")
        for _ in range(100):
            if marker.exists():
                break
            threading.Event().wait(0.05)
        self.assertTrue(marker.exists(), "the browser command never ran")
        proc.terminate()
        out, err = proc.communicate(timeout=5)
        self.assertNotIn(b"browser-out", out)
        self.assertNotIn(b"browser-err", err)

    def test_no_browser_is_opened_without_a_display(self):
        from unittest import mock

        from docket.cli import web

        env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
        server = mock.Mock()
        server.server_address = ("127.0.0.1", 1)
        server.serve_forever.side_effect = KeyboardInterrupt
        args = argparse.Namespace(port=0, where=None)
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(sys, "platform", "linux"),
            mock.patch("docket.web.server.make_server", return_value=server),
            mock.patch("docket.cli.web.selection"),
            mock.patch("webbrowser.open") as opened,
            mock.patch("signal.signal"),
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            self.assertEqual(web.cmd_graph_web(args), 0)
        opened.assert_not_called()
        self.assertEqual(out.getvalue(), "http://127.0.0.1:1/\n")

    def test_a_held_default_port_falls_back(self):
        first = self.start(port=None)
        a = self.first_line(first)
        second = self.start(port=None)
        b = self.first_line(second)
        for line in (a, b):
            self.assertRegex(line, r"^http://127\.0\.0\.1:\d+/\n$")
        self.assertNotEqual(a, b)
