import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from app.core.database import get_supabase
from typing import Optional

async def generate_student_report_pdf(student_id: str, term: str, template_id: Optional[str] = None) -> bytes:
    db = get_supabase()

    # 1. Fetch student info
    student = db.table("students").select("*, classes(name, school_id)").eq("id", student_id).single().execute()
    if not student.data:
        raise ValueError("Student not found")
    student_data = student.data
    class_id = student_data["class_id"]
    class_name = student_data["classes"]["name"]
    school_id = student_data["classes"]["school_id"]

    # 2. Fetch school info
    school = db.table("schools").select("name, county").eq("id", school_id).single().execute()
    school_data = school.data
    school_name = school_data["name"]
    school_county = school_data["county"]

    # 3. Fetch template if provided, else use default style
    primary_color = colors.HexColor("#1e3a8a")
    secondary_color = colors.HexColor("#f0f4ff")
    logo_url = None
    show_attendance = True
    show_fee_status = True
    show_teacher_remarks = True
    show_overall_evaluation = True
    
    # Check if school is premium for custom logo/styling
    school_info = db.table("schools").select("is_premium, logo_url").eq("id", school_id).single().execute().data
    is_premium = school_info.get("is_premium", False) if school_info else False
    if is_premium and school_info.get("logo_url"):
        logo_url = school_info["logo_url"]

    if template_id:
        template = db.table("report_templates").select("*").eq("id", template_id).eq("school_id", school_id).single().execute()
        if template.data:
            t = template.data
            primary_color = colors.HexColor(t.get("primary_color", "#1e3a8a"))
            secondary_color = colors.HexColor(t.get("secondary_color", "#f0f4ff"))
            if is_premium:
                logo_url = t.get("logo_url") or logo_url
            show_attendance = t.get("show_attendance", True)
            show_fee_status = t.get("show_fee_status", True)
            show_teacher_remarks = t.get("show_teacher_remarks", True)
            show_overall_evaluation = t.get("show_overall_evaluation", True)

    # 4. Fetch approved results
    results = (
        db.table("results")
        .select("*, subjects(name)")
        .eq("student_id", student_id)
        .eq("term", term)
        .eq("approval_status", "approved")
        .execute()
        .data or []
    )
    total_score = sum(r["score"] for r in results)
    mean_score = total_score / len(results) if results else 0

    subject_remarks = {}
    for r in results:
        sub_name = r["subjects"]["name"]
        if r.get("remarks"):
            subject_remarks[sub_name] = r["remarks"]

    # 5. Fetch attendance if needed
    attendance_pct = None
    attendance_total = None
    if show_attendance:
        att = db.table("attendance").select("status").eq("student_id", student_id).execute().data or []
        present = sum(1 for a in att if a["status"].lower() == "present")
        total = len(att)
        attendance_pct = round((present / total) * 100, 1) if total > 0 else 0
        attendance_total = total

    # 6. Fetch fee status if needed (SAFE QUERY – no crash when missing)
    fee_balance = None
    fee_cleared = None
    if show_fee_status:
        fee_result = db.table("fee_balances").select("balance, cleared").eq("student_id", student_id).eq("term", term).limit(1).execute()
        fee_data = fee_result.data[0] if fee_result.data else {"balance": 0, "cleared": False}
        fee_balance = fee_data["balance"]
        fee_cleared = fee_data["cleared"]

    # 7. AI overall evaluation / Executive Summary
    overall_remark = ""
    if show_overall_evaluation:
        try:
            from app.services.ai_summary_service import generate_student_summary
            overall_remark = await generate_student_summary(student_id, term)
        except Exception:
            from app.services.remark_generator import generate_professional_remark
            overall_remark = generate_professional_remark(student_data['name'], "overall performance", mean_score)

    # 8. Fetch Awarded Badges
    badges_list = db.table("student_badges").select("badges(name)").eq("student_id", student_id).eq("term", term).execute().data or []
    badge_names = [b["badges"]["name"] for b in badges_list if b.get("badges")]

    # --- Build PDF ---
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="Title",
        parent=styles["Title"],
        textColor=primary_color,
        fontSize=18,
        spaceAfter=10
    )
    heading_style = ParagraphStyle(
        name="Heading2",
        parent=styles["Heading2"],
        textColor=primary_color,
        fontSize=14,
        spaceAfter=8
    )
    normal_style = styles["Normal"]
    centered = ParagraphStyle(name="Centered", parent=normal_style, alignment=TA_CENTER)

    elements = []

    # Logo (Simple placeholder - we assume it's a URL and we'd ideally download it, but for simplicity we use it if possible)
    if logo_url:
        try:
            from reportlab.lib.utils import ImageReader
            img = Image(logo_url, width=40*mm, height=20*mm)
            elements.append(img)
            elements.append(Spacer(1, 5*mm))
        except:
            pass

    elements.append(Paragraph(f"{school_name}", title_style))
    elements.append(Paragraph(f"{school_county} County", centered))
    elements.append(Spacer(1, 5*mm))
    elements.append(Paragraph("Student Report Card", heading_style))
    
    # Student Info Table for better layout
    info_data = [
        [Paragraph(f"<b>Name:</b> {student_data['name']}", normal_style), Paragraph(f"<b>Admission No:</b> {student_data['admission_number']}", normal_style)],
        [Paragraph(f"<b>Class:</b> {class_name}", normal_style), Paragraph(f"<b>Term:</b> {term}", normal_style)]
    ]
    info_table = Table(info_data, colWidths=[90*mm, 90*mm])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2*mm),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 5*mm))

    # Subject scores table
    table_data = [["Subject", "Score (%)"]]
    for r in results:
        table_data.append([r["subjects"]["name"], f"{r['score']:.1f}"])
    table_data.append(["Mean Score", f"{mean_score:.2f}"])

    table = Table(table_data, colWidths=[130*mm, 50*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), primary_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, len(table_data)-1), (-1, len(table_data)-1), secondary_color),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 5*mm))

    # Attendance & Fee Status in one row
    extra_data = []
    att_cell = ""
    fee_cell = ""
    if show_attendance and attendance_pct is not None:
        att_cell = f"<b>Attendance:</b> {attendance_pct}% ({attendance_total} days recorded)"
    
    if show_fee_status and fee_balance is not None:
        status_text = "Cleared" if fee_cleared else f"Outstanding: KES {fee_balance:,.2f}"
        fee_cell = f"<b>Fee Status:</b> {status_text}"
    
    if att_cell or fee_cell:
        extra_data.append([Paragraph(att_cell, normal_style), Paragraph(fee_cell, normal_style)])
        extra_table = Table(extra_data, colWidths=[90*mm, 90*mm])
        elements.append(extra_table)
        elements.append(Spacer(1, 5*mm))

    # Teacher remarks
    if show_teacher_remarks and subject_remarks:
        elements.append(Paragraph("Subject Teacher Remarks", heading_style))
        for sub, remark in subject_remarks.items():
            elements.append(Paragraph(f"<b>{sub}:</b> {remark}", normal_style))
        elements.append(Spacer(1, 3*mm))

    # Overall evaluation / AI Summary
    if show_overall_evaluation and overall_remark:
        elements.append(Paragraph("Executive Summary & Evaluation", heading_style))
        elements.append(Paragraph(overall_remark, normal_style))

    # Achievement Badges
    if badge_names:
        elements.append(Spacer(1, 5*mm))
        elements.append(Paragraph("Achievement Badges", heading_style))
        badges_text = ", ".join(badge_names)
        elements.append(Paragraph(f"Awarded: <b>{badges_text}</b>", normal_style))

    # Footer
    elements.append(Spacer(1, 10*mm))
    from datetime import datetime
    elements.append(Paragraph(f"Printed on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
