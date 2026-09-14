# Review an accepted manuscript and its production proofs

This package supports three review passes: import fidelity, proof fidelity, and
proofreading. Run one provider, then import its `review.json` into the copy-editing
workspace. Findings are advisory: an editor accepts exact replacements or edits the manuscript,
builds fresh proofs, and approves the exact publication bundle.

## Quick start

1. Extract the ZIP to a separate folder and open a terminal in `review-package`.
2. Install Python 3.10+ and sign in to your preferred coding CLI beforehand.
3. Run **one** of the commands below. No Python packages are required.
4. Choose **Import review findings** in the workspace and select the resulting
   `results/<run>/review.json`. Read coverage and limitations as well as findings.

```bash
# Codex: invokes codex exec with a read-only sandbox and a JSON output schema.
python3 review.py run --provider codex

# Claude Code: invokes claude -p with Read, Glob and Grep tools only.
python3 review.py run --provider claude

# agy: first obtain the exact available model name, then use Flash >= 3.8.
agy models
python3 review.py run --provider agy --model 'Gemini 3.8 Flash (High)'
```

Choose an explicit model for Codex or Claude with `--model MODEL` if desired;
otherwise your CLI's configured default applies. For agy, substitute the newest
available Flash model at 3.8 or above, using its exact name from `agy models`.
The agy adapter embeds text evidence in its prompt and requests no file tools.
It is **text-only**: images and binary documents must be reported unread. The
250,000-character prompt limit fails explicitly; choose a smaller package or
another provider when exceeded. Package hashes are checked after every local
agent run. Run exported packages in their own directory.

To run only proofreading (useful after editorial changes):

```bash
python3 review.py run --provider codex --passes proofreading
```

Pass any combination of `import-fidelity proof-fidelity proofreading` after
`--passes`; the default requests all three in one agent invocation. This does
not launch three separate agents or pay for three separate runs.

## OpenRouter: text and visual review

OpenRouter is an API route, not a local coding agent. The runner sends text,
manuscript figures (PNG/JPEG/WebP), and labeled PDF page images. During export,
`pdftoppm` renders available PDFs at 110 dpi; originals remain in the package.
Choose a model supporting **image inputs and structured outputs** with enough
context and image capacity. Read small table cells in the original at higher zoom
if the supplied page image is insufficient. Missing page rendering is reported
as a limitation; the runner never silently downgrades to text-only review.

Set `OPENROUTER_API_KEY` in your terminal environment using your normal secret
manager. Never paste it into a manuscript, result or version-controlled file.
Select a model supporting structured outputs and enough context for the package.

```bash
# Substitute a real provider/model ID. This reports request size; no API call.
python3 review.py run --provider openrouter --model 'provider/model'

# After checking the selected model's pricing and your data-sharing policy:
python3 review.py run --provider openrouter --model 'provider/model' --send
```

`--max-tokens 12000` is the default output limit, not a monetary cap. Request bytes
are not a token count or cost estimate. Check input/output prices and context
limits for your selected model before sending. Images are batched, eight per
request by default (`--batch-images 8`). All text evidence is repeated in each
batch to preserve comparison context. The dry run lists **every planned request**,
its image count and encoded byte size before anything is sent. Each batch must
fit the 32 MB limit; use fewer images or explicitly change `--max-request-mb`.
Batch results are validated, merged and deduplicated; raw responses and usage
are retained per batch. There are no silent retries, truncation or provider
switches. A failed batch prevents a successful combined result.

Local CLI execution also usually uses cloud models. Your CLI login, subscription,
API billing and provider data policies apply. Exporting a package makes no model
calls. Running a provider command initiates review using that provider.

## Evidence and interpretation

- `canonical/`: current manuscript, bibliography, metadata and manuscript assets.
- `baseline/`: frozen initial-import text, bibliography and metadata, when available.
  Read provenance: a reconstructed baseline is not a historical first import.
- `originals/`: supplied source documents and assets, including archives. Historical
  drafts may coexist; use source-selection notes and report unresolved ambiguity.
- `proof-source/`: the manuscript text used for the included production proofs.
- `proofs/`: exact available outputs and their build manifest.
- `text-extracts/`: searchable PDF/Word sidecars when extraction tools were available.
  Text extraction can lose equations, tables and reading order; inspect originals.
- `page-images/`: rendered PDF pages, labeled by original PDF filename and page.
- `packet.json`: package ID, revisions, file hashes, inventory and known limitations.
- `prompt.md`, `schema.json`: review instructions and required response structure.

Import fidelity compares originals with the initial-import baseline, then checks
whether discrepancies remain in canonical. Changes between baseline and canonical
may be intended copy-edits. Older manuscripts can lack a baseline; report that
limitation and avoid automatically restoring original wording. Proof fidelity compares
the included proof source with its outputs, even if newer editorial changes exist.
The package explicitly records stale or missing proofs. Proofreading examines the
current canonical manuscript, preserving voice, dialect and scientific meaning.

Every evidence file must be marked checked, partial or unread with useful coverage
notes. A zero-issue result with unread pages is **not** a clean bill of health.
Text quotations are checked against bundled evidence, allowing Unicode normalization,
whitespace and PDF line-end hyphenation.
PDF/image quotations require manual verification. The validator establishes
structure, package identity and quote presence, not the truth of a model's claim,
the completeness of its review or the correctness of a suggested replacement.

The workspace shows the latest imported report and flags it when manuscript,
configuration, originals or included proof bytes have changed. Earlier reports
remain on disk. Findings do not change publication validation or approval state.
**Accept correction** applies a literal replacement only when its quoted canonical
passage occurs exactly once and the review still matches the working revision.
Read both the passage and replacement first. Queries, layout fixes and ambiguous
quotations require manual editing. **Reject finding** records the decision without
changing the manuscript. Decisions persist alongside the imported report; accepted
edits advance its working revision. Other edits make the report stale. Build fresh
proofs after corrections and repeat review when needed. Browser spell checking is also available for manuscript prose; its language
and dictionary depend on your browser/OS settings and it may flag citation keys.

## Troubleshooting and manual use

If a model cannot read a file or hits context limits, it must report the limitation.
For long manuscripts, run a selected pass or ask an interactive agent to review
specific sections and declare partial coverage. OpenRouter batches images, but
does not split oversized text contexts. Selected passes reduce task scope, not
the evidence size. Never interpret an unread file as having passed review.
Agent failures and invalid JSON do not become successful reviews. Inspect the
run's `agent.log`, `stdout.txt` or `raw-response.txt`, fix the cause and rerun.

You can also ask an interactive agent to follow `prompt.md` and return JSON matching
`schema.json`. Validate its saved response before importing:

```bash
python3 review.py validate path/to/review.json
```

Codex, Claude, agy and OpenRouter completed live compatibility tests on
14 September 2026; see the repository’s `docs/review-evaluation.md` for the
fixtures, findings and limitations. These are smoke tests, not accuracy guarantees.
CLI flags were also checked against installed CLI help during implementation.
Provider interfaces can change; update the runner if your installed CLI rejects a
flag. References: [Codex CLI](https://developers.openai.com/codex/cli/reference/),
[Claude programmatic usage](https://code.claude.com/docs/en/headless),
[OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs).
