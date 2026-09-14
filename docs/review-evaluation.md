# Review and conversion verification

All four review adapters completed live smoke tests on 14 September 2026.
Codex found all six planted defect types in one synthetic comparison. OpenRouter
identified a changed participant count using an image-only accepted original.
These results establish working integrations and useful checks on these inputs;
they do not establish error rates or make model review a publication guarantee.

## Reproduce the synthetic checks

Create a package without making a model call:

```bash
.venv/bin/python engine/scripts/evaluate_review.py
# For an accepted-image versus canonical-text comparison:
.venv/bin/python engine/scripts/evaluate_review.py --visual
```

The command prints a directory. Open a terminal there and run one of the commands
in its README. Use `--passes import-fidelity` for the visual comparison. The text
fixture plants a dropped consent paragraph, changed table mean, caption mismatch,
changed citation, proof participant count of 102 instead of 120, and “results is”.
The visual fixture puts 120 in the image and 102 in canonical text.

| Adapter | Live model / task | Observed result |
|---|---|---|
| Codex | gpt-6-astra; all three passes | All six planted types found; also flagged an added paragraph. [Result](evaluation/codex-synthetic.json) |
| Claude Code | Configured CLI default; proofreading | Grammar finding plus optional caption/citation queries. [Result](evaluation/claude-proofreading.json) |
| agy | Gemini 3.8 Flash (High); proofreading | Correct grammar finding from embedded text; text-only coverage. [Result](evaluation/agy-proofreading.json) |
| OpenRouter | openai/gpt-4.1-mini; visual import fidelity | Read 120 from the accepted image and flagged canonical 102. Cost returned: $0.0010148. [Result](evaluation/openrouter-visual.json) |

The OpenRouter visual result also incorrectly said the titles matched: the
accepted image says “Accepted study record”, while canonical says “Study record”.
The count finding is grounded; that summary sentence is not. The validator checks
schema, evidence quotations and hashes, not every claim in a model's prose.

An additional gpt-5-nano run accepted the image-bearing request but reported the
image unread; its text comparison cannot count as visual verification. That run
cost $0.0019917. Free-model probes returned a rejected request or malformed JSON;
the runner refused them as completed reviews. agy file-tool access was denied in
an earlier probe; its supported adapter now embeds text and requires no tools.
These outcomes are why coverage and failure states remain visible.

## Accepted manuscript checks

The Hussey Word manuscript and Stylometry accepted LaTeX archive/PDF are retained
in the repository, with source selection recorded. Both have reconstructed import
baselines labeled as such. Codex reviewed source/proof text, tables, equations,
figures and PDF page images; human inspection checked the resulting layout fixes.
This is targeted conversion verification, not scientific peer review.

Hussey checks cover all seven display equations, its comparison table and four
figures. Narrative author suppression and original reference keys are preserved;
BibLaTeX retains DOIs and corporate authors. Explicit captions become native
figures, without a second automatic description caption. The three EMF+ images
are recovered from their embedded bitmap pixels; blank conversions fail. Current
PDF figures and the table were visually inspected. JATS author emails are restored
from the explicit source field rather than a neighboring boolean. Publication
fields and keywords remain incomplete and prevent approval.

Stylometry checks cover native figures and caption citations in all output
formats, exact accepted PDF figure assets, section references, equations and
wrapping of the five-column translation table. The latter was visually checked
across its page break. DOI/date/publication assignment and corresponding-author
selection remain editorial inputs. The source's learning-rate notation
`3\text{e--}5` remains an author query; it has not been silently reinterpreted.

## Browser and automated verification

Chrome checks used a separate uploaded synthetic manuscript. Upload, metadata
form saves, visual prose saves including Enter, review import, exact correction
acceptance, finding rejection and selection comments were exercised. The existing
editorial's local source edit was kept separate from test changes.

The automated suite includes the complete HTML/PDF/JATS/OJS build and approval
cycle, immutable output checks, external-edit conflicts, accepted/rejected review
decisions, comment anchors, baseline preservation, multimodal payload contents,
PDF quotation normalization, batch merging, metadata preservation, EMF+ extraction,
blank-image rejection and native LaTeX figures. Run:

```bash
R2_INTEGRATION=1 .venv/bin/pytest -q
```

The journal's live OJS staging import is deferred because its URL and test
credentials are unavailable. Offline schema and package checks are automated.
