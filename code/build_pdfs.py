"""Render the Day 5 deliverables to PDF.

    python code/build_pdfs.py

Produces, in the repo root:
    slides.pdf      21 landscape slides, one per page
    SCRIPT.pdf      timed speaking script
    QA_HELPER.pdf   Q&A crib sheet

Uses WeasyPrint rather than headless Chrome: Chrome cannot spawn its sandbox
helpers in this build environment and hangs indefinitely, even on trivial
input.  WeasyPrint is pure Python (via cairo/pango) and needs no subprocess.

Requires:  brew install pango   +   pip install weasyprint markdown
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import markdown
from weasyprint import CSS, HTML

REPO = Path(__file__).resolve().parent.parent

DOC_CSS = """
@page { size: Letter; margin: 15mm 14mm;
        @bottom-right { content: counter(page); font-size: 8pt; color: #8a94a0; } }
body { font: 10pt/1.48 "Helvetica Neue", Helvetica, Arial, sans-serif;
       color: #14181d; }
h1 { font-size: 20pt; margin: 0 0 .3em; border-bottom: 3px solid #f0b72f;
     padding-bottom: .18em; }
h2 { font-size: 13.5pt; margin: 1.3em 0 .4em; border-bottom: 1px solid #d6dde5;
     padding-bottom: .16em; page-break-after: avoid; }
h3 { font-size: 11pt; margin: .9em 0 .28em; color: #8a6100;
     page-break-after: avoid; }
table { width: 100%; border-collapse: collapse; margin: .55em 0; font-size: 9pt;
        page-break-inside: avoid; }
th { text-align: left; background: #f2f5f8; border-bottom: 1.5px solid #cbd5e0;
     padding: 4px 6px; font-size: 8pt; text-transform: uppercase;
     letter-spacing: .04em; }
td { padding: 4px 6px; border-bottom: .5px solid #e6ebf0; vertical-align: top; }
code { font-family: Menlo, monospace; background: #eef2f6; padding: 0 3px;
       border-radius: 3px; font-size: .88em; }
blockquote { margin: .5em 0; padding: .45em .8em; background: #fbfcfd;
             border-left: 3px solid #f0b72f; page-break-inside: avoid; }
blockquote p { margin: .3em 0; }
hr { border: none; border-top: .5px solid #d6dde5; margin: 1.3em 0; }
ul, ol { padding-left: 1.25em; margin: .35em 0; }
li { margin: .14em 0; }
strong { color: #000; }
"""

# Slides: force every section onto its own landscape page.
SLIDE_PRINT_CSS = """
@page { size: 280mm 157mm; margin: 0; }
html, body { background: #0d1117 !important; }
#nav, #bar { display: none !important; }
.slide { display: block !important; width: 280mm; height: 157mm;
         padding: 9mm 13mm; overflow: hidden;
         page-break-after: always; page-break-inside: avoid; }
/* WeasyPrint has no flex layout: forcing display:flex leaves .inner
   unconstrained and lets a dense slide spill onto a second page. Block
   layout with a hard height and overflow:hidden keeps one slide = one page. */
/* :last-child fails here — <div id='nav'> follows the final
   <section>, so the last slide still emitted a trailing blank
   page. :last-of-type matches the section correctly. */
.slide:last-of-type { page-break-after: auto; }
.inner { width: 100%; }

/* Dense slides (notably the anchor-bug slide) overflow onto a second page at
   screen sizing. Tighten print typography so every slide fits on exactly one
   page — clipping with overflow:hidden would silently drop content instead. */
.slide h2 { font-size: 26pt; margin-bottom: .3em; }
.slide .lead { font-size: 11pt; margin-bottom: .6em; }
.slide .kicker { margin-bottom: .5em; }
.slide p, .slide li, .slide .card p { font-size: 10.5pt; }
.slide table.t { font-size: 10pt; margin: .25em 0; }
.slide table.t td, .slide table.t th { padding: 4px 7px; }
.slide table.t.compact td, .slide table.t.compact th { padding: 3px 6px; font-size: 9.5pt; }
.slide .callout { font-size: 10pt; padding: 8px 12px; margin-top: .5em; }
.slide .note { font-size: 9.5pt; padding: 8px 11px; }
.slide .strip { font-size: 9.5pt; padding: 6px 11px; }
.slide .stat { padding: 8px 12px; }
.slide .stat .big { font-size: 22pt; }
.slide .stat span:last-child { font-size: 9pt; }
.slide .card { padding: 11px 13px; }
.slide .cols2, .slide .cols3, .slide .split { margin: .45em 0; }
.slide .eq { font-size: 30pt; margin: .2em 0 .45em; }
.slide .eq.small { font-size: 19pt; }
.slide ul.tick li { padding: 4px 0 4px 18px; font-size: 10.5pt; }
.slide ol.big-list li { font-size: 11pt; padding: 5px 0; }
.slide .eq-svg { height: 120pt; }

/* WeasyPrint's CSS Grid support is partial: display:grid silently degrades to
   block, so the two- and three-column layouts stacked vertically and pushed
   dense slides onto a second page. Table layout is fully supported and gives
   the same visual result in a fixed-size page. */
.slide .cols2, .slide .cols3, .slide .split {
    display: table !important; width: 100%; border-spacing: 7pt 0; }
.slide .cols2 > *, .slide .cols3 > *, .slide .split > * {
    display: table-cell !important; vertical-align: top; }
.slide .cols2 > * { width: 50%; }
.slide .cols3 > * { width: 33.33%; }
.slide .split > *:first-child { width: 58%; }
.slide .split > *:last-child  { width: 42%; }
/* .stats is itself a .split child, so it must stay table-cell — an earlier
   `display:block` here silently collapsed the whole right-hand column. Only
   the boxes inside it become blocks, and their spans too, since .stat relied
   on flex-direction:column which WeasyPrint ignores. */
.slide .stats > .stat { display: block !important; margin-bottom: 5pt; }
.slide .stat > span { display: block; }
.slide .stat .big { line-height: 1.1; white-space: nowrap; }
.slide .chart.dd .eq-svg { height: 62pt; }
"""


def md_to_pdf(md_path: Path, pdf: Path) -> bool:
    body = markdown.markdown(md_path.read_text(),
                             extensions=["tables", "fenced_code", "sane_lists"])
    html = f"<!doctype html><meta charset='utf-8'><body>{body}</body>"
    HTML(string=html, base_url=str(REPO)).write_pdf(pdf, stylesheets=[CSS(string=DOC_CSS)])
    return pdf.exists()


def slides_to_pdf(src: Path, pdf: Path) -> bool:
    """Render one slide per page, shrinking any slide that would overflow.

    WeasyPrint has no flexbox and only partial CSS Grid, so a slide laid out
    for the browser can overflow its page and silently split in two. Rather
    than hand-tune CSS per slide, each slide is rendered on its own and, if it
    still spills, re-rendered at progressively smaller scale until it fits.
    That guarantees one slide = one page for any future edit to the deck.
    """
    from pypdf import PdfReader, PdfWriter

    html = re.sub(r"<script>.*?</script>", "", src.read_text(), flags=re.S)
    head = html[: html.index("<body>") + len("<body>")]
    sections = re.findall(r"<section class=\"slide.*?</section>", html, flags=re.S)
    if not sections:
        return False

    writer = PdfWriter()
    shrunk = []
    for i, sec in enumerate(sections, 1):
        for scale in (1.0, 0.92, 0.84, 0.76, 0.68, 0.6):
            doc = f"{head}{sec}</body></html>"
            css = CSS(string=SLIDE_PRINT_CSS + f"\n.slide{{font-size:{scale*100:.0f}%}}")
            buf = io.BytesIO()
            HTML(string=doc, base_url=str(REPO)).write_pdf(buf, stylesheets=[css])
            buf.seek(0)
            reader = PdfReader(buf)
            if len(reader.pages) == 1:
                if scale < 1.0:
                    shrunk.append((i, scale))
                writer.add_page(reader.pages[0])
                break
        else:
            writer.add_page(reader.pages[0])  # give up: keep first page only
            shrunk.append((i, "clipped"))

    with open(pdf, "wb") as fh:
        writer.write(fh)
    if shrunk:
        detail = ", ".join(f"#{i} @{s if isinstance(s,str) else f'{s:.0%}'}" for i, s in shrunk)
        print(f"     (auto-shrunk to fit: {detail})")
    return pdf.exists()


def main() -> int:
    jobs = [("slides.pdf", REPO / "slides.html", slides_to_pdf),
            ("SCRIPT.pdf", REPO / "SCRIPT.md", md_to_pdf),
            ("QA_HELPER.pdf", REPO / "QA_HELPER.md", md_to_pdf)]
    failed = 0
    for name, src, fn in jobs:
        if not src.exists():
            print(f"  - {name:<16} source missing: {src.name}")
            failed += 1
            continue
        out = REPO / name
        try:
            fn(src, out)
            print(f"  ok {name:<16} {out.stat().st_size / 1024:.0f} KB")
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗  {name:<16} {exc}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
