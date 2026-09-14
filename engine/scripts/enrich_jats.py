"""Inject R2-specific front matter into Pandoc-generated JATS.

Pandoc's `jats_publishing` writer emits a solid <article-meta> (title,
contributors, abstract, keywords, references) but does not expose the
journal's DOI, article categories, lay summary, funding, or license. This
step adds them in place so the JATS galley is a faithful archival record.

Idempotent: re-running on an already-enriched file is a no-op for each
element (it checks before inserting).

Usage:
    python engine/scripts/enrich_jats.py manuscripts/R2.2025.001/article.xml manuscripts/R2.2025.001
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.dom import minidom

from lxml import etree

import r2meta

JATS_NS = None  # Pandoc JATS is in the null namespace


def _text_el(doc, tag, text, **attrs):
    el = doc.createElement(tag)
    for k, v in attrs.items():
        el.setAttribute(k, str(v))
    if text is not None:
        el.appendChild(doc.createTextNode(str(text)))
    return el


def _first(parent, tag):
    nodes = parent.getElementsByTagName(tag)
    return nodes[0] if nodes else None


def enrich(xml_path: Path, manuscript_dir: Path, *, draft=False, issues_path=None) -> None:
    meta = r2meta.load(manuscript_dir)
    r2 = meta.get("r2", {})
    doc = minidom.parse(str(xml_path))

    article = _first(doc, "article")
    if article is None:
        raise SystemExit("No <article> element found — not a JATS file?")

    # article-type attribute on <article> (override Pandoc's default "other")
    if r2.get("article-type"):
        article.setAttribute("article-type", str(r2["article-type"]).lower())

    front = _first(doc, "front")
    article_meta = _first(doc, "article-meta")
    journal_meta = _first(doc, "journal-meta")

    if front is None or article_meta is None:
        raise ValueError("JATS output must contain front/article-meta")
    if journal_meta is None:
        journal_meta = doc.createElement("journal-meta")
        front.insertBefore(journal_meta, article_meta)
    article.setAttribute("dtd-version", "1.3")
    article.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink")
    if doc.doctype:
        doc.removeChild(doc.doctype)

    # --- journal-meta: journal title, publisher, issn -----------------
    if journal_meta is not None:
        if r2.get("journal") and not journal_meta.getElementsByTagName("journal-title"):
            grp = doc.createElement("journal-title-group")
            grp.appendChild(_text_el(doc, "journal-title", r2["journal"]))
            journal_meta.insertBefore(grp, journal_meta.firstChild)
        if r2.get("issn") and not journal_meta.getElementsByTagName("issn"):
            journal_meta.appendChild(_text_el(doc, "issn", r2["issn"]))
        if r2.get("publisher") and not journal_meta.getElementsByTagName("publisher"):
            pub = doc.createElement("publisher")
            pub.appendChild(_text_el(doc, "publisher-name", r2["publisher"]))
            journal_meta.appendChild(pub)

    if article_meta is None:
        doc.writexml(open(xml_path, "w", encoding="utf-8"))
        return

    if not journal_meta.getElementsByTagName("journal-id"):
        journal_meta.insertBefore(_text_el(doc, "journal-id", meta.get("ojs", {}).get("journal-path", "journal"),
                                           **{"journal-id-type": "publisher-id"}), journal_meta.firstChild)

    # Restore explicit source email values; an empty Quarto email can otherwise
    # inherit a boolean from its author metadata context in the JATS template.
    contributors = [n for n in article_meta.getElementsByTagName("contrib")
                    if n.getAttribute("contrib-type") == "author"]
    authors = meta.get("_authors", [])
    if len(contributors) != len(authors):
        raise ValueError("JATS contributor count does not match manuscript authors")
    for contributor, author in zip(contributors, authors):
        for email in list(contributor.getElementsByTagName("email")):
            email.parentNode.removeChild(email)
        if author.get("email"):
            contributor.appendChild(_text_el(doc, "email", author["email"]))
        if author.get("corresponding"):
            contributor.setAttribute("corresp", "yes")

    # --- DOI as <article-id pub-id-type="doi"> ------------------------
    if r2.get("doi"):
        has_doi = any(n.getAttribute("pub-id-type") == "doi"
                      for n in article_meta.getElementsByTagName("article-id"))
        if not has_doi:
            article_meta.insertBefore(
                _text_el(doc, "article-id", r2["doi"], **{"pub-id-type": "doi"}),
                article_meta.firstChild)

    # --- article categories: article-type + discipline ----------------
    if not article_meta.getElementsByTagName("article-categories"):
        cats = doc.createElement("article-categories")
        for kind, val in (("heading", r2.get("article-type")),
                          ("subject", r2.get("discipline"))):
            if val:
                grp = doc.createElement("subj-group")
                grp.setAttribute("subj-group-type", kind)
                grp.appendChild(_text_el(doc, "subject", val))
                cats.appendChild(grp)
        if cats.hasChildNodes():
            # article-categories must precede title-group
            tg = _first(article_meta, "title-group")
            article_meta.insertBefore(cats, tg if tg else article_meta.firstChild)

    # --- volume / elocation -------------------------------------------
    if r2.get("volume") and not article_meta.getElementsByTagName("volume"):
        article_meta.appendChild(_text_el(doc, "volume", r2["volume"]))
    if r2.get("article-id") and not article_meta.getElementsByTagName("elocation-id"):
        article_meta.appendChild(_text_el(doc, "elocation-id", r2["article-id"]))

    # --- permissions / license ----------------------------------------
    if r2.get("license") and not article_meta.getElementsByTagName("permissions"):
        perm = doc.createElement("permissions")
        lic = doc.createElement("license")
        if r2.get("license-url"):
            lic.setAttribute("xlink:href", r2["license-url"])
        lic.appendChild(_text_el(doc, "license-p",
                                 f"Published under the {r2['license']} license."))
        perm.appendChild(lic)
        article_meta.appendChild(perm)

    # --- lay summary as a second <abstract abstract-type="..."> -------
    if r2.get("lay-summary"):
        already = any(a.getAttribute("abstract-type") == "summary"
                      for a in article_meta.getElementsByTagName("abstract"))
        if not already:
            lay = doc.createElement("abstract")
            lay.setAttribute("abstract-type", "summary")
            lay.appendChild(_text_el(doc, "title", "Lay Summary"))
            lay.appendChild(_text_el(doc, "p", str(r2["lay-summary"]).strip()))
            kw = _first(article_meta, "kwd-group")
            article_meta.insertBefore(lay, kw) if kw else article_meta.appendChild(lay)

    # --- custom-meta-group: badges + recommended citation -------------
    for existing in list(article_meta.getElementsByTagName("custom-meta")):
        name = _first(existing, "meta-name")
        if name is not None and name.firstChild and name.firstChild.nodeValue in {"open-science-badges", "recommended-citation"}:
            existing.parentNode.removeChild(existing)
    cmg = _first(article_meta, "custom-meta-group") or doc.createElement("custom-meta-group")

    def _cmeta(name, value):
        cm = doc.createElement("custom-meta")
        cm.appendChild(_text_el(doc, "meta-name", name))
        cm.appendChild(_text_el(doc, "meta-value", value))
        cmg.appendChild(cm)

    badges = r2.get("badges", {}) or {}
    earned = [k for k, v in badges.items() if v]
    if earned:
        _cmeta("open-science-badges", ", ".join(earned))
    if r2.get("recommended-citation"):
        _cmeta("recommended-citation", str(r2["recommended-citation"]).strip())
    if cmg.hasChildNodes():
        article_meta.appendChild(cmg)

    for empty_tag in ("author-notes", "custom-meta-group", "history"):
        for node in list(article_meta.getElementsByTagName(empty_tag)):
            if not any(n.nodeType == n.ELEMENT_NODE for n in node.childNodes):
                node.parentNode.removeChild(node)
    # Scalar Quarto abstracts can arrive as raw text; Publishing requires
    # paragraph/block content while preserving any inline emphasis/citations.
    for abstract in article_meta.getElementsByTagName("abstract"):
        blocks = {"title", "p", "sec", "list", "def-list", "fig", "table-wrap", "boxed-text"}
        group = []
        for node in list(abstract.childNodes) + [None]:
            if node is None or (node.nodeType == node.ELEMENT_NODE and node.tagName in blocks):
                if any(n.nodeType == n.ELEMENT_NODE or (n.nodeValue or "").strip() for n in group):
                    para = doc.createElement("p")
                    abstract.insertBefore(para, group[0])
                    for child in group:
                        para.appendChild(child)
                group = []
            else:
                group.append(node)
    # JATS Publishing requires metadata in schema order.
    order = "article-id article-version article-version-alternatives article-categories title-group contrib-group aff aff-alternatives x author-notes pub-date pub-date-not-available volume volume-id volume-series issue issue-id issue-title issue-title-group issue-sponsor issue-part supplement fpage lpage page-range elocation-id email ext-link uri product supplementary-material history pub-history permissions self-uri related-article related-object abstract trans-abstract kwd-group funding-group support-group conference counts custom-meta-group".split()
    rank = {tag: i for i, tag in enumerate(order)}
    children = [n for n in article_meta.childNodes if n.nodeType == n.ELEMENT_NODE]
    for node in sorted(children, key=lambda n: rank.get(n.tagName, len(rank))):
        article_meta.appendChild(node)
    data = doc.toxml(encoding="utf-8")
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    tree = etree.fromstring(data, parser)
    schema = etree.RelaxNG(etree.parse(str(Path(__file__).resolve().parents[1] /
                                         "schemas/jats-1.3/JATS-journalpublishing1-3.rng")))
    issues = []
    try:
        schema.assertValid(tree)
    except etree.DocumentInvalid as e:
        if not draft:
            raise
        issues = [dict(code="jats-schema", severity="error", file="article.xml", message=str(entry.message))
                  for entry in e.error_log]
    if issues_path:
        Path(issues_path).write_text(json.dumps(issues, indent=2))
    xml_path.write_bytes(b'<?xml version="1.0" encoding="utf-8"?>\n' + etree.tostring(tree, method="c14n"))
    print(f"Enriched JATS: {xml_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("xml_path")
    ap.add_argument("manuscript_dir", nargs="?")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--issues")
    args = ap.parse_args()
    xml = Path(args.xml_path)
    enrich(xml, Path(args.manuscript_dir) if args.manuscript_dir else xml.parent,
           draft=args.draft, issues_path=args.issues)
