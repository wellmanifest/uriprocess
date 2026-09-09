"""Synthetic package fixtures test conformance, never production or behavior."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "operations"))
from conformance import ConformanceError, check_package, main


class ConformanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.package = self.root / "package"
        self.package.mkdir()

    def write(self, name, value, mode=0o644):
        path = self.package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
        path.chmod(mode)

    def fixture(self, native=False):
        if native:
            files = {"pyproject.toml": b'[project]\nname="example-connector"\nversion="1.0.0"\ndependencies=["example-runtime>=1"]\n[project.entry-points."urirun.bindings"]\nexample="example.core:bindings"\n',
                     "example/core.py": b"# preserved source fixture\n", "tests/test_core.py": b"# preserved test fixture\n",
                     "example/connector.json": json.dumps({"routes": ["example://host/item/query"]}).encode()}
            manifest = {"schema": "uriprocess.native-package/v1", "kind": "python-connector",
                        "public_uris": ["example://host/item/query"], "native_manifest": "example/connector.json",
                        "native_distribution": "example-connector", "native_version": "1.0.0",
                        "entry_points": {"example": "example.core:bindings"}, "dependencies": ["example-runtime>=1"],
                        "source": "provenance.json", "production_binding_verified": False}
        else:
            files = {"process.poa.json": json.dumps({"schema": "poa.process/v1", "process_ref": "poa://example.test/process/check/v1"}).encode(),
                     "src/check.mjs": b"// preserved source fixture\n", "tests/check.test.mjs": b"// preserved test fixture\n"}
            manifest = {"schema": "uriprocess.package/v1", "process_ref": "poa://example.test/process/check/v1",
                        "contract": "process.poa.json", "language": "javascript", "entry": "src/check.mjs",
                        "export": "check", "transport": "stdin-json", "request_fields": ["ticket", "context"],
                        "base_image": "node:22@sha256:" + "a" * 64, "role": "decision-library",
                        "executes_declared_capabilities": False, "authority": "decision-only; no execution grant",
                        "source": "provenance.json"}
            self.write("package.json", {"type": "module", "exports": "./src/check.mjs"})
            self.write("package-lock.json", {})
            self.write("bin.mjs", b"// adapter fixture\n", 0o755)
            self.write("Dockerfile", ("FROM " + manifest["base_image"] + "\n").encode())
            self.write(".dockerignore", b"node_modules\n")
        for name, value in files.items():
            self.write(name, value)
        provenance = {"schema": "uriprocess.provenance/v1", "repository": "https://example.test/owner/source",
                      "revision": "a" * 40, "files": [{"source": "original/" + name, "destination": name,
                                                       "sha256": hashlib.sha256(value).hexdigest(),
                                                       **({"mode": 0o644} if native else {})}
                                                      for name, value in files.items()]}
        self.write("uriprocess.json", manifest)
        self.write("provenance.json", provenance)
        return manifest, provenance

    def rejected(self, code):
        with self.assertRaises(ConformanceError) as error:
            check_package(self.package)
        self.assertEqual(error.exception.code, code)

    def test_poa_package_is_read_only_and_claims_only_local_consistency(self):
        self.fixture()
        before = {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
                  for p in self.package.rglob("*") if p.is_file()}
        result = check_package(self.package)
        self.assertEqual(result["profile"], "poa-node-v1")
        self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns) for p in before})
        for flag in ("upstream_git_verified", "behavior_verified", "guard_authenticated",
                     "execution_authority", "publication_authority", "production_verified"):
            self.assertIs(result[flag], False)

    def test_native_package_preserves_native_entrypoints_dependencies_and_routes(self):
        manifest, _ = self.fixture(native=True)
        result = check_package(self.package)
        self.assertEqual(result["profile"], "python-native-v1")
        self.assertEqual(result["public_uris"], manifest["public_uris"])

    def test_equivalent_npm_export_map_is_accepted_but_rebinding_is_rejected(self):
        self.fixture()
        self.write("package.json", {"type": "module", "exports": {".": "./src/check.mjs"}})
        self.assertEqual(check_package(self.package)["status"], "passed")
        self.write("package.json", {"type": "module", "exports": "./src/different.mjs"})
        self.rejected("URP-IDENTITY-001")

    def test_unknown_profile_and_false_execution_claim_rejected(self):
        manifest, _ = self.fixture()
        manifest["schema"] = "future.package/v2"
        self.write("uriprocess.json", manifest)
        self.rejected("URP-SCHEMA-001")
        manifest["schema"] = "uriprocess.package/v1"
        manifest["executes_declared_capabilities"] = True
        self.write("uriprocess.json", manifest)
        self.rejected("URP-SCHEMA-001")

    def test_mutable_or_short_source_revisions_rejected(self):
        _, provenance = self.fixture()
        for revision in ("main", "v1.0.0", "abcdef1", "A" * 40):
            provenance["revision"] = revision
            self.write("provenance.json", provenance)
            self.rejected("URP-SCHEMA-001")

    def test_changed_source_bytes_and_git_executable_modes_rejected(self):
        self.fixture()
        path = self.package / "src/check.mjs"
        original = path.read_bytes()
        path.write_bytes(original + b"changed")
        self.rejected("URP-INTEGRITY-001")
        path.write_bytes(original)
        path.chmod(0o755)
        self.rejected("URP-INTEGRITY-001")
        path.chmod(0o664)
        self.assertEqual(check_package(self.package)["status"], "passed")

    def test_self_consistent_source_change_cannot_claim_upstream_verification(self):
        _, provenance = self.fixture()
        self.write("src/check.mjs", b"locally rehashed change")
        for record in provenance["files"]:
            if record["destination"] == "src/check.mjs":
                record["sha256"] = hashlib.sha256((self.package / record["destination"]).read_bytes()).hexdigest()
        self.write("provenance.json", provenance)
        self.assertFalse(check_package(self.package)["upstream_git_verified"])

    def test_uri_and_native_metadata_drift_rejected(self):
        manifest, _ = self.fixture()
        manifest["process_ref"] = "poa://example.test/process/other/v1"
        self.write("uriprocess.json", manifest)
        self.rejected("URP-IDENTITY-001")

    def test_native_bindings_and_dependency_changes_rejected(self):
        manifest, _ = self.fixture(native=True)
        manifest["dependencies"] = []
        self.write("uriprocess.json", manifest)
        self.rejected("URP-IDENTITY-001")
        manifest["dependencies"] = ["example-runtime>=1"]
        manifest["entry_points"] = {"example": "example.other:bindings"}
        self.write("uriprocess.json", manifest)
        self.rejected("URP-IDENTITY-001")

    def test_removing_original_tests_even_with_updated_provenance_rejected(self):
        _, provenance = self.fixture()
        (self.package / "tests/check.test.mjs").unlink()
        provenance["files"] = [r for r in provenance["files"] if not r["destination"].startswith("tests/")]
        self.write("provenance.json", provenance)
        self.rejected("URP-TESTS-001")

    def test_parent_relative_absolute_and_backslash_paths_rejected(self):
        _, provenance = self.fixture()
        for path in ("../private", "/private", "dir\\private", "dir/../private"):
            provenance["files"][0]["source"] = path
            self.write("provenance.json", provenance)
            self.rejected("URP-PATH-001")

    def test_symlink_and_fifo_are_never_followed_or_consumed(self):
        self.fixture()
        path = self.package / "src/check.mjs"
        path.unlink()
        path.symlink_to(self.root / "outside")
        self.rejected("URP-PATH-001")
        path.unlink()
        os.mkfifo(path)
        self.rejected("URP-PATH-001")

    def test_extra_files_duplicate_sources_and_missing_modes_rejected(self):
        _, provenance = self.fixture(native=True)
        self.write("unselected", b"extra")
        self.rejected("URP-INTEGRITY-001")
        (self.package / "unselected").unlink()
        provenance["files"][0].pop("mode")
        self.write("provenance.json", provenance)
        self.rejected("URP-SCHEMA-001")
        provenance["files"][0]["mode"] = 0o644
        provenance["files"].append(provenance["files"][0])
        self.write("provenance.json", provenance)
        self.rejected("URP-INTEGRITY-001")

    def test_duplicate_json_keys_and_nonfinite_values_rejected(self):
        self.fixture()
        for raw in (b'{"schema":"a","schema":"b"}', b'{"field":NaN}', b'{broken'):
            self.write("uriprocess.json", raw)
            self.rejected("URP-DATA-001")

    def test_source_credentials_queries_and_malformed_authority_rejected(self):
        _, provenance = self.fixture()
        for url in ("https://actor:secret@example.test/repo", "https://example.test/repo?token=value", "https://[/repo"):
            provenance["repository"] = url
            self.write("provenance.json", provenance)
            self.rejected("URP-IDENTITY-001")

    def test_inventory_limit_and_cli_failure_are_bounded(self):
        self.fixture()
        with patch("conformance.MAX_ENTRIES", 2):
            self.rejected("URP-PATH-001")
        self.write("Dockerfile", b"")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["--package", str(self.package)]), 2)
        self.assertEqual(json.loads(output.getvalue()), {"status": "invalid", "code": "URP-IDENTITY-001", "execution_authority": False})


if __name__ == "__main__":
    unittest.main()
