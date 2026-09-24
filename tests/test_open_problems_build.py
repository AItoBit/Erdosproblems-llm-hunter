"""Protect catalog identity, dated status, and moved attempt/review links."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import build_site


def catalog_record(problem_id='problem.example', rank=1):
    return {
        'problemId': problem_id,
        'canonicalTitle': 'An example question',
        'exactTarget': 'Determine whether every example has the stated property.',
        'primaryDomain': 'number_theory',
        'primaryDomainLabel': 'Number theory',
        'releaseRank': rank,
        'releaseStatus': 'open',
        'displayStatus': 'open_disputed_claim',
        'statusStatement': 'open',
        'statusQualification': 'The cited claim remains disputed.',
        'statusReviewedAt': '2026-09-22',
        'sources': [{'citation': 'Original statement', 'url': 'https://example.org/statement'}],
        'formalStatementSource': {'citation': 'Formal definition', 'url': 'https://example.org/formal'},
        'rankingEvidence': {'rankBand90': [1, 2]},
    }


def catalog():
    return {
        'records': [catalog_record(), catalog_record('problem.example.second', 2)],
        'recordCount': 2,
        'publicationId': 'example.v22',
        'releaseVersion': 22,
        'editionDate': '2026-09-22',
        'publicBoundary': 'Ranks are editorial importance, not proof evidence.',
    }


def mo_info():
    return {
        'title': 'Question &quot;one&quot;', 'score': 3, 'tags': ['example'],
        'creation_date': '2010-01-01', 'link': 'https://mathoverflow.net/questions/1',
    }


class OpenCatalogValidationTests(unittest.TestCase):
    def load(self, snapshot):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'catalog.json'
            path.write_text(json.dumps(snapshot), encoding='utf-8')
            with patch.object(build_site, 'OPEN_PROBLEMS_PATH', path):
                return build_site.load_open_problems_catalog()

    def test_shipped_catalog_has_500_unique_stable_ids_and_complete_ranks(self):
        snapshot = build_site.load_open_problems_catalog()
        self.assertEqual(snapshot['recordCount'], 500)
        self.assertEqual(snapshot['publicationId'], 'proofatlas.open-problem-ranking.top500.v22')
        self.assertEqual({r['releaseRank'] for r in snapshot['records']}, set(range(1, 501)))
        self.assertEqual(len({r['problemId'] for r in snapshot['records']}), 500)

    def test_empty_review_date_is_preserved_without_inventing_evidence(self):
        snapshot = catalog()
        snapshot['records'][0]['statusReviewedAt'] = ''
        self.assertEqual(self.load(snapshot), snapshot)

    def test_duplicate_ids_and_ranks_fail_instead_of_overwriting_records(self):
        for key, expected in [('problemId', 'Duplicate open problem ID'),
                              ('releaseRank', 'Duplicate open problem rank')]:
            snapshot = catalog()
            snapshot['records'][1][key] = snapshot['records'][0][key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, expected):
                self.load(snapshot)

    def test_invalid_ranks_ids_sources_and_record_counts_fail_explicitly(self):
        cases = [
            ('problemId', '../outside'), ('problemId', 'mo:1'), ('problemId', ''),
            ('releaseRank', True), ('releaseRank', '1'), ('releaseRank', 0),
            ('releaseRank', 3), ('sources', []), ('exactTarget', ''),
        ]
        for key, value in cases:
            snapshot = catalog()
            snapshot['records'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.load(snapshot)
        for count in [1, True, '2']:
            snapshot = catalog()
            snapshot['recordCount'] = count
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, 'recordCount'):
                self.load(snapshot)


class OpenProblemsBuildTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.patchers = [
            patch.object(build_site, 'BASE_DIR', self.root),
            patch.object(build_site, 'ATTACKS_DIR', self.root / 'attacks'),
            patch.object(build_site, 'REVIEWS_DIR', self.root / 'reviews'),
            patch.object(build_site, 'DATA_DIR', self.root / 'docs' / 'data'),
            patch.object(build_site, 'get_file_date', return_value='2026-09-24'),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        return target

    def statement_only(self):
        return '% COLLECTION_METADATA: ' + json.dumps({
            'schema_version': 1, 'kind': 'statement_only',
            'source_urls': ['https://example.org/formal'],
            'independently_reviewed': False,
        }) + '\nFULL SOLUTION\nCOMPLETION ESTIMATE: 100%'

    def test_stable_ids_load_versioned_attempts_without_overwriting_snapshot_status(self):
        self.write('attacks/open_problems/Example_Model/problem.example_v2.tex',
                   'UNRESOLVED\nCOMPLETION ESTIMATE: 25%')
        self.write('attacks/open_problems/Example_Model/problem.example.tex',
                   'FULL SOLUTION\nCOMPLETION ESTIMATE: 70%')
        self.write('reviews/open_problems/problem.example.json', '{"status": "incorrect"}')
        snapshot = catalog()
        result = build_site.build_open_problems_data({}, snapshot)['problem.example']
        self.assertEqual(result['status'], 'open_disputed_claim')
        self.assertEqual(result['release_status'], 'open')
        self.assertEqual(result['llm_status'], 'unresolved')
        self.assertEqual(result['completion'], 70)
        self.assertEqual([a['version'] for a in result['attacks']], [1, 2])
        self.assertEqual(result['attacks'][1]['file_path'],
                         'attacks/open_problems/Example_Model/problem.example_v2.tex')
        self.assertEqual(result['review']['status'], 'incorrect')
        self.assertEqual(result['catalog_record'], snapshot['records'][0])
        self.assertEqual(result['link'], 'https://example.org/formal')
        self.assertEqual(result['edition_date'], snapshot['editionDate'])
        self.assertEqual(result['status_reviewed_at'], '2026-09-22')

    def test_statement_only_records_and_no_attempts_have_no_claim_or_completion(self):
        self.write('attacks/open_problems/Statement_Model/problem.example.tex', self.statement_only())
        snapshot = catalog()
        snapshot['records'][0]['statusReviewedAt'] = ''
        result = build_site.build_open_problems_data({}, snapshot)
        for problem in result.values():
            self.assertEqual(problem['llm_status'], 'none')
            self.assertNotIn('completion', problem)
        self.assertIsNone(result['problem.example']['status_reviewed_at'])
        self.assertEqual(result['problem.example']['attacks'][0]['entry_kind'], 'statement_only')

    def test_ids_with_internal_periods_work_and_ranks_do_not_identify_attempts(self):
        self.write('attacks/open_problems/Model/problem.example.second.tex', 'UNRESOLVED')
        snapshot = catalog()
        snapshot['records'][0]['releaseRank'], snapshot['records'][1]['releaseRank'] = 2, 1
        result = build_site.build_open_problems_data({}, snapshot)
        self.assertEqual(list(result), ['problem.example.second', 'problem.example'])
        self.assertEqual(len(result['problem.example.second']['attacks']), 1)
        self.assertEqual(result['problem.example']['attacks'], [])

    def test_unknown_and_invalid_ranked_tex_filenames_fail_instead_of_disappearing(self):
        for filename in ['1.tex', 'problem.unknown.tex', 'problem.example_v0.tex',
                         'problem.example_title.tex']:
            path = self.write(f'attacks/open_problems/Model/{filename}', 'UNRESOLVED')
            with self.subTest(filename=filename), self.assertRaisesRegex(ValueError, 'Unknown ranked'):
                build_site.build_open_problems_data({}, catalog())
            path.unlink()

    def test_moved_mo_paths_and_legacy_review_remain_usable(self):
        self.write('attacks/open_problems/mo/Example_Model/1-question_v2.tex',
                   'UNRESOLVED\nCOMPLETION ESTIMATE: 12%')
        self.write('attacks/mo/Example_Model/1-obsolete.tex', 'FULL SOLUTION')
        self.write('reviews/mo/1.json', '{"status": "incorrect"}')
        with patch.object(build_site, 'load_mo_problems_list', return_value={'1': mo_info()}):
            mo = build_site.build_mo_data()
        self.assertEqual(len(mo['1']['attacks']), 1)
        self.assertEqual(mo['1']['attacks'][0]['file_path'],
                         'attacks/open_problems/mo/Example_Model/1-question_v2.tex')
        self.assertEqual(mo['1']['review']['status'], 'incorrect')
        result = build_site.build_open_problems_data(mo, catalog())
        self.assertEqual(set(result), {'problem.example', 'problem.example.second', 'mo:1'})
        self.assertEqual(result['mo:1']['mo_id'], '1')
        self.assertEqual(result['mo:1']['title'], 'Question "one"')
        self.assertIsNone(result['mo:1']['rank'])
        self.assertEqual(result['mo:1']['status'], 'unreviewed')
        self.assertEqual(result['mo:1']['llm_status'], 'unresolved')
        self.assertEqual(result['mo:1']['review'], mo['1']['review'])
        self.assertEqual(mo['1']['id'], '1')
        self.assertEqual(mo['1']['status'], 'unresolved')

    def test_new_mo_review_location_takes_precedence(self):
        self.write('reviews/mo/1.json', '{"status": "incorrect"}')
        self.write('reviews/open_problems/mo/1.json', '{"status": "incomplete"}')
        with patch.object(build_site, 'load_mo_problems_list', return_value={'1': mo_info()}):
            mo = build_site.build_mo_data()
        self.assertEqual(mo['1']['review']['status'], 'incomplete')

    def test_stats_and_js_exports_count_actual_attempts_across_both_collections(self):
        self.write('attacks/open_problems/Statement_Model/problem.example.tex', self.statement_only())
        self.write('attacks/open_problems/Actual_Model/problem.example.second.tex', 'UNRESOLVED')
        mo = {'1': {'id': '1', **mo_info(), 'attacks': [{
            'model': 'MO model', 'status': 'unresolved', 'completion': 30,
        }]}, '2': {'id': '2', **mo_info(), 'attacks': [{
            'model': 'Statement model', 'status': 'unresolved', 'completion': 0,
            'entry_kind': 'statement_only',
        }]}}
        snapshot = catalog()
        problems = build_site.build_open_problems_data(mo, snapshot)
        with patch.object(build_site, 'load_erdos_status', return_value={'problems': {}}):
            build_site.generate_js_data({}, mo, problems, snapshot)
        stats_js = (build_site.DATA_DIR / 'stats.js').read_text(encoding='utf-8')
        stats = json.loads(stats_js.removeprefix('var siteStats = ').removesuffix(';\n'))
        self.assertEqual(stats['open_problems'], {
            'total_problems': 4, 'ranked_total': 2, 'mo_total': 2,
            'with_attacks': 2, 'ranked_with_attacks': 1, 'models': ['Actual Model', 'MO model'],
        })
        self.assertEqual(stats['mo']['with_attacks'], 1)
        self.assertEqual(stats['mo']['models'], ['MO model'])
        js = (build_site.DATA_DIR / 'open_problems_data.js').read_text(encoding='utf-8')
        self.assertIn('window.OPEN_PROBLEMS_DATA = openProblems;', js)
        self.assertIn('window.OPEN_PROBLEMS_CATALOG = openProblemsCatalog;', js)
        exported = json.loads(js.removeprefix('var openProblems = ').split(';\n', 1)[0])
        self.assertEqual(exported, problems)
        self.assertTrue((build_site.DATA_DIR / 'mo_data.js').is_file())


class RepositoryMigrationTests(unittest.TestCase):
    def test_real_catalog_preserves_all_legacy_mo_links_and_namespaces(self):
        with patch.object(build_site, 'get_file_date', return_value='2026-09-24'):
            mo = build_site.build_mo_data()
            problems = build_site.build_open_problems_data(mo)
        self.assertEqual(len(mo), 100)
        self.assertEqual(len(problems), 600)
        self.assertEqual(sum(p['collection'] == 'ranked' for p in problems.values()), 500)
        self.assertEqual(sum(bool(p['attacks']) for p in mo.values()), 93)
        for qid, problem in mo.items():
            self.assertEqual(problem['attacks'], problems[f'mo:{qid}']['attacks'])
            self.assertIsNone(problems[f'mo:{qid}']['rank'])
            for attack in problem['attacks']:
                self.assertTrue(attack['file_path'].startswith('attacks/open_problems/mo/'))
                self.assertTrue((build_site.BASE_DIR / attack['file_path']).is_file())


if __name__ == '__main__':
    unittest.main()
