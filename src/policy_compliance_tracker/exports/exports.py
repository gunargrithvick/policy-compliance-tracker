import csv
import html
import io
import json
import textwrap
import zipfile
from datetime import datetime
from typing import Any, Dict, Iterable, List


TRACKER_EXPORT_COLUMNS = [
    "tracker_id",
    "status",
    "priority",
    "risk_score",
    "risk_score_max",
    "owner",
    "regulator",
    "regulation_title",
    "version",
    "supersedes_tracker_id",
    "policy_change_required",
    "policy_change_reason",
    "impacted_policy",
    "required_policy_update",
    "impacted_control",
    "control_gap",
    "due_date",
    "confidence",
    "change_detected",
    "change_summary",
    "change_impact",
    "review_required",
    "review_reason",
    "analysis_provider",
    "obligations_structured",
    "evidence_records",
    "retrieval_diagnostics",
    "mapping_graph",
    "evidence",
    "created_at",
    "updated_at",
    "source_path",
    "source_url",
    "feed_name",
    "downloaded_at",
    "regulator_source",
]


def _safe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def tracker_entries_to_csv(entries: Iterable[Dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=TRACKER_EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for entry in entries:
        writer.writerow({column: _safe(entry.get(column)) for column in TRACKER_EXPORT_COLUMNS})
    return buffer.getvalue()


def analysis_to_csv(result: Dict[str, Any]) -> str:
    record = result.get("tracker_record") or {}
    rows = [
        ("Summary", result.get("summary", "")),
        ("Policy Mapping", result.get("mapping", "")),
        ("Control Matrix", result.get("control_matrix", "")),
        ("Impact Tracker", result.get("impact_tracker", "")),
    ]
    for key, value in record.items():
        rows.append((key, value))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Field", "Value"])
    writer.writerows(rows)
    return buffer.getvalue()


def analysis_to_text(result: Dict[str, Any]) -> str:
    return (
        "POLICY COMPLIANCE REPORT\n"
        + "=" * 60
        + f"\nGenerated: {datetime.utcnow().isoformat()}Z\n\n"
        + f"--- SUMMARY ---\n{result.get('summary', '')}\n\n"
        + f"--- POLICY MAPPING ---\n{result.get('mapping', '')}\n\n"
        + f"--- CONTROL MATRIX MAPPING ---\n{result.get('control_matrix', '')}\n\n"
        + f"--- POLICY COMPLIANCE TRACKER ---\n{result.get('impact_tracker', '')}\n"
    )


def analysis_to_markdown(result: Dict[str, Any]) -> str:
    return (
        "# Policy Compliance Report\n\n"
        f"**Generated:** {datetime.utcnow().isoformat()}Z\n\n"
        f"## Summary\n{result.get('summary', '')}\n\n"
        f"## Policy Mapping\n{result.get('mapping', '')}\n\n"
        f"## Control Matrix Mapping\n{result.get('control_matrix', '')}\n\n"
        f"## Policy Compliance Tracker\n{result.get('impact_tracker', '')}\n"
    )


def analysis_to_json(result: Dict[str, Any]) -> str:
    return json.dumps(result, indent=2, default=str)


def _column_letter(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _worksheet_xml(rows: List[List[Any]]) -> str:
    xml_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            ref = f"{_column_letter(column_index)}{row_index}"
            text = html.escape(_safe(value), quote=True)
            cells.append(
                f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'
            )
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData>'
        + "".join(xml_rows)
        + '</sheetData></worksheet>'
    )


def rows_to_xlsx(rows: List[List[Any]]) -> bytes:
    created = datetime.utcnow().isoformat() + "Z"
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Tracker" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        '<dc:title>Policy Compliance Tracker</dc:title>'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
        '</cp:coreProperties>'
    )
    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>Compliance Agent</Application>'
        '</Properties>'
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", _worksheet_xml(rows))
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)
    return buffer.getvalue()


def tracker_entries_to_xlsx(entries: Iterable[Dict[str, Any]]) -> bytes:
    rows = [TRACKER_EXPORT_COLUMNS]
    rows.extend(
        [[_safe(entry.get(column)) for column in TRACKER_EXPORT_COLUMNS] for entry in entries]
    )
    return rows_to_xlsx(rows)


def analysis_to_xlsx(result: Dict[str, Any]) -> bytes:
    rows = [["Field", "Value"]]
    rows.extend(
        [
            ["Summary", result.get("summary", "")],
            ["Policy Mapping", result.get("mapping", "")],
            ["Control Matrix", result.get("control_matrix", "")],
            ["Impact Tracker", result.get("impact_tracker", "")],
        ]
    )
    for key, value in (result.get("tracker_record") or {}).items():
        rows.append([key, value])
    return rows_to_xlsx(rows)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_to_pdf(title: str, body: str) -> bytes:
    wrapped_lines = [title, ""]
    for raw_line in body.splitlines():
        if not raw_line.strip():
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(textwrap.wrap(raw_line, width=92) or [""])

    lines_per_page = 48
    pages = [
        wrapped_lines[index:index + lines_per_page]
        for index in range(0, len(wrapped_lines), lines_per_page)
    ] or [[""]]

    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    page_refs = []

    for page_index, page_lines in enumerate(pages):
        content_lines = ["BT", "/F1 10 Tf", "50 790 Td", "14 TL"]
        for line in page_lines:
            content_lines.append(f"({_pdf_escape(line)}) Tj")
            content_lines.append("T*")
        content_lines.append("ET")
        stream = "\n".join(content_lines)
        content_object_number = len(objects) + 2
        page_object_number = len(objects) + 1
        page_refs.append(f"{page_object_number} 0 R")
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_object_number} 0 R >>"
            )
        )
        objects.append(
            f"<< /Length {len(stream.encode('latin-1', errors='replace'))} >>\nstream\n{stream}\nendstream"
        )

    objects[1] = f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>"

    output = io.BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{index} 0 obj\n{obj}\nendobj\n".encode("latin-1", errors="replace"))

    xref_at = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.write(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF"
        ).encode("ascii")
    )
    return output.getvalue()


def tracker_entries_to_pdf(entries: Iterable[Dict[str, Any]]) -> bytes:
    lines = []
    for entry in entries:
        lines.append(
            (
                f"{entry.get('tracker_id', '')} | {entry.get('priority', '')} | "
                f"{entry.get('status', '')} | {entry.get('owner', '')}"
            )
        )
        lines.append(f"Regulation: {entry.get('regulation_title', '')}")
        policy_required = "Yes" if entry.get("policy_change_required") else "No"
        lines.append(f"Policy change required: {policy_required}")
        lines.append(f"Policy reason: {entry.get('policy_change_reason', '')}")
        lines.append(f"Controls: {entry.get('impacted_control', '')}")
        lines.append(f"Change: {entry.get('change_summary', '')}")
        lines.append(f"Source: {entry.get('source_url') or entry.get('source_path', '')}")
        lines.append("")
    return text_to_pdf("Policy Compliance Tracker", "\n".join(lines))


def analysis_to_pdf(result: Dict[str, Any]) -> bytes:
    return text_to_pdf("Policy Compliance Report", analysis_to_text(result))
