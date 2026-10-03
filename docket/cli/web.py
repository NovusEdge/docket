"""`docket graph --web`: serve the relation graph to a browser until stopped."""

from __future__ import annotations

import argparse
import json
import sys

from docket import ROOT, env
from docket.cli.export import selection

# docket.cli imports this module while building the parser on every
# invocation, so the server, browser and renderer imports stay inside the
# functions that need them.
DEFAULT_PORT = 7347


def web_command() -> list[str]:
    """The argv the terminal viewer runs for `w`; it appends --where QUERY."""
    return [sys.executable, str(ROOT / "bin" / "docket"), "graph", "--web"]


def port_arg(text: str) -> int:
    if not text.isdigit() or int(text) > 65535:
        raise argparse.ArgumentTypeError(f"{text!r} is not a port, 0 to 65535")
    return int(text)


def web_conflict(args: argparse.Namespace) -> str | None:
    """The first terminal-only flag given with --web, or None."""
    if not args.web:
        return None
    for flag, on in (
        ("--interactive", args.interactive),
        ("--no-interactive", args.no_interactive),
        ("--plain", args.plain),
        ("--style", args.style is not None),
    ):
        if on:
            return flag
    return None


def _payload(args: argparse.Namespace) -> bytes:
    # Read on every request: the page polls, and a ledger of a few hundred
    # records reads and renders in milliseconds.
    from docket.graph_export import to_dot
    from docket.ledger import project

    _, shown, superseded = selection(args)
    records = project(env.read(env.ledger_path()), validated=True)
    body = {
        "dot": to_dot(shown, superseded=superseded),
        "records": records,
        "title": env.project_root().name,
    }
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def _stop(*_: object) -> None:
    raise KeyboardInterrupt


def cmd_graph_web(args: argparse.Namespace) -> int:
    import signal
    import webbrowser

    from docket.web import server as web_server

    root = web_server.WEB_ROOT
    missing = [
        str(root / name) for name in web_server.ASSETS.values() if not (root / name).is_file()
    ]
    if missing:
        print(f"docket: web view files missing: {', '.join(missing)}", file=sys.stderr)
        return 1
    selection(args)  # a bad --where fails here, before anything binds
    port = DEFAULT_PORT if args.port is None else args.port
    server = web_server.make_server(lambda: _payload(args), port)
    # Installed before the URL line: a caller may terminate as soon as it reads it.
    signal.signal(signal.SIGTERM, _stop)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    # flush: the terminal viewer reads this line through a pipe.
    print(url, flush=True)
    try:
        try:
            webbrowser.open(url)
        except Exception:
            pass
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
