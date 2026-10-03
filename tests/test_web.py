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
from docket.web.server import make_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.body = {"dot": "digraph docket {}", "records": [], "title": "t"}
        self.server = make_server(lambda: json.dumps(self.body).encode(), 0)
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
        other = make_server(lambda: b"{}", self.port)
        try:
            self.assertNotEqual(other.server_address[1], self.port)
        finally:
            other.server_close()

    def test_a_failing_payload_is_a_500_and_the_server_lives(self):
        def boom():
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

    def start(self, port=0):
        env = {
            **os.environ,
            "BROWSER": "true",
            "DOCKET_NO_UPDATE_CHECK": "1",
            "DOCKET_HOME": str(self.root / "home"),
        }
        argv = [sys.executable, str(ROOT / "bin" / "docket"), "graph", "--web"]
        if port is not None:
            argv += ["--port", str(port)]
        proc = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, cwd=self.root
        )
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

    def test_a_held_default_port_falls_back(self):
        first = self.start(port=None)
        a = self.first_line(first)
        second = self.start(port=None)
        b = self.first_line(second)
        for line in (a, b):
            self.assertRegex(line, r"^http://127\.0\.0\.1:\d+/\n$")
        self.assertNotEqual(a, b)
