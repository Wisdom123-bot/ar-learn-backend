import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from app.core.database import get_supabase
from typing import Optional

def generate_student_report_pdf(student_id: str, term: str, template_id: Optional[str] = None) -> bytes:
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

    if template_id:
        template = db.table("report_templates").select("*").eq("id", template_id).eq("school_id", school_id).single().execute()
        if template.data:
            t = template.data
            primary_color = colors.HexColor(t.get("primary_color", "#1e3a8a"))
            secondary_color = colors.HexColor(t.get("secondary_color", "#f0f4ff"))
            logo_url = t.get("logo_url")
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

    # 6. Fetch fee status if needed
    fee_balance = None
    fee_cleared = None
    if show_fee_status:
        fee = db.table("fee_balances").select("balance, cleared").eq("student_id", student_id).eq("term", term).single().execute()
        if fee.data:
            fee_balance = fee.data["balance"]
            fee_cleared = fee.data["cleared"]

    # --- Build PDF ---
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm
    )
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    normal_style = styles["Normal"]
    centered = ParagraphStyle(name="Centered", parent=normal_style, alignment=TA_CENTER)

    elements = []

    # Logo
    if logo_url:
        try:
            # Simple placeholder – in production you'd download the image, for now we skip
            pass
        except:
            pass

    elements.append(Paragraph(f"{school_name}", title_style))
    elements.append(Paragraph(f"{school_county} County", centered))
    elements.append(Spacer(1, 5*mm))
    elements.append(Paragraph("Student Report Card", heading_style))
    elements.append(Paragraph(f"Name: {student_data['name']}", normal_style))
    elements.append(Paragraph(f"Admission No: {student_data['admission_number']}", normal_style))
    elements.append(Paragraph(f"Class: {class_name}", normal_style))
    elements.append(Paragraph(f"Term: {term}", normal_style))
    elements.append(Spacer(1, 5*mm))

    # Subject scores table
    table_data = [["Subject", "Score (%)"]]
    for r in results:
        table_data.append([r["subjects"]["name"], f"{r['score']:.1f}"])
    table_data.append(["Mean Score", f"{mean_score:.2f}"])

    table = Table(table_data, colWidths=[100*mm, 50*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), primary_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, len(table_data)-1), (-1, len(table_data)-1), secondary_color),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 5*mm))

    # Attendance
    if show_attendance and attendance_pct is not None:
        elements.append(Paragraph("Attendance", heading_style))
        elements.append(Paragraph(f"Present: {attendance_pct}% ({attendance_total} days recorded)", normal_style))
        elements.append(Spacer(1, 3*mm))

    # Fee status
    if show_fee_status and fee_balance is not None:
        elements.append(Paragraph("Fee Status", heading_style))
        status_text = "Cleared" if fee_cleared else f"Outstanding: KES {fee_balance:,.2f}"
        elements.append(Paragraph(status_text, normal_style))
        elements.append(Spacer(1, 3*mm))

    # Teacher remarks
    if show_teacher_remarks and subject_remarks:
        elements.append(Paragraph("Subject Teacher Remarks", heading_style))
        for sub, remark in subject_remarks.items():
            elements.append(Paragraph(f"<b>{sub}:</b> {remark}", normal_style))
        elements.append(Spacer(1, 3*mm))

    # Overall evaluation
    if show_overall_evaluation:
        from app.services.remark_generator import generate_professional_remark
        overall_remark = generate_professional_remark(student_data['name'], "overall performance", mean_score)
        elements.append(Paragraph("Overall Evaluation", heading_style))
        elements.append(Paragraph(overall_remark, normal_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()