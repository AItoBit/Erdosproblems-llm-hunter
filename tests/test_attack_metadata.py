"""Keep quoted, rejected solution claims out of the site's attempt metadata."""

import unittest

from build_site import extract_completion, parse_attack


class AttackMetadataTests(unittest.TestCase):
    def test_correction_review_is_unresolved_without_a_completion_claim(self):
        content = r'''
\section{Review and correction of the claimed ``disproof''}
\textbf{``FULL SOLUTION --- COUNTEREXAMPLE / DISPROOF''}
\textbf{``COMPLETION: 100\%''}
are incorrect for the original open problem.
\item The completion estimate ``100\%'' is false for the original problem.
\item The original strengthening remains open in general.
'''
        attack = parse_attack(content, 'gpt pro 5.4')
        self.assertEqual(attack['status'], 'unresolved')
        self.assertNotIn('completion', attack)
        self.assertEqual(attack['raw'], content)

    def test_rejected_value_does_not_hide_a_corrected_estimate(self):
        for content in [
            r"The completion estimate ``100\%'' is false; the corrected estimate is 35\%.",
            r"COMPLETION ESTIMATE: 35\%, not 100\%.",
            r"COMPLETION ESTIMATE: 35\%; the earlier 100\% is incorrect.",
        ]:
            with self.subTest(content=content):
                self.assertEqual(extract_completion(content), 35)

    def test_ordinary_percentages_and_fractions_are_preserved(self):
        for content, expected in [
            (r'COMPLETION ESTIMATE: 0\%', 0),
            (r'COMPLETION ESTIMATE: 35\%', 35),
            (r'COMPLETION ESTIMATE: 100\%', 100),
            ('COMPLETION ESTIMATE\n0.25', 25),
        ]:
            with self.subTest(content=content):
                self.assertEqual(extract_completion(content), expected)

    def test_completion_rate_estimate_heading_used_by_astra_attempts(self):
        content = r'\textbf{Completion rate estimate: 40\%.}'
        self.assertEqual(extract_completion(content), 40)

    def test_rejected_decimal_is_not_reinterpreted_as_a_fraction(self):
        for content in [
            r'COMPLETION ESTIMATE: 0.50\% is false.',
            'COMPLETION ESTIMATE: 0.50 is incorrect.',
        ]:
            with self.subTest(content=content):
                self.assertIsNone(extract_completion(content))

    def test_latest_valid_block_wins_and_confidence_is_ignored(self):
        content = '\n\n\n\n'.join([
            r'COMPLETION ESTIMATE: 20\%',
            r'COMPLETION ESTIMATE: 45\%',
            r"The completion estimate ``100\%'' is false.",
            r'COMPLETION ESTIMATE: confidence 95\%',
        ])
        self.assertEqual(extract_completion(content), 45)

    def test_status_keeps_explicit_solved_and_unresolved_cases(self):
        for content, expected in [
            ('FULL SOLUTION', 'solved'),
            ('UNRESOLVED', 'unresolved'),
            ('The conjecture remains\nopen.', 'unresolved'),
        ]:
            with self.subTest(content=content):
                self.assertEqual(parse_attack(content, 'test')['status'], expected)


if __name__ == '__main__':
    unittest.main()
