"""Canonical reference validator and polyglot snippet generator for URP-012."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qsl, urlsplit

try:
    from .urp_io import (
        SCHEME_RE as _SCHEME_RE,
    )
    from .urp_io import (
        ConformanceError,
        has_surrogate,
        is_forbidden_uri_char,
        reject_nonfinite_or_surrogates,
        require,
        strict_json_loads,
    )
except ImportError:  # pragma: no cover - direct operations sys.path import
    from urp_io import (
        SCHEME_RE as _SCHEME_RE,
    )
    from urp_io import (
        ConformanceError,
        has_surrogate,
        is_forbidden_uri_char,
        reject_nonfinite_or_surrogates,
        require,
        strict_json_loads,
    )

VERSION = "0.3.0"


def _is_forbidden_uri_char(ch: str) -> bool:
    return is_forbidden_uri_char(ch)


def _parse_query_params(query: str) -> dict[str, Any]:
    if not query:
        return {}
    result: dict[str, Any] = {}
    for key, val in parse_qsl(query, keep_blank_values=True):
        require(
            bool(key.strip()) and not has_surrogate(key) and not has_surrogate(val),
            "URP-IDENTITY-001",
        )
        result[key] = val
    return result


def _parse_json_object(raw: str) -> dict[str, Any]:
    parsed = strict_json_loads(raw)
    require(isinstance(parsed, dict), "URP-DATA-001")
    return dict(parsed)


def _normalize_payload(
    payload: Any, query_defaults: dict[str, Any]
) -> tuple[str, list[dict[str, Any]]]:
    if payload is None:
        return "single", [dict(query_defaults)]
    if isinstance(payload, dict):
        reject_nonfinite_or_surrogates(payload)
        return "single", [{**query_defaults, **payload}]
    if isinstance(payload, (list, tuple)):
        require(len(payload) > 0, "URP-DATA-001")
        reject_nonfinite_or_surrogates(payload)
        records: list[dict[str, Any]] = []
        for item in payload:
            require(isinstance(item, dict), "URP-DATA-001")
            records.append({**query_defaults, **item})
        return "jsonl", records
    if isinstance(payload, str):
        require(not has_surrogate(payload), "URP-DATA-001")
        lines = [ln.strip() for ln in payload.splitlines() if ln.strip()]
        require(len(lines) > 0, "URP-DATA-001")
        records = [{**query_defaults, **_parse_json_object(ln)} for ln in lines]
        mode = "jsonl" if (len(records) > 1 or "\n" in payload.strip()) else "single"
        return mode, records
    raise ConformanceError("URP-DATA-001")


def validate_uri_invocation(address: str, payload: Any = None) -> dict[str, Any]:
    """Validate `<scheme>://<authority>/<path>[?query]` and parse JSON or JSONL payloads (URP-012)."""
    require(isinstance(address, str) and bool(address.strip()), "URP-IDENTITY-001")
    require(not any(_is_forbidden_uri_char(c) for c in address), "URP-IDENTITY-001")
    try:
        parts = urlsplit(address)
    except ValueError as exc:
        raise ConformanceError("URP-IDENTITY-001") from exc

    require(
        bool(parts.scheme and _SCHEME_RE.fullmatch(parts.scheme))
        and bool(parts.hostname)
        and bool(parts.path and parts.path != "/")
        and "@" not in parts.netloc
        and not parts.fragment,
        "URP-IDENTITY-001",
    )
    raw_segments = parts.path.split("/")[1:]
    require(
        bool(raw_segments) and not any(seg in ("", ".", "..") for seg in raw_segments),
        "URP-IDENTITY-001",
    )

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


def _escape_js_json(raw_json: str) -> str:
    return raw_json.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _escape_bash_double_quoted(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
    )


def _escape_rust_str(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _render_python(target_uri: str, defaults_json: str) -> str:
    defaults_obj = json.loads(defaults_json)
    return (
        "from dockuri_uri import uri\n\n"
        f"_DEFAULTS = {defaults_obj!r}\n\n"
        "def invoke(payload=None):\n"
        "    merged = {**_DEFAULTS, **(payload or {})} if isinstance(payload, dict) or payload is None else payload\n"
        f"    return uri({target_uri!r}, merged)\n"
    )


def _render_bash(target_uri: str, defaults_json: str) -> str:
    single_quoted_defaults = "'" + defaults_json.replace("'", "'\"'\"'") + "'"
    escaped_uri = _escape_bash_double_quoted(target_uri)
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'if [ "$#" -gt 0 ]; then PAYLOAD="$1"; else PAYLOAD={single_quoted_defaults}; fi\n'
        f'uri "{escaped_uri}" "$PAYLOAD"\n'
    )


def _render_javascript(target_uri: str, defaults_json: str) -> str:
    uri_literal = _escape_js_json(json.dumps(target_uri))
    safe_defaults = _escape_js_json(defaults_json)
    return (
        'import { uri } from "dockuri-uri";\n\n'
        f"const DEFAULTS = {safe_defaults};\n\n"
        "export async function invoke(payload = {}) {\n"
        "  const merged = typeof payload === 'string' ? payload : { ...DEFAULTS, ...payload };\n"
        f"  return await uri({uri_literal}, merged);\n"
        "}\n"
    )


def _render_typescript(target_uri: str, defaults_json: str) -> str:
    uri_literal = _escape_js_json(json.dumps(target_uri))
    safe_defaults = _escape_js_json(defaults_json)
    return (
        'import { uri } from "dockuri-uri";\n\n'
        f"const DEFAULTS: Record<string, unknown> = {safe_defaults};\n\n"
        "export async function invoke(payload: Record<string, unknown> | string = {}): Promise<unknown> {\n"
        "  const merged = typeof payload === 'string' ? payload : { ...DEFAULTS, ...payload };\n"
        f"  return await uri({uri_literal}, merged);\n"
        "}\n"
    )


def _render_rust(target_uri: str, defaults_json: str) -> str:
    escaped_defaults = _escape_rust_str(defaults_json)
    escaped_uri = _escape_rust_str(target_uri)
    return (
        "use dockuri_uri::uri;\n"
        "use serde_json::Value;\n\n"
        "pub fn invoke(payload: Option<&str>) -> Result<Value, String> {\n"
        f'    let body = payload.unwrap_or("{escaped_defaults}");\n'
        f'    uri("{escaped_uri}", body)\n'
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
    merged_defaults = (
        validated["args"] if defaults is not None or validated["query"] else {}
    )
    defaults_json = json.dumps(
        merged_defaults, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return renderer(target_uri, defaults_json)
