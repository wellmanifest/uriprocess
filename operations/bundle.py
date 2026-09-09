"""Build or verify the exact, portable standard adoption projection."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("VERSION", "policy.json", "schemas/package.schema.json", "operations/conformance.py")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    version = (ROOT / "VERSION").read_text().strip()
    policy = json.loads((ROOT / "policy.json").read_text())
    if policy["version"] != version:
        raise ValueError("Policy and release versions differ")
    result = {"schema": "wellmanifest.uriprocess/bundle/v1", "standard": "wellmanifest/uriprocess",
              "version": version, "files": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                            for name in FILES}}
    target = ROOT / "bundle.json"
    if args.check:
        if json.loads(target.read_text()) != result:
            raise ValueError("Standard bundle drift; regenerate within the material change")
    else:
        target.write_text(json.dumps(result, indent=2) + "\n")
    print("Standard bundle: verified" if args.check else "Standard bundle: built")


if __name__ == "__main__":
    main()
