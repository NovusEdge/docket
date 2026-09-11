#!/usr/bin/env python3
"""Install docket: a command on PATH plus a hook in every agent harness found
on this machine. Downloaded and run directly (`curl -fsSLO ... && python3
install.py`), not piped, so it always has a real tty to prompt with and a
real __file__ to find the checkout beside.

Must parse on Python 3.8: this file is how docket tells a too-old
interpreter it needs 3.10, so the check below has to run before anything
that would raise SyntaxError on 3.8 does.
"""
from __future__ import annotations

import sys

if sys.version_info < (3, 10):
    sys.stderr.write(
        "docket needs Python 3.10 or later; this interpreter is %d.%d.\n"
        % sys.version_info[:2]
    )
    sys.exit(1)

import argparse
import json
import os
import subprocess
from collections import namedtuple
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable, List, Optional, Tuple

GLYPHS = {"ok": "✓", "warn": "!", "bad": "✗", "skip": "·"}
GLYPHS_ASCII = {"ok": "ok", "warn": "!", "bad": "x", "skip": "-"}
COLORS = {"ok": "2", "warn": "3", "bad": "1", "skip": "8"}


def _use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt" and not os.environ.get("WT_SESSION"):
        return False
    return True


def _use_glyphs() -> bool:
    enc = getattr(sys.stdout, "encoding", None) or ""
    try:
        "✓".encode(enc)
        return True
    except (LookupError, UnicodeEncodeError):
        return False


USE_COLOR = _use_color()
GLYPH = GLYPHS if _use_glyphs() else GLYPHS_ASCII


def _c(code: str, text: str) -> str:
    if not USE_COLOR:
        return text
    return "\033[3%sm%s\033[0m" % (code, text)


def _dim(text: str) -> str:
    return _c("8", text)


def head(title: str, sub: str = "") -> None:
    print()
    line = "  %s %s" % (_c("3", title), _dim(sub)) if sub else "  %s" % _c("3", title)
    print(line)
    print("  " + _dim("─" * 50))


def _row(kind: str, label: str, detail: str = "") -> None:
    glyph = _c(COLORS[kind], GLYPH[kind])
    print("  %s %-14s %s" % (glyph, label, _dim(detail) if detail else ""))


def ok(label: str, detail: str = "") -> None:
    _row("ok", label, detail)


def warn(label: str, detail: str = "") -> None:
    _row("warn", label, detail)


def bad(label: str, detail: str = "") -> None:
    _row("bad", label, detail)


def skip(label: str, detail: str = "") -> None:
    _row("skip", label, detail)


def ask(prompt: str, default: str, no_tty: bool = False) -> str:
    """One-line prompt. Returns default immediately without a real tty, since
    a downloaded-and-run install must never block a non-interactive caller."""
    if no_tty or not sys.stdin.isatty():
        return default
    try:
        reply = input("  %s [%s]: " % (prompt, default)).strip()
    except EOFError:
        return default
    return reply or default


# Planning produces only these three. Anything a harness needs that they
# cannot express, such as Codex's TOML, happens outside the plan.
Write = namedtuple("Write", "path text")
Link = namedtuple("Link", "src dst")
Remove = namedtuple("Remove", "path")
Row = namedtuple("Row", "harness status detail")

Action = object  # Write, Link or Remove; untyped so 3.8 need not parse a Union

ExistsFn = Callable[[Path], bool]
ReadFn = Callable[[Path], Optional[str]]

Ctx = namedtuple(
    "Ctx",
    "home os_name checkout python path_entries exists read_text link_target project cwd",
)


def make_ctx(home: Path, os_name: str, checkout: Path, python: str,
             path_entries: List[str], exists: ExistsFn, read_text: ReadFn,
             link_target: ReadFn, project: bool, cwd: Path) -> Ctx:
    return Ctx(home, os_name, checkout, python, path_entries, exists, read_text,
               link_target, project, cwd)


def real_exists(p: Path) -> bool:
    return p.exists()


def real_read_text(p: Path) -> Optional[str]:
    try:
        return p.read_text()
    except OSError:
        return None


def real_link_target(p: Path) -> Optional[str]:
    try:
        return os.readlink(str(p))
    except OSError:
        return None


def pure_path(os_name: str, *parts: str) -> Path:
    """A path for os_name, buildable from a different host OS so a Linux test
    can assert what the Windows branch would plan."""
    cls = PureWindowsPath if os_name == "nt" else PurePosixPath
    return cls(*parts)


def on_path(directory: Path, path_entries: List[str]) -> bool:
    """directory is on PATH, compared entry by entry after normalising, never
    by substring: '~/.local/bin' must not match '~/.local/binx'."""
    want = str(directory).rstrip("/\\")
    for entry in path_entries:
        if not entry:
            continue
        if entry.rstrip("/\\") == want:
            return True
    return False


def on_path_cmd(name: str, path_entries: List[str], os_name: str, exists: ExistsFn) -> bool:
    """Whether an executable named `name` sits in a PATH directory. Folds
    command detection into the same pure `exists` the planner already takes,
    so no harness needs shutil.which."""
    names = [name, name + ".exe", name + ".cmd"] if os_name == "nt" else [name]
    for entry in path_entries:
        if not entry:
            continue
        base = pure_path(os_name, entry)
        for n in names:
            if exists(Path(str(base / n))):
                return True
    return False


def run_prefix(os_name: str, python: str, me: Path) -> str:
    """The command an agent or shim runs. A no-extension, shebangless file
    runs verbatim on POSIX but needs the interpreter spelled out on Windows,
    where cmd.exe and PowerShell won't execute it directly."""
    if os_name == "nt":
        return '"%s" "%s"' % (python, me)
    return str(me)


def default_prefix(home: Path, os_name: str) -> Path:
    if env := os.environ.get("PREFIX"):
        return Path(env).expanduser()
    return home / ".local" / "bin"


def default_dir(home: Path, os_name: str) -> Path:
    if env := os.environ.get("XDG_DATA_HOME"):
        return Path(env).expanduser() / "docket"
    if os_name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "docket"
    return home / ".local" / "share" / "docket"


def plan_command(ctx: Ctx, prefix: Path) -> Tuple[List[Action], Row]:
    docket_bin = ctx.checkout / "bin" / "docket"
    if ctx.os_name == "nt":
        target = prefix / "docket.cmd"
        content = (
            "@echo off\r\n"
            '"%s" "%s" %%*\r\n' % (ctx.python, docket_bin)
        )
        if ctx.read_text(target) == content:
            return [], Row("command", "skip", str(target))
        return [Write(target, content)], Row("command", "ok", str(target))

    target = prefix / "docket"
    # A link left over from a checkout that has since moved points nowhere.
    # Re-running the installer is the documented update path, so it has to
    # repair that rather than report the stale link as already installed.
    if ctx.link_target(target) == str(docket_bin):
        return [], Row("command", "skip", str(target))
    return [Link(docket_bin, target)], Row("command", "ok", str(target))


MARKER = "# added by the docket installer"


def shell_rc(home: Path, shell: str) -> Path:
    name = Path(shell).name
    if name == "zsh":
        return home / ".zshrc"
    if name == "bash":
        return home / ".bashrc"
    if name == "fish":
        return home / ".config" / "fish" / "config.fish"
    return home / ".profile"


def _sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def rc_line(shell: str, directory: Path) -> str:
    if Path(shell).name == "fish":
        return "fish_add_path %s" % _sh_quote(str(directory))
    return 'export PATH=%s:"$PATH"' % _sh_quote(str(directory))


def plan_rc_append(ctx: Ctx, prefix: Path, shell: str) -> Tuple[List[Action], Row]:
    if on_path(prefix, ctx.path_entries):
        return [], Row("path", "skip", "already on PATH")

    path = shell_rc(ctx.home, shell)
    line = rc_line(shell, prefix)
    existing = ctx.read_text(path) or ""
    if any(l.strip() == line for l in existing.splitlines()):
        return [], Row("path", "skip", "%s already has it" % path)

    block = ""
    if existing and not existing.endswith("\n"):
        block += "\n"
    if existing:
        block += "\n"
    block += "%s\n%s\n" % (MARKER, line)
    return [Write(path, existing + block)], Row("path", "warn", "added to %s, restart your shell" % path)


def _load_json(text: Optional[str]) -> dict:
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _dump_json(data: dict) -> str:
    return json.dumps(data, indent=2) + "\n"


def plan_claude(ctx: Ctx) -> Tuple[List[Action], Row]:
    installed = _load_json(ctx.read_text(ctx.home / ".claude" / "plugins" / "installed_plugins.json"))
    for key in installed.get("plugins", {}):
        if key.split("@")[0] == "docket":
            return [], Row("claude-code", "skip", "already a plugin: %s" % key)

    link = (ctx.cwd if ctx.project else ctx.home) / ".claude" / "skills" / "docket"
    # --project inside the docket repo would point the link at its own parent.
    if ctx.project and Path(ctx.cwd) == Path(ctx.checkout):
        return [], Row("claude-code", "skip", "the checkout is already the project")
    if ctx.link_target(link) == str(ctx.checkout):
        return [], Row("claude-code", "skip", str(link))
    if ctx.exists(link):
        return [], Row("claude-code", "skip", str(link))
    return [Link(ctx.checkout, link)], Row("claude-code", "ok", str(link))


def gemini_hook_entry(ctx: Ctx) -> dict:
    return {
        "name": "docket",
        "hooks": [
            {
                "type": "command",
                "command": '%s context --for gemini' % run_prefix(ctx.os_name, ctx.python, ctx.checkout / "bin" / "docket"),
                "timeout": 5000,
            }
        ],
    }


def _merge_hook_list(hooks: list, entry: dict, name_key: str = "name",
                      match: Optional[Callable[[dict], bool]] = None) -> Tuple[list, bool]:
    """Replace the entry docket owns (matched by `match`, or by name_key)
    and leave every other entry untouched. Returns (new_list, changed)."""
    matcher = match or (lambda h: h.get(name_key) == entry.get(name_key))
    out = []
    replaced = False
    changed = False
    for h in hooks:
        if matcher(h):
            replaced = True
            if h != entry:
                changed = True
            out.append(entry)
        else:
            out.append(h)
    if not replaced:
        out.append(entry)
        changed = True
    return out, changed


def plan_gemini(ctx: Ctx) -> Tuple[List[Action], Row]:
    if not ctx.exists(ctx.home / ".gemini"):
        return [], Row("gemini", "skip", "~/.gemini not found")

    path = ctx.home / ".gemini" / "settings.json"
    data = _load_json(ctx.read_text(path))
    hooks = data.setdefault("hooks", {})
    entries = hooks.setdefault("SessionStart", [])
    new_entries, changed = _merge_hook_list(entries, gemini_hook_entry(ctx))
    if not changed:
        return [], Row("gemini", "skip", str(path))
    hooks["SessionStart"] = new_entries
    return [Write(path, _dump_json(data))], Row("gemini", "ok", str(path))


def cursor_hook_entry(ctx: Ctx) -> dict:
    return {"command": '%s context --for cursor' % run_prefix(ctx.os_name, ctx.python, ctx.checkout / "bin" / "docket")}


def _docket_owns(command: str, ctx: Ctx) -> bool:
    return str(ctx.checkout / "bin" / "docket") in command


def plan_cursor(ctx: Ctx) -> Tuple[List[Action], Row]:
    if not ctx.exists(ctx.home / ".cursor"):
        return [], Row("cursor", "skip", "~/.cursor not found")

    actions: List[Action] = []
    path = ctx.home / ".cursor" / "hooks.json"
    data = _load_json(ctx.read_text(path))
    hooks = data.setdefault("hooks", {})
    entries = hooks.setdefault("sessionStart", [])
    entry = cursor_hook_entry(ctx)
    new_entries, changed = _merge_hook_list(
        entries, entry, match=lambda h: _docket_owns(h.get("command", ""), ctx)
    )
    if changed:
        hooks["sessionStart"] = new_entries
        data.setdefault("version", 1)
        actions.append(Write(path, _dump_json(data)))
        detail = str(path)
    else:
        detail = "%s up to date" % path

    if ctx.project:
        rule = ctx.cwd / ".cursor" / "rules" / "docket.mdc"
        text = (
            "---\nalwaysApply: true\n---\n\n"
            "See docket's skill for when and how to record a decision.\n"
        )
        if ctx.read_text(rule) != text:
            actions.append(Write(rule, text))

    if not actions:
        return [], Row("cursor", "skip", detail)
    return actions, Row("cursor", "ok", detail)


def copilot_hook_entry(ctx: Ctx) -> dict:
    docket_bin = ctx.checkout / "bin" / "docket"
    bash = 'DOCKET_AUTHOR=copilot %s context --for copilot' % run_prefix("posix", ctx.python, docket_bin)
    ps = '$env:DOCKET_AUTHOR="copilot"; & "%s" "%s" context --for copilot' % (ctx.python, docket_bin)
    return {"type": "command", "bash": bash, "powershell": ps, "timeoutSec": 5}


def plan_copilot(ctx: Ctx) -> Tuple[List[Action], Row]:
    present = ctx.exists(ctx.home / ".copilot") or on_path_cmd("copilot", ctx.path_entries, ctx.os_name, ctx.exists)
    if not present:
        return [], Row("copilot", "skip", "copilot not found")

    path = ctx.home / ".copilot" / "hooks" / "sessionStart.json"
    data = _load_json(ctx.read_text(path))
    data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    entries = hooks.setdefault("sessionStart", [])
    entry = copilot_hook_entry(ctx)
    new_entries, changed = _merge_hook_list(
        entries, entry, match=lambda h: _docket_owns(h.get("bash", ""), ctx)
    )
    if not changed:
        return [], Row("copilot", "skip", str(path))
    hooks["sessionStart"] = new_entries
    return [Write(path, _dump_json(data))], Row("copilot", "ok", str(path))


def opencode_plugin_source(ctx: Ctx) -> str:
    """v1 plugin API (opencode 1.18.x): a named export, an async function of
    PluginInput returning a Hooks object. `experimental.chat.system.transform`
    mutates output.system in place; there is no return value. Verified
    against sst/opencode's packages/plugin/src/index.ts -- the default-export
    `Plugin.define` shape in docs/installation.md is the unreleased v2 API."""
    docket_bin = ctx.checkout / "bin" / "docket"
    return (
        'import { execFileSync } from "node:child_process"\n\n'
        'const PYTHON = %s\n'
        'const DOCKET = %s\n\n'
        "export const Docket = async () => {\n"
        "  return {\n"
        '    "experimental.chat.system.transform": async (input, output) => {\n'
        "      try {\n"
        "        const ledger = execFileSync(PYTHON, [DOCKET, \"context\"], {\n"
        '          encoding: "utf8",\n'
        '          env: { ...process.env, DOCKET_AUTHOR: "opencode" },\n'
        "        })\n"
        "        if (ledger.trim()) output.system.push(ledger)\n"
        "      } catch {\n"
        "        return\n"
        "      }\n"
        "    },\n"
        "  }\n"
        "}\n"
    ) % (json.dumps(ctx.python), json.dumps(str(docket_bin)))


def plan_opencode(ctx: Ctx) -> Tuple[List[Action], Row]:
    if not ctx.exists(ctx.home / ".config" / "opencode"):
        return [], Row("opencode", "skip", "~/.config/opencode not found")

    path = ctx.home / ".config" / "opencode" / "plugins" / "docket" / "index.ts"
    text = opencode_plugin_source(ctx)
    if ctx.read_text(path) == text:
        return [], Row("opencode", "skip", str(path))
    return [Write(path, text)], Row("opencode", "ok", str(path))


def codex_present(ctx: Ctx) -> bool:
    return on_path_cmd("codex", ctx.path_entries, ctx.os_name, ctx.exists)


def codex_commands(ctx: Ctx) -> List[List[str]]:
    return [
        ["codex", "plugin", "marketplace", "add", str(ctx.checkout)],
        ["codex", "plugin", "add", "docket@NovusEdge"],
    ]


def codex_remove_commands() -> List[List[str]]:
    return [["codex", "plugin", "remove", "docket@NovusEdge"]]


HARNESS_TABLE = {
    "claude-code": plan_claude,
    "gemini": plan_gemini,
    "cursor": plan_cursor,
    "copilot": plan_copilot,
    "opencode": plan_opencode,
}


def plan(ctx: Ctx, prefix: Path, shell: str, selected: Optional[List[str]]) -> Tuple[List[Action], List[Row]]:
    actions: List[Action] = []
    rows: List[Row] = []

    cmd_actions, cmd_row = plan_command(ctx, prefix)
    actions += cmd_actions
    rows.append(cmd_row)

    rc_actions, rc_row = plan_rc_append(ctx, prefix, shell)
    actions += rc_actions
    rows.append(rc_row)

    names = selected if selected else list(HARNESS_TABLE)
    for name in names:
        fn = HARNESS_TABLE.get(name)
        if fn is None:
            rows.append(Row(name, "bad", "unknown harness"))
            continue
        a, r = fn(ctx)
        actions += a
        rows.append(r)

    # Codex enablement lives in config.toml, and the standard library cannot
    # write TOML. The CLI owns those two files, so apply() runs the commands
    # instead of planning a Write.
    if not selected or "codex" in selected:
        if codex_present(ctx):
            rows.append(Row("codex", "ok", " && ".join(" ".join(c) for c in codex_commands(ctx))))
        else:
            rows.append(Row("codex", "skip", "codex not found"))

    return actions, rows


def apply(actions: List[Action]) -> None:
    """The only code in this file that writes to disk."""
    for action in actions:
        if isinstance(action, Write):
            path = Path(action.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(action.text, newline="\n")
        elif isinstance(action, Link):
            dst = Path(action.dst)
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_name(dst.name + ".docket-tmp")
            if tmp.exists() or tmp.is_symlink():
                tmp.unlink()
            os.symlink(str(action.src), str(tmp))
            os.replace(str(tmp), str(dst))
        elif isinstance(action, Remove):
            path = Path(action.path)
            if path.is_symlink() or path.exists():
                path.unlink()
        else:
            raise TypeError("unknown action: %r" % (action,))


def describe(action: Action) -> str:
    if isinstance(action, Write):
        return "write  %s" % action.path
    if isinstance(action, Link):
        return "link   %s -> %s" % (action.dst, action.src)
    if isinstance(action, Remove):
        return "remove %s" % action.path
    return repr(action)


def _strip_hook(entries: list, ctx: Ctx, command_key: str) -> list:
    return [h for h in entries if not _docket_owns(h.get(command_key, ""), ctx)]


def plan_rc_remove(ctx: Ctx, prefix: Path, shell: str) -> List[Action]:
    """Drop the marker comment and the PATH line the installer appended.

    veil leaves its own block in the rc file forever; an uninstall that leaves
    a PATH entry pointing at a deleted command is worse than no uninstall.
    """
    path = shell_rc(ctx.home, shell)
    existing = ctx.read_text(path)
    if not existing:
        return []

    line = rc_line(shell, prefix)
    kept = []
    dropped = False
    for text in existing.splitlines():
        if text.strip() == MARKER or text.strip() == line:
            dropped = True
            continue
        kept.append(text)
    if not dropped:
        return []
    return [Write(path, "\n".join(kept).rstrip("\n") + "\n")]


def plan_uninstall(ctx: Ctx, prefix: Path, shell: str) -> List[Action]:
    actions: List[Action] = []

    for target in (prefix / "docket", prefix / "docket.cmd"):
        if ctx.exists(target):
            actions.append(Remove(target))

    actions += plan_rc_remove(ctx, prefix, shell)

    link = (ctx.cwd if ctx.project else ctx.home) / ".claude" / "skills" / "docket"
    if ctx.exists(link):
        actions.append(Remove(link))

    gpath = ctx.home / ".gemini" / "settings.json"
    gdata = _load_json(ctx.read_text(gpath))
    ghooks = gdata.get("hooks", {}).get("SessionStart", [])
    gremaining = [h for h in ghooks if h.get("name") != "docket"]
    if len(gremaining) != len(ghooks):
        gdata["hooks"]["SessionStart"] = gremaining
        actions.append(Write(gpath, _dump_json(gdata)))

    cpath = ctx.home / ".cursor" / "hooks.json"
    cdata = _load_json(ctx.read_text(cpath))
    centries = cdata.get("hooks", {}).get("sessionStart", [])
    cremaining = _strip_hook(centries, ctx, "command")
    if len(cremaining) != len(centries):
        cdata["hooks"]["sessionStart"] = cremaining
        actions.append(Write(cpath, _dump_json(cdata)))

    copath = ctx.home / ".copilot" / "hooks" / "sessionStart.json"
    codata = _load_json(ctx.read_text(copath))
    coentries = codata.get("hooks", {}).get("sessionStart", [])
    coremaining = _strip_hook(coentries, ctx, "bash")
    if len(coremaining) != len(coentries):
        codata["hooks"]["sessionStart"] = coremaining
        actions.append(Write(copath, _dump_json(codata)))

    ocpath = ctx.home / ".config" / "opencode" / "plugins" / "docket" / "index.ts"
    if ctx.exists(ocpath):
        actions.append(Remove(ocpath))

    return actions


def find_checkout() -> Optional[Path]:
    here = Path(__file__).resolve().parent
    if (here / "bin" / "docket").exists():
        return here
    return None


def clone_checkout(directory: Path, no_tty: bool) -> Optional[Path]:
    chosen = ask("Clone docket into", str(directory), no_tty)
    target = Path(chosen).expanduser()
    if target.exists() and any(target.iterdir()):
        r = subprocess.run(["git", "-C", str(target), "pull", "--ff-only"])
        if r.returncode != 0:
            bad("checkout", "%s exists and is not a clean docket clone" % target)
            return None
        return target
    r = subprocess.run(["git", "clone", "https://github.com/NovusEdge/docket.git", str(target)])
    if r.returncode != 0:
        bad("checkout", "git clone failed")
        return None
    return target


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="install.py", description=__doc__)
    p.add_argument("--dir", help="where to put the checkout if it must be cloned")
    p.add_argument("--prefix", help="where to put the docket command (default ~/.local/bin)")
    p.add_argument("--harness", action="append", help="only wire this harness; repeatable")
    p.add_argument("--project", action="store_true", help="wire this project instead of the user's home")
    p.add_argument("--yes", action="store_true", help="never prompt")
    p.add_argument("--no-tty", action="store_true", help="treat stdin as non-interactive")
    p.add_argument("--uninstall", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    no_tty = args.no_tty or args.yes

    home = Path.home()
    os_name = "nt" if os.name == "nt" else "posix"
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    shell = os.environ.get("SHELL", "/bin/sh")

    checkout = find_checkout()
    if checkout is None:
        directory = Path(args.dir).expanduser() if args.dir else default_dir(home, os_name)
        checkout = clone_checkout(directory, no_tty)
        if checkout is None:
            return 1

    prefix = Path(args.prefix).expanduser() if args.prefix else default_prefix(home, os_name)
    if sys.prefix != sys.base_prefix:
        warn("interpreter", "running from a venv; hooks will call %s" % sys.executable)

    ctx = make_ctx(
        home=home, os_name=os_name, checkout=checkout, python=sys.executable,
        path_entries=path_entries, exists=real_exists, read_text=real_read_text,
        link_target=real_link_target, project=args.project, cwd=Path.cwd(),
    )

    if args.uninstall:
        actions = plan_uninstall(ctx, prefix, shell)
        head("docket uninstall")
        codex = codex_remove_commands() if codex_present(ctx) else []
        if not actions and not codex:
            skip("nothing to remove")
            return 0
        for a in actions:
            print("  " + describe(a))
        for c in codex:
            print("  run    " + " ".join(c))
        if args.dry_run:
            return 0
        if not args.yes and ask("Remove these", "yes", no_tty).lower() not in ("y", "yes"):
            return 130
        apply(actions)
        for c in codex:
            subprocess.run(c, capture_output=True, text=True)
        ok("done", "your decision ledgers were left alone")
        return 0

    actions, rows = plan(ctx, prefix, shell, args.harness)

    head("docket install", str(checkout))
    for row in rows:
        fn = {"ok": ok, "warn": warn, "bad": bad, "skip": skip}[row.status]
        fn(row.harness, row.detail)

    if args.dry_run:
        print()
        for a in actions:
            print("  " + describe(a))
        return 0

    try:
        apply(actions)
    except OSError as e:
        bad("apply", str(e))
        return 1

    if (not args.harness or "codex" in args.harness) and codex_present(ctx):
        for command in codex_commands(ctx):
            r = subprocess.run(command, capture_output=True, text=True)
            if r.returncode != 0:
                warn("codex", "`%s` failed: %s" % (" ".join(command), r.stderr.strip()[:120]))
                break

    if os_name == "nt" and not on_path(prefix, path_entries):
        windows_path_add(prefix)

    print()
    ok("installed", "run `docket --version` in a new shell")
    return 0


def windows_path_add(directory: Path) -> None:
    """Append directory to the user's PATH via the registry, not setx: setx
    rewrites the value as REG_SZ and expands every %VAR% already in PATH,
    corrupting it the same way [Environment]::SetEnvironmentVariable does."""
    import winreg
    import ctypes

    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS)
    try:
        try:
            value, kind = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            value, kind = "", winreg.REG_EXPAND_SZ
        parts = [p for p in value.split(";") if p]
        if str(directory) in parts:
            return
        parts.append(str(directory))
        winreg.SetValueEx(key, "Path", 0, kind, ";".join(parts))
    finally:
        winreg.CloseKey(key)

    HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG = 0xFFFF, 0x1A, 0x0002
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", SMTO_ABORTIFHUNG, 5000, None
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
