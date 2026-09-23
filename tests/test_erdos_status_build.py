"""Ensure database results do not become claims about the hosted LLM attempts."""

import copy
import unittest

from build_site import apply_erdos_status


def snapshot(state, formal='unformalized'):
    label = state if formal == 'unformalized' else f'{state} ({formal})'
    return {
        'database_url': 'https://teorth.github.io/erdosproblems/',
        'problems': {'1': {
            'status': label,
            'informal_status': state,
            'status_updated': '2026-09-22',
            'statement_formalization': {'state': 'yes', 'url': None},
            'solution_formalization': {'state': formal, 'url': None},
        }},
    }


class ErdosStatusBuildTests(unittest.TestCase):
    def setUp(self):
        self.problem = {
            'number': '1',
            'status': 'unresolved',
            'completion': 35,
            'attacks': [{'status': 'unresolved', 'completion': 35, 'raw': 'UNRESOLVED'}],
            'review': {'status': 'incorrect'},
        }

    def test_all_resolved_categories_override_completion_without_changing_attempts(self):
        for state in ['proved', 'disproved', 'solved', 'independent']:
            with self.subTest(state=state):
                original = copy.deepcopy(self.problem)
                result = apply_erdos_status({'1': copy.deepcopy(original)}, snapshot(state))['1']
                self.assertEqual(result['status'], state)
                self.assertTrue(result['is_solved'])
                self.assertEqual(result['completion'], 100)
                self.assertEqual(result['completion_source'], 'database')
                self.assertEqual(result['llm_completion'], 35)
                self.assertEqual(result['llm_status'], 'unresolved')
                self.assertEqual(result['attacks'], original['attacks'])
                self.assertEqual(result['review'], original['review'])

    def test_unresolved_categories_keep_llm_estimates(self):
        for state in ['open', 'falsifiable', 'verifiable', 'decidable', 'not provable', 'not disprovable']:
            with self.subTest(state=state):
                result = apply_erdos_status({'1': copy.deepcopy(self.problem)}, snapshot(state))['1']
                self.assertFalse(result['is_solved'])
                self.assertEqual(result['completion'], 35)
                self.assertEqual(result['completion_source'], 'llm')

    def test_formalization_alone_does_not_resolve_open_problem(self):
        result = apply_erdos_status({'1': copy.deepcopy(self.problem)}, snapshot('open', 'Lean'))['1']
        self.assertEqual(result['status'], 'open (Lean)')
        self.assertFalse(result['is_solved'])
        self.assertEqual(result['completion'], 35)

    def test_solved_problem_without_attempts_still_gets_full_completion(self):
        result = apply_erdos_status({'1': {'status': 'solved', 'attacks': []}}, snapshot('proved'))['1']
        self.assertEqual(result['llm_status'], 'none')
        self.assertEqual(result['completion'], 100)
        self.assertNotIn('llm_completion', result)

    def test_open_problem_without_estimate_retains_blank_completion(self):
        result = apply_erdos_status({'1': {'status': 'solved', 'attacks': []}}, snapshot('open'))['1']
        self.assertNotIn('completion', result)
        self.assertNotIn('completion_source', result)
        self.assertFalse(result['is_solved'])

    def test_missing_status_fails_before_modifying_any_problem(self):
        problems = {'1': copy.deepcopy(self.problem), '2': copy.deepcopy(self.problem)}
        before = copy.deepcopy(problems)
        with self.assertRaisesRegex(ValueError, 'Missing upstream status.*2'):
            apply_erdos_status(problems, snapshot('proved'))
        self.assertEqual(problems, before)


if __name__ == '__main__':
    unittest.main()
