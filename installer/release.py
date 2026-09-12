#!/usr/bin/env python3
"""Cross-build and checksum docket installer release artifacts."""
import argparse
import hashlib
import os
import subprocess
from pathlib import Path

TARGETS = (("linux", "amd64"), ("linux", "arm64"), ("darwin", "amd64"), ("darwin", "arm64"), ("windows", "amd64"), ("windows", "arm64"))


def build_all(output_dir, version, installer_dir=None):
    installer_dir = Path(installer_dir or Path(__file__).resolve().parent)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for goos, goarch in TARGETS:
        suffix = ".exe" if goos == "windows" else ""
        target = output_dir / ("docket-installer-%s-%s%s" % (goos, goarch, suffix))
        env = os.environ.copy()
        env.update({"CGO_ENABLED": "0", "GOOS": goos, "GOARCH": goarch})
        subprocess.check_call(["go", "build", "-trimpath", "-ldflags", "-s -w -X main.version=%s" % version, "-o", str(target), "."], cwd=str(installer_dir), env=env)
        artifacts.append(target)
    with (output_dir / "SHA256SUMS").open("w", encoding="ascii", newline="\n") as stream:
        for artifact in artifacts:
            stream.write("%s  %s\n" % (hashlib.sha256(artifact.read_bytes()).hexdigest(), artifact.name))
    return artifacts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("dist/installer"))
    parser.add_argument("--version")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    version = args.version or (root / "VERSION").read_text(encoding="utf-8").strip()
    build_all(args.output_dir.resolve(), version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
