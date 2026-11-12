"""Build or verify the exact, portable standard adoption projection."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

try:
    from .urp_io import read_file, strict_json_loads
except ImportError:  # pragma: no cover - direct script import
    from urp_io import read_file, strict_json_loads

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "VERSION",
    "policy.json",
    "schemas/package.schema.json",
    "operations/bundle.py",
    "operations/urp_io.py",
    "operations/conformance.py",
    "operations/uri_contract.py",
)


def _write_atomic(target: Path, content: bytes) -> None:
    if target.is_symlink():
        raise ValueError("Refusing to write bundle through symlink")
    fd, tmp_name = tempfile.mkstemp(
        prefix=".bundle-", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    version = read_file(ROOT, "VERSION")[0].decode("utf-8").strip()
    policy = strict_json_loads(read_file(ROOT, "policy.json")[0])
    if not isinstance(policy, dict) or policy.get("version") != version:
        raise ValueError("Policy and release versions differ")
    result = {
        "schema": "wellmanifest.uriprocess/bundle/v1",
        "standard": "wellmanifest/uriprocess",
        "version": version,
        "files": {
            name: hashlib.sha256(read_file(ROOT, name)[0]).hexdigest() for name in FILES
        },
    }
    if args.check:
        observed = strict_json_loads(read_file(ROOT, "bundle.json")[0])
        if observed != result:
            raise ValueError(
                "Standard bundle drift; regenerate within the material change"
            )
    else:
        _write_atomic(
            ROOT / "bundle.json", (json.dumps(result, indent=2) + "\n").encode("utf-8")
        )
    print("Standard bundle: verified" if args.check else "Standard bundle: built")


if __name__ == "__main__":
    main()
