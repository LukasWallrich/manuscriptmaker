# Copy-editing workspace

Copy-edit a manuscript in one workspace, inspect the production HTML/PDF, and
approve the exact HTML/PDF/JATS/OJS bundle. Importing, reviewing and correcting
may take several passes; publication requires one final approval of current,
validated outputs. No model is permitted to approve publication.

## Editor workflow

1. Upload an editable Word, Quarto, Markdown or LaTeX manuscript. Supply the
   accepted PDF as reference evidence; use a ZIP for projects with folders.
2. Complete **Edit article details**, including authors, affiliations and
   publication identifiers. Unknown fields are retained. The original source
   and the initial import remain available for comparison.
3. Edit prose visually, including bold and italic formatting. Citation and
   inline equation tokens are protected. Tables, figures, code and other
   structured content expose their source; use the source tabs for full control.
   Untouched blocks retain their exact source. Browser spelling suggestions
   depend on installed UK/US dictionaries.
4. Select a passage and add an editorial comment. Comments persist locally,
   survive unrelated edits and flag changed anchors for relocation. Resolve
   them when addressed. External source changes trigger a save conflict.
5. Build proofs and inspect the actual production output. Download a review
   package for optional import-fidelity, proof-fidelity and proofreading passes.
   Follow its README to run a coding agent or OpenRouter; import `review.json`.
6. Read coverage and limitations. Accept exact, uniquely located corrections or
   reject findings; both decisions persist. Make queries and layout changes
   manually. Rebuild after changes, then **Approve & download** when all
   required publication fields and deterministic checks pass.

Source, configuration and output hashes prevent stale approval. A new build
uses an isolated source snapshot and does not reimport or overwrite edited
source. Reimports produce separate proposals under `.imports/`.

## Review evidence and local state

New imports freeze text, bibliography and available metadata under
`source/initial-import/`. The two accepted fixtures have explicitly labeled
reconstructed baselines. Packages include that baseline, current canonical
source, accepted originals, exact proof-source snapshots, rendered files,
PDF page images, checks and file hashes. See the
[portable runner README](../engine/review/README.md) for provider commands.

Reviews and decisions live under `_build/llm-review/<article>/<packet>/`;
comments live under `_build/editorial/<article>/`. They persist across workspace
restarts but are local, gitignored state. Preserve `_build/` when backing up an
active editorial session. This is a local editor with conflict detection, not a
multi-user collaboration server.

## Supported input boundaries

Word reference-manager citations export to BibLaTeX with DOI and corporate-author
information. Explicit Figure captions become native figures. The EMF+ adapter
recovers a single full-frame bitmap; transformed or vector drawings use the
external converter, and blank results fail explicitly.

LaTeX imports preserve native figures/caption citations, section references and
tables. PDF figures are rendered from the referenced PDF, not an alternative
PNG that may be a different version. Text-heavy tables receive wrapping column
widths in PDF. Package loading is omitted during conversion; arbitrary custom
macros and tracked Word changes still require inspection of the import against
the original. No claim of lossless conversion for arbitrary source projects is
made. Code execution is disabled in production rendering.

OpenRouter sends labeled images and batches them, with all text repeated as
comparison context. It refuses requests over the configured byte limit and
never truncates evidence silently. Text must fit the selected model's context.
The agy adapter is text-only and explicitly limits prompt size. Coverage remains
part of every review result; schema validity cannot establish review accuracy.

## Verification and publication boundary

[Evaluation evidence](review-evaluation.md) covers live provider smoke tests,
planted defects, browser workflows and the two accepted manuscripts. Automated
tests cover imports, assets, metadata, comments, decisions, quote validation,
staleness, XML schemas, concurrent saves and the complete release pipeline.

**The OJS staging import test is deferred at the user's request.** No staging URL
or credentials are available. Offline validation targets OJS 3.3.0-15; an actual
journal import must still check configured user groups, genres and uploader
accounts. Compatibility with OJS 3.4/3.5 has not been established.

All bundled manuscripts are registered fixtures and excluded from publication.
Missing publication identifiers, corresponding-author choices and manuscript
queries are editorial inputs, not values to invent to bypass validation.
