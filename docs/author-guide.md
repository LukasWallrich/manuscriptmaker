# Copy-editing guide

Use the local workspace to edit a manuscript once and inspect the production
proofs generated from it. Start it using the setup commands in the repository
README. The static browser preview is useful for a quick look; edits made
there do not update the production manuscript.

## Prepare the accepted manuscript

Copy `manuscripts/_TEMPLATE/` into a new article folder. Preserve the accepted
file in `source/`. If importing Word or LaTeX, delete the template's
`article.qmd`, then run `normalize.py` once. Word citations need live reference
manager fields; otherwise supply a bibliography. For a LaTeX project with
several main files, explicitly select the accepted version with `--source`.

Check the imported content against the original, particularly tables,
figures, equations and references. Complete article details and publication
fields from verified records. The folder name must match `r2.article-id`.
An existing canonical article is never replaced during a build. Use
`--reimport` to create a separate import proposal if the original changes.

## Edit and review

1. Open the workspace and choose the article.
2. Edit manuscript text, article details, publication fields or references.
   Changes autosave after a pause in typing. Keep `[@citation-key]` citations,
   figure paths and identifiers intact.
3. Select **Build proofs**. Review the actual HTML and PDF and resolve the
   listed publication issues. Rebuild after edits; the workspace marks old
   proofs as out of date.
4. When the proof is complete and current, select **Approve & download**.
   The package contains those exact files, without another rendering pass.

Autosave refuses to overwrite files changed by another editor or application.
Reload the page to read external edits before continuing. Keep the workspace
local: it binds to localhost and is not a multi-user hosted service.

## Handoff and publication

The package contains HTML, PDF, JATS XML with its figures, a JATS ZIP and an
OJS native import file. OJS receives PDF, HTML and a JATS archive galley in an unpublished production submission.
Before the first production import, verify journal-specific section, author
user-group, uploader and genre settings in a staging OJS instance.

For GitHub Pages publication, merge the reviewed source and choose the
**Approve and publish reviewed proofs** workflow on `main`, supplying the
article ID and reviewed proof-build run ID. It refuses changed sources,
incomplete bundles and test fixtures. Merge itself does not publish.

## Common issues

| Issue | Action |
|---|---|
| TODO or missing metadata | Replace it with verified publication details. |
| Unresolved citation | Correct its key or add the reference to the bibliography. |
| Missing or unsupported figure | Supply the file or install the metafile converters. |
| Missing author email | Obtain the author's email for the OJS export. |
| Failed PDF/JATS | Read the retained build log; correct the reported source or template issue. |
| Proof out of date | Build and review a new proof before approval. |
