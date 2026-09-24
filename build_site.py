#!/usr/bin/env python3
"""
Build script for Erdosproblems-llm-hunter website.
Reads TeX files from the attacks directory and saved problem catalogs,
generates JSON data files for the static site.
"""

import os
import json
import csv
import html
import re
import subprocess
from datetime import datetime
from pathlib import Path

# Directories
BASE_DIR = Path(__file__).parent
ATTACKS_DIR = BASE_DIR / "attacks"
LISTS_DIR = BASE_DIR / "lists"
DATA_DIR = BASE_DIR / "docs" / "data"
REVIEWS_DIR = BASE_DIR / "reviews"
ERDOS_STATUS_PATH = LISTS_DIR / "erdos_status.json"
OPEN_PROBLEMS_PATH = LISTS_DIR / "top500-v22.json"
# Tao's database includes independence results in its total solved count.
RESOLVED_ERDOS_STATUSES = {'proved', 'disproved', 'solved', 'independent'}
# Requested display rule for the Erdos LLM Claim column. This deliberately
# differs from the database's resolved categories and from individual attempts.
UNRESOLVED_ERDOS_CLAIM_STATUSES = {'open', 'falsifiable', 'decidable'}


def load_erdos_status():
    """Load the versioned upstream snapshot; ordinary builds work offline."""
    with ERDOS_STATUS_PATH.open(encoding='utf-8') as f:
        return json.load(f)


def apply_erdos_status(problems, snapshot):
    """Apply the database display rule while preserving actual attempt claims."""
    statuses = snapshot['problems']
    missing = sorted(set(problems) - set(statuses), key=int)
    if missing:
        raise ValueError(
            'Missing upstream status for Erdos problems: '
            + ', '.join(missing)
            + '. Run python scripts/sync_erdos_status.py before building.'
        )

    for number, problem in problems.items():
        upstream = statuses[number]
        has_attempts = any(
            attack.get('entry_kind') != 'statement_only'
            for attack in problem.get('attacks', [])
        )
        problem['attempt_status'] = problem['status'] if has_attempts else 'none'
        problem['llm_status'] = (
            'unresolved'
            if upstream['informal_status'] in UNRESOLVED_ERDOS_CLAIM_STATUSES
            else 'solved'
        )
        problem['llm_status_source'] = 'database_rule'
        problem['status'] = upstream['status']
        problem['status_updated'] = upstream['status_updated']
        problem['is_solved'] = upstream['informal_status'] in RESOLVED_ERDOS_STATUSES
        problem['statement_formalization'] = upstream['statement_formalization']
        problem['solution_formalization'] = upstream['solution_formalization']
        problem['database_url'] = snapshot['database_url']
        if isinstance(problem.get('completion'), (int, float)):
            problem['llm_completion'] = problem['completion']
            problem['completion_source'] = 'llm'
        if problem['is_solved']:
            problem['completion'] = 100
            problem['completion_source'] = 'database'
    return problems


def read_tex_file(filepath):
    """Read a TeX file and return its content."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return ""


def extract_completion(content):
    """Extract completion estimate percentage from TeX content.

    Looks for 'COMPLETION ESTIMATE' and scans that line plus the next 3 lines.
    If multiple blocks are present, the latest block with a valid value wins.
    Returns a float percentage (0-100) or None.
    """
    lines = content.splitlines()
    last_value = None
    confidence_re = re.compile(r'\bconfiden\w*\b', re.IGNORECASE)

    def is_confidence_context(text, start, end, window=80):
        left = max(0, start - window)
        right = min(len(text), end + window)
        return confidence_re.search(text[left:right]) is not None

    def is_rejected_value(text, start, end):
        # Reviews may quote a completion claim only to reject it. Match the
        # rejection next to that value, without discarding a corrected estimate.
        formatting = r'\\[A-Za-z]+\*?|[{}\'"`“”‘’$]'
        before = re.sub(formatting, '', text[:start])
        after = re.sub(formatting, '', text[end:])
        return (
            re.search(r'\b(?:not|rather than)\s*$', before, re.IGNORECASE)
            or re.match(
                r'\s*(?:(?:is|was|would be)\s+)?'
                r'(?:false|incorrect|invalid|wrong|rejected|unsupported|unjustified)\b',
                after, re.IGNORECASE,
            )
        )

    for idx, line in enumerate(lines):
        if not re.search(r'COMPLETION\s*(?:RATE\s*)?ESTIMATE', line, re.IGNORECASE):
            continue

        window = lines[idx:idx + 4]
        window_text = "\n".join(window)

        # Prefer explicit percentages.
        local_values = []
        for match in re.finditer(r'(\d+(?:\.\d+)?)\s*\\?%', window_text):
            if is_confidence_context(window_text, match.start(), match.end()):
                continue
            if is_rejected_value(window_text, match.start(), match.end()):
                continue
            try:
                local_values.append(float(match.group(1)))
            except ValueError:
                continue

        if local_values:
            last_value = local_values[-1]
            continue

        # Fallback: decimal fraction (e.g., 0.10) -> convert to percent.
        for match in re.finditer(r'\b0?\.\d+\b', window_text):
            if re.match(r'\s*\\?%', window_text[match.end():]):
                continue
            if is_confidence_context(window_text, match.start(), match.end()):
                continue
            if is_rejected_value(window_text, match.start(), match.end()):
                continue
            try:
                decimal_value = float(match.group(0))
            except ValueError:
                continue
            if decimal_value <= 1:
                last_value = decimal_value * 100

    return last_value


def get_file_date(filepath):
    """Get the date when a file was last updated.

    First tries to get the latest git commit date, then falls back to
    file modification time.

    Returns date in YYYY-MM-DD format.
    """
    try:
        # Try to get the latest git commit date for this file
        result = subprocess.run(
            ['git', 'log', '-1', '--format=%aI', '--', str(filepath)],
            capture_output=True,
            text=True,
            cwd=filepath.parent
        )
        if result.returncode == 0 and result.stdout.strip():
            # Parse ISO format date and extract just the date part
            git_date = result.stdout.strip().split('\n')[0]
            return datetime.fromisoformat(git_date.replace('Z', '+00:00')).strftime('%Y-%m-%d')
    except Exception as e:
        pass
    
    # Fall back to file modification time
    try:
        mtime = os.path.getmtime(filepath)
        return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
    except Exception as e:
        print(f"Warning: Could not get date for {filepath}: {e}")
        return datetime.now().strftime('%Y-%m-%d')


def parse_collection_metadata(content):
    """Read an attributed collection record without treating its header as prose.

    Invalid metadata stops the build: silently discarding attribution could
    misrepresent an imported writeup as a new mathematical attempt.
    """
    first_line, separator, remainder = content.partition('\n')
    marker = re.match(r'^\s*%\s*COLLECTION_METADATA:\s*(.*)$', first_line)
    if not marker:
        return None, content
    try:
        metadata = json.loads(marker.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError('Invalid COLLECTION_METADATA JSON') from exc
    if not isinstance(metadata, dict) or metadata.get('schema_version') != 1:
        raise ValueError('Unsupported COLLECTION_METADATA schema_version')
    kind = metadata.get('kind')
    if kind not in {'reused_writeup', 'statement_only'}:
        raise ValueError('Invalid COLLECTION_METADATA kind')
    if metadata.get('independently_reviewed') is not False:
        raise ValueError('Collection imports must explicitly be independently_reviewed: false')
    if kind == 'reused_writeup':
        for key in ('source_model', 'primary_source'):
            if not isinstance(metadata.get(key), str) or not metadata[key].strip():
                raise ValueError(f'COLLECTION_METADATA requires {key}')
        paths = metadata.get('source_paths')
        if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and p for p in paths):
            raise ValueError('COLLECTION_METADATA requires source_paths')
        if metadata.get('source_claim') not in {'solved', 'unresolved'}:
            raise ValueError('Invalid COLLECTION_METADATA source_claim')
        completion = metadata.get('source_completion')
        if completion is not None and (
            type(completion) not in (int, float) or not 0 <= completion <= 100
        ):
            raise ValueError('Invalid COLLECTION_METADATA source_completion')
    else:
        urls = metadata.get('source_urls')
        if not isinstance(urls, list) or not all(isinstance(url, str) for url in urls):
            raise ValueError('COLLECTION_METADATA requires source_urls')
    return metadata, remainder if separator else ''


def parse_attack(content, model_name, date_posted=None):
    """Parse an attack TeX file and extract structured data."""
    provenance, content = parse_collection_metadata(content)
    # Look for section markers
    sections = {}
    current_section = 'preamble'
    current_content = []

    for line in content.split('\n'):
        line_stripped = line.strip()
        # Check for section headers (numbered or named)
        section_match = re.match(r'^(\d+)\)\s*(.*)', line_stripped)
        if section_match:
            if current_content:
                sections[current_section] = '\n'.join(current_content).strip()
            current_section = section_match.group(2).upper() if section_match.group(2) else f"SECTION_{section_match.group(1)}"
            current_content = []
        elif line_stripped.startswith('PROBLEM') or line_stripped.startswith('OUTPUT'):
            if current_content:
                sections[current_section] = '\n'.join(current_content).strip()
            current_section = line_stripped.split()[0]
            current_content = [line_stripped.replace(current_section, '').strip()]
        else:
            current_content.append(line)

    if current_content:
        sections[current_section] = '\n'.join(current_content).strip()

    # Determine status from raw content.
    status = 'unresolved' if re.search(
        r'\bunresolved\b|\bremains\s+open\b', content, re.IGNORECASE
    ) else 'solved'

    completion = extract_completion(content)
    if provenance:
        if provenance['kind'] == 'statement_only':
            status, completion = 'unresolved', 0
        else:
            status = provenance['source_claim']
            # Other included versions may quote incompatible estimates. Only
            # the attributed primary source supplies this record's estimate.
            completion = provenance.get('source_completion')

    attack_data = {
        'model': model_name,
        'sections': sections,
        'status': status,
        'raw': content
    }

    if provenance:
        attack_data['provenance'] = provenance
        attack_data['entry_kind'] = provenance['kind']

    if completion is not None:
        attack_data['completion'] = completion
    
    if date_posted:
        attack_data['date_posted'] = date_posted
    
    return attack_data


def load_erdos_problems_list():
    """Load the Erdos problems list CSV."""
    csv_path = LISTS_DIR / "erdos_problems.csv"
    problems = {}
    if csv_path.exists():
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                problems[row['number']] = {
                    'status_url': row.get('status', ''),
                    'problem_url': row.get('problem_url', f"https://www.erdosproblems.com/{row['number']}")
                }
    return problems


def load_mo_problems_list():
    """Load the MathOverflow problems list CSV."""
    csv_path = LISTS_DIR / "mo_problems.csv"
    problems = {}
    if csv_path.exists():
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                qid = row['question_id']
                problems[qid] = {
                    'title': row.get('title', '').replace('&#39;', "'"),
                    'score': int(row.get('score', 0)),
                    'tags': row.get('tags', '').split(';'),
                    'creation_date': row.get('creation_date', ''),
                    'link': row.get('link', f"https://mathoverflow.net/questions/{qid}")
                }
    return problems


def load_open_problems_catalog():
    """Read and validate the versioned ranking without requiring local-only data.

    The supplied edition is evidence about its dated status, not an independent
    verification of any problem's current mathematical status.
    """
    with OPEN_PROBLEMS_PATH.open(encoding='utf-8') as f:
        snapshot = json.load(f)
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('records'), list):
        raise ValueError('Open problems catalog requires a records array')
    records = snapshot['records']
    count = snapshot.get('recordCount')
    if type(count) is not int or count != len(records) or count < 1:
        raise ValueError('Open problems catalog recordCount does not match its records')
    ids, ranks = set(), set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('Malformed open problems catalog record')
        problem_id = record.get('problemId')
        if not isinstance(problem_id, str) or not re.fullmatch(
            r'problem\.[a-z0-9]+(?:[.-][a-z0-9]+)*', problem_id
        ):
            raise ValueError(f'Malformed open problem ID: {problem_id!r}')
        if problem_id in ids:
            raise ValueError(f'Duplicate open problem ID: {problem_id}')
        ids.add(problem_id)
        rank = record.get('releaseRank')
        if type(rank) is not int or rank < 1:
            raise ValueError(f'Malformed open problem rank for {problem_id}: {rank!r}')
        if rank in ranks:
            raise ValueError(f'Duplicate open problem rank: {rank}')
        ranks.add(rank)
        for key in ('canonicalTitle', 'exactTarget', 'primaryDomain',
                    'primaryDomainLabel', 'displayStatus', 'releaseStatus',
                    'statusQualification'):
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError(f'Open problem {problem_id} requires {key}')
        sources = record.get('sources')
        if not isinstance(sources, list) or not sources or not all(
            isinstance(source, dict) and isinstance(source.get('url'), str)
            and source['url'].startswith(('https://', 'http://'))
            and isinstance(source.get('citation'), str) and source['citation'].strip()
            for source in sources
        ):
            raise ValueError(f'Open problem {problem_id} requires attributed sources')
    if ranks != set(range(1, count + 1)):
        raise ValueError('Open problems catalog ranks must be contiguous from 1 to recordCount')
    return snapshot


def load_review(problem_type, problem_id):
    """Load review metadata for a problem, if present."""
    review_path = REVIEWS_DIR / problem_type / f"{problem_id}.json"
    if not review_path.exists():
        return None
    try:
        with open(review_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load review for {problem_type} {problem_id}: {e}")
        return None


def build_erdos_data():
    """Build data for Erdos problems.

    Problem statements are NOT included - users are directed to
    erdosproblems.com for the actual problem content.
    """
    attacks_dir = ATTACKS_DIR / "erdos"
    problems_list = load_erdos_problems_list()
    status_snapshot = load_erdos_status()
    for problem_num in status_snapshot['problems']:
        problems_list.setdefault(problem_num, {})

    problems = {}

    # Include the full upstream catalogue, retaining any CSV-specific links.
    for problem_num, list_info in problems_list.items():
        problems[problem_num] = {
            'number': problem_num,
            'problem_url': list_info.get('problem_url', f"https://www.erdosproblems.com/{problem_num}"),
            'database_url': list_info.get('status_url', 'https://teorth.github.io/erdosproblems/'),
            'attacks': []
        }

    # Load attacks
    if attacks_dir.exists():
        for model_dir in attacks_dir.iterdir():
            if model_dir.is_dir() and not model_dir.name.startswith('.'):
                model_name = model_dir.name.replace('_', ' ')
                for tex_file in sorted(model_dir.glob("*.tex")):
                    filename = tex_file.stem
                    match = re.match(r'^(?P<id>\d+)(?:_v(?P<ver>\d+))?$', filename)
                    if not match:
                        continue
                    problem_num = match.group('id')
                    version = int(match.group('ver') or 1)
                    content = read_tex_file(tex_file)
                    date_posted = get_file_date(tex_file)
                    parsed = parse_attack(content, model_name, date_posted)
                    parsed['file_path'] = tex_file.relative_to(BASE_DIR).as_posix()
                    parsed['version'] = version

                    if problem_num in problems:
                        problems[problem_num]['attacks'].append(parsed)
                    else:
                        # Problem not in CSV list but has attack - still add it
                        problems[problem_num] = {
                            'number': problem_num,
                            'problem_url': f"https://www.erdosproblems.com/{problem_num}",
                            'database_url': 'https://teorth.github.io/erdosproblems/',
                            'attacks': [parsed]
                        }

    # Attach review metadata, if any
    for problem_num, problem_data in problems.items():
        review = load_review('erdos', problem_num)
        if review:
            problem_data['review'] = review

    # Sort attacks so versioned files appear after base attempts
    for problem_data in problems.values():
        problem_data['attacks'].sort(
            key=lambda attack: (
                attack.get('model', ''),
                attack.get('version', 1),
                attack.get('file_path', '')
            )
        )

    # Aggregate completion across all attacks for each problem
    for problem_num, problem_data in problems.items():
        completions = [
            attack.get('completion')
            for attack in problem_data.get('attacks', [])
            if isinstance(attack.get('completion'), (int, float))
        ]
        if completions:
            problem_data['completion'] = max(completions)

    # Aggregate status across all attacks for each problem
    problems = aggregate_problem_status(problems)

    return apply_erdos_status(problems, status_snapshot)


def build_mo_data():
    """Build data for MathOverflow problems.

    Problem statements are NOT included - users are directed to
    MathOverflow for the actual problem content.
    """
    attacks_dir = ATTACKS_DIR / "open_problems" / "mo"
    problems_list = load_mo_problems_list()

    problems = {}

    # Load from CSV list (link to external sources only)
    for qid, info in problems_list.items():
        problems[qid] = {
            'id': qid,
            'title': info['title'],
            'score': info['score'],
            'tags': info['tags'],
            'creation_date': info['creation_date'],
            'link': info['link'],
            'attacks': []
        }

    # Load attacks
    if attacks_dir.exists():
        for model_dir in attacks_dir.iterdir():
            if model_dir.is_dir() and not model_dir.name.startswith('.'):
                model_name = model_dir.name.replace('_', ' ')
                for tex_file in sorted(model_dir.glob("*.tex")):
                    # Extract question ID from filename
                    filename = tex_file.stem
                    qid_match = re.match(r'^(\d+)', filename)
                    if qid_match:
                        qid = qid_match.group(1)
                        version_match = re.search(r'_v(\d+)', filename)
                        version = int(version_match.group(1)) if version_match else 1
                        content = read_tex_file(tex_file)
                        date_posted = get_file_date(tex_file)
                        parsed = parse_attack(content, model_name, date_posted)
                        parsed['file_path'] = tex_file.relative_to(BASE_DIR).as_posix()
                        parsed['version'] = version

                        # Check for "solved" in filename without overriding unresolved content.
                        if '--solved--' in filename.lower() and parsed.get('status') != 'unresolved':
                            parsed['status'] = 'solved'

                        if qid in problems:
                            problems[qid]['attacks'].append(parsed)

    # Attach review metadata, if any
    for qid, problem_data in problems.items():
        review = load_review('open_problems/mo', qid) or load_review('mo', qid)
        if review:
            problem_data['review'] = review

    # Sort attacks so versioned files appear after base attempts
    for problem_data in problems.values():
        problem_data['attacks'].sort(
            key=lambda attack: (
                attack.get('model', ''),
                attack.get('version', 1),
                attack.get('file_path', '')
            )
        )

    # Aggregate completion across all attacks for each problem
    for qid, problem_data in problems.items():
        completions = [
            attack.get('completion')
            for attack in problem_data.get('attacks', [])
            if isinstance(attack.get('completion'), (int, float))
        ]
        if completions:
            problem_data['completion'] = max(completions)

    # Aggregate status across all attacks for each problem
    problems = aggregate_problem_status(problems)

    return problems


def summarize_open_problem_attempts(problem):
    """Keep writeup claims and estimates separate from catalog status."""
    problem['attacks'].sort(key=lambda attack: (
        attack.get('model', ''), attack.get('version', 1), attack.get('file_path', '')
    ))
    attempts = [a for a in problem['attacks'] if a.get('entry_kind') != 'statement_only']
    problem['llm_status'] = (
        'none' if not attempts else
        'unresolved' if any(a.get('status') == 'unresolved' for a in attempts) else 'solved'
    )
    problem['llm_status_source'] = 'attempts'
    completions = [a['completion'] for a in attempts
                   if type(a.get('completion')) in (int, float)]
    if completions:
        problem['completion'] = max(completions)
        problem['completion_source'] = 'llm'


def build_open_problems_data(mo_problems=None, snapshot=None):
    """Join the ranked edition and legacy MO collection without asserting overlap.

    A rank identifies a position in one edition; the stable problemId identifies
    its attempts. MO IDs occupy a separate namespace and receive no ranking.
    """
    if snapshot is None:
        snapshot = load_open_problems_catalog()
    if mo_problems is None:
        mo_problems = build_mo_data()
    problems = {}
    for record in sorted(snapshot['records'], key=lambda item: item['releaseRank']):
        problem_id = record['problemId']
        formal_source = record.get('formalStatementSource') or {}
        problems[problem_id] = {
            'id': problem_id,
            'title': record['canonicalTitle'],
            'collection': 'ranked',
            'rank': record['releaseRank'],
            'domain': record['primaryDomain'],
            'domain_label': record['primaryDomainLabel'],
            'exact_target': record['exactTarget'],
            'link': formal_source.get('url') or record['sources'][0]['url'],
            'sources': record['sources'],
            'status': record['displayStatus'],
            'release_status': record['releaseStatus'],
            'status_statement': record.get('statusStatement'),
            'status_qualification': record['statusQualification'],
            'status_reviewed_at': record.get('statusReviewedAt') or None,
            'edition_date': snapshot.get('editionDate'),
            'publication_id': snapshot.get('publicationId'),
            'reader_question': record.get('readerQuestion'),
            'why_it_matters': record.get('whyItMatters'),
            'family_label': record.get('familyLabel'),
            # Preserve exact scope, dated evidence and ranking provenance.
            'catalog_record': record,
            'attacks': [],
        }

    attacks_dir = ATTACKS_DIR / 'open_problems'
    if attacks_dir.exists():
        for model_dir in sorted(attacks_dir.iterdir()):
            if not model_dir.is_dir() or model_dir.name.startswith('.') or model_dir.name == 'mo':
                continue
            for tex_file in sorted(model_dir.glob('*.tex')):
                match = re.fullmatch(r'(?P<id>problem\.[a-z0-9.-]+)(?:_v(?P<ver>[1-9]\d*))?', tex_file.stem)
                if not match or match.group('id') not in problems:
                    raise ValueError(
                        f'Unknown ranked open problem attempt: {tex_file}. '
                        'Use a catalog problemId, optionally followed by _vN.'
                    )
                parsed = parse_attack(read_tex_file(tex_file), model_dir.name.replace('_', ' '),
                                      get_file_date(tex_file))
                parsed['file_path'] = tex_file.relative_to(BASE_DIR).as_posix()
                parsed['version'] = int(match.group('ver') or 1)
                problems[match.group('id')]['attacks'].append(parsed)

    for problem_id, problem in problems.items():
        review = load_review('open_problems', problem_id)
        if review:
            problem['review'] = review
        summarize_open_problem_attempts(problem)

    for qid, original in sorted(mo_problems.items(), key=lambda item: int(item[0])):
        problem = {
            **original,
            'id': f'mo:{qid}',
            'title': html.unescape(original['title']),
            'mo_id': qid,
            'collection': 'mo',
            'rank': None,
            'domain': 'mathoverflow',
            'domain_label': 'MathOverflow',
            'exact_target': None,
            'sources': [{'citation': html.unescape(original['title']), 'url': original['link']}],
            'status': 'unreviewed',
            'status_qualification': 'Legacy MathOverflow collection; current mathematical status has not been reviewed against the ranked catalog.',
            'status_reviewed_at': None,
        }
        # Recompute from actual attempts; a statement-only MO record must not
        # inherit the old empty-aggregate "solved" state or estimate.
        problem.pop('completion', None)
        summarize_open_problem_attempts(problem)
        problems[problem['id']] = problem
    return problems


def aggregate_problem_status(problems):
    """Aggregate status for each problem based on all its attacks.
    
    Rule: If at least one attack has status 'unresolved' (case-insensitive),
    then the problem status is 'unresolved'. Otherwise, it's 'solved'.
    """
    for problem_id, problem_data in problems.items():
        attacks = [
            attack for attack in problem_data.get('attacks', [])
            if attack.get('entry_kind') != 'statement_only'
        ]
        
        # Check if any attack is unresolved
        has_unresolved = any(
            attack.get('status', '').lower() == 'unresolved' 
            for attack in attacks
        )
        
        if has_unresolved:
            problem_data['status'] = 'unresolved'
        else:
            problem_data['status'] = 'solved'
    
    return problems


def generate_js_data(erdos_problems, mo_problems, open_problems=None, open_catalog=None):
    """Generate JavaScript data files for the frontend."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if open_catalog is None:
        open_catalog = load_open_problems_catalog()
    if open_problems is None:
        open_problems = build_open_problems_data(mo_problems, open_catalog)

    # Generate erdos_data.js
    with open(DATA_DIR / "erdos_data.js", 'w', encoding='utf-8') as f:
        # Sort by problem number
        sorted_problems = dict(sorted(erdos_problems.items(), key=lambda x: int(x[0]) if x[0].isdigit() else float('inf')))
        f.write(f"var erdosProblems = {json.dumps(sorted_problems, indent=2)};\n")
        source = {key: value for key, value in load_erdos_status().items() if key != 'problems'}
        f.write(f"var erdosStatusSync = {json.dumps(source, indent=2)};\n")

    # Generate mo_data.js
    with open(DATA_DIR / "mo_data.js", 'w', encoding='utf-8') as f:
        # Sort by question ID
        sorted_problems = dict(sorted(mo_problems.items(), key=lambda x: int(x[0]) if x[0].isdigit() else float('inf')))
        f.write(f"var moProblems = {json.dumps(sorted_problems, indent=2)};\n")

    with open(DATA_DIR / 'open_problems_data.js', 'w', encoding='utf-8') as f:
        f.write(f'var openProblems = {json.dumps(open_problems, indent=2)};\n')
        f.write('window.OPEN_PROBLEMS_DATA = openProblems;\n')
        catalog_info = {
            'edition_date': open_catalog.get('editionDate'),
            'publication_id': open_catalog.get('publicationId'),
            'release_version': open_catalog.get('releaseVersion'),
            'published_at': open_catalog.get('publishedAt'),
            'public_boundary': open_catalog.get('publicBoundary'),
            'source_path': 'lists/top500-v22.json',
        }
        f.write(f'var openProblemsCatalog = {json.dumps(catalog_info, indent=2)};\n')
        f.write('window.OPEN_PROBLEMS_CATALOG = openProblemsCatalog;\n')

    # Generate summary statistics
    stats = {
        'erdos': {
            'total_problems': len(erdos_problems),
            'with_attacks': sum(
                1 for p in erdos_problems.values()
                if any(a.get('entry_kind') != 'statement_only' for a in p.get('attacks', []))
            ),
            'solved_problems': sum(1 for p in erdos_problems.values() if p['is_solved']),
            'models': sorted(set(
                a['model']
                for p in erdos_problems.values()
                for a in p.get('attacks', [])
            ))
        },
        'mo': {
            'total_problems': len(mo_problems),
            'with_attacks': sum(
                1 for p in mo_problems.values()
                if any(a.get('entry_kind') != 'statement_only' for a in p.get('attacks', []))
            ),
            'models': sorted(set(
                a['model']
                for p in mo_problems.values()
                for a in p.get('attacks', [])
                if a.get('entry_kind') != 'statement_only'
            ))
        },
        'open_problems': {
            'total_problems': len(open_problems),
            'ranked_total': sum(p['collection'] == 'ranked' for p in open_problems.values()),
            'mo_total': sum(p['collection'] == 'mo' for p in open_problems.values()),
            'with_attacks': sum(
                1 for p in open_problems.values()
                if any(a.get('entry_kind') != 'statement_only' for a in p.get('attacks', []))
            ),
            'ranked_with_attacks': sum(
                1 for p in open_problems.values() if p['collection'] == 'ranked'
                and any(a.get('entry_kind') != 'statement_only' for a in p.get('attacks', []))
            ),
            'models': sorted(set(
                a['model'] for p in open_problems.values() for a in p.get('attacks', [])
                if a.get('entry_kind') != 'statement_only'
            )),
        }
    }

    with open(DATA_DIR / "stats.js", 'w', encoding='utf-8') as f:
        f.write(f"var siteStats = {json.dumps(stats, indent=2)};\n")

    print(f"Generated data files in {DATA_DIR}")
    print(f"  Erdos problems: {stats['erdos']['total_problems']} ({stats['erdos']['with_attacks']} with attacks)")
    print(f"  MO problems: {stats['mo']['total_problems']} ({stats['mo']['with_attacks']} with attacks)")
    print(f"  Open problems: {stats['open_problems']['total_problems']} ({stats['open_problems']['ranked_total']} ranked, {stats['open_problems']['with_attacks']} with attacks)")


def main():
    print("Building Erdosproblems-llm-hunter site data...")

    erdos_problems = build_erdos_data()
    mo_problems = build_mo_data()
    open_catalog = load_open_problems_catalog()
    open_problems = build_open_problems_data(mo_problems, open_catalog)

    generate_js_data(erdos_problems, mo_problems, open_problems, open_catalog)

    print("Build complete!")


if __name__ == "__main__":
    main()
