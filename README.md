# Problem Hunting with LLMs

A collection of attempts by advanced Large Language Models (LLMs), mostly by GPT Pro 5.2, to solve open mathematical problems from the [Erdos Problems](https://www.erdosproblems.com/) collection and [MathOverflow](https://mathoverflow.net/).


**Live Site:** [mehmetmars7.github.io/Erdosproblems-llm-hunter](https://mehmetmars7.github.io/Erdosproblems-llm-hunter)

## Overview

This project documents and tracks LLM attempts to solve challenging open mathematical problems. The website automatically updates when new TeX files are added to the repository.

The Erdos index includes all **1,221 problems** in the saved collaborative database. The [expanded GPT_6_Astra_Ultra collection](attacks/erdos/GPT_6_Astra_Ultra/) covers all **642 unresolved database entries**, including 433 attributed imports and 50 statement-only records awaiting an attempt. Reused work retains its original model attribution and unverified completion claims. The directly checked official tags page reports 635 unresolved; the collection preserves the broader database scope. Only `.tex` writeups are published from this collection; working notes, manifests, and verification reports are kept outside the repository.

### Problem Sources

- **Erdos Problems**: Open problems posed by Paul Erdos, one of the most prolific mathematicians in history
  - Problem statements: [erdosproblems.com](https://www.erdosproblems.com/)
  - Latest status and formalization links: [Terry Tao's Erdos Problems Database](https://teorth.github.io/erdosproblems/)

- **MathOverflow**: Open problems from the professional mathematics Q&A site
  - Source: [mathoverflow.net](https://mathoverflow.net/)

### Featured LLM Models

Only the most advanced frontier LLMs with demonstrated mathematical reasoning capabilities are featured:

- GPT Pro (OpenAI)
- GPT 5.2 (OpenAI)
- GPT Codex 5.2 (OpenAI)
- Gemini Deep Think (Google)
- Opus 4.5 (Anthropic)

## Repository Structure

```
Erdosproblems-llm-hunter/
├── Problems/               # Local reference only (not published)
│   ├── Erdos_Problems/     # Problem statements link to erdosproblems.com
│   └── MO_problems/        # Problem statements link to MathOverflow
├── Attacks/
│   ├── Erdos_problems/     # LLM attempts organized by model
│   └── MO_problems/        # LLM attempts for MO problems
├── Lists/
│   ├── Erdos_Problems.csv  # Erdos problem metadata with URLs
│   └── MO_problems.csv     # MO problem metadata with URLs
├── data/                   # Generated JSON data (auto-generated)
├── .github/workflows/      # GitHub Actions for auto-deployment
├── index.html              # Main page
├── erdos.html              # Erdos problems listing
├── mo.html                 # MathOverflow problems listing
├── problem.html            # Individual problem view
├── about.html              # About page
├── build_site.py           # Build script
├── styles.css              # Styling
├── app.js                  # Frontend JavaScript
├── CONTRIBUTING.md         # Contribution guidelines
└── LICENSE                 # Apache 2.0 License
```

## How It Works

1. **Problem Statements**: Canonical statements remain at the external sources below. The expanded Erdos collection also includes 50 sourced statement-only records where no local attempt was available:
   - Erdos problems: [erdosproblems.com/X](https://www.erdosproblems.com/) for problem X
   - MO problems: Original MathOverflow question links
2. **LLM Attempts**: Stored as TeX files in `Attacks/` directory
3. **Build Process**: `build_site.py` processes attacks and generates JSON data
4. **Auto-Update**: GitHub Actions automatically rebuilds the site when:
   - Files in `Attacks/` are modified
   - Files in `Lists/` are modified
5. **Rendering**: MathJax renders LaTeX mathematics in the browser

## Local Development

```bash
# Refresh the status snapshot from Tao's GitHub repository (requires network)
python3 -m pip install -r requirements.txt
python3 scripts/sync_erdos_status.py

# Run the build script (uses the saved snapshot; works offline)
python3 build_site.py

# Serve locally (Python)
python3 -m http.server 8000 --directory docs
```

Then open `http://localhost:8000` in your browser.

Problem statuses are saved in `lists/erdos_status.json`, with the upstream commit
and the time they were checked. Every problem listed in this repository must have
a matching status; the build fails if any are missing. GitHub Actions refreshes
this snapshot before building the published site, using the upstream GitHub data
without scraping individual pages on erdosproblems.com.

The Erdos **LLM Claim** column follows an automatic database rule: `open`,
`falsifiable`, and `decidable` map to `unresolved`; every other informal status
maps to `solved`, including rows without attempts. Individual attempt claims are
unchanged, and their original aggregate is stored in `attempt_status`.
The generated `llm_status_source` field identifies the rule as `database_rule`.
The original database status remains visible on problem detail pages.
Problems marked
proved, disproved, solved, or independent receive **100% Completion**, following
the database's definition of resolved problems. For other problems, completion
remains the existing LLM estimate. Statement formalization and solution formalization
are reported separately; an `open (Lean)` problem remains open. Attempt contents
and community reviews retain their separate meanings. MathOverflow claim labels
continue to reflect the hosted attempts.

Run the synchronization and build checks with `python3 -m unittest discover -s tests`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on submitting new LLM attempts.

## Acknowledgments

- **Paata Ivanisvili** - For the idea and name "Problem Hunting with LLMs"
- **Terry Tao** - For the Erdos Problems database
- **Thomas Bloom** - For the erdosproblems.com website

## Disclaimer

**Important:** LLM output is not fully reliable. The attempts documented on this website represent exploratory work by frontier AI models and should not be considered verified mathematical proofs.

The Erdos **LLM Claim** label is assigned by the database rule above and does not
mean that an LLM has supplied a verified solution. The original **Problem Status**
comes from [Tao's collaborative database](https://teorth.github.io/erdosproblems/)
and does not validate the LLM attempts hosted here. Claims within individual
attempts still require mathematical verification.

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.
