#!/usr/bin/env python3
"""Refresh the checked-in Erdős status snapshot from teorth/erdosproblems.

Install the optional sync dependency with ``pip install -r requirements.txt``.
Normal site builds consume the JSON snapshot without requiring network or YAML.
"""

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "lists" / "erdos_status.json"
DATABASE_URL = "https://teorth.github.io/erdosproblems/"
REPOSITORY_URL = "https://github.com/teorth/erdosproblems"
COMMIT_API = "https://api.github.com/repos/teorth/erdosproblems/commits/main"
RAW_BASE = "https://raw.githubusercontent.com/teorth/erdosproblems"
STATEMENT_BASE = (
    "https://github.com/google-deepmind/formal-conjectures/blob/main/"
    "FormalConjectures/ErdosProblems"
)
INFORMAL_STATES = {
    "open", "proved", "disproved", "solved", "falsifiable", "verifiable",
    "decidable", "not provable", "not disprovable", "independent",
}


def validate_commit(commit):
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Source commit must be a full, lowercase 40-character Git SHA.")
    return commit


def fetch_text(url):
    request = Request(url, headers={"User-Agent": "Erdosproblems-llm-hunter-status-sync"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def parse_yaml(text):
    try:
        import yaml
    except ImportError as exc:
        raise ValueError("Install the sync dependency: python -m pip install -r requirements.txt") from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid upstream YAML: {exc}") from exc


def state_field(problem, field, allowed, number):
    value = problem.get(field)
    if not isinstance(value, dict) or not isinstance(value.get("state"), str):
        raise ValueError(f"Problem {number}: {field}.state must be a string.")
    if value["state"] not in allowed:
        raise ValueError(f"Problem {number}: unsupported {field}.state {value['state']!r}.")
    return value


def optional_date(value, label):
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        value = value.isoformat()
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{label} must be an ISO date (YYYY-MM-DD).")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} is not a valid date: {value!r}.") from exc
    return value


def optional_url(value, label):
    if value is None:
        return None
    if not isinstance(value, str) or re.search(r"[\s\x00-\x1f\x7f]", value):
        raise ValueError(f"{label} must be an HTTP(S) URL without whitespace.")
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in {"http", "https"} and bool(parsed.hostname)
            and parsed.username is None and parsed.password is None
        )
        parsed.port  # Reject malformed port numbers as well.
    except ValueError as exc:
        raise ValueError(f"{label} is not a valid HTTP(S) URL.") from exc
    if not valid:
        raise ValueError(f"{label} must be an absolute HTTP(S) URL without credentials.")
    return value


def build_snapshot(data, commit):
    validate_commit(commit)
    if not isinstance(data, list) or not data:
        raise ValueError("Upstream data must be a nonempty list of problems.")
    problems = {}
    for index, problem in enumerate(data, start=1):
        if not isinstance(problem, dict):
            raise ValueError(f"Upstream entry {index} must be an object.")
        number = problem.get("number")
        if not isinstance(number, str) or not re.fullmatch(r"[1-9][0-9]*", number):
            raise ValueError(f"Upstream entry {index} has an invalid problem number: {number!r}.")
        if number in problems:
            raise ValueError(f"Duplicate upstream problem number: {number}.")

        informal = state_field(problem, "informal_status", INFORMAL_STATES, number)
        formal = state_field(problem, "formal_status", {"unformalized", "Lean"}, number)
        statement = state_field(problem, "formalized", {"yes", "no"}, number)
        expected_status = informal["state"]
        if formal["state"] != "unformalized":
            expected_status += f" ({formal['state']})"
        combined = state_field(problem, "status", {expected_status}, number)
        for name, value in (
            ("informal_status", informal), ("formal_status", formal),
            ("formalized", statement), ("status", combined),
        ):
            optional_date(value.get("last_update"), f"Problem {number}: {name}.last_update")
        solution_url = optional_url(formal.get("url"), f"Problem {number}: formal_status.url")
        if solution_url and formal["state"] == "unformalized":
            raise ValueError(f"Problem {number}: an unformalized solution cannot have a proof URL.")

        problems[number] = {
            "status": combined["state"],
            "informal_status": informal["state"],
            "status_updated": optional_date(combined.get("last_update"), f"Problem {number}: status.last_update"),
            "statement_formalization": {
                "state": statement["state"],
                "url": f"{STATEMENT_BASE}/{number}.lean" if statement["state"] == "yes" else None,
            },
            # Upstream never invents a solution link when no URL was supplied.
            # In particular, "open (Lean)" is still informally open.
            "solution_formalization": {"state": formal["state"], "url": solution_url},
        }
    return {
        "source_url": f"{REPOSITORY_URL}/blob/{commit}/data/problems.yaml",
        "source_commit": commit,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "database_url": DATABASE_URL,
        "problems": dict(sorted(problems.items(), key=lambda item: int(item[0]))),
    }


def write_snapshot(snapshot, output):
    """Replace the previous snapshot only after all input has been validated."""
    output = Path(output)
    serialized = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent, prefix=f".{output.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(serialized)
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Read a downloaded upstream YAML file without network access.")
    parser.add_argument("--source-commit", help="Full upstream commit SHA corresponding to --input.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Snapshot destination (default: lists/erdos_status.json).")
    args = parser.parse_args(argv)
    if bool(args.input) != bool(args.source_commit):
        parser.error("--input and --source-commit must be supplied together.")
    try:
        if args.input:
            commit = validate_commit(args.source_commit)
            yaml_text = args.input.read_text(encoding="utf-8")
        else:
            latest = json.loads(fetch_text(COMMIT_API))
            if not isinstance(latest, dict):
                raise ValueError("GitHub returned an invalid commit response.")
            commit = validate_commit(latest.get("sha"))
            yaml_text = fetch_text(f"{RAW_BASE}/{commit}/data/problems.yaml")
        snapshot = build_snapshot(parse_yaml(yaml_text), commit)
        write_snapshot(snapshot, args.output)
    except (ValueError, OSError, URLError) as exc:
        parser.exit(1, f"Status sync failed: {exc}\n")
    print(f"Synced {len(snapshot['problems'])} problem statuses from {commit} to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
