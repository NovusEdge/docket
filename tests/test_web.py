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
        self.body = {"records": [], "shown": None, "title": "t"}
        self.seen = []
        self.dist = tempfile.TemporaryDirectory()
        root = Path(self.dist.name)
        (root / "assets").mkdir()
        (root / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")
        (root / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
        (root / "assets" / "index-abc123.css").write_text("body{}", encoding="utf-8")
        (root / "THIRD_PARTY_LICENSES.txt").write_text("MIT", encoding="utf-8")
        (root / "notes.md").write_text("not served", encoding="utf-8")

        def payload(params):
            self.seen.append(params)
            if params.get("group") == "bad":
                raise BadRequest("group must be none, kind or scope")
            return json.dumps({**self.body, "params": params}).encode()

        self.server = make_server(payload, 0, root=root)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.dist.cleanup()

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

    def test_hashed_assets_are_served_immutable(self):
        status, headers, body = self.get("/assets/index-abc123.js")
        self.assertEqual((status, body), (200, b"console.log(1)"))
        self.assertIn("javascript", headers["Content-Type"])
        self.assertEqual(headers["Cache-Control"], "max-age=31536000, immutable")
        status, headers, _ = self.get("/assets/index-abc123.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", headers["Content-Type"])

    def test_the_page_is_not_cached(self):
        _, headers, _ = self.get("/")
        self.assertEqual(headers["Cache-Control"], "no-cache")

    def test_the_licence_file_is_served(self):
        status, headers, _ = self.get("/THIRD_PARTY_LICENSES.txt")
        self.assertEqual(status, 200)
        self.assertIn("text/plain", headers["Content-Type"])

    def test_the_graph_carries_an_etag_and_a_match_gets_304(self):
        status, headers, body = self.get("/api/graph")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["records"], [])
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
        self.assertEqual(body, b"forbidden")

    def test_localhost_by_name_is_allowed(self):
        status, _, _ = self.get("/api/graph", {"Host": f"localhost:{self.port}"})
        self.assertEqual(status, 200)

    def test_paths_outside_the_route_list_are_404(self):
        for path in (
            "/../ledger.jsonl",
            "/server.py",
            "/notes.md",
            "/assets/../index.html",
            "/nope",
            "/index.html",
            "/viz-global.js",
        ):
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

    def start(self, port=0, browser="true", stderr=subprocess.DEVNULL, extra=()):
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
        argv += extra
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
        self.assertNotIn("dot", data)
        self.assertIn("records", data)
        self.assertIsNone(data["shown"])
        proc.terminate()
        self.assertEqual(proc.wait(timeout=5), 0)

    def graph(self, query, extra=()):
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
        proc = self.start(extra=extra)
        line = self.first_line(proc)
        port = int(line.rsplit(":", 1)[1].rstrip("/\n"))
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/graph" + query)
        resp = conn.getresponse()
        return resp.status, resp.read().decode()

    def test_layout_parameters_are_ignored(self):
        status, body = self.graph("?group=x&hops=9&focus=nope&orphans=maybe")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(sorted(r["id"] for r in data["records"]), ["c1", "c2", "c3"])
        self.assertIsNone(data["shown"])

    def test_where_names_the_shown_records(self):
        from unittest import mock

        from docket.cli import web

        a = {"id": "c1", "kind": "claim", "text": "a"}
        b = {"id": "c2", "kind": "claim", "text": "b"}
        with (
            mock.patch("docket.env.read", return_value=[]),
            mock.patch("docket.cli.web.selection", return_value=([a, b], [b], False)),
            mock.patch("docket.ledger.project", return_value=[a, b]),
        ):
            data = json.loads(web._payload(argparse.Namespace(where="b"), {}))
        self.assertEqual(data["shown"], ["c2"])
        self.assertEqual(len(data["records"]), 2)

    def test_where_reaches_the_payload_as_shown_ids(self):
        status, body = self.graph("", extra=["--where", "b"])
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["shown"], ["c2"])

    def test_find_also_reaches_the_payload(self):
        status, body = self.graph("", extra=["--find", "c"])
        self.assertEqual(status, 200)
        self.assertIsNotNone(json.loads(body)["shown"])

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

    def run_in_terminal(self, stdin_tty: bool, display: bool = True):
        from unittest import mock

        from docket.cli import web

        env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
        # The fake stdout is a tty, so outside an agent session the banner is
        # coloured and its escape codes split the strings asserted below.
        env["NO_COLOR"] = "1"
        if display:
            env["DISPLAY"] = ":0"
        server = mock.Mock()
        server.server_address = ("127.0.0.1", 1)
        server.serve_forever.side_effect = KeyboardInterrupt
        out = io.StringIO()
        out.isatty = lambda: True
        stdin = io.StringIO()
        stdin.isatty = lambda: stdin_tty
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(sys, "platform", "linux"),
            mock.patch("docket.web.server.make_server", return_value=server),
            mock.patch("docket.cli.web.selection"),
            mock.patch("docket.cli.web._open_quietly") as opened,
            mock.patch("threading.Thread") as thread,
            mock.patch("signal.signal"),
            mock.patch.object(sys, "stdin", stdin),
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(web.cmd_graph_web(argparse.Namespace(port=0, where=None)), 0)
        return out.getvalue(), opened, thread

    def test_a_terminal_gets_a_banner_and_no_browser(self):
        out, opened, thread = self.run_in_terminal(stdin_tty=True)
        opened.assert_not_called()
        self.assertIn("Local:   http://127.0.0.1:1/", out)
        self.assertIn("o + enter to open in a browser, q + enter to quit", out)
        thread.return_value.start.assert_called_once()

    def test_without_a_display_the_banner_does_not_offer_o(self):
        out, _, _ = self.run_in_terminal(stdin_tty=True, display=False)
        self.assertIn("press q + enter to quit", out)
        self.assertNotIn("o + enter", out)

    def test_without_a_terminal_on_stdin_no_keys_are_offered(self):
        out, opened, thread = self.run_in_terminal(stdin_tty=False)
        opened.assert_not_called()
        self.assertIn("http://127.0.0.1:1/", out)
        self.assertNotIn("press", out)
        thread.assert_not_called()

    def test_o_opens_the_browser_and_q_stops_the_server(self):
        from unittest import mock

        from docket.cli import web

        server = mock.Mock()
        with (
            mock.patch.object(sys, "stdin", io.StringIO("x\nO\nq\no\n")),
            mock.patch("docket.cli.web._open_quietly") as opened,
        ):
            web._read_keys(server, "http://127.0.0.1:1/", can_open=True)
        opened.assert_called_once_with("http://127.0.0.1:1/")
        server.shutdown.assert_called_once()

    def test_a_held_default_port_falls_back(self):
        first = self.start(port=None)
        a = self.first_line(first)
        second = self.start(port=None)
        b = self.first_line(second)
        for line in (a, b):
            self.assertRegex(line, r"^http://127\.0\.0\.1:\d+/\n$")
        self.assertNotEqual(a, b)
