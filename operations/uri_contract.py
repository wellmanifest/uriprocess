"""Canonical reference validator and polyglot snippet generator for URP-012."""
from __future__ import annotations

import json
import re
from typing import Any, Callable
from urllib.parse import parse_qsl, urlsplit

from conformance import ConformanceError, require

VERSION = "0.3.0"
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*$")


def _parse_query_params(query: str) -> dict[str, Any]:
    if not query:
        return {}
    result: dict[str, Any] = {}
    for key, val in parse_qsl(query, keep_blank_values=True):
        require(bool(key.strip()), "URP-IDENTITY-001")
        result[key] = val
    return result


def _parse_json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise ConformanceError("URP-DATA-001") from exc
    require(isinstance(parsed, dict), "URP-DATA-001")
    return dict(parsed)


def _normalize_payload(payload: Any, query_defaults: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    if payload is None:
        return "single", [dict(query_defaults)]
    if isinstance(payload, dict):
        return "single", [{**query_defaults, **payload}]
    if isinstance(payload, (list, tuple)):
        require(len(payload) > 0, "URP-DATA-001")
        records: list[dict[str, Any]] = []
        for item in payload:
            require(isinstance(item, dict), "URP-DATA-001")
            records.append({**query_defaults, **item})
        return "jsonl", records
    if isinstance(payload, str):
        lines = [ln.strip() for ln in payload.splitlines() if ln.strip()]
        require(len(lines) > 0, "URP-DATA-001")
        records = [{**query_defaults, **_parse_json_object(ln)} for ln in lines]
        mode = "jsonl" if (len(records) > 1 or "\n" in payload.strip()) else "single"
        return mode, records
    raise ConformanceError("URP-DATA-001")


def validate_uri_invocation(address: str, payload: Any = None) -> dict[str, Any]:
    """Validate `<scheme>://<authority>/<path>[?query]` and parse JSON or JSONL payloads (URP-012)."""
    require(isinstance(address, str) and bool(address.strip()), "URP-IDENTITY-001")
    require(not any(c.isspace() or ord(c) < 32 for c in address), "URP-IDENTITY-001")
    try:
        parts = urlsplit(address)
    except ValueError as exc:
        raise ConformanceError("URP-IDENTITY-001") from exc

    require(
        bool(parts.scheme and _SCHEME_RE.match(parts.scheme))
        and bool(parts.hostname)
        and bool(parts.path and parts.path != "/")
        and parts.username is None
        and parts.password is None
        and not parts.fragment,
        "URP-IDENTITY-001",
    )
    segments = [seg for seg in parts.path.split("/") if seg]
    require(len(segments) >= 1 and not any(seg in (".", "..") for seg in segments), "URP-IDENTITY-001")

    query_params = _parse_query_params(parts.query)
    mode, records = _normalize_payload(payload, query_params)
    canonical_uri = f"{parts.scheme}://{parts.netloc}{parts.path}"

    return {
        "schema": "uriprocess.invocation/v1",
        "valid": True,
        "uri": canonical_uri,
        "raw_uri": address,
        "scheme": parts.scheme,
        "authority": parts.netloc,
        "path": parts.path,
        "query": query_params,
        "mode": mode,
        "args": records[0],
        "records": records,
        "record_count": len(records),
        "is_lifecycle_op": canonical_uri.startswith("proc://system/process/"),
    }


def _render_python(target_uri: str, defaults_json: str) -> str:
    return (
        "from dockuri_uri import uri\n\n"
        f"_DEFAULTS = {defaults_json}\n\n"
        "def invoke(payload=None):\n"
        "    merged = {**_DEFAULTS, **(payload or {})} if isinstance(payload, dict) or payload is None else payload\n"
        f"    return uri({target_uri!r}, merged)\n"
    )


def _render_bash(target_uri: str, defaults_json: str) -> str:
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'PAYLOAD="${{1:-{defaults_json}}}"\n'
        f'uri "{target_uri}" "$PAYLOAD"\n'
    )


def _render_javascript(target_uri: str, defaults_json: str) -> str:
    return (
        'import { uri } from "dockuri-uri";\n\n'
        f"const DEFAULTS = {defaults_json};\n\n"
        "export async function invoke(payload = {}) {\n"
        "  const merged = typeof payload === 'string' ? payload : { ...DEFAULTS, ...payload };\n"
        f'  return await uri("{target_uri}", merged);\n'
        "}\n"
    )


def _render_typescript(target_uri: str, defaults_json: str) -> str:
    return (
        'import { uri } from "dockuri-uri";\n\n'
        f"const DEFAULTS: Record<string, unknown> = {defaults_json};\n\n"
        "export async function invoke(payload: Record<string, unknown> | string = {}): Promise<unknown> {\n"
        "  const merged = typeof payload === 'string' ? payload : { ...DEFAULTS, ...payload };\n"
        f'  return await uri("{target_uri}", merged);\n'
        "}\n"
    )


def _render_rust(target_uri: str, defaults_json: str) -> str:
    escaped_defaults = defaults_json.replace("\\", "\\\\").replace('"', '\\"')
    return (
        "use dockuri_uri::uri;\n"
        "use serde_json::Value;\n\n"
        "pub fn invoke(payload: Option<&str>) -> Result<Value, String> {\n"
        f'    let body = payload.unwrap_or("{escaped_defaults}");\n'
        f'    uri("{target_uri}", body)\n'
        "}\n"
    )


_LANG_RENDERERS: dict[str, Callable[[str, str], str]] = {
    "python": _render_python,
    "py": _render_python,
    "bash": _render_bash,
    "sh": _render_bash,
    "shell": _render_bash,
    "javascript": _render_javascript,
    "js": _render_javascript,
    "mjs": _render_javascript,
    "typescript": _render_typescript,
    "ts": _render_typescript,
    "rust": _render_rust,
    "rs": _render_rust,
}


def render_polyglot_uri_link(
    target_uri: str,
    lang: str = "python",
    defaults: dict[str, Any] | None = None,
) -> str:
    """Generate standardized zero-duplication polyglot wrapper code calling `uri('<target_uri>', payload)`."""
    validated = validate_uri_invocation(target_uri, defaults)
    key = (lang or "").strip().lower()
    renderer = _LANG_RENDERERS.get(key)
    if renderer is None:
        raise ValueError(f"Unsupported polyglot target language: {lang!r}")
    merged_defaults = validated["args"] if defaults is not None or validated["query"] else {}
    defaults_json = json.dumps(merged_defaults, sort_keys=True, separators=(",", ":"))
    return renderer(target_uri, defaults_json)
