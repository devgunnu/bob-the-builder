"""File parsers: uploaded bytes -> normalized markdown (G1).

Supported: PDF, DOCX, MD, HTML, TXT, CSV. Every parser returns a `ParsedFile`
with a title, markdown text and metadata. The text is what `Document.text`
holds, so chunk offsets downstream are computed on exactly this string.

Parsers are pure and synchronous (PDF and DOCX parsing is CPU-bound); async
callers run them through `asyncio.to_thread`.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import PurePath

SUPPORTED_EXTENSIONS = (
    ".pdf",
    ".docx",
    ".md",
    ".markdown",
    ".html",
    ".htm",
    ".txt",
    ".csv",
)

# CSV files with more rows than this are written as one section per row, so the
# chunker can split them (it never splits inside a table).
CSV_TABLE_MAX_ROWS = 30
CSV_TABLE_MAX_COLS = 8
TITLE_MAX_CHARS = 120


class ParseError(ValueError):
    """The file cannot be turned into text. The message is shown to the user."""


@dataclass(frozen=True)
class ParsedFile:
    title: str
    text: str
    metadata: dict[str, str] = field(default_factory=dict)


def parse_file(name: str, data: bytes) -> ParsedFile:
    """Parse one uploaded file. Raises ParseError for unsupported or empty files."""
    ext = PurePath(name).suffix.lower()
    parser = _PARSERS.get(ext)
    if parser is None:
        supported = ", ".join(SUPPORTED_EXTENSIONS)
        raise ParseError(f"{name}: unsupported file type '{ext or 'none'}' (supported: {supported})")
    parsed = parser(name, data)
    text = normalize_markdown(parsed.text)
    if not text:
        hint = " (scanned PDFs without a text layer are not supported)" if ext == ".pdf" else ""
        raise ParseError(f"{name}: no text found{hint}")
    return ParsedFile(title=parsed.title, text=text, metadata=parsed.metadata)


def normalize_markdown(text: str) -> str:
    """One canonical form: \\n line ends, no trailing spaces, at most one blank line in a row."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------- helpers ----------


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _stem_title(name: str) -> str:
    return PurePath(name).stem.replace("_", " ").replace("-", " ").strip() or name


def _clip_title(title: str) -> str:
    title = " ".join(title.split())
    return title[:TITLE_MAX_CHARS]


def _md_cell(value: str) -> str:
    return " ".join(str(value).split()).replace("|", "\\|")


def _md_table(header: list[str], rows: list[list[str]]) -> str:
    width = len(header)
    lines = [
        "| " + " | ".join(_md_cell(h) for h in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in rows:
        padded = (row + [""] * width)[:width]
        lines.append("| " + " | ".join(_md_cell(c) for c in padded) + " |")
    return "\n".join(lines)


# ---------- parsers ----------

# Links with no visible text, e.g. docs heading anchors "[\u200b](#section)".
EMPTY_LINK = re.compile(r"\[[\s\u200b]*\]\([^)]*\)[ \t]*")
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
FIRST_HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def _parse_markdown(name: str, data: bytes) -> ParsedFile:
    text = _decode(data).replace("\r\n", "\n")
    metadata: dict[str, str] = {}
    match = FRONT_MATTER.match(text)
    if match:
        for line in match.group(1).splitlines():
            key, sep, value = line.partition(":")
            if sep and key.strip():
                metadata[key.strip()] = value.strip()
        text = text[match.end() :]
    heading = FIRST_HEADING.search(text)
    title = metadata.get("title") or (heading.group(1) if heading else _stem_title(name))
    return ParsedFile(title=_clip_title(title), text=text, metadata=metadata)


def _parse_text(name: str, data: bytes) -> ParsedFile:
    text = _decode(data)
    return ParsedFile(title=_clip_title(_stem_title(name)), text=text)


def _parse_html(name: str, data: bytes) -> ParsedFile:
    from bs4 import BeautifulSoup
    from markdownify import markdownify

    soup = BeautifulSoup(_decode(data), "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "template",
            "svg",
            "nav",
            "footer",
            "head",
            "button",
            "form",
        ]
    ):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    markdown = markdownify(str(root), heading_style="ATX", bullets="-", strip=["img"])
    markdown = EMPTY_LINK.sub("", markdown)
    if not title:
        heading = FIRST_HEADING.search(markdown)
        title = heading.group(1) if heading else _stem_title(name)
    return ParsedFile(title=_clip_title(title), text=markdown)


def _parse_pdf(name: str, data: bytes) -> ParsedFile:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            reader.decrypt("")
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except (PdfReadError, ValueError, KeyError) as exc:
        raise ParseError(f"{name}: cannot read PDF ({exc})") from exc
    meta_title = ""
    if reader.metadata is not None and reader.metadata.title:
        meta_title = str(reader.metadata.title)
    text = "\n\n".join(page for page in pages if page)
    return ParsedFile(
        title=_clip_title(meta_title or _stem_title(name)),
        text=text,
        metadata={"pages": str(len(pages))},
    )


def _parse_docx(name: str, data: bytes) -> ParsedFile:
    import docx
    from docx.opc.exceptions import PackageNotFoundError
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = docx.Document(io.BytesIO(data))
    except (PackageNotFoundError, KeyError, ValueError) as exc:
        raise ParseError(f"{name}: cannot read DOCX ({exc})") from exc

    blocks: list[str] = []
    first_heading = ""
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if not text:
                continue
            style = (paragraph.style.name if paragraph.style is not None else "") or ""
            level = _docx_heading_level(style)
            if level:
                blocks.append(f"{'#' * level} {text}")
                first_heading = first_heading or text
            elif "List" in style:
                blocks.append(f"- {text}")
            else:
                blocks.append(text)
        elif tag == "tbl":
            table = Table(child, document)
            rows = [[cell.text for cell in row.cells] for row in table.rows]
            if rows:
                blocks.append(_md_table(rows[0], rows[1:]))

    core_title = (document.core_properties.title or "").strip()
    title = core_title or first_heading or _stem_title(name)
    # Consecutive list items read better without blank lines between them.
    text = "\n\n".join(blocks)
    text = re.sub(r"(^- .*)\n\n(?=- )", r"\1\n", text, flags=re.MULTILINE)
    return ParsedFile(title=_clip_title(title), text=text)


def _docx_heading_level(style: str) -> int:
    if style == "Title":
        return 1
    match = re.fullmatch(r"Heading (\d)", style)
    return min(int(match.group(1)), 6) if match else 0


def _parse_csv(name: str, data: bytes) -> ParsedFile:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [row for row in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in row)]
    if not rows:
        return ParsedFile(title=_stem_title(name), text="")
    header, records = rows[0], rows[1:]
    title = _clip_title(_stem_title(name))
    metadata = {"rows": str(len(records)), "columns": str(len(header))}
    if len(records) <= CSV_TABLE_MAX_ROWS and len(header) <= CSV_TABLE_MAX_COLS:
        return ParsedFile(title=title, text=_md_table(header, records), metadata=metadata)
    sections = []
    for index, record in enumerate(records, start=1):
        label = _md_cell(record[0]) if record and record[0].strip() else f"Row {index}"
        fields = [
            f"- **{_md_cell(col)}**: {_md_cell(value)}"
            for col, value in zip(header, record, strict=False)
            if value.strip()
        ]
        sections.append(f"## {label}\n\n" + "\n".join(fields))
    return ParsedFile(title=title, text="\n\n".join(sections), metadata=metadata)


_PARSERS = {
    ".pdf": _parse_pdf,
    ".docx": _parse_docx,
    ".md": _parse_markdown,
    ".markdown": _parse_markdown,
    ".html": _parse_html,
    ".htm": _parse_html,
    ".txt": _parse_text,
    ".csv": _parse_csv,
}
