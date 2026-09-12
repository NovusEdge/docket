#!/usr/bin/env python3
"""Compatibility launcher for docket's native Go installer.

This file deliberately uses Python 3.8 syntax so an old interpreter can print
the Python 3.10 requirement enforced by the installed docket ledger CLI.
"""
import sys

if sys.version_info < (3, 10):
    sys.stderr.write(
        "docket needs Python 3.10 or later; this interpreter is %d.%d.\n"
        % sys.version_info[:2]
    )
    sys.exit(1)

import hashlib
import os
import platform as platform_module
import re
import shutil
import stat
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPOSITORY = "NovusEdge/docket"


def asset_name(platform, machine):
    systems = {"linux": "linux", "darwin": "darwin", "win32": "windows"}
    machines = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
    system = systems.get(platform.lower())
    architecture = machines.get(machine.lower())
    if not system or not architecture:
        raise RuntimeError("unsupported platform: %s/%s (supported: Linux, macOS, or Windows on amd64 or arm64)" % (platform, machine))
    return "docket-installer-%s-%s%s" % (system, architecture, ".exe" if system == "windows" else "")


def _release_base():
    version = os.environ.get("DOCKET_INSTALLER_VERSION")
    if version:
        if not re.match(r"^[A-Za-z0-9._-]+$", version) or version in (".", ".."):
            raise RuntimeError("DOCKET_INSTALLER_VERSION must be a simple release tag")
        return "https://github.com/%s/releases/download/%s" % (REPOSITORY, version)
    return "https://github.com/%s/releases/latest/download" % REPOSITORY


def _read_url(url):
    try:
        with urllib.request.urlopen(url) as response:
            return response.read()
    except (OSError, urllib.error.URLError) as exc:
        raise RuntimeError(
            "No prebuilt installer is available at %s (%s). The release may "
            "not be published yet; try again later or set "
            "DOCKET_INSTALLER_VERSION to a published tag." % (url, exc)
        )


def _expected_checksum(manifest, name):
    try:
        text = manifest.decode("utf-8")
    except UnicodeDecodeError:
        raise RuntimeError("release SHA256SUMS is not valid UTF-8")
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1].lstrip("*") == name:
            digest = fields[0].lower()
            if len(digest) == 64 and all(c in "0123456789abcdef" for c in digest):
                return digest
            raise RuntimeError("release SHA256SUMS has an invalid digest for %s" % name)
    raise RuntimeError("release SHA256SUMS has no entry for %s" % name)


def _run_downloaded(argv, platform, machine, cwd):
    name = asset_name(platform, machine)
    base = _release_base()
    manifest = _read_url(base + "/SHA256SUMS")
    payload = _read_url(base + "/" + name)
    expected = _expected_checksum(manifest, name)
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise RuntimeError("checksum mismatch for %s; refusing to execute it" % name)
    with tempfile.TemporaryDirectory(prefix="docket-installer-") as directory:
        binary = Path(directory) / name
        binary.write_bytes(payload)
        if platform != "win32":
            binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
        return subprocess.call([str(binary)] + list(argv), cwd=cwd)


def _checkout_for(script):
    installer_dir = script.resolve().parent
    checkout = installer_dir.parent
    if (installer_dir / "go.mod").is_file() and (checkout / "bin" / "docket").is_file():
        return checkout
    return None


def _run_checkout(checkout, argv, cwd):
    go = shutil.which("go")
    if not go:
        raise RuntimeError("Go is required to build the installer from a checkout. Install Go, or run a downloaded install.py outside the checkout to use a release binary.")
    with tempfile.TemporaryDirectory(prefix="docket-installer-build-") as directory:
        suffix = ".exe" if sys.platform == "win32" else ""
        binary = Path(directory) / ("docket-installer" + suffix)
        env = os.environ.copy()
        env["CGO_ENABLED"] = "0"
        subprocess.check_call([go, "build", "-o", str(binary), "."], cwd=str(checkout / "installer"), env=env)
        command = [str(binary), "--checkout", str(checkout.resolve())] + list(argv)
        return subprocess.call(command, cwd=cwd)


def launch(argv, script=None, platform=None, machine=None, cwd=None):
    script = Path(script if script is not None else __file__)
    cwd = cwd if cwd is not None else os.getcwd()
    checkout = _checkout_for(script)
    if checkout is not None:
        return _run_checkout(checkout, argv, cwd)
    platform = platform if platform is not None else sys.platform
    machine = machine if machine is not None else platform_module.machine()
    return _run_downloaded(argv, platform, machine, cwd)


def main():
    try:
        return launch(sys.argv[1:])
    except RuntimeError as exc:
        sys.stderr.write("docket installer: %s\n" % exc)
        return 1
    except subprocess.CalledProcessError as exc:
        sys.stderr.write("docket installer: local Go build failed (exit %d)\n" % exc.returncode)
        return exc.returncode or 1
    except OSError as exc:
        sys.stderr.write("docket installer: %s\n" % exc)
        return 1
    except KeyboardInterrupt:
        sys.stderr.write("docket installer: interrupted\n")
        return 130


if __name__ == "__main__":
    sys.exit(main())
