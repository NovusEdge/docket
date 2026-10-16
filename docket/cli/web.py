"""`docket graph --web`: serve the relation graph to a browser until stopped."""

from __future__ import annotations

import argparse
import json
import os
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


def _filtered(args: argparse.Namespace) -> bool:
    # Unfiltered, the page needs retired records too, which selection() leaves
    # out unless asked; so it gets every record and no shown list.
    return any(getattr(args, flag, None) for flag in ("where", "kind", "state", "find"))


def _payload(args: argparse.Namespace, params: dict[str, str]) -> bytes:
    # Read on every request: the page polls, and a ledger of a few hundred
    # records reads in milliseconds. The page lays the graph out itself, so
    # query parameters sent by older pages are ignored.
    from docket.ledger import project

    _, shown, _ = selection(args)
    records = project(env.read(env.ledger_path()), validated=True)
    body = {
        "records": records,
        "shown": [e["id"] for e in shown] if _filtered(args) else None,
        "title": env.project_root().name,
    }
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def _stop(*_: object) -> None:
    raise KeyboardInterrupt


def _open_quietly(url: str) -> None:
    """Open the browser with its stdout and stderr on the null device.

    webbrowser starts the browser as a child that inherits our descriptors,
    and a browser starting fresh writes GPU, sandbox and extension warnings
    to them. The URL line is already flushed, so nothing of ours is lost.
    """
    import webbrowser

    saved = [os.dup(1), os.dup(2)]
    null = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(null, 1)
        os.dup2(null, 2)
        webbrowser.open(url)
    finally:
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        for fd in (null, *saved):
            os.close(fd)


def _banner(url: str, can_open: bool, keys: bool) -> str:
    from docket.cli.term import _c, _use_color, _use_glyphs

    color = _use_color()
    arrow = _c("2", "➜" if _use_glyphs() else ">", color)
    lines = [
        "",
        f"  {_c('6', 'docket', color)}  web view of {env.project_root().name}",
        "",
        f"  {arrow}  Local:   {_c('6', url, color)}",
    ]
    if keys:
        hint = "q + enter to quit"
        if can_open:
            hint = "o + enter to open in a browser, " + hint
        lines.append(f"  {arrow}  press {hint}")
    return "\n".join(lines) + "\n"


def _read_keys(server, url: str, can_open: bool) -> None:
    # EOF (Ctrl-D) ends the prompt, not the server; Ctrl-C still stops it.
    for line in sys.stdin:
        key = line.strip().lower()
        if key == "o" and can_open:
            try:
                _open_quietly(url)
            except Exception as exc:
                print(f"docket: cannot open a browser: {exc}", file=sys.stderr)
        elif key == "q":
            server.shutdown()
            return


def cmd_graph_web(args: argparse.Namespace) -> int:
    import signal
    import threading

    from docket.web import server as web_server

    index = web_server.DIST / "index.html"
    if not index.is_file():
        print(f"docket: web view files missing: {index}; run `just web-build`", file=sys.stderr)
        return 1
    selection(args)  # a bad --where fails here, before anything binds
    port = DEFAULT_PORT if args.port is None else args.port
    server = web_server.make_server(lambda params: _payload(args, params), port)
    # Installed before the URL line: a caller may terminate as soon as it reads it.
    signal.signal(signal.SIGTERM, _stop)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    # Without a display webbrowser falls back to a console browser (lynx,
    # w3m) on the inherited terminal and blocks there.
    can_open = sys.platform in ("win32", "darwin") or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    try:
        if sys.stdout.isatty():
            keys = sys.stdin.isatty()
            print(_banner(url, can_open, keys), flush=True)
            if keys:
                threading.Thread(
                    target=_read_keys, args=(server, url, can_open), daemon=True
                ).start()
        else:
            # The terminal viewer reads this one line through a pipe, and its
            # `w` key promises a browser, so a piped run still opens one.
            print(url, flush=True)
            try:
                if can_open:
                    _open_quietly(url)
            except Exception:
                pass
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
