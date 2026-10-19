"""Read-only package conformance, without upstream or execution authority."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tomllib
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

STANDARD_ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 4096


class ConformanceError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(condition, code):
    if not condition:
        raise ConformanceError(code)


def relative(value):
    require(isinstance(value, str) and value and "\\" not in value
            and not any(ord(c) < 32 for c in value), "URP-PATH-001")
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.as_posix() == value
            and not any(part in (".", "..") for part in value.split("/")), "URP-PATH-001")
    return path.parts


def read_file(root, name):
    """Read through directory descriptors; never follow a path component."""
    parts = Path(os.path.abspath(root)).parts
    relative_parts = relative(name)
    fd = file_fd = None
    try:
        fd = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for part in (*parts[1:], *relative_parts[:-1]):
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        file_fd = os.open(relative_parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        observed = os.fstat(file_fd)
        require(stat.S_ISREG(observed.st_mode), "URP-PATH-001")
        require(observed.st_size <= MAX_BYTES, "URP-DATA-001")
        remaining, chunks = MAX_BYTES + 1, []
        while remaining:
            chunk = os.read(file_fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        value = b"".join(chunks)
        require(len(value) <= MAX_BYTES, "URP-DATA-001")
        return value, 0o755 if observed.st_mode & stat.S_IXUSR else 0o644
    except OSError as exc:
        raise ConformanceError("URP-PATH-001") from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if fd is not None:
            os.close(fd)


def document(root, name):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "URP-DATA-001")
            result[key] = value
        return result

    def constant(_):
        raise ConformanceError("URP-DATA-001")

    try:
        return json.loads(read_file(root, name)[0], object_pairs_hook=pairs, parse_constant=constant)
    except ConformanceError:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ConformanceError("URP-DATA-001") from exc


_IGNORED_DIRS = {
    ".git", "target", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", ".worktrees", ".subactor", ".governance", ".planfile",
    "build", "dist", ".benchmarks", ".cursor", ".github", ".githooks",
}
_IGNORED_FILES = {".willrust-inventory.cache", "Cargo.lock"}


def inventory(root):
    files, pending, count = set(), [Path(root)], 0
    while pending:
        folder = pending.pop()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if entry.name in _IGNORED_DIRS or entry.name.endswith(".egg-info") or entry.name in _IGNORED_FILES:
                        continue
                    count += 1
                    require(count <= MAX_ENTRIES, "URP-PATH-001")
                    observed = entry.stat(follow_symlinks=False)
                    require(stat.S_ISREG(observed.st_mode) or stat.S_ISDIR(observed.st_mode), "URP-PATH-001")
                    path = Path(entry.path)
                    name = path.relative_to(root).as_posix()
                    relative(name)
                    if stat.S_ISDIR(observed.st_mode):
                        pending.append(path)
                    else:
                        files.add(name)
        except OSError as exc:
            raise ConformanceError("URP-PATH-001") from exc
    return files


def validate_uri(uri):
    try:
        value = urlsplit(uri)
        require(bool(value.scheme and value.hostname and value.path)
                and value.username is None and value.password is None
                and not value.query and not value.fragment, "URP-IDENTITY-001")
    except ValueError as exc:
        raise ConformanceError("URP-IDENTITY-001") from exc


def validate_schema(schema, definition, value):
    validator = Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/" + definition})
    require(next(validator.iter_errors(value), None) is None, "URP-SCHEMA-001")


def _validate_poa_node(root, manifest, copied):
    require(manifest["contract"] in copied and manifest["entry"] in copied, "URP-INTEGRITY-001")
    require(any(name.startswith("tests/") and name.endswith(".test.mjs") for name in copied), "URP-TESTS-001")
    contract = document(root, manifest["contract"])
    require(isinstance(contract, dict) and contract.get("schema") == "poa.process/v1"
            and contract.get("process_ref") == manifest["process_ref"], "URP-IDENTITY-001")
    distribution = document(root, "package.json")
    require(isinstance(distribution, dict) and distribution.get("type") == "module"
            and distribution.get("exports") in ("./" + manifest["entry"],
                                                  {".": "./" + manifest["entry"]}), "URP-IDENTITY-001")
    docker_lines = read_file(root, "Dockerfile")[0].splitlines()
    require(docker_lines and docker_lines[0] == ("FROM " + manifest["base_image"]).encode(), "URP-IDENTITY-001")
    require(read_file(root, "bin.mjs")[1] == 0o755, "URP-INTEGRITY-001")
    return [manifest["process_ref"]]


def _validate_python_native(root, manifest, copied):
    require(manifest["native_manifest"] in copied and "pyproject.toml" in copied, "URP-INTEGRITY-001")
    require(any(name.startswith("tests/test_") and name.endswith(".py") for name in copied), "URP-TESTS-001")
    native = document(root, manifest["native_manifest"])
    try:
        project = tomllib.loads(read_file(root, "pyproject.toml")[0].decode())["project"]
        require(isinstance(native, dict) and native.get("routes") == manifest["public_uris"]
                and project["name"] == manifest["native_distribution"]
                and project["version"] == manifest["native_version"]
                and project["entry-points"]["urirun.bindings"] == manifest["entry_points"]
                and project.get("dependencies", []) == manifest["dependencies"], "URP-IDENTITY-001")
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ConformanceError("URP-IDENTITY-001") from exc
    return manifest["public_uris"]


def _validate_rust_uri(root, manifest, copied):
    require(manifest["cargo_manifest"] in copied and "src/lib.rs" in copied, "URP-INTEGRITY-001")
    require(any((name.startswith("tests/") and (name.endswith(".rs") or name.endswith(".py"))) for name in copied), "URP-TESTS-001")
    try:
        cargo = tomllib.loads(read_file(root, manifest["cargo_manifest"])[0].decode())
        package = cargo["package"]
        require(package["name"] == manifest["crate_name"]
                and package["version"] == manifest["crate_version"], "URP-IDENTITY-001")
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


def check_package(root):
    root = Path(os.path.abspath(root))
    policy = document(STANDARD_ROOT, "policy.json")
    schema = document(STANDARD_ROOT, "schemas/package.schema.json")
    manifest = document(root, "uriprocess.json")
    require(isinstance(manifest, dict), "URP-SCHEMA-001")
    profiles = [name for name, profile in policy["profiles"].items()
                if profile["manifest_schema"] == manifest.get("schema")]
    require(len(profiles) == 1, "URP-SCHEMA-001")
    profile = profiles[0]
    validate_schema(schema, profile, manifest)
    provenance = document(root, manifest["source"])
    validate_schema(schema, "provenance", provenance)
    validate_uri(provenance["repository"])
    copied, source_paths = set(), set()
    for record in provenance["files"]:
        relative(record["source"])
        relative(record["destination"])
        require(record["source"] not in source_paths and record["destination"] not in copied, "URP-INTEGRITY-001")
        source_paths.add(record["source"])
        copied.add(record["destination"])
        data, mode = read_file(root, record["destination"])
        require(hashlib.sha256(data).hexdigest() == record["sha256"], "URP-INTEGRITY-001")
        require(profile == "poa-node-v1" or "mode" in record, "URP-SCHEMA-001")
        require(mode == record.get("mode", 0o644), "URP-INTEGRITY-001")
    generated = set(policy["profiles"][profile]["generated_files"])
    require(not generated.intersection(copied), "URP-INTEGRITY-001")
    actual_files = inventory(root)
    require(actual_files == copied | generated, "URP-INTEGRITY-001")

    validator_fn = _PROFILE_VALIDATORS.get(profile)
    require(validator_fn is not None, "URP-SCHEMA-001")
    uris = validator_fn(root, manifest, copied)
    for uri in uris:
        validate_uri(uri)
    return {"schema": "wellmanifest.uriprocess/conformance/v1", "status": "passed",
            "standard": policy["standard"], "version": policy["version"], "profile": profile,
            "public_uris": uris, "files_checked": len(actual_files), "source_revision": provenance["revision"],
            "upstream_git_verified": False, "behavior_verified": False, "guard_authenticated": False,
            "execution_authority": False, "publication_authority": False, "production_verified": False}


import re
import sys

_URI_CALL_RE = re.compile(
    r"""(?:(?<![a-zA-Z0-9_])uri\s*\(\s*['"]([^'"]+)['"]|^\s*(?:wellman\s+)?uri\s+['"]?([a-z][a-z0-9+.-]*://[^\s'"]+)['"]?)"""
)
_SCAN_EXTS = {".py", ".sh", ".mjs", ".js", ".ts", ".rs", ".policy", ".curi"}
_PROCESS_REGISTRY = {}


def register_uri_process(address, handler):
    validate_uri(address)
    _PROCESS_REGISTRY[address] = handler


def validate_invocation(envelope):
    schema = document(STANDARD_ROOT, "schemas/package.schema.json")
    validate_schema(schema, "invocation", envelope)
    validate_uri(envelope["uri"])
    return envelope


def validate_invocation_result(result):
    schema = document(STANDARD_ROOT, "schemas/package.schema.json")
    validate_schema(schema, "invocation-result", result)
    validate_uri(result["uri"])
    return result


def _builtin_check_package(args):
    pkg = args.get("package", ".")
    return check_package(Path(pkg))


def _builtin_scan_links(args):
    root = args.get("root", ".")
    return scan_uri_links(Path(root))


def _ensure_builtins():
    if not _PROCESS_REGISTRY:
        _PROCESS_REGISTRY["proc://uriprocess/conformance/check"] = _builtin_check_package
        _PROCESS_REGISTRY["proc://uriprocess/invocation/scan"] = _builtin_scan_links


def uri(address="", payload=None, *, stream=False):
    """Universal URI process invocation function (URP-012) with JSONL envelope normalization."""
    _ensure_builtins()
    items = []
    if payload is None:
        require(bool(address), "URP-IDENTITY-001")
        validate_uri(address)
        items.append({"schema": "uriprocess.invocation/v1", "id": "r1", "uri": address, "args": {}})
    elif isinstance(payload, dict):
        target_uri = str(payload.get("uri") or address or "")
        require(bool(target_uri), "URP-IDENTITY-001")
        validate_uri(target_uri)
        req_id = str(payload.get("id") or "r1")
        args = payload["args"] if ("uri" in payload and isinstance(payload.get("args"), dict)) else (
            {k: v for k, v in payload.items() if k not in ("schema", "id", "uri")} if "uri" in payload else dict(payload)
        )
        items.append({"schema": "uriprocess.invocation/v1", "id": req_id, "uri": target_uri, "args": args})
    elif isinstance(payload, str):
        lines = [ln.strip() for ln in payload.splitlines() if ln.strip()]
        require(bool(lines), "URP-DATA-001")
        for idx, line in enumerate(lines):
            try:
                parsed = json.loads(line)
            except ValueError as exc:
                raise ConformanceError("URP-DATA-001") from exc
            require(isinstance(parsed, dict), "URP-DATA-001")
            target_uri = str(parsed.get("uri") or address or "")
            require(bool(target_uri), "URP-IDENTITY-001")
            validate_uri(target_uri)
            req_id = str(parsed.get("id") or f"r{idx + 1}")
            args = parsed["args"] if ("uri" in parsed and isinstance(parsed.get("args"), dict)) else (
                {k: v for k, v in parsed.items() if k not in ("schema", "id", "uri")} if "uri" in parsed else dict(parsed)
            )
            items.append({"schema": "uriprocess.invocation/v1", "id": req_id, "uri": target_uri, "args": args})
    else:
        raise ConformanceError("URP-DATA-001")

    results = []
    for req in items:
        validate_invocation(req)
        target_uri = req["uri"]
        require(target_uri in _PROCESS_REGISTRY, "URP-IDENTITY-001")
        raw_out = _PROCESS_REGISTRY[target_uri](req["args"])
        req_canonical = json.dumps({"id": req["id"], "uri": target_uri, "args": req["args"]}, sort_keys=True)
        req_sha = hashlib.sha256(req_canonical.encode("utf-8")).hexdigest()
        res_canonical = json.dumps(raw_out, sort_keys=True, default=str)
        res_sha = hashlib.sha256(f"{req_sha}:{res_canonical}".encode("utf-8")).hexdigest()
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

    is_multi = stream or len(results) > 1 or (isinstance(payload, str) and "\n" in payload.strip())
    return results if is_multi else results[0]


def scan_uri_links(root):
    """Scan polyglot scripts for `uri('<full-uri>', ...)` and `uri <full-uri> '<jsonl>'` links (URP-012)."""
    root = Path(os.path.abspath(root))
    files = inventory(root)
    valid_links, invalid_links = [], []
    for rel in sorted(files):
        ext = PurePosixPath(rel).suffix
        if ext not in _SCAN_EXTS:
            continue
        raw_bytes, _ = read_file(root, rel)
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
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
                    invalid_links.append({"path": rel, "line": line_no, "uri": candidate, "code": exc.code})
    require(not invalid_links, "URP-IDENTITY-001")
    return {
        "schema": "wellmanifest.uriprocess/link-scan/v1",
        "status": "passed",
        "valid_link_count": len(valid_links),
        "valid_links": valid_links,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--check-links", type=Path)
    parser.add_argument("--invoke", type=str)
    parser.add_argument("--payload", type=str, default=None)
    args = parser.parse_args(argv)
    try:
        if args.invoke:
            result = uri(args.invoke, args.payload)
        elif args.check_links:
            result = scan_uri_links(args.check_links)
        elif args.package:
            result = check_package(args.package)
        else:
            raise ConformanceError("URP-DATA-001")
    except ConformanceError as exc:
        print(json.dumps({"status": "invalid", "code": exc.code, "execution_authority": False}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

