# GPT Pro 5.4 source import

Imported 165 TeX files from `_Local/Erdos_problems/GPT_Pro_5.4` as 264
attempts covering 174 problems. The four existing attempts (`10.tex`,
`43.tex`, `653.tex`, and `654.tex`) were preserved unchanged.

[`import_manifest.json`](import_manifest.json) records every source filename,
source SHA-256, original line ranges, target filename, target SHA-256, and
explicit round number where available. Line ranges are 1-based and inclusive.
Concatenating those ranges, preceded by `archive_note` when present,
reproduces the target file exactly. Every source line is retained in at least
one target file. The PNG screenshot was not an attempt and was not imported.

The version suffixes enumerate archived attempts, not their internal round
numbers. Explicit round headings and continuation dependencies determine the
order where possible; distinct branches and duplicate downloads are retained.
Existing versions are never replaced.

Mapping details:

- `289_290_291_solutions.tex` contains attempts for **288, 289, and 291**.
  Its section headings and problem statements determine the target numbers;
  it contains no attempt for 290.
- Multi-problem files are split at their problem headings, with shared
  introductory material and references retained in each applicable extract.
- The combined report for 789, 873, and 875 has shared introductory and
  concluding material. Each extract has an archive note explaining that its
  source's 68% estimate applies to the joint report.
- Embedded rounds in `23_solutions.tex` and both `36_solutions` files are
  separate versions. The two copies of rounds 2 and 3 for problem 36 differ
  in proof-ending notation, and both are preserved.
- Problems 9, 12, 15, 30, 50, and 65 require ordering by their contents rather
  than their download filenames. Problem 65's correction is placed after
  round 12 and before round 13.
- The problem 884 sources repeat a round-2 heading despite continuing earlier
  work. Their content dependencies place `884_solutions (1).tex` after
  `884_solutions(4).tex` and before `884_solutions(5).tex`.

These are archived model attempts; this import checks identity, ordering,
content preservation, and site integration, not mathematical correctness.
