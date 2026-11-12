"""Descriptor-safe regular-file I/O and strict JSON decoding for wellmanifest/uriprocess."""

from __future__ import annotations

import errno
import json
import math
import os
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

MAX_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 4096
SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*$", re.ASCII)
_FORBIDDEN_URI_CHARS = frozenset({"\\", '"', "'", "`", "<", ">", "{", "}", "|"})

_IGNORED_DIRS = {
    ".git",
    "target",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    ".worktrees",
    ".subactor",
    ".governance",
    ".planfile",
    "build",
    "dist",
    ".benchmarks",
    ".cursor",
    ".github",
    ".githooks",
}
_IGNORED_FILES = {".willrust-inventory.cache", "Cargo.lock"}


class ConformanceError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def require(condition: object, code: str) -> None:
    if not condition:
        raise ConformanceError(code)


def has_surrogate(text: str) -> bool:
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)


def is_forbidden_uri_char(ch: str) -> bool:
    code = ord(ch)
    return (
        ch.isspace()
        or code < 32
        or code == 127
        or 0x80 <= code <= 0x9F
        or 0xD800 <= code <= 0xDFFF
        or ch in _FORBIDDEN_URI_CHARS
    )


def validate_uri(uri_str: Any) -> None:
    require(isinstance(uri_str, str) and bool(uri_str.strip()), "URP-IDENTITY-001")
    require(not any(is_forbidden_uri_char(c) for c in uri_str), "URP-IDENTITY-001")
    try:
        value = urlsplit(uri_str)
    except ValueError as exc:
        raise ConformanceError("URP-IDENTITY-001") from exc
    require(
        bool(value.scheme and SCHEME_RE.fullmatch(value.scheme))
        and bool(value.hostname and value.path)
        and "@" not in value.netloc
        and not value.query
        and not value.fragment,
        "URP-IDENTITY-001",
    )
    segments = [seg for seg in value.path.split("/") if seg]
    require(
        bool(segments) and not any(seg in (".", "..") for seg in segments),
        "URP-IDENTITY-001",
    )


def reject_nonfinite_or_surrogates(node: Any) -> None:
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, str):
            require(not has_surrogate(cur), "URP-DATA-001")
        elif isinstance(cur, float):
            require(math.isfinite(cur), "URP-DATA-001")
        elif isinstance(cur, (list, tuple)):
            stack.extend(cur)
        elif isinstance(cur, dict):
            for key, val in cur.items():
                if isinstance(key, str):
                    require(not has_surrogate(key), "URP-DATA-001")
                stack.append(val)


def strict_json_loads(raw: bytes | str) -> Any:
    def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, "URP-DATA-001")
            result[key] = value
        return result

    def _constant(_token: str) -> Any:
        raise ConformanceError("URP-DATA-001")

    def _float(token: str) -> float:
        val = float(token)
        require(math.isfinite(val), "URP-DATA-001")
        return val

    try:
        if isinstance(raw, (bytes, bytearray)):
            require(len(raw) <= MAX_BYTES, "URP-DATA-001")
            text = bytes(raw).decode("utf-8")
        elif isinstance(raw, str):
            require(not has_surrogate(raw), "URP-DATA-001")
            require(len(raw.encode("utf-8")) <= MAX_BYTES, "URP-DATA-001")
            text = raw
        else:
            raise ConformanceError("URP-DATA-001")
        parsed = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=_constant,
            parse_float=_float,
        )
    except ConformanceError:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ConformanceError("URP-DATA-001") from exc
    reject_nonfinite_or_surrogates(parsed)
    return parsed


def relative(value: Any) -> tuple[str, ...]:
    require(
        isinstance(value, str)
        and bool(value)
        and "\\" not in value
        and not any(
            ord(c) < 32
            or ord(c) == 127
            or 0x80 <= ord(c) <= 0x9F
            or 0xD800 <= ord(c) <= 0xDFFF
            for c in value
        ),
        "URP-PATH-001",
    )
    path = PurePosixPath(value)
    parts = value.split("/")
    require(
        not path.is_absolute()
        and path.as_posix() == value
        and not any(part in ("", ".", "..") or part != part.strip() for part in parts),
        "URP-PATH-001",
    )
    return path.parts


def reject_symlink_ancestors(root: str | Path) -> Path:
    raw = str(root)
    require(bool(raw) and "\x00" not in raw, "URP-PATH-001")
    target = Path(raw)
    anchor_base = target if target.is_absolute() else Path(os.getcwd())
    probe = Path(anchor_base.anchor)
    rel_parts = (
        target.parts[1:]
        if target.is_absolute()
        else (*anchor_base.parts[1:], *target.parts)
    )
    for part in rel_parts:
        if part in ("", "."):
            continue
        if part == "..":
            probe = probe.parent
            continue
        probe = probe / part
        try:
            st = os.lstat(probe)
        except OSError as exc:
            raise ConformanceError("URP-PATH-001") from exc
        require(not stat.S_ISLNK(st.st_mode), "URP-PATH-001")
    abs_root = Path(os.path.abspath(raw))
    try:
        root_st = os.lstat(abs_root)
    except OSError as exc:
        raise ConformanceError("URP-PATH-001") from exc
    require(stat.S_ISDIR(root_st.st_mode), "URP-PATH-001")
    return abs_root


def read_file(
    root: str | Path, name: str, *, max_bytes: int = MAX_BYTES
) -> tuple[bytes, int]:
    """Read through directory descriptors; never follow a path component."""
    abs_root = reject_symlink_ancestors(root)
    parts = abs_root.parts
    relative_parts = relative(name)
    dir_flags = (
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    file_flags = (
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    fd: int | None = None
    file_fd: int | None = None
    try:
        fd = os.open(parts[0], dir_flags)
        for part in (*parts[1:], *relative_parts[:-1]):
            next_fd = os.open(part, dir_flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        leaf_lst = os.lstat(relative_parts[-1], dir_fd=fd)
        require(stat.S_ISREG(leaf_lst.st_mode), "URP-PATH-001")
        file_fd = os.open(relative_parts[-1], file_flags, dir_fd=fd)
        observed = os.fstat(file_fd)
        require(
            stat.S_ISREG(observed.st_mode)
            and (leaf_lst.st_dev, leaf_lst.st_ino)
            == (observed.st_dev, observed.st_ino),
            "URP-PATH-001",
        )
        require(observed.st_size <= max_bytes, "URP-DATA-001")
        remaining = max_bytes + 1
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(file_fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        value = b"".join(chunks)
        require(len(value) <= max_bytes, "URP-DATA-001")
        return value, 0o755 if observed.st_mode & stat.S_IXUSR else 0o644
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ConformanceError("URP-PATH-001") from exc
        raise ConformanceError("URP-PATH-001") from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if fd is not None:
            os.close(fd)


def document(root: str | Path, name: str, *, max_bytes: int = MAX_BYTES) -> Any:
    return strict_json_loads(read_file(root, name, max_bytes=max_bytes)[0])


def inventory(root: str | Path, *, max_entries: int = MAX_ENTRIES) -> set[str]:
    abs_root = reject_symlink_ancestors(root)
    files: set[str] = set()
    pending = [abs_root]
    count = 0
    while pending:
        folder = pending.pop()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if (
                        entry.name in _IGNORED_DIRS
                        or entry.name.endswith(".egg-info")
                        or entry.name in _IGNORED_FILES
                    ):
                        continue
                    count += 1
                    require(count <= max_entries, "URP-PATH-001")
                    observed = entry.stat(follow_symlinks=False)
                    require(
                        stat.S_ISREG(observed.st_mode)
                        or stat.S_ISDIR(observed.st_mode),
                        "URP-PATH-001",
                    )
                    path = Path(entry.path)
                    name = path.relative_to(abs_root).as_posix()
                    relative(name)
                    if stat.S_ISDIR(observed.st_mode):
                        pending.append(path)
                    else:
                        files.add(name)
        except OSError as exc:
            raise ConformanceError("URP-PATH-001") from exc
    return files
