"""Read-only package conformance, without upstream or execution authority."""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import re
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

try:
    from . import urp_io as _urp_io
except ImportError:  # pragma: no cover - direct operations sys.path import
    import urp_io as _urp_io

ConformanceError = _urp_io.ConformanceError
reject_nonfinite_or_surrogates = _urp_io.reject_nonfinite_or_surrogates
reject_symlink_ancestors = _urp_io.reject_symlink_ancestors
relative = _urp_io.relative
require = _urp_io.require
strict_json_loads = _urp_io.strict_json_loads
validate_uri = _urp_io.validate_uri

STANDARD_ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.3.0"
MAX_BYTES = _urp_io.MAX_BYTES
MAX_ENTRIES = _urp_io.MAX_ENTRIES

_URI_CALL_RE = re.compile(
    r"""(?:(?<![a-zA-Z0-9_])uri\s*\(\s*['"]([^'"]+)['"]|^\s*(?:wellman\s+)?uri\s+['"]?([a-z][a-z0-9+.-]*://[^\s'"]+)['"]?)"""
)
_SCAN_EXTS = {".py", ".sh", ".mjs", ".js", ".ts", ".rs", ".policy", ".curi"}
_PROCESS_REGISTRY: dict[str, Any] = {}


def read_file(root: str | Path, name: str) -> tuple[bytes, int]:
    return _urp_io.read_file(root, name, max_bytes=MAX_BYTES)


def document(root: str | Path, name: str) -> Any:
    return _urp_io.document(root, name, max_bytes=MAX_BYTES)


def inventory(root: str | Path) -> set[str]:
    return _urp_io.inventory(root, max_entries=MAX_ENTRIES)


@functools.lru_cache(maxsize=1)
def _standard_policy_and_schema() -> tuple[dict[str, Any], dict[str, Any]]:
    policy = document(STANDARD_ROOT, "policy.json")
    schema = document(STANDARD_ROOT, "schemas/package.schema.json")
    return policy, schema


@functools.lru_cache(maxsize=16)
def _compiled_schema_validator(definition: str) -> Draft202012Validator:
    _, schema = _standard_policy_and_schema()
    return Draft202012Validator(
        {"$defs": schema["$defs"], "$ref": "#/$defs/" + definition}
    )


def validate_schema(schema: dict[str, Any], definition: str, value: Any) -> None:
    _, std_schema = _standard_policy_and_schema()
    if schema is std_schema:
        validator = _compiled_schema_validator(definition)
    else:
        validator = Draft202012Validator(
            {"$defs": schema["$defs"], "$ref": "#/$defs/" + definition}
        )
    require(next(validator.iter_errors(value), None) is None, "URP-SCHEMA-001")


def _validate_poa_node(
    root: Path, manifest: dict[str, Any], copied: set[str]
) -> list[str]:
    require(
        manifest["contract"] in copied and manifest["entry"] in copied,
        "URP-INTEGRITY-001",
    )
    require(
        any(
            name.startswith("tests/") and name.endswith(".test.mjs") for name in copied
        ),
        "URP-TESTS-001",
    )
    contract = document(root, manifest["contract"])
    require(
        isinstance(contract, dict)
        and contract.get("schema") == "poa.process/v1"
        and contract.get("process_ref") == manifest["process_ref"],
        "URP-IDENTITY-001",
    )
    distribution = document(root, "package.json")
    require(
        isinstance(distribution, dict)
        and distribution.get("type") == "module"
        and distribution.get("exports")
        in ("./" + manifest["entry"], {".": "./" + manifest["entry"]}),
        "URP-IDENTITY-001",
    )
    docker_lines = read_file(root, "Dockerfile")[0].splitlines()
    require(
        docker_lines and docker_lines[0] == ("FROM " + manifest["base_image"]).encode(),
        "URP-IDENTITY-001",
    )
    require(read_file(root, "bin.mjs")[1] == 0o755, "URP-INTEGRITY-001")
    return [manifest["process_ref"]]


def _validate_python_native(
    root: Path, manifest: dict[str, Any], copied: set[str]
) -> list[str]:
    require(
        manifest["native_manifest"] in copied and "pyproject.toml" in copied,
        "URP-INTEGRITY-001",
    )
    require(
        any(name.startswith("tests/test_") and name.endswith(".py") for name in copied),
        "URP-TESTS-001",
    )
    native = document(root, manifest["native_manifest"])
    try:
        project = tomllib.loads(read_file(root, "pyproject.toml")[0].decode())[
            "project"
        ]
        require(
            isinstance(native, dict)
            and native.get("routes") == manifest["public_uris"]
            and project["name"] == manifest["native_distribution"]
            and project["version"] == manifest["native_version"]
            and project["entry-points"]["urirun.bindings"] == manifest["entry_points"]
            and project.get("dependencies", []) == manifest["dependencies"],
            "URP-IDENTITY-001",
        )
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ConformanceError("URP-IDENTITY-001") from exc
    return manifest["public_uris"]


def _validate_rust_uri(
    root: Path, manifest: dict[str, Any], copied: set[str]
) -> list[str]:
    require(
        manifest["cargo_manifest"] in copied and "src/lib.rs" in copied,
        "URP-INTEGRITY-001",
    )
    require(
        any(
            name.startswith("tests/") and name.endswith((".rs", ".py"))
            for name in copied
        ),
        "URP-TESTS-001",
    )
    try:
        cargo = tomllib.loads(read_file(root, manifest["cargo_manifest"])[0].decode())
        package = cargo["package"]
        require(
            package["name"] == manifest["crate_name"]
            and package["version"] == manifest["crate_version"],
            "URP-IDENTITY-001",
        )
        if "cdylib-c-abi" in manifest["transports"]:
            crate_types = cargo.get("lib", {}).get("crate-type", [])
            require("cdylib" in crate_types, "URP-IDENTITY-001")
        lib_bytes = read_file(root, "src/lib.rs")[0]
        require(manifest["ffi_symbol"].encode() in lib_bytes, "URP-IDENTITY-001")
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ConformanceError("URP-IDENTITY-001") from exc
    return manifest["public_uris"]


_PROFILE_VALIDATORS = {
    "poa-node-v1": _validate_poa_node,
    "python-native-v1": _validate_python_native,
    "rust-uri-v1": _validate_rust_uri,
}


def check_package(root: str | Path) -> dict[str, Any]:
    abs_root = reject_symlink_ancestors(root)
    policy, schema = _standard_policy_and_schema()
    manifest = document(abs_root, "uriprocess.json")
    require(isinstance(manifest, dict), "URP-SCHEMA-001")
    profiles = [
        name
        for name, profile in policy["profiles"].items()
        if profile["manifest_schema"] == manifest.get("schema")
    ]
    require(len(profiles) == 1, "URP-SCHEMA-001")
    profile = profiles[0]
    validate_schema(schema, profile, manifest)
    provenance = document(abs_root, manifest["source"])
    validate_schema(schema, "provenance", provenance)
    validate_uri(provenance["repository"])
    copied: set[str] = set()
    source_paths: set[str] = set()
    for record in provenance["files"]:
        relative(record["source"])
        relative(record["destination"])
        require(
            record["source"] not in source_paths
            and record["destination"] not in copied,
            "URP-INTEGRITY-001",
        )
        source_paths.add(record["source"])
        copied.add(record["destination"])
        data, mode = read_file(abs_root, record["destination"])
        require(
            hashlib.sha256(data).hexdigest() == record["sha256"], "URP-INTEGRITY-001"
        )
        require(profile == "poa-node-v1" or "mode" in record, "URP-SCHEMA-001")
        require(mode == record.get("mode", 0o644), "URP-INTEGRITY-001")
    generated = set(policy["profiles"][profile]["generated_files"])
    require(not generated.intersection(copied), "URP-INTEGRITY-001")
    actual_files = inventory(abs_root)
    require(actual_files == copied | generated, "URP-INTEGRITY-001")

    validator_fn = _PROFILE_VALIDATORS.get(profile)
    require(validator_fn is not None, "URP-SCHEMA-001")
    uris = validator_fn(abs_root, manifest, copied)
    for uri_item in uris:
        validate_uri(uri_item)
    return {
        "schema": "wellmanifest.uriprocess/conformance/v1",
        "status": "passed",
        "standard": policy["standard"],
        "version": policy["version"],
        "profile": profile,
        "public_uris": uris,
        "files_checked": len(actual_files),
        "source_revision": provenance["revision"],
        "upstream_git_verified": False,
        "behavior_verified": False,
        "guard_authenticated": False,
        "execution_authority": False,
        "publication_authority": False,
        "production_verified": False,
    }


def register_uri_process(address: str, handler: Any) -> None:
    validate_uri(address)
    _PROCESS_REGISTRY[address] = handler


def validate_invocation(envelope: dict[str, Any]) -> dict[str, Any]:
    _, schema = _standard_policy_and_schema()
    validate_schema(schema, "invocation", envelope)
    validate_uri(envelope["uri"])
    return envelope


def validate_invocation_result(result: dict[str, Any]) -> dict[str, Any]:
    _, schema = _standard_policy_and_schema()
    validate_schema(schema, "invocation-result", result)
    validate_uri(result["uri"])
    return result


def _builtin_check_package(args: dict[str, Any]) -> dict[str, Any]:
    pkg = args.get("package", ".")
    return check_package(Path(pkg))


def _builtin_scan_links(args: dict[str, Any]) -> dict[str, Any]:
    root = args.get("root", ".")
    return scan_uri_links(Path(root))


def _ensure_builtins() -> None:
    if not _PROCESS_REGISTRY:
        _PROCESS_REGISTRY["proc://uriprocess/conformance/check"] = (
            _builtin_check_package
        )
        _PROCESS_REGISTRY["proc://uriprocess/invocation/scan"] = _builtin_scan_links


def _extract_envelope_item(
    parsed: dict[str, Any], default_address: str, default_id: str
) -> dict[str, Any]:
    reject_nonfinite_or_surrogates(parsed)
    target_uri = str(parsed.get("uri") or default_address or "")
    require(bool(target_uri), "URP-IDENTITY-001")
    validate_uri(target_uri)
    req_id = str(parsed.get("id") or default_id)
    if "uri" in parsed and isinstance(parsed.get("args"), dict):
        args = parsed["args"]
    elif "uri" in parsed:
        args = {k: v for k, v in parsed.items() if k not in ("schema", "id", "uri")}
    else:
        args = dict(parsed)
    return {
        "schema": "uriprocess.invocation/v1",
        "id": req_id,
        "uri": target_uri,
        "args": args,
    }


def uri(
    address: str = "", payload: Any = None, *, stream: bool = False
) -> dict[str, Any] | list[dict[str, Any]]:
    """Universal URI process invocation function (URP-012) with JSONL envelope normalization."""
    _ensure_builtins()
    items: list[dict[str, Any]] = []
    if payload is None:
        require(bool(address), "URP-IDENTITY-001")
        validate_uri(address)
        items.append(
            {
                "schema": "uriprocess.invocation/v1",
                "id": "r1",
                "uri": address,
                "args": {},
            }
        )
    elif isinstance(payload, dict):
        items.append(_extract_envelope_item(payload, address, "r1"))
    elif isinstance(payload, str):
        lines = [ln.strip() for ln in payload.splitlines() if ln.strip()]
        require(bool(lines), "URP-DATA-001")
        for idx, line in enumerate(lines):
            parsed = strict_json_loads(line)
            require(isinstance(parsed, dict), "URP-DATA-001")
            items.append(_extract_envelope_item(parsed, address, f"r{idx + 1}"))
    else:
        raise ConformanceError("URP-DATA-001")

    results: list[dict[str, Any]] = []
    for req in items:
        validate_invocation(req)
        target_uri = req["uri"]
        require(target_uri in _PROCESS_REGISTRY, "URP-IDENTITY-001")
        raw_out = _PROCESS_REGISTRY[target_uri](req["args"])
        reject_nonfinite_or_surrogates(raw_out)
        req_canonical = json.dumps(
            {"id": req["id"], "uri": target_uri, "args": req["args"]},
            sort_keys=True,
            allow_nan=False,
        )
        req_sha = hashlib.sha256(req_canonical.encode("utf-8")).hexdigest()
        res_canonical = json.dumps(
            raw_out, sort_keys=True, default=str, allow_nan=False
        )
        res_sha = hashlib.sha256(f"{req_sha}:{res_canonical}".encode()).hexdigest()
        env = {
            "schema": "uriprocess.invocation-result/v1",
            "id": req["id"],
            "uri": target_uri,
            "ok": True,
            "tier": "floor",
            "provider": "in_process_registry",
            "result": raw_out,
            "receipt": {
                "request_sha256": req_sha,
                "sha256": res_sha,
            },
        }
        validate_invocation_result(env)
        results.append(env)

    is_multi = (
        stream
        or len(results) > 1
        or (isinstance(payload, str) and "\n" in payload.strip())
    )
    return results if is_multi else results[0]


def scan_uri_links(root: str | Path) -> dict[str, Any]:
    """Scan polyglot scripts for `uri('<full-uri>', ...)` and `uri <full-uri> '<jsonl>'` links (URP-012)."""
    abs_root = reject_symlink_ancestors(root)
    files = inventory(abs_root)
    valid_links: list[dict[str, Any]] = []
    invalid_links: list[dict[str, Any]] = []
    for rel in sorted(files):
        ext = PurePosixPath(rel).suffix
        if ext not in _SCAN_EXTS:
            continue
        raw_bytes, _ = read_file(abs_root, rel)
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith(("#", "//")):
                continue
            for match in _URI_CALL_RE.finditer(line):
                candidate = (match.group(1) or match.group(2) or "").strip()
                if not candidate:
                    continue
                try:
                    validate_uri(candidate)
                    require(urlsplit(candidate).path != "/", "URP-IDENTITY-001")
                    valid_links.append({"path": rel, "line": line_no, "uri": candidate})
                except ConformanceError as exc:
                    invalid_links.append(
                        {
                            "path": rel,
                            "line": line_no,
                            "uri": candidate,
                            "code": exc.code,
                        }
                    )
    require(not invalid_links, "URP-IDENTITY-001")
    return {
        "schema": "wellmanifest.uriprocess/link-scan/v1",
        "status": "passed",
        "valid_link_count": len(valid_links),
        "valid_links": valid_links,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--check-links", type=Path)
    parser.add_argument("--invoke", type=str)
    parser.add_argument("--payload", type=str, default=None)
    args = parser.parse_args(argv)
    try:
        if args.invoke:
            result: Any = uri(args.invoke, args.payload)
        elif args.check_links:
            result = scan_uri_links(args.check_links)
        elif args.package:
            result = check_package(args.package)
        else:
            raise ConformanceError("URP-DATA-001")
    except ConformanceError as exc:
        print(
            json.dumps(
                {"status": "invalid", "code": exc.code, "execution_authority": False}
            )
        )
        return 2
    print(json.dumps(result, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
