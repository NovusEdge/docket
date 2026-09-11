"""Run with: python3 tests/test_install.py"""

import json
import shutil
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


def ctx_for(home, os_name, files, project=False, cwd=None, links=None, path_entries=None, forced=None):
    exists, read_text, link_target = fake_fs(files, links)
    return inst.make_ctx(
        home=home, os_name=os_name, checkout=Path("/checkout"), python="/usr/bin/python3",
        path_entries=path_entries if path_entries is not None else ["/home/u/.local/bin"],
        exists=exists, read_text=read_text, link_target=link_target, project=project,
        cwd=cwd or home, forced=frozenset(forced or ()),
    )


def scripted(replies):
    """A read_line that hands out replies in order and fails loudly if the
    flow asks for more than the test scripted."""
    it = iter(replies)

    def read_line():
        try:
            return next(it)
        except StopIteration:
            raise AssertionError("flow asked for a reply the test did not script")
    return read_line


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

    # An explicitly chosen harness is configured even when its directory is
    # absent, because the guided flow offers undetected harnesses for a tool
    # the user is about to install.
    bare = ctx_for(posix_home, "posix", {})
    actions, row = inst.plan_cursor(bare)
    assert actions == [] and row.status == "skip", "an unchosen absent harness stays skipped"

    forced = bare._replace(forced=frozenset({"cursor"}))
    actions, row = inst.plan_cursor(forced)
    assert row.status == "ok" and actions, "a chosen harness must be configured"

    # PATH membership rejects a look-alike directory.
    assert inst.on_path(PurePosixPath("/home/u/.local/bin"), ["/home/u/.local/binx"]) is False
    assert inst.on_path(PurePosixPath("/home/u/.local/bin"), ["/home/u/.local/bin"]) is True

    # Every prompt returns its documented default when there is no tty.
    assert inst.ask("dir", "/default/dir", no_tty=True) == "/default/dir"

    # --- interactive flow ---
    noop_write = lambda line: None

    posix_home2 = PurePosixPath("/home/u")
    detect_ctx = ctx_for(posix_home2, "posix", {
        str(posix_home2 / ".gemini"): "",
        str(posix_home2 / ".cursor"): "",
    })
    names = inst.harness_names()
    detected = inst.detect_harnesses(detect_ctx)
    assert detected[names.index("gemini")] is True
    assert detected[names.index("cursor")] is True
    assert detected[names.index("copilot")] is False

    # Accepting every default selects exactly the detected harnesses.
    selected = inst.select_harnesses(names, detected, scripted([""]), noop_write)
    assert set(selected) == {"gemini", "cursor"}

    # Typing an index toggles it; an undetected harness can be selected this way.
    copilot_i = names.index("copilot") + 1
    selected = inst.select_harnesses(names, detected, scripted(["%d" % copilot_i, ""]), noop_write)
    assert "copilot" in selected and "gemini" in selected and "cursor" in selected

    # Toggling twice is a no-op.
    gemini_i = names.index("gemini") + 1
    selected = inst.select_harnesses(names, detected, scripted(["%d" % gemini_i, "%d" % gemini_i, ""]), noop_write)
    assert set(selected) == {"gemini", "cursor"}

    selected = inst.select_harnesses(names, detected, scripted(["all", ""]), noop_write)
    assert set(selected) == set(names)

    selected = inst.select_harnesses(names, detected, scripted(["none", ""]), noop_write)
    assert selected == []

    # Unparseable input re-prompts instead of falling through to a default.
    selected = inst.select_harnesses(names, detected, scripted(["nonsense", ""]), noop_write)
    assert set(selected) == {"gemini", "cursor"}, "garbage must not be read as acceptance"

    # confirm() re-prompts on unparseable input and honours the stated default.
    assert inst.confirm("go", True, scripted([""]), noop_write) is True
    assert inst.confirm("go", False, scripted([""]), noop_write) is False
    assert inst.confirm("go", True, scripted(["huh", "n"]), noop_write) is False

    # A prefix typed as ~/x expands; a relative one becomes absolute against cwd.
    home3 = PurePosixPath("/home/u")
    cwd3 = PurePosixPath("/work/proj")
    got = inst.ask_prefix(home3 / ".local" / "bin", home3, cwd3, scripted(["~/x"]), noop_write)
    assert str(got) == str(home3 / "x"), got
    got = inst.ask_prefix(home3 / ".local" / "bin", home3, cwd3, scripted(["bin"]), noop_write)
    assert str(got) == str(cwd3 / "bin"), got
    got = inst.ask_prefix(home3 / ".local" / "bin", home3, cwd3, scripted([""]), noop_write)
    assert str(got) == str(home3 / ".local" / "bin"), got

    # Declining the PATH append drops the rc Write and marks the row skipped.
    ctx_path = ctx_for(posix_home2, "posix", {}, path_entries=[])
    prefix2 = posix_home2 / ".local" / "bin"
    actions, rows = inst.plan(ctx_path, prefix2, "/bin/bash", [])
    actions2, rows2 = inst.confirm_path(ctx_path, prefix2, "/bin/bash", actions, rows, scripted(["n"]), noop_write)
    assert not any(isinstance(a, inst.Write) and str(a.path).endswith(".bashrc") for a in actions2)
    row = next(r for r in rows2 if r.harness == "path")
    assert row.status == "skip"

    # --dry-run and --yes run main() end to end without a tty and without
    # calling read_line, since input() would block if the flow tried.
    with tempfile.TemporaryDirectory() as tmp:
        env = {"HOME": tmp, "PATH": "/usr/bin:/bin"}
        r = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent.parent / "install.py"),
             "--dry-run", "--dir", str(Path(tmp) / "checkout")],
            input="", capture_output=True, text=True, env=env, timeout=30,
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert not any(Path(tmp).rglob("*")), "dry-run must write nothing"

    # --- swap_checkout ---
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        dest = d / "install"
        dest.mkdir()
        (dest / ".git").mkdir()
        (dest / "old.txt").write_text("old")

        new_tree = d / "clone-staging"
        new_tree.mkdir()
        (new_tree / ".git").mkdir()
        (new_tree / "bin").mkdir()
        (new_tree / "bin" / "docket").write_text("#!/usr/bin/env python3\n")

        inst.swap_checkout(new_tree, dest)
        assert (dest / ".git").is_dir(), "the new clone's .git must survive the swap"
        assert (dest / "bin" / "docket").exists()
        assert not (dest / "old.txt").exists(), "the old tree's contents must be replaced"
        assert not new_tree.exists(), "the staging tree must be consumed by the swap"
        assert not any(p.name.endswith(".docket-old") for p in d.iterdir()), "no leftover aside directory"

        # A failed swap restores the original and leaves no aside directory.
        dest2 = d / "install2"
        dest2.mkdir()
        (dest2 / ".git").mkdir()
        (dest2 / "marker.txt").write_text("still here")

        real_move = shutil.move
        calls = []

        def flaky_move(src, dst):
            calls.append((src, dst))
            if len(calls) == 2:  # the move of new_tree into dest2
                raise OSError("simulated failure")
            return real_move(src, dst)

        new_tree2 = d / "clone-staging2"
        new_tree2.mkdir()

        try:
            shutil.move = flaky_move
            raised = False
            try:
                inst.swap_checkout(new_tree2, dest2)
            except OSError:
                raised = True
            assert raised, "swap_checkout must propagate the failure"
        finally:
            shutil.move = real_move

        assert (dest2 / "marker.txt").exists(), "a failed swap must restore the original directory"
        assert not any(p.name.endswith(".docket-old") for p in d.iterdir()), "no leftover aside directory after a failed swap"

    # --- forced harnesses override detection ---
    posix_home4 = PurePosixPath("/home/u")
    ctx_undetected = ctx_for(posix_home4, "posix", {})  # no ~/.gemini, ~/.cursor, ~/.copilot, ~/.config/opencode

    for fn, name in ((inst.plan_gemini, "gemini"), (inst.plan_cursor, "cursor"),
                     (inst.plan_copilot, "copilot"), (inst.plan_opencode, "opencode")):
        actions, row = fn(ctx_undetected)
        assert row.status == "skip", "%s: undetected and unforced must still skip" % name

    ctx_forced = ctx_for(posix_home4, "posix", {}, forced={"gemini", "cursor", "copilot", "opencode"})
    for fn, name in ((inst.plan_gemini, "gemini"), (inst.plan_cursor, "cursor"),
                     (inst.plan_copilot, "copilot"), (inst.plan_opencode, "opencode")):
        actions, row = fn(ctx_forced)
        assert row.status == "ok", "%s: a forced-but-undetected harness must still plan its config" % name
        assert any(isinstance(a, inst.Write) for a in actions), actions

    # main()'s plan() call must carry the interactive selection into ctx.forced.
    ctx_plan = ctx_for(posix_home4, "posix", {})
    actions, rows = inst.plan(ctx_plan._replace(forced=frozenset({"cursor"})),
                              posix_home4 / ".local" / "bin", "/bin/bash", ["cursor"])
    cursor_row = next(r for r in rows if r.harness == "cursor")
    assert cursor_row.status == "ok", "plan() must honour a forced selection passed through ctx"

    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
