# Ticket 003: Harden polyglot snippet escaping, symlink ancestors, float overflow, surrogates, and bundle IO

- **ID**: ticket-003
- **Owner**: agent:antigravity
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Created**: 2026-11-12

## Session authorization

- `SESSION_EXECUTION_AUTHORIZATION`: Autonomous execution, testing, security hardening, and protected Validator publication requested by the repository owner.

## Goal and scope

1. **Eliminate polyglot snippet command/quote injection (`operations/uri_contract.py`)**: Quote `defaults_json` as a POSIX single-quoted literal in `_render_bash` (blocking `$(...)` / `` `...` `` / `}` injection) and escape double-quoted URI literals across Bash, JavaScript, TypeScript (`\u2028`/`\u2029`), and Rust snippet renderers; reject unencoded quotes, backticks, backslashes, C0/DEL/C1 controls, lone surrogates, and empty/`. `/`..` segments in `validate_uri_invocation()` and `validate_uri()`.
2. **Modularize `< 500`-line `urp_io.py`, harden symlink ancestors, float overflow, & UTF-16 surrogates (`operations/urp_io.py`, `operations/conformance.py`, `operations/bundle.py`)**: Extract descriptor-safe `read_file`, lexical `reject_symlink_ancestors` (blocking `sym_dir` and `sym_dir/..` before `os.path.abspath`), `lstat`/`fstat` `(st_dev, st_ino)` checks, and `strict_json_loads` (rejecting duplicate keys, `NaN`/`Infinity`, `1e309` float overflow, and lone UTF-16 surrogates `\ud800`..`\udfff`); cache compiled `Draft202012Validator` instances; and harden `operations/bundle.py` with atomic writes and regenerated `bundle.json`.
3. **Regression suite (`tests/test_hardening.py`)**: Execute generated Bash snippets against adversarial subshell/backtick/quote payloads and verify symlink-ancestor, float-overflow, surrogate, URI dot-segment, bundle, and `< 500`-line invariants.

## Acceptance criteria

- [x] AC-01: `ruff check --no-cache operations/ tests/test_hardening.py`, `python3 -B operations/bundle.py --check`, `python3 -B -m unittest discover -s tests -v`, `./project/governance-check.sh --base origin/main`, and `wellman check` pass with 0 errors and all Python modules stay `< 500` lines.

## Tracking boundary

This directory contains the minimal reviewed intent. Optional participant prose
and raw command logs are not required delivery output.
