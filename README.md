# R2 Publishing Workflow

Copy-edit one canonical manuscript and generate the journal's HTML, PDF and
JATS proofs from that saved source. A local browser workspace brings editing,
production proofs and publication checks together. Approval freezes the
reviewed files and downloads a publication package, including an OJS import.

## Start copy-editing

Requires Python 3.10+, Quarto 1.9.38 and TinyTeX. Install once:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
quarto install tinytex
bash engine/scripts/install_tex.sh
```

Then open the workspace:

```bash
.venv/bin/python engine/scripts/workspace.py
```

Choose a manuscript, edit its text or metadata, and select **Build proofs**.
Edits autosave to the canonical source; the HTML/PDF pane displays production
output. **Approve & download** becomes available only for a complete, current
proof with no publication blockers. Approval checks the source and output
hashes and packages the exact files reviewed.

The workspace provides visual prose editing, protected citation/equation tokens,
authors and publication forms, and selection-anchored comments. Complex blocks
retain their Quarto source; YAML/BibTeX tabs remain available for direct editing. The separate `docs/preview/` tool remains an
approximate visual editor whose exports do not feed this pipeline. Use the
local workspace for production copy-editing.

## Test manuscripts

| Fixture | Coverage | Publication status |
|---|---|---|
| `R2.2025.001` | R2 inaugural editorial; many authors, affiliations and citations | Test only; several author emails are missing |
| `Hussey` | Accepted Word manuscript; narrative citations, DOIs, tables, equations and EMF+ figures | Test only; keywords and publication fields need completion |
| `Stylometry` | Accepted LaTeX project plus reference PDF; multiple versions, figures, equations, complex tables and footnotes | Test only; publication fields and corresponding author need assignment |

The fixtures are recorded in `engine/fixtures.json` and cannot be published
by the publication command. Originals are preserved under each `source/`
folder. The Stylometry fixture includes an extraction review with its source
provenance and unresolved editorial questions.

Full-frame EMF+ bitmaps, including the Hussey figures, are recovered directly.
Other Word metafiles need `emf2svg-conv`, `wmf2svg` (for WMF) and `rsvg-convert`.
PDF figures and review page images need Poppler. On macOS, install
`brew install libemf2svg librsvg poppler`; CI installs corresponding Linux packages.
Blank raster conversions are rejected.

## Import and build from the command line

```bash
# Initial import only; an existing article.qmd is always preserved.
.venv/bin/python engine/scripts/normalize.py manuscripts/ARTICLE_ID

# A reimport writes a separate proposal under .imports/ for comparison.
.venv/bin/python engine/scripts/normalize.py manuscripts/Stylometry \
  --source manuscripts/Stylometry/source/main.tex --reimport

# Draft proofs, with visible publication issues:
.venv/bin/python engine/scripts/build.py manuscripts/R2.2025.001
# HTML/JATS only, when LaTeX is unavailable (cannot be approved):
.venv/bin/python engine/scripts/build.py manuscripts/R2.2025.001 --no-pdf
# Strict release validation:
.venv/bin/python engine/scripts/build.py manuscripts/ARTICLE_ID --mode release
```

Each build gets a clean `_build/<id>/<run>/` directory containing:

- `outputs/`: proof files and linked JATS assets; complete releases also
  contain a JATS archive and the OJS import package.
- `manifest.json`: source hashes, output hashes, Quarto version and readiness.
- `issues.json` and `build.log`: publication issues and rendering diagnostics.
- `project/`: the editable source and rendering engine snapshot.

Builds never use stale galleys or overwrite edited source. Code execution is
disabled during Quarto rendering; submit precomputed manuscript content.

## Validation and approval

Checks cover required metadata, placeholders, article IDs, author emails and
resolved affiliations, ORCID checksums, publication dates, citation keys,
internal links and local figures. JATS validates against the bundled NLM
Journal Publishing 1.3 RELAX NG schema. OJS XML validates against the bundled
OJS 3.3.0-15 native schema. The OJS JATS galley is a ZIP containing XML and
its figures so dependent assets remain available. The OJS submission remains
unpublished until an editor publishes it in OJS.

Schema validity does not replace an import test in the target journal's
staging OJS instance, or visual proofreading of complex tables and equations.
Missing data is reported; author contact details are never fabricated.

PRs build affected manuscripts and upload proofs, sources and diagnostics.
Changes to shared code, themes or configuration select all fixtures. Publishing
is an explicit **Approve and publish reviewed proofs** workflow action: an
editor supplies the reviewed run and article ID. It verifies that the source
still matches and copies those proof files without rerendering. Merge alone
does not publish an article.

## Agent review and proofreading

In the workspace, choose **Download review package** to export the saved manuscript,
accepted originals, available proofs, PDF page images, validation results and a
portable runner. Extract the ZIP and follow its README to use Codex, `claude -p`,
agy or OpenRouter. All three review passes (import fidelity, proof fidelity and
proofreading) are included by default. Export makes no model calls.

```bash
.venv/bin/python engine/scripts/review_packet.py manuscripts/Stylometry
# In the extracted review-package directory:
python3 review.py run --provider codex
```

Use **Import review findings** to load the resulting `review.json`. The workspace
shows evidence, proposed corrections, coverage, limitations and revision status.
**Accept correction** applies a uniquely located exact replacement; **Reject finding**
records an editorial decision. Queries and layout changes use manual editing.
Build fresh proofs after editing. Findings do
not override publication validation or approve a manuscript.

See [the package README](engine/review/README.md) for all provider commands,
OpenRouter image support and cost controls, evidence semantics and troubleshooting.
OpenRouter includes labeled PNG/JPEG/WebP images and rendered PDF pages; choose a
vision model supporting structured outputs. PDF sidecars require Poppler's
`pdftotext` and `pdftoppm` on the workspace host. Missing extraction/rendering is
reported in the package. The extracted runner needs only Python 3.10+ and the
selected, authenticated CLI (or an OpenRouter API key).

## Uploading manuscripts and checking spelling

Choose **Upload manuscript**, enter a new article ID, and select editable Word,
Quarto, Markdown or LaTeX files. Include the accepted PDF as reference evidence;
PDF-only import is not supported. For projects with folders, figures and a
bibliography, upload a ZIP. Limits: 30 MB total, 100 uploaded files, 2,000 archive
entries and 100 MB expanded per archive. Remove hidden configuration files from
ZIPs. Use **Main source** for ambiguous projects, e.g. `paper/main.tex`.

Imports are staged and installed only on success. Existing manuscript IDs are
never overwritten. Uploaded originals stay under `source/`; complete the
publication fields before building proofs. Upload stays on the local workspace
host and does not publish, commit files or contact a model provider.

Browser spell checking is enabled for the Manuscript tab. Toggle it or choose UK/US
English under **Language and agent review**. Metadata and bibliography tabs do not
use spell checking. Underlining and suggestions require the relevant dictionary
to be enabled in your browser/OS; citation keys and technical words may be flagged.

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
# Full rendering/approval test; also requires pdftotext (Poppler):
R2_INTEGRATION=1 .venv/bin/pytest -q -k release_pipeline
```

See [the editing guide](docs/author-guide.md) for the workflow and
[implementation notes](docs/copyediting.md) for supported behavior and the deferred
OJS staging check. [Live review evaluation](docs/review-evaluation.md) documents
provider compatibility and conversion checks. Journal design
lives in `_extensions/r2/` and `themes/r2/`; `_quarto.yml` selects the theme.
Third-party XML schemas retain their own licence notices under `engine/schemas/`.
