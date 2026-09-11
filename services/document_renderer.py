"""Deterministic PDF/DOCX renderer for approved Draft Studio packages."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from html import escape as xml_escape

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from services.document_catalogue import (
    PRODUCT_CODE,
    DocumentProduct,
)
from services.document_address_service import render_premises_address


MAX_ARTIFACT_BYTES = 5 * 1024 * 1024
_TOKEN = re.compile(r"\[([a-z_]+)\]")


@dataclass(frozen=True)
class RenderedArtifact:
    kind: str
    content: bytes
    content_type: str
    extension: str
    content_hash: str
    manifest_hash: str
    renderer_version: str


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _number_words(number: int) -> str:
    if number == 0:
        return "zero rupees only"
    ones = (
        "", "one", "two", "three", "four", "five", "six", "seven",
        "eight", "nine", "ten", "eleven", "twelve", "thirteen",
        "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
        "nineteen",
    )
    tens = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")

    def under_hundred(value: int) -> list[str]:
        if value < 20:
            return [ones[value]] if value else []
        return [tens[value // 10]] + ([ones[value % 10]] if value % 10 else [])

    def under_thousand(value: int) -> list[str]:
        result: list[str] = []
        if value >= 100:
            result.extend((ones[value // 100], "hundred"))
        result.extend(under_hundred(value % 100))
        return result

    parts: list[str] = []
    for unit_value, unit_name in ((10_000_000, "crore"), (100_000, "lakh"), (1_000, "thousand")):
        count, number = divmod(number, unit_value)
        if count:
            parts.extend(under_thousand(count))
            parts.append(unit_name)
    parts.extend(under_thousand(number))
    return " ".join(parts) + " rupees only"


def _clean_text(value: object) -> str:
    text = str(value or "").strip()
    return text.replace("<", "").replace(">", "")


def _token_values(answers: dict[str, object]) -> dict[str, str]:
    monthly = int(str(answers["monthly_licence_fee_inr"]))
    deposit = int(str(answers["refundable_deposit_inr"]))
    values = {key: _clean_text(value) for key, value in answers.items()}
    values.update({
        "execution_date_or_blank": "________________",
        "monthly_licence_fee_words": _number_words(monthly),
        "refundable_deposit_words": _number_words(deposit),
        "rendered_premises_address": render_premises_address(answers),
        "premises_property_reference_or_none": values.get("premises_property_reference", "NONE"),
        "included_areas_or_none": values.get("included_areas", "NONE"),
        "permitted_occupant_names_or_none": values.get("permitted_occupant_names", "NONE"),
    })
    return values


def _render_source(
    product: DocumentProduct,
    answers: dict[str, object],
) -> str:
    source = product.template_path.read_text(encoding="utf-8")
    marker = "## Output notice"
    if marker not in source:
        raise ValueError("document_template_marker_missing")
    source = source[source.index(marker):]
    values = _token_values(answers)

    missing: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = values.get(key)
        if not value:
            missing.add(key)
            return ""
        return value

    rendered = _TOKEN.sub(replace, source)
    if missing:
        raise ValueError("missing_document_tokens:" + ",".join(sorted(missing)))

    inventory = values.get("inventory_items", "NONE")
    schedule_marker = "Render only when the customer confirms one or more inventory items."
    if inventory == "NONE":
        start = rendered.find("## Schedule 2: Inventory")
        end = rendered.find("## Signature and witness blocks")
        if start >= 0 and end > start:
            rendered = rendered[:start] + rendered[end:]
    else:
        items = [item.strip() for item in inventory.split(",") if item.strip()]
        numbered = "\n".join(f"{index}. {item}" for index, item in enumerate(items, 1))
        rendered = rendered.replace(
            schedule_marker,
            numbered + "\n\nThe Parties shall verify this list and visible condition together at handover.",
        )
        rendered = rendered.replace(
            'Number each escaped item and include: "The Parties shall verify this list and visible\ncondition together at handover."',
            "",
        )
    rendered = re.sub(r"`([^`]*)`", r"\1", rendered)
    return rendered.strip()


def _plain_ascii(value: str) -> str:
    return (
        value.replace("—", "-").replace("–", "-")
        .replace("’", "'").replace("“", '"').replace("”", '"')
        .replace("₹", "INR")
    )


def _paragraphs(markdown: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for block in re.split(r"\n\s*\n", markdown):
        value = " ".join(line.strip() for line in block.splitlines()).strip()
        if not value:
            continue
        if value.startswith("## "):
            result.append(("heading1", value[3:]))
        elif value.startswith("### "):
            result.append(("heading2", value[4:]))
        elif value.startswith("> "):
            result.append(("notice", value[2:]))
        else:
            result.append(("body", value))
    return result


def _pdf(
    markdown: str,
    *,
    preview: bool,
    renderer_version: str,
) -> bytes:
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="NyaySetu Residential Leave and Licence Agreement",
        # Retained as immutable artifact metadata so existing approved golden
        # hashes are not invalidated by the customer-facing product rename.
        author="NyaySetu Document Studio",
        creator=renderer_version,
        invariant=1,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="DocumentTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=16, leading=20, spaceAfter=12))
    styles.add(ParagraphStyle(name="DocumentNotice", parent=styles["BodyText"], borderWidth=1, borderPadding=8, leading=13, spaceAfter=10))
    story = []
    if preview:
        story.extend((Paragraph("PREVIEW - NOT FOR EXECUTION", styles["DocumentTitle"]), Spacer(1, 6)))
    for kind, text in _paragraphs(_plain_ascii(markdown)):
        safe = xml_escape(text)
        if kind == "heading1":
            story.append(Paragraph(safe, styles["DocumentTitle"]))
        elif kind == "heading2":
            story.append(Paragraph(safe, styles["Heading2"]))
        elif kind == "notice":
            story.append(Paragraph(safe, styles["DocumentNotice"]))
        else:
            story.append(Paragraph(safe, styles["BodyText"]))
        story.append(Spacer(1, 6))

    def watermark(canvas, _document):
        if not preview:
            return
        canvas.saveState()
        canvas.setFillGray(0.85)
        canvas.setFont("Helvetica-Bold", 34)
        canvas.translate(A4[0] / 2, A4[1] / 2)
        canvas.rotate(35)
        canvas.drawCentredString(0, 0, "PREVIEW - NOT FOR EXECUTION")
        canvas.restoreState()

    document.build(story, onFirstPage=watermark, onLaterPages=watermark)
    return output.getvalue()


def _docx(markdown: str) -> bytes:
    paragraphs = []
    for kind, text in _paragraphs(_plain_ascii(markdown)):
        style = "Title" if kind == "heading1" else "Heading2" if kind == "heading2" else "Normal"
        paragraphs.append(
            '<w:p><w:pPr><w:pStyle w:val="%s"/></w:pPr><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>'
            % (style, xml_escape(text))
        )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        + "".join(paragraphs)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1020" w:right="1020" w:bottom="1020" w:left="1020"/></w:sectPr></w:body></w:document>'
    )
    content_types = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
    relationships = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
    output = io.BytesIO()
    # Store entries without deflate compression. Deflate bitstreams may differ
    # between zlib implementations even when their uncompressed XML is
    # identical, which would make the approved artifact hash platform-specific.
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in (("[Content_Types].xml", content_types), ("_rels/.rels", relationships), ("word/document.xml", document_xml)):
            info = zipfile.ZipInfo(name, date_time=(2026, 8, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o600 << 16
            archive.writestr(info, content.encode("utf-8"))
    return output.getvalue()


def render(product: DocumentProduct, answers: dict[str, object], kind: str) -> RenderedArtifact:
    if kind not in {"PREVIEW_PDF", "FINAL_PDF", "FINAL_DOCX"}:
        raise ValueError("unsupported_document_artifact_kind")
    markdown = _render_source(product, answers)
    if kind.endswith("PDF"):
        content = _pdf(
            markdown,
            preview=kind == "PREVIEW_PDF",
            renderer_version=product.renderer_version,
        )
        content_type, extension = "application/pdf", "pdf"
    else:
        content = _docx(markdown)
        content_type, extension = "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"
    if not content or len(content) > MAX_ARTIFACT_BYTES:
        raise ValueError("document_artifact_size_invalid")
    content_hash = _sha256(content)
    manifest = {
        "answers_hash": _sha256(json.dumps(answers, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")),
        "artifact_hash": content_hash,
        "artifact_kind": kind,
        "renderer_version": product.renderer_version,
        "schema_hash": product.schema_hash,
        "template_hash": product.template_hash,
        "template_version": product.template_version,
    }
    manifest_hash = _sha256(json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return RenderedArtifact(
        kind,
        content,
        content_type,
        extension,
        content_hash,
        manifest_hash,
        product.renderer_version,
    )


def golden_answers(
    product: DocumentProduct | None = None,
) -> dict[str, object]:
    if product is None:
        from services.document_catalogue import resolve_product

        product = resolve_product(PRODUCT_CODE)
    return dict(product.golden_answers())


def golden_hashes(product: DocumentProduct) -> tuple[str, str]:
    answers = golden_answers(product)
    return render(product, answers, "FINAL_PDF").content_hash, render(product, answers, "FINAL_DOCX").content_hash
