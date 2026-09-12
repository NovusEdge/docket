#!/usr/bin/env python3
"""Cross-build docket graph viewer release assets and their checksums."""
import argparse
import hashlib
import os
import subprocess
from pathlib import Path


TARGETS = (
    ("linux", "amd64"),
    ("linux", "arm64"),
    ("darwin", "amd64"),
    ("darwin", "arm64"),
    ("windows", "amd64"),
    ("windows", "arm64"),
)


def build_all(output_dir, version, graph_dir=None):
    graph_dir = Path(graph_dir or Path(__file__).resolve().parent)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for goos, goarch in TARGETS:
        suffix = ".exe" if goos == "windows" else ""
        target = output_dir / ("docket-graph-%s-%s%s" % (goos, goarch, suffix))
        env = os.environ.copy()
        env.update({"CGO_ENABLED": "0", "GOOS": goos, "GOARCH": goarch})
        subprocess.check_call(
            [
                "go",
                "build",
                "-trimpath",
                "-ldflags",
                "-s -w -X main.version=%s" % version,
                "-o",
                str(target),
                ".",
            ],
            cwd=str(graph_dir),
            env=env,
        )
        artifacts.append(target)
    with (output_dir / "GRAPH-SHA256SUMS").open("w", encoding="ascii", newline="\n") as stream:
        for artifact in artifacts:
            stream.write("%s  %s\n" % (hashlib.sha256(artifact.read_bytes()).hexdigest(), artifact.name))
    return artifacts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("dist/graph"))
    parser.add_argument("--version")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    version = args.version or (root / "VERSION").read_text(encoding="utf-8").strip()
    build_all(args.output_dir.resolve(), version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
