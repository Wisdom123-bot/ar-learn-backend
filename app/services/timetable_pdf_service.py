import io
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from app.core.database import get_supabase

def generate_timetable_pdf(entries, title, school_name, sub_title=""):
    """
    Generate a weekly timetable PDF.
    entries: list of dicts with day_of_week, start_time, end_time, subject_name, class_name/teacher_name
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=10*mm, rightMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="Title",
        parent=styles["Title"],
        fontSize=18,
        spaceAfter=5
    )
    centered = ParagraphStyle(name="Centered", parent=styles["Normal"], alignment=TA_CENTER)
    
    elements = []
    elements.append(Paragraph(school_name, title_style))
    elements.append(Paragraph(title, centered))
    if sub_title:
        elements.append(Paragraph(sub_title, centered))
    elements.append(Spacer(1, 5*mm))
    
    # Extract unique time slots and sort them
    time_slots = sorted(list(set((e["start_time"], e["end_time"]) for e in entries)), key=lambda x: x[0])
    
    # Days
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    # Build Table Data
    header = ["Time"] + days
    table_data = [header]
    
    # Determine if any entry has a 'break' label (to identify slots that are breaks)
    # Or we can just highlight slots that are empty across all days as potential breaks?
    # Better: if it's a teacher timetable, we only show their subjects. 
    # If it's a class timetable, it's usually full.
    
    for start, end in time_slots:
        row = [f"<b>{start[:5]} - {end[:5]}</b>"]
        for day in days:
            # Find entry for this slot
            match = next((e for e in entries if e["day_of_week"] == day and e["start_time"] == start), None)
            if match:
                subject = match.get('subject_name', match.get('subjects', {}).get('name', 'N/A'))
                other_info = match.get("class_name", match.get("classes", {}).get("name", ""))
                
                content = f"<b>{subject}</b>"
                if other_info:
                    content += f"<br/>{other_info}"
                row.append(Paragraph(content, centered))
            else:
                row.append("")
        table_data.append(row)
        
    t = Table(table_data, colWidths=[25*mm] + [50*mm]*5)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
    ]))
    
    elements.append(t)
    
    # Add footer
    elements.append(Spacer(1, 10*mm))
    from datetime import datetime
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", centered))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer.read()
