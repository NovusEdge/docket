"""Run with: python3 tests/test_install.py"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath, PureWindowsPath

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import install as inst


def fake_fs(files, links=None):
    """files: {str(path): text}. links: {str(path): symlink target}."""
    links = links or {}

    def exists(p):
        return str(p) in files or str(p) in links

    def read_text(p):
        return files.get(str(p))

    def link_target(p):
        return links.get(str(p))

    return exists, read_text, link_target


def ctx_for(home, os_name, files, project=False, cwd=None, links=None):
    exists, read_text, link_target = fake_fs(files, links)
    return inst.make_ctx(
        home=home, os_name=os_name, checkout=Path("/checkout"), python="/usr/bin/python3",
        path_entries=["/home/u/.local/bin"], exists=exists, read_text=read_text,
        link_target=link_target, project=project, cwd=cwd or home,
    )


def main() -> int:
    # Planning is pure: both branches assertable from whatever host runs the test.
    posix_home = PurePosixPath("/home/u")
    win_home = PureWindowsPath("C:/Users/u")

    ctx = ctx_for(posix_home, "posix", {})
    actions, _ = inst.plan_command(ctx, posix_home / ".local" / "bin")
    assert any(isinstance(a, inst.Link) and str(a.dst).endswith("docket") for a in actions), actions

    ctx = ctx_for(win_home, "nt", {})
    actions, _ = inst.plan_command(ctx, win_home / "bin")
    assert any(isinstance(a, inst.Write) and str(a.path).endswith("docket.cmd") for a in actions), actions

    # A link left by a checkout that has since moved must be repaired, not
    # reported as already installed.
    link = posix_home / ".local" / "bin" / "docket"
    ctx = ctx_for(posix_home, "posix", {}, links={str(link): "/old/checkout/bin/docket"})
    actions, _ = inst.plan_command(ctx, posix_home / ".local" / "bin")
    assert any(isinstance(a, inst.Link) for a in actions), "a stale link must be relinked"

    ctx = ctx_for(posix_home, "posix", {}, links={str(link): "/checkout/bin/docket"})
    actions, row = inst.plan_command(ctx, posix_home / ".local" / "bin")
    assert actions == [] and row.status == "skip", "a correct link must be left alone"

    # Every planned JSON parses and carries the resolved absolute checkout path.
    ctx = ctx_for(posix_home, "posix", {
        str(posix_home / ".gemini"): "",
        str(posix_home / ".cursor"): "",
        str(posix_home / ".copilot"): "",
        str(posix_home / ".config" / "opencode"): "",
    })
    for fn in (inst.plan_gemini, inst.plan_cursor, inst.plan_copilot):
        actions, row = fn(ctx)
        assert row.status == "ok", row
        for a in actions:
            if isinstance(a, inst.Write) and a.path.suffix != ".mdc":
                data = json.loads(a.text)
                assert "/path/to/" not in a.text, a.text
                assert "/checkout" in a.text, a.text
    actions, row = inst.plan_opencode(ctx)
    assert row.status == "ok"
    assert "/path/to/" not in actions[0].text
    assert "/checkout" in actions[0].text

    # A second plan over an applied tree produces no actions.
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        home = d / "home"
        checkout = d / "checkout"
        (checkout / "bin").mkdir(parents=True)
        (checkout / "bin" / "docket").write_text("#!/usr/bin/env python3\n")
        prefix = home / ".local" / "bin"
        (home / ".gemini").mkdir(parents=True)
        (home / ".cursor").mkdir(parents=True)
        (home / ".copilot").mkdir(parents=True)
        (home / ".config" / "opencode").mkdir(parents=True)

        ctx = inst.make_ctx(
            home=home, os_name="posix", checkout=checkout, python=sys.executable,
            path_entries=[str(prefix)], exists=inst.real_exists, read_text=inst.real_read_text,
            link_target=inst.real_link_target, project=False, cwd=home,
        )
        actions, rows = inst.plan(ctx, prefix, "/bin/bash", None)
        assert actions, "first plan over an empty tree must do something"
        inst.apply(actions)

        actions2, rows2 = inst.plan(ctx, prefix, "/bin/bash", None)
        assert actions2 == [], actions2

        # --uninstall leaves the ledger and unmanaged keys untouched.
        ledger_dir = home.parent / "proj" / ".docket"
        ledger_dir.mkdir(parents=True)
        ledger = ledger_dir / "ledger.jsonl"
        ledger.write_text('{"id": "d1"}\n')

        gemini_path = home / ".gemini" / "settings.json"
        gdata = json.loads(gemini_path.read_text())
        gdata["hooks"]["SessionStart"].append({"name": "someone-else", "hooks": []})
        gemini_path.write_text(json.dumps(gdata))

        uninstall_actions = inst.plan_uninstall(ctx, prefix, "/bin/bash")
        inst.apply(uninstall_actions)

        assert ledger.exists(), "uninstall must not touch the decision ledger"
        remaining = json.loads(gemini_path.read_text())
        names = [h.get("name") for h in remaining["hooks"]["SessionStart"]]
        assert "someone-else" in names, "unmanaged hook entries must survive uninstall"
        assert "docket" not in names, "docket's own entry must be gone"
        assert not (prefix / "docket").exists()

    # The rc-file append is idempotent.
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        ctx = inst.make_ctx(
            home=d, os_name="posix", checkout=Path("/checkout"), python="/usr/bin/python3",
            path_entries=[], exists=inst.real_exists, read_text=inst.real_read_text,
            link_target=inst.real_link_target, project=False, cwd=d,
        )
        prefix = d / "bin"
        actions, row = inst.plan_rc_append(ctx, prefix, "/bin/bash")
        assert row.status == "warn"
        inst.apply(actions)
        first = (d / ".bashrc").read_text()

        actions2, row2 = inst.plan_rc_append(ctx, prefix, "/bin/bash")
        assert actions2 == [], "a second plan against the same rc file must be a no-op"

        (d / ".bashrc").write_text(first + "alias ll='ls -l'\n")
        inst.apply(inst.plan_rc_remove(ctx, prefix, "/bin/bash"))
        after = (d / ".bashrc").read_text()
        assert inst.MARKER not in after, "uninstall must remove the PATH line it added"
        assert "alias ll" in after, "uninstall must leave the user's own rc lines"

    # PATH membership rejects a look-alike directory.
    assert inst.on_path(PurePosixPath("/home/u/.local/bin"), ["/home/u/.local/binx"]) is False
    assert inst.on_path(PurePosixPath("/home/u/.local/bin"), ["/home/u/.local/bin"]) is True

    # Every prompt returns its documented default when there is no tty.
    assert inst.ask("dir", "/default/dir", no_tty=True) == "/default/dir"

    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
