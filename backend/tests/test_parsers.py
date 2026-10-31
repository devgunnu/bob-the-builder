"""Parser tests on real content: the demo/smoke pages (a real Firecrawl scrape).

PDF, DOCX, HTML and CSV fixtures are built at test time from the smoke pages,
so every assertion checks that real facts from the docs survive parsing.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pytest

from bob.connectors.parsers import ParseError, normalize_markdown, parse_file

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = REPO_ROOT / "demo" / "smoke"


def smoke_body(name: str) -> str:
    text = (SMOKE / name).read_text(encoding="utf-8")
    return re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.DOTALL).strip()


def test_markdown_reads_front_matter_and_keeps_body():
    data = (SMOKE / "rate-limits.md").read_bytes()
    parsed = parse_file("rate-limits.md", data)
    assert parsed.title == "Rate Limits | Firecrawl"
    assert parsed.metadata["source_url"] == "https://docs.firecrawl.dev/rate-limits"
    assert not parsed.text.startswith("---")
    assert "| Free | 10 | 10 | 2 | 10 | 2 | 500 | 500 |" in parsed.text


def test_all_smoke_pages_parse_and_are_normalized():
    for path in sorted(SMOKE.glob("*.md")):
        parsed = parse_file(path.name, path.read_bytes())
        assert parsed.text == normalize_markdown(parsed.text)
        assert "\n\n\n" not in parsed.text
        assert parsed.title


def test_txt_uses_filename_title():
    body = smoke_body("webhooks-security.md")
    parsed = parse_file("webhook_security_notes.txt", body.encode())
    assert parsed.title == "webhook security notes"
    assert "X-Firecrawl-Signature" in parsed.text


def test_docx_keeps_headings_lists_and_tables():
    docx = pytest.importorskip("docx")
    body = smoke_body("webhooks-overview.md")
    document = docx.Document()
    document.add_heading("Webhooks", level=1)
    document.add_heading("Timeouts & Retries", level=2)
    timeout_line = next(line for line in body.splitlines() if "10 seconds" in line)
    document.add_paragraph(timeout_line.replace("**", ""))
    document.add_paragraph("Retries after 1 minute", style="List Bullet")
    document.add_paragraph("Retries after 5 minutes", style="List Bullet")
    table = document.add_table(rows=3, cols=2)
    for row, cells in zip(
        table.rows,
        [("Retry", "Delay"), ("1st", "1 minute"), ("2nd", "5 minutes")],
        strict=True,
    ):
        row.cells[0].text, row.cells[1].text = cells
    buffer = io.BytesIO()
    document.save(buffer)

    parsed = parse_file("webhooks.docx", buffer.getvalue())
    assert parsed.title == "Webhooks"
    assert "# Webhooks" in parsed.text
    assert "## Timeouts & Retries" in parsed.text
    assert "within 10 seconds" in parsed.text
    assert "- Retries after 1 minute\n- Retries after 5 minutes" in parsed.text
    assert "| Retry | Delay |" in parsed.text
    assert "| 2nd | 5 minutes |" in parsed.text


def test_pdf_extracts_text_and_page_count():
    pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    lines = [
        line.replace("**", "")
        for line in smoke_body("features-key-restrictions.md").splitlines()
        if line and not line.startswith(("|", "```", "{", "}", '"'))
    ][:40]
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Key Restrictions")
    half = len(lines) // 2
    for page_lines in (lines[:half], lines[half:]):
        y = 750
        for line in page_lines:
            pdf.drawString(40, y, line[:100])
            y -= 16
        pdf.showPage()
    pdf.save()

    parsed = parse_file("key-restrictions.pdf", buffer.getvalue())
    assert parsed.title == "Key Restrictions"
    assert parsed.metadata["pages"] == "2"
    assert "Key Restrictions are an enterprise feature" in parsed.text
    assert lines[-1][:40] in parsed.text  # text from page 2 survives too


def test_html_drops_scripts_and_nav():
    body = smoke_body("rate-limits.md")
    paragraph = body.split("\n\n")[0]
    html = (
        "<html><head><title>Rate Limits | Firecrawl</title>"
        "<script>window.docsConfig = {theme: 'aspen'}</script></head>"
        "<body><nav><a href='/'>Home</a><a href='/billing'>Billing</a></nav>"
        f"<main><h1><a href='#rate-limits'>\u200b</a>Rate Limits</h1>"
        "<button>Copy page</button>"
        f"<p>{paragraph}</p>"
        "<table><tr><th>Plan</th><th>/crawl</th></tr><tr><td>Free</td><td>2</td></tr></table>"
        "</main><footer>Suggest edits</footer></body></html>"
    )
    parsed = parse_file("rate-limits.html", html.encode())
    assert parsed.title == "Rate Limits | Firecrawl"
    assert parsed.text.startswith("# Rate Limits")
    assert "concurrency limits cap how many jobs can run in parallel" in parsed.text
    assert "docsConfig" not in parsed.text
    assert "Suggest edits" not in parsed.text
    assert "Home" not in parsed.text
    assert "Copy page" not in parsed.text
    assert "](#" not in parsed.text
    assert "Free" in parsed.text


def _rate_limit_rows() -> tuple[list[str], list[list[str]]]:
    table = [
        line
        for line in smoke_body("rate-limits.md").splitlines()
        if line.startswith("| ") and "/scrape" in line or line.startswith("| Free | 10")
    ]
    header = [c.strip() for c in table[0].strip("|").split("|")]
    rows = [
        [c.strip() for c in line.strip("|").split("|")]
        for line in smoke_body("rate-limits.md").splitlines()
        if re.match(r"^\| (Free|Hobby|Standard|Growth|Scale) \| \d", line) and len(line.split("|")) == 10
    ]
    return header, rows


def test_small_csv_becomes_markdown_table():
    header, rows = _rate_limit_rows()
    buffer = io.StringIO()
    csv.writer(buffer).writerows([header, *rows])
    parsed = parse_file("rate_limits.csv", buffer.getvalue().encode())
    assert parsed.text.splitlines()[0].startswith("| Plan | /scrape |")
    assert "| Hobby | 100 | 100 | 20 |" in parsed.text
    assert parsed.metadata["rows"] == str(len(rows))


def test_large_csv_becomes_one_section_per_row():
    header, rows = _rate_limit_rows()
    many = [[f"{row[0]} team {n}", *row[1:]] for n in range(8) for row in rows]
    buffer = io.StringIO()
    csv.writer(buffer).writerows([header, *many])
    parsed = parse_file("rate_limits_by_team.csv", buffer.getvalue().encode())
    assert "|" not in parsed.text.splitlines()[0]
    assert "## Free team 0" in parsed.text
    assert "- **/crawl**: 2" in parsed.text
    assert parsed.text.count("\n## ") == len(many) - 1


def test_unsupported_and_empty_files_raise_clear_errors():
    with pytest.raises(ParseError, match="unsupported file type '.xlsx'"):
        parse_file("plans.xlsx", b"PK\x03\x04")
    with pytest.raises(ParseError, match="no text found"):
        parse_file("empty.md", b"\n\n   \n")
    with pytest.raises(ParseError, match="cannot read PDF"):
        parse_file("broken.pdf", b"not a pdf")
