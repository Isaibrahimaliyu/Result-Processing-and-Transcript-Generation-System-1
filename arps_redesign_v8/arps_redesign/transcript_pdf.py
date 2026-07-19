"""
ARPTGS — Official Transcript PDF Generator  (v3 — matches official CRF document style)
Ibrahim Badamasi Babangida University, Lapai, Niger State
Uses ReportLab to produce a print-ready, security-featured academic transcript
styled to match the university's official Course Registration Form (CRF)
document: plain white background, logo + student photo in the letterhead,
bordered tables throughout, a faint centered watermark crest, and a
multi-signature footer.

Install: pip install reportlab qrcode pillow
"""
from __future__ import annotations
import os
import hashlib
from io import BytesIO
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, HRFlowable, Image as RLImage,
)
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib.utils import ImageReader

try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None

# ── University branding ───────────────────────────────────────
UNIVERSITY_NAME = "IBRAHIM BADAMASI BABANGIDA UNIVERSITY"
UNIVERSITY_LOC  = "LAPAI, NIGER STATE."
FACULTY_NAME    = "Faculty of Science"
DEPARTMENT_NAME = "Computer Science"
REGISTRAR_NAME  = "Dr. A. M. Suleiman"
REGISTRAR_TITLE = "Registrar"

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img")
_LOGO_PATH  = os.path.join(_ASSETS_DIR, "ibbul_logo.png")
_UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads", "passports")

# ── Colour palette — plain, formal, matches the official CRF ──
BLACK      = colors.black
WHITE      = colors.white
INK        = colors.HexColor("#1F2933")
GREEN      = colors.HexColor("#00A85B")
PALE_MINT  = colors.HexColor("#F4FCEE")
BORDER     = colors.HexColor("#333333")
TEXT_MUTED = colors.HexColor("#4B5563")


def _security_code(student, token) -> str:
    """Printed security/reference code, cryptographically tied to the QR
    token when one exists (see qr_verify.py); otherwise a document
    reference number derived from the student + date."""
    if token is not None:
        raw = hashlib.sha256(f"{token.token}:{student.matric_no}".encode()).hexdigest().upper()
    else:
        raw = hashlib.sha256(f"{student.matric_no}:{date.today().isoformat()}".encode()).hexdigest().upper()
    chunk = raw[:16]
    return "-".join(chunk[i:i+4] for i in range(0, 16, 4))


_watermark_cache: dict = {}


def _get_watermark_reader():
    """Build (once, cached) a faint low-opacity version of the university
    crest to sit behind the diagonal text watermark."""
    if "reader" in _watermark_cache:
        return _watermark_cache["reader"]
    reader = None
    try:
        if PILImage is not None:
            im = PILImage.open(_LOGO_PATH).convert("RGBA")
            alpha = im.split()[3].point(lambda p: int(p * 0.08))
            im.putalpha(alpha)
            buf = BytesIO()
            im.save(buf, format="PNG")
            buf.seek(0)
            reader = ImageReader(buf)
    except Exception:
        reader = None
    _watermark_cache["reader"] = reader
    return reader


def _draw_watermark(c: pdfcanvas.Canvas, doc):
    """Faint diagonal university-name text watermark with the crest behind
    it — matches the official CRF document's watermark treatment."""
    page_w, page_h = A4

    # Faint crest sits behind the text
    reader = _get_watermark_reader()
    if reader is not None:
        c.saveState()
        size = 11 * cm
        try:
            c.drawImage(reader, (page_w - size) / 2, (page_h - size) / 2,
                        width=size, height=size, mask='auto')
        except Exception:
            pass
        c.restoreState()

    # Large diagonal text, one pass across the page
    c.saveState()
    try:
        c.setFillColor(GREEN, alpha=0.09)
    except TypeError:
        c.setFillColorRGB(0.85, 0.93, 0.87)
    c.setFont("Helvetica-Bold", 30)
    c.translate(page_w / 2, page_h / 2)
    c.rotate(35)
    lines = ["IBRAHIM BADAMASI BABANGIDA", "UNIVERSITY, LAPAI"]
    line_h = 34
    start_y = (len(lines) - 1) * line_h / 2
    for i, line in enumerate(lines):
        c.drawCentredString(0, start_y - i * line_h, line)
    c.restoreState()


def generate_transcript_pdf(student, cgpa_data: dict, token=None, base_url: str = "", doc_type: str = "transcript") -> bytes:
    """
    Generate an official PDF academic transcript styled to match the
    university's official CRF document.

    Args:
        student:    Student model instance.
        cgpa_data:  Dict returned by engine.compute_cgpa().
        token:      Optional TranscriptToken instance. When supplied, a QR
                    verification code + matching security code are embedded.
        doc_type:   "transcript" (official, signed) or "statement" (personal copy).

    Returns:
        Raw PDF bytes ready to stream to the browser.
    """
    is_official = (doc_type != "statement")
    doc_title   = "OFFICIAL ACADEMIC TRANSCRIPT" if is_official else "STATEMENT OF ACADEMIC RESULTS"
    CONTENT_WIDTH = 17.4 * cm   # shared width so every section's border lines up flush
    session_label = None
    breakdown = cgpa_data.get("semester_breakdown", [])
    if breakdown:
        years = sorted({s["session_year"] for s in breakdown})
        session_label = f"{years[0]} — {years[-1]} Academic Sessions" if len(years) > 1 else f"{years[0]} Academic Session"

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.6*cm, rightMargin=1.6*cm,
        topMargin=1.3*cm, bottomMargin=1.6*cm,
        title=f"{doc_title} — {student.matric_no}",
    )

    styles = getSampleStyleSheet()
    story  = []

    def _style(name, **kw):
        return ParagraphStyle(name, parent=styles["Normal"], **kw)

    s_uni = _style("uni", fontSize=14.5, fontName="Helvetica-Bold",
                   textColor=BLACK, alignment=TA_CENTER, spaceAfter=1, leading=17)
    s_loc = _style("loc", fontSize=11.5, fontName="Helvetica-Bold",
                   textColor=BLACK, alignment=TA_CENTER, spaceAfter=3)
    s_session = _style("session", fontSize=9.5, fontName="Helvetica",
                       textColor=INK, alignment=TA_CENTER, spaceAfter=1)
    s_doctitle = _style("doctitle", fontSize=10.5, fontName="Helvetica-Bold",
                        textColor=BLACK, alignment=TA_CENTER, spaceAfter=1)

    # ── Letterhead: logo | university text | student photo ────
    try:
        logo_flowable = RLImage(_LOGO_PATH, width=2.1*cm, height=2.1*cm)
    except Exception:
        logo_flowable = Spacer(2.1*cm, 2.1*cm)

    photo_flowable = None
    if getattr(student, "passport_photo", None):
        photo_path = os.path.join(_UPLOADS_DIR, student.passport_photo)
        if os.path.exists(photo_path):
            try:
                photo_flowable = RLImage(photo_path, width=2.3*cm, height=2.7*cm)
            except Exception:
                photo_flowable = None
    if photo_flowable is None:
        # Placeholder box matching the passport-photo footprint on the CRF
        ph_tbl = Table([[""]], colWidths=[2.3*cm], rowHeights=[2.7*cm])
        ph_tbl.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F4F6")),
        ]))
        photo_flowable = ph_tbl

    header_center = [
        Paragraph(UNIVERSITY_NAME, s_uni),
        Paragraph(UNIVERSITY_LOC, s_loc),
    ]
    if session_label:
        header_center.append(Paragraph(f"{session_label}.", s_session))
    header_center.append(Spacer(1, 2))
    header_center.append(Paragraph(doc_title, s_doctitle))

    header_tbl = Table(
        [[logo_flowable, header_center, photo_flowable]],
        colWidths=[2.6*cm, CONTENT_WIDTH - 5.2*cm, 2.6*cm],
    )
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",  (0, 0), (0, 0),   "LEFT"),
        ("ALIGN",  (2, 0), (2, 0),   "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 1.3, BLACK),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    frame_rows = [[header_tbl]]

    # ── Bio-data grid — bordered, plain, matches the CRF's label|value grid ──
    grad_year = (student.entry_year or 2020) + 4
    sex_map = {"M": "Male", "F": "Female"}
    sex_display = sex_map.get(getattr(student, "gender", None), "—")

    def _lbl(txt):
        return Paragraph(f"<b>{txt}</b>", _style(f"lbl_{txt}", fontSize=8, fontName="Helvetica-Bold", textColor=BLACK))
    def _val(txt):
        return Paragraph(str(txt), _style(f"val_{txt}", fontSize=8, textColor=BLACK))

    bio_rows = [
        [_lbl("Full Name"), _val(student.full_name.upper()), _lbl("Matric No"), _val(student.matric_no)],
        [_lbl("Faculty"),   _val(FACULTY_NAME.upper()),        _lbl("Date of Birth"),
         _val(student.date_of_birth.strftime("%Y-%m-%d") if student.date_of_birth else "—")],
        [_lbl("Department"), _val(student.department.upper() if student.department else DEPARTMENT_NAME.upper()),
         _lbl("Level"), _val(student.level)],
        [_lbl("Entry Year"), _val(student.entry_year or "—"), _lbl("Expected Grad."), _val(grad_year)],
        [_lbl("Sex"), _val(sex_display), _lbl("Date Issued"), _val(date.today().strftime("%Y-%m-%d"))],
    ]
    bio_tbl = Table(bio_rows, colWidths=[2.9*cm, 7.2*cm, 3.1*cm, 4.2*cm])
    bio_tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, BORDER),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    frame_rows.append([bio_tbl])

    # ── Semester course tables — plain bordered, matches the CRF table style ──
    col_w = [1.9*cm, 6.9*cm, 1.3*cm, 1.5*cm, 1.5*cm, 1.4*cm, 1.2*cm, 1.7*cm]

    def _cell(txt, bold=False, align="LEFT"):
        fn = "Helvetica-Bold" if bold else "Helvetica"
        key = str(txt)[:10].replace(" ", "_").replace("/", "_")
        return Paragraph(str(txt), _style(f"c_{key}_{bold}", fontSize=7.6, fontName=fn, textColor=BLACK, alignment=TA_LEFT if align=="LEFT" else TA_CENTER))

    grand_total_units = 0

    for sem in breakdown:
        rows = [[
            _cell("Code", bold=True), _cell("Title", bold=True),
            _cell("Units", bold=True, align="C"), _cell("CA", bold=True, align="C"),
            _cell("Exam", bold=True, align="C"), _cell("Total", bold=True, align="C"),
            _cell("Grade", bold=True, align="C"), _cell("Qual. Pts", bold=True, align="C"),
        ]]
        for c in sem["courses"]:
            rows.append([
                _cell(c["code"], bold=True),
                _cell(c["title"]),
                _cell(c["credit_unit"], align="C"),
                _cell(f"{c['ca_score']:.1f}", align="C"),
                _cell(f"{c['exam_score']:.1f}", align="C"),
                _cell(f"{c['total_score']:.1f}", bold=True, align="C"),
                _cell(c["grade"], bold=True, align="C"),
                _cell(f"{c['quality_points']:.1f}", align="C"),
            ])

        # Semester label row spans the full table width — plain, bordered, no fill
        label_tbl = Table([[
            Paragraph(f"<b>{sem['session_year']} Academic Session — {sem['semester']} Semester</b>",
                      _style("semlbl", fontSize=8.3, fontName="Helvetica-Bold", textColor=BLACK)),
            Paragraph(f"Semester GPA: <b>{sem['gpa']:.2f}</b>",
                      _style("semgpa", fontSize=8.3, fontName="Helvetica-Bold", textColor=BLACK, alignment=TA_RIGHT)),
        ]], colWidths=[sum(col_w) * 0.65, sum(col_w) * 0.35])
        label_tbl.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
            ("BACKGROUND", (0, 0), (-1, -1), PALE_MINT),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        frame_rows.append([label_tbl])

        course_tbl = Table(rows, colWidths=col_w)
        course_tbl.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        frame_rows.append([course_tbl])

        grand_total_units += sem["total_units"]
        total_row = Table([[
            Paragraph(f"Total Units This Semester: <b>{sem['total_units']}</b>   |   Quality Points: <b>{sem['quality_points']:.1f}</b>",
                      _style("totrow", fontSize=7.8, textColor=BLACK, alignment=TA_RIGHT)),
        ]], colWidths=[sum(col_w)])
        total_row.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        frame_rows.append([total_row])

    # ── Cumulative summary — same plain bordered style ────────
    cgpa      = cgpa_data.get("cgpa", 0.0)
    deg_class = cgpa_data.get("degree_class", "N/A")
    tot_units = cgpa_data.get("total_units", 0)
    tot_qp    = cgpa_data.get("total_quality_points", 0.0)

    def _sum_lbl(txt):
        return Paragraph(f"<b>{txt}</b>", _style(f"sl_{txt[:8]}", fontSize=8.5, fontName="Helvetica-Bold", textColor=BLACK))
    def _sum_val(txt):
        return Paragraph(str(txt), _style(f"sv_{str(txt)[:8]}", fontSize=8.5, textColor=BLACK))

    sum_rows = [
        [Paragraph("<b>CUMULATIVE ACADEMIC SUMMARY (GRAND TOTAL)</b>",
                   _style("sh", fontSize=9, fontName="Helvetica-Bold", textColor=BLACK, alignment=TA_CENTER)), "", "", ""],
        [_sum_lbl("Total Credit Units:"), _sum_val(tot_units),
         _sum_lbl("Total Quality Points:"), _sum_val(f"{tot_qp:.2f}")],
        [_sum_lbl("Cumulative GPA (CGPA):"), _sum_val(f"{cgpa:.2f} / 5.00"),
         _sum_lbl("Degree Classification:"), _sum_val(deg_class)],
    ]
    sum_tbl = Table(sum_rows, colWidths=[4.5*cm, 3.6*cm, 4.5*cm, 4.8*cm])
    sum_tbl.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("GRID", (0, 0), (-1, -1), 0.6, BORDER),
        ("BACKGROUND", (0, 0), (-1, 0), PALE_MINT),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    frame_rows.append([sum_tbl])

    # ── Signature block — matches the CRF's multi-signatory layout ──
    s_sig_cap = _style("sigcap", fontSize=7, fontName="Helvetica", textColor=BLACK, alignment=TA_CENTER)
    s_sig_name = _style("signame", fontSize=9.5, fontName="Times-Italic", textColor=BLACK, alignment=TA_CENTER)

    if is_official:
        def _sig_line(caption, printed_name=None):
            cell = []
            if printed_name:
                cell.append(Paragraph(printed_name, s_sig_name))
            cell.append(HRFlowable(width="85%", thickness=0.7, color=BLACK, hAlign="CENTER", spaceBefore=(2 if not printed_name else 1), spaceAfter=2))
            cell.append(Paragraph(caption, s_sig_cap))
            return cell

        sig_row1 = Table([[
            _sig_line("SIGNATURE OF HOD &amp; DATE"),
            _sig_line("SIGNATURE OF DEAN &amp; DATE"),
        ]], colWidths=[CONTENT_WIDTH/2, CONTENT_WIDTH/2])
        sig_row1.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
            ("TOPPADDING", (0,0), (-1,-1), 14),
            ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ]))
        frame_rows.append([sig_row1])

        sig_row2 = Table([[
            _sig_line("SIGNATURE OF REGISTRAR &amp; DATE", printed_name=REGISTRAR_NAME),
        ]], colWidths=[CONTENT_WIDTH])
        sig_row2.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ("ALIGN", (0,0), (0,0), "CENTER"),
            ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
            ("TOPPADDING", (0,0), (-1,-1), 10),
            ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ]))
        frame_rows.append([sig_row2])
    else:
        s_notice = _style("notice", fontSize=7.5, fontName="Helvetica-Oblique", textColor=TEXT_MUTED, alignment=TA_CENTER)
        notice_tbl = Table([[Paragraph(
            "This Statement of Results is for personal reference only and does not "
            "bear institutional signatures. For an official signed transcript, "
            "contact the Examination Office.", s_notice)]], colWidths=[CONTENT_WIDTH])
        notice_tbl.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
            ("TOPPADDING", (0,0), (-1,-1), 12),
            ("BOTTOMPADDING", (0,0), (-1,-1), 12),
        ]))
        frame_rows.append([notice_tbl])

    # ── Security code + QR verification (bottom-right, matches CRF's QR placement) ──
    sec_code = _security_code(student, token)
    s_small = _style("small", fontSize=7, textColor=BLACK, alignment=TA_LEFT, leading=10)
    s_small_b = _style("smallb", fontSize=7.3, fontName="Helvetica-Bold", textColor=BLACK, alignment=TA_LEFT, leading=10)

    footer_left = [
        Paragraph(
            "*** This is a computer-generated document. Original signature is not required "
            "when authenticity is confirmed via the QR code / security code below. ***",
            s_small),
        Spacer(1, 2),
        Paragraph(
            f"SOURCE: Ibrahim Badamasi Babangida University, Lapai — Official Academic Records Portal"
            + (f", {session_label}." if session_label else "."),
            s_small),
        Spacer(1, 2),
        Paragraph("SCAN THE QR CODE TO VERIFY THIS DOCUMENT IS AUTHENTIC.", s_small_b),
        Spacer(1, 3),
        Paragraph(f"SECURITY CODE: <font face='Courier-Bold'>{sec_code}</font>", s_small),
    ]

    qr_img = None
    if token is not None:
        try:
            from qr_verify import generate_qr_png, build_verify_url
            verify_url = build_verify_url(token.token, base_url=base_url)
            qr_png_bytes = generate_qr_png(verify_url, box_size=4)
            qr_buf = BytesIO(qr_png_bytes)
            qr_img = RLImage(qr_buf, width=2.3*cm, height=2.3*cm)
            footer_left.append(Spacer(1, 2))
            footer_left.append(Paragraph(
                f"Token: <font face='Courier'>{token.token[:24]}…</font>", s_small))
        except Exception:
            qr_img = None

    if qr_img is None:
        qr_img = Spacer(2.3*cm, 2.3*cm)

    footer_tbl = Table([[footer_left, qr_img]], colWidths=[CONTENT_WIDTH - 3.2*cm, 3.2*cm])
    footer_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    frame_rows.append([footer_tbl])

    # ── Wrap every section into ONE master table so all the border lines
    # join together into a single continuous rectangle, rather than separate
    # floating boxes with gaps between them. ──────────────────────────────
    master_tbl = Table(frame_rows, colWidths=[CONTENT_WIDTH])
    master_tbl.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.6, BLACK),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(master_tbl)

    doc.build(story, onFirstPage=_draw_watermark, onLaterPages=_draw_watermark)
    return buf.getvalue()
