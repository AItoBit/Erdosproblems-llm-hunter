import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import sync_erdos_status as sync


COMMIT = "0123456789abcdef0123456789abcdef01234567"


def entry(number="1", informal="open", formal="unformalized", statement="no"):
    status = informal + (f" ({formal})" if formal != "unformalized" else "")
    return {
        "number": number,
        "informal_status": {"state": informal, "last_update": "2026-09-20"},
        "formal_status": {"state": formal},
        "status": {"state": status, "last_update": "2026-09-20"},
        "formalized": {"state": statement},
    }


class StatusSnapshotTests(unittest.TestCase):
    def test_preserves_every_informal_status_and_pinned_provenance(self):
        states = sorted(sync.INFORMAL_STATES)
        data = [entry(str(index), state) for index, state in enumerate(states, start=1)]
        snapshot = sync.build_snapshot(data, COMMIT)
        self.assertEqual(len(snapshot["problems"]), len(states))
        for index, state in enumerate(states, start=1):
            record = snapshot["problems"][str(index)]
            self.assertEqual(record["status"], state)
            self.assertEqual(record["informal_status"], state)
        self.assertEqual(snapshot["source_commit"], COMMIT)
        self.assertEqual(snapshot["source_url"], f"{sync.REPOSITORY_URL}/blob/{COMMIT}/data/problems.yaml")
        self.assertEqual(snapshot["database_url"], sync.DATABASE_URL)
        self.assertTrue(snapshot["checked_at"].endswith("Z"))

    def test_open_lean_is_still_open_and_has_distinct_formalizations(self):
        problem = entry("390", formal="Lean", statement="yes")
        problem["formal_status"]["url"] = "https://example.org/proof.lean"
        record = sync.build_snapshot([problem], COMMIT)["problems"]["390"]
        self.assertEqual(record["status"], "open (Lean)")
        self.assertEqual(record["informal_status"], "open")
        self.assertEqual(record["solution_formalization"]["url"], "https://example.org/proof.lean")
        self.assertEqual(record["statement_formalization"]["url"], f"{sync.STATEMENT_BASE}/390.lean")

    def test_no_invented_proof_link_or_statement_link(self):
        record = sync.build_snapshot([entry(formal="Lean")], COMMIT)["problems"]["1"]
        self.assertIsNone(record["solution_formalization"]["url"])
        self.assertIsNone(record["statement_formalization"]["url"])

    def test_rejects_duplicate_and_invalid_ids(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            sync.build_snapshot([entry(), entry()], COMMIT)
        for number in [1, None, "01", "0", "1-2", "../1"]:
            with self.subTest(number=number), self.assertRaises(ValueError):
                sync.build_snapshot([entry(number)], COMMIT)

    def test_rejects_malformed_schema_and_inconsistent_derived_status(self):
        invalid = [None, {}, [], [None]]
        for field, value in [
            ("informal_status", {"state": "unknown"}),
            ("formal_status", {"state": "Coq"}),
            ("formalized", {"state": True}),
            ("status", {"state": "proved"}),
            ("status", None),
        ]:
            problem = entry()
            problem[field] = value
            invalid.append([problem])
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                sync.build_snapshot(data, COMMIT)

    def test_rejects_unsafe_or_malformed_solution_links(self):
        for url in ["javascript:alert(1)", "//example.org/a", "https:///a", "https://a b/c", "https://a:bad/p", "https://user:password@example.org/a", 7]:
            problem = entry(formal="Lean")
            problem["formal_status"]["url"] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                sync.build_snapshot([problem], COMMIT)
        problem = entry()
        problem["formal_status"]["url"] = "https://example.org/a"
        with self.assertRaisesRegex(ValueError, "unformalized"):
            sync.build_snapshot([problem], COMMIT)

    def test_dates_are_validated_and_missing_date_is_null(self):
        problem = entry()
        problem["status"].pop("last_update")
        self.assertIsNone(sync.build_snapshot([problem], COMMIT)["problems"]["1"]["status_updated"])
        for value in ["2026-02-30", "20260920", 123]:
            changed = deepcopy(problem)
            changed["informal_status"]["last_update"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                sync.build_snapshot([changed], COMMIT)

    def test_rejects_invalid_commit(self):
        for commit in [None, "main", COMMIT[:7], "a" * 39 + "/"]:
            with self.subTest(commit=commit), self.assertRaises(ValueError):
                sync.build_snapshot([entry()], commit)

    def test_malformed_yaml_and_unquoted_iso_dates(self):
        with self.assertRaisesRegex(ValueError, "Invalid upstream YAML"):
            sync.parse_yaml("number: [broken")
        problem = entry()
        problem["status"]["last_update"] = sync.parse_yaml("2026-09-20")
        record = sync.build_snapshot([problem], COMMIT)["problems"]["1"]
        self.assertEqual(record["status_updated"], "2026-09-20")

    def test_cli_offline_is_atomic_and_makes_no_network_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "problems.yaml"
            output = Path(directory) / "status.json"
            source.write_text(json.dumps([entry()]), encoding="utf-8")
            args = ["--input", str(source), "--source-commit", COMMIT, "--output", str(output)]
            with patch.object(sync, "fetch_text", side_effect=AssertionError("No network expected")):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(sync.main(args), 0)
                original = output.read_bytes()
                self.assertEqual(len(json.loads(original)["problems"]), 1)
                source.write_text(json.dumps([entry(), entry()]), encoding="utf-8")
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                    sync.main(args)
                self.assertEqual(failure.exception.code, 1)
                self.assertEqual(output.read_bytes(), original)
                self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ["problems.yaml", "status.json"])

    def test_cli_requires_offline_arguments_together(self):
        for args in [["--input", "problems.yaml"], ["--source-commit", COMMIT]]:
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                sync.main(args)
            self.assertEqual(failure.exception.code, 2)

    def test_online_fetch_uses_one_pinned_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.json"
            with patch.object(sync, "fetch_text", side_effect=[json.dumps({"sha": COMMIT}), json.dumps([entry()])]) as fetch:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(sync.main(["--output", str(output)]), 0)
            self.assertEqual(fetch.call_args_list[0].args[0], sync.COMMIT_API)
            self.assertEqual(fetch.call_args_list[1].args[0], f"{sync.RAW_BASE}/{COMMIT}/data/problems.yaml")
            self.assertEqual(json.loads(output.read_text())["source_commit"], COMMIT)


if __name__ == "__main__":
    unittest.main()
