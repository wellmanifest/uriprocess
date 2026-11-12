"""Security and conformance regression tests for wellmanifest/uriprocess (ticket-003)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "operations") not in sys.path:
    sys.path.insert(0, str(ROOT / "operations"))

from conformance import (
    ConformanceError,
    check_package,
    document,
    register_uri_process,
    uri,
    validate_uri,
)
from uri_contract import render_polyglot_uri_link, validate_uri_invocation


class HardeningTests(unittest.TestCase):
    def test_polyglot_bash_js_ts_rust_snippets_prevent_command_and_quote_injection(
        self,
    ) -> None:
        target = "proc://system/process/manage/v1"
        adversarial_defaults = {
            "cmd": "$(printf '%s%s' INJ SUBSHELL)",
            "backtick": "`printf '%s%s' INJ BT`",
            "quotes": "single'double\"backslash\\brace}",
        }
        bash_code = render_polyglot_uri_link(
            target, lang="bash", defaults=adversarial_defaults
        )
        # Execute the generated Bash snippet with a mock `uri` function that prints its exact argv as JSON
        harness = (
            "uri() { python3 -c 'import json, sys; print(json.dumps(sys.argv[1:]))' \"$@\"; }\n"
            + "\n".join(ln for ln in bash_code.splitlines() if not ln.startswith("#!"))
        )
        proc = subprocess.run(
            ["bash", "-c", harness],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        argv_out = json.loads(proc.stdout.strip())
        self.assertEqual(argv_out[0], target)
        self.assertEqual(json.loads(argv_out[1]), adversarial_defaults)
        self.assertNotIn("INJSUBSHELL", argv_out[1])
        self.assertNotIn("INJBT", argv_out[1])

        for lang in ("javascript", "typescript", "rust", "python"):
            snippet = render_polyglot_uri_link(
                target, lang=lang, defaults=adversarial_defaults
            )
            self.assertIn(target, snippet)

    def test_uri_and_invocation_reject_dot_segments_quotes_controls_and_surrogates(
        self,
    ) -> None:
        for bad_uri in (
            "proc://host/../escape",
            "proc://host/a/./b",
            'proc://host/a"b',
            "proc://host/a'b",
            "proc://host/a`b",
            "proc://host/a\x7fb",
            "proc://host/a\x85b",
            "proc://host/a\ud800b",
            "1bad://host/path",
        ):
            with self.subTest(bad_uri=repr(bad_uri)):
                with self.assertRaises(ConformanceError) as err1:
                    validate_uri(bad_uri)
                self.assertEqual(err1.exception.code, "URP-IDENTITY-001")
                with self.assertRaises(ConformanceError) as err2:
                    validate_uri_invocation(bad_uri, {})
                self.assertEqual(err2.exception.code, "URP-IDENTITY-001")

    def test_float_overflow_and_lone_surrogates_fail_closed(self) -> None:
        register_uri_process("proc://demo/echo/v1", lambda args: {"echo": args})
        for bad_jsonl in (
            '{"x": 1e309}',
            '{"x": -1e309}',
            '{"x": NaN}',
            '{"x": "\\ud800"}',
            '{"k": 1, "k": 2}',
        ):
            with self.subTest(bad_jsonl=bad_jsonl):
                with self.assertRaises(ConformanceError) as err:
                    uri("proc://demo/echo/v1", bad_jsonl)
                self.assertEqual(err.exception.code, "URP-DATA-001")
                with self.assertRaises(ConformanceError) as err_c:
                    validate_uri_invocation("proc://demo/echo/v1", bad_jsonl)
                self.assertEqual(err_c.exception.code, "URP-DATA-001")

        for bad_dict in ({"x": float("inf")}, {"s": "\ud800"}, {"\udfff": 1}):
            with self.assertRaises(ConformanceError) as err_d:
                uri("proc://demo/echo/v1", bad_dict)
            self.assertEqual(err_d.exception.code, "URP-DATA-001")

    def test_symlink_ancestors_and_symlink_root_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            real_pkg = base / "real_pkg"
            real_pkg.mkdir()
            (real_pkg / "doc.json").write_text('{"ok": true}\n', encoding="utf-8")
            sym_pkg = base / "sym_pkg"
            sym_pkg.symlink_to(real_pkg)

            with self.assertRaises(ConformanceError) as err1:
                document(sym_pkg, "doc.json")
            self.assertEqual(err1.exception.code, "URP-PATH-001")

            with self.assertRaises(ConformanceError) as err2:
                document(f"{sym_pkg}/../real_pkg", "doc.json")
            self.assertEqual(err2.exception.code, "URP-PATH-001")

            with self.assertRaises(ConformanceError) as err3:
                check_package(sym_pkg)
            self.assertEqual(err3.exception.code, "URP-PATH-001")

    def test_bundle_check_and_500_line_modularity_budget(self) -> None:
        res = subprocess.run(
            [sys.executable, "-B", str(ROOT / "operations/bundle.py"), "--check"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        for py_path in (
            *(ROOT / "operations").glob("*.py"),
            *(ROOT / "tests").glob("*.py"),
        ):
            lines = len(py_path.read_text(encoding="utf-8").splitlines())
            self.assertLess(lines, 500, f"{py_path} has {lines} lines (>= 500)")


if __name__ == "__main__":
    unittest.main()
