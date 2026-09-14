# Review an accepted manuscript and its production proofs

This package supports three review passes: import fidelity, proof fidelity, and
proofreading. Run one provider, then import its `review.json` into the copy-editing
workspace. Findings are advisory: an editor makes changes in the manuscript,
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
The runner retains agy's sandbox and grants access to this extracted directory.
It checks package hashes after execution because agy's sandbox still permits
some file writes. Do not run agents against your live manuscript repository.

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
limits for your selected model before sending. The runner makes one request;
it does not silently retry failures, truncate evidence or switch providers.
The dry run reports image count and encoded request size. Requests above 32 MB
are refused; increase `--max-request-mb` explicitly only after checking provider
limits. Usage returned by OpenRouter is saved alongside the result.

Local CLI execution also usually uses cloud models. Your CLI login, subscription,
API billing and provider data policies apply. Exporting a package makes no model
calls. Running a provider command initiates review using that provider.

## Evidence and interpretation

- `canonical/`: current manuscript, bibliography, metadata and manuscript assets.
- `originals/`: supplied source documents and assets, including archives. Historical
  drafts may coexist; use source-selection notes and report unresolved ambiguity.
- `proof-source/`: the manuscript text used for the included production proofs.
- `proofs/`: exact available outputs and their build manifest.
- `text-extracts/`: searchable PDF/Word sidecars when extraction tools were available.
  Text extraction can lose equations, tables and reading order; inspect originals.
- `page-images/`: rendered PDF pages, labeled by original PDF filename and page.
- `packet.json`: package ID, revisions, file hashes, inventory and known limitations.
- `prompt.md`, `schema.json`: review instructions and required response structure.

Import fidelity compares originals with the current canonical manuscript. There
is currently no frozen initial-import baseline, so differences might be intentional
copy-edits. Do not automatically restore original wording. Proof fidelity compares
the included proof source with its outputs, even if newer editorial changes exist.
The package explicitly records stale or missing proofs. Proofreading examines the
current canonical manuscript, preserving voice, dialect and scientific meaning.

Every evidence file must be marked checked, partial or unread with useful coverage
notes. A zero-issue result with unread pages is **not** a clean bill of health.
Text quotations are checked against bundled evidence (ignoring whitespace).
PDF/image quotations require manual verification. The validator establishes
structure, package identity and quote presence, not the truth of a model's claim,
the completeness of its review or the correctness of a suggested replacement.

The workspace shows the latest imported report and flags it when manuscript,
configuration, originals or included proof bytes have changed. Earlier reports
remain on disk. Findings do not change publication validation or approval state.
Apply suggestions manually, build proofs again, and request another review when
needed. Browser spell checking is also available for manuscript prose; its language
and dictionary depend on your browser/OS settings and it may flag citation keys.

## Troubleshooting and manual use

If a model cannot read a file or hits context limits, it must report the limitation.
For long manuscripts, run a selected pass or ask an interactive agent to review
specific sections and declare partial coverage. No automated chunking is implemented.
Agent failures and invalid JSON do not become successful reviews. Inspect the
run's `agent.log`, `stdout.txt` or `raw-response.txt`, fix the cause and rerun.

You can also ask an interactive agent to follow `prompt.md` and return JSON matching
`schema.json`. Validate its saved response before importing:

```bash
python3 review.py validate path/to/review.json
```

CLI flags were checked against installed CLI help during implementation.
Provider interfaces can change; update the runner if your installed CLI rejects a
flag. References: [Codex CLI](https://developers.openai.com/codex/cli/reference/),
[Claude programmatic usage](https://code.claude.com/docs/en/headless),
[OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs).
