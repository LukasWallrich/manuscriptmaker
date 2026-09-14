# Copy-editing implementation

The working path is canonical source → isolated production proofs → approval
of the exact bundle. Source and output hashes prevent stale approval; initial
imports and reimport proposals are separate from proof generation. A local
workspace supplies autosave, conflict detection, proof viewing and download.

## Remaining work before broad editorial deployment

- Provide structured forms for authors, affiliations and publication metadata,
  and a rich-text editor that preserves citation keys, equations and table IDs.
  The current workspace edits Markdown/YAML/BibTeX directly.
- Add selection-anchored comments and suggested edits for collaborative review.
  The local workspace currently supports one editor and detects external changes.
- Test OJS import against the journal's staging instance. Offline validation
  covers OJS 3.3.0-15; it does not check configured user groups, genres or uploader
  accounts, or promise compatibility with OJS 3.4/3.5.
- Compare every complex table/equation in the Word and Stylometry fixtures
  against the accepted originals. Schema validity and successful rendering
  alone do not establish conversion fidelity or acceptable layout.
- Extend import coverage for arbitrary multi-file LaTeX projects, custom macros,
  tracked Word changes and unusual bibliography formats. Import skips LaTeX
  package loading and preserves unknown content for review; unsupported cases
  need an explicit adapter rather than silent deletion.
- Evaluate the portable agent reviews against deliberately corrupted fixtures:
  dropped paragraphs, swapped table cells, citation loss and caption mismatches.
  The runner validates output structure and quoted text but model error rates
  have not yet been benchmarked. Provider commands are tested with fixtures/mocks;
  live provider compatibility depends on installed CLI/model versions.
- Add a frozen initial-import baseline and recorded editorial decisions so import
  fidelity findings can distinguish conversion errors from intended copy-edits.
- Add section/page batching for manuscripts exceeding model context/image limits.
  The current runner requests selected passes in one invocation and reports limits.

## Fixtures

The editorial is a real canonical manuscript. Hussey supplies Word conversion
coverage with intentionally incomplete metadata. Stylometry supplies an
accepted LaTeX project and its PDF as provided by the user on 14 September
2026. Its source archive contains historical versions and a stale bibliography;
`main.tex` and its declared `references.bib` are the selected inputs.

The fixture registry is the publication exclusion list. Add new accepted
manuscripts there when using them for tests. Record source/version, original
PDF when available, expected unresolved fields and the features being tested.
Do not fill unknown publication fields merely to make a fixture pass approval.

## Verification

Unit tests cover non-destructive import, source ambiguity, placeholders,
metadata, references/assets, XML schemas, immutable approval, shared-code
change detection and concurrent saves. The optional full integration test
builds an edited synthetic manuscript in all formats, checks its text and
metadata, and confirms that approved downloads contain the reviewed bytes.
