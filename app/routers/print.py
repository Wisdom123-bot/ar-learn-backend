from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from typing import Optional
from app.core.database import get_supabase
from app.services.remark_generator import generate_professional_remark

router = APIRouter(prefix="/print", tags=["print"])


@router.get("/report/{student_id}", response_class=HTMLResponse)
async def print_report(
    student_id: str,
    term: str = Query(...),
    template_id: Optional[str] = Query(None),
):
    db = get_supabase()

    # Fetch student info
    student = db.table("students").select("*, classes(name, school_id)").eq("id", student_id).single().execute()
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found")
    s = student.data
    class_name = s["classes"]["name"] if s.get("classes") else ""
    school_id = s["classes"]["school_id"]
    school = db.table("schools").select("name, county").eq("id", school_id).single().execute()
    school_name = school.data["name"] if school.data else ""
    school_county = school.data["county"] if school.data else ""

    # Template styling (defaults)
    primary_color = "#1e3a8a"
    secondary_color = "#f0f4ff"
    logo_url = ""
    motto = ""
    phone = ""
    email = ""
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
            primary_color = t.get("primary_color", "#1e3a8a")
            secondary_color = t.get("secondary_color", "#f0f4ff")
            motto = t.get("motto", "")
            phone = t.get("phone", "")
            email = t.get("email", "")

            # Only use template logo if premium, otherwise fallback to school logo or none
            if is_premium:
                logo_url = t.get("logo_url", "") or logo_url
            
            show_attendance = t.get("show_attendance", True)
            show_fee_status = t.get("show_fee_status", True)
            show_teacher_remarks = t.get("show_teacher_remarks", True)
            show_overall_evaluation = t.get("show_overall_evaluation", True)

    # Results
    results = db.table("results").select("*, subjects(name), teachers(name)").eq("student_id", student_id).eq("term", term).eq("approval_status", "approved").execute().data or []
    total = sum(r["score"] for r in results)
    mean = round(total / len(results), 2) if results else 0

    subject_rows = ""
    for r in results:
        subj = r["subjects"]["name"] if r.get("subjects") else "Unknown"
        teacher_name = r["teachers"]["name"] if r.get("teachers") else "N/A"
        
        # Professional remark for each subject if enabled
        subj_remark = ""
        if show_teacher_remarks:
             # Use the actual teacher remark if it exists, otherwise use rule-based generation
             raw_remark = r.get("remarks", "")
             subj_remark = f"<div style='font-size: 0.75em; color: #666; margin-top: 4px; font-style: italic;'>{generate_professional_remark(s['name'], subj, r['score'], teacher_remark=raw_remark)}</div>"
        
        subject_rows += f"""
            <tr>
                <td>
                    <div style='font-weight: bold;'>{subj}</div>
                    <div style='font-size: 0.7em; color: #999;'>Teacher: {teacher_name}</div>
                    {subj_remark}
                </td>
                <td style='text-align:center; font-weight: bold;'>{r['score']}%</td>
            </tr>
        """

    # Attendance (conditionally)
    attendance_html = ""
    if show_attendance:
        att = db.table("attendance").select("status").eq("student_id", student_id).execute().data or []
        present = sum(1 for a in att if a["status"].lower() == "present")
        total_att = len(att)
        att_pct = round((present / total_att) * 100, 1) if total_att > 0 else 0
        attendance_html = f"""
        <div class="section">
            <h3>Attendance</h3>
            <p>Present: {present}/{total_att} days ({att_pct}%)</p>
        </div>"""

    # Fee status (conditionally, safe query)
    fee_html = ""
    if show_fee_status:
        fee_result = db.table("fee_balances").select("balance, cleared").eq("student_id", student_id).eq("term", term).limit(1).execute()
        fee_data = fee_result.data[0] if fee_result.data else {"balance": 0, "cleared": False}
        balance = fee_data["balance"]
        cleared = fee_data["cleared"]
        fee_html = f"""
        <div class="section">
            <h3>Fee Status</h3>
            <p>Balance: KES {balance:,.2f} <span class="badge {'cleared' if cleared else 'not-cleared'}">{'Cleared' if cleared else 'Not Cleared'}</span></p>
        </div>"""

    # AI overall evaluation / Executive Summary (conditionally)
    evaluation_html = ""
    if show_overall_evaluation:
        # Instead of just rule-based, we'll try to generate a proper AI summary if possible
        # For performance, we'll use a wrapper that might call our AI service
        try:
            from app.services.ai_summary_service import generate_student_summary
            import asyncio
            
            # Using loop.run_until_complete is risky in FastAPI but let's assume we can get it
            # Actually, since this is a sync endpoint (async def but HTMLResponse), we can use await
            ai_remark = await generate_student_summary(student_id, term)
        except Exception:
            # Fallback to rule-based if AI fails
            ai_remark = generate_professional_remark(s["name"], "overall performance", mean)
            
        evaluation_html = f"""
        <div class="section">
            <h3>Executive Summary & Evaluation</h3>
            <p style="line-height: 1.6; color: #444;">{ai_remark}</p>
        </div>"""

        # Teacher remarks (conditionally)
    remarks_html = ""
    if show_teacher_remarks:
        remark_entries = db.table("class_teacher_remarks").select("remark").eq("student_id", student_id).eq("class_id", s.get("class_id", "")).eq("term", term).execute().data or []
        if remark_entries:
            remarks_html = "<div class='section'><h3>Class Teacher Remarks</h3>"
            for rem in remark_entries:
                remarks_html += f"<p>{rem['remark']}</p>"
            remarks_html += "</div>"

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Report Card - {s['name']}</title>
        <style>
            @media print {{
                body {{ margin: 0; }}
                .no-print {{ display: none; }}
            }}
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 800px;
                margin: 20px auto;
                padding: 20px;
                color: #333;
            }}
            .header {{ text-align: center; margin-bottom: 20px; border-bottom: 2px solid {primary_color}; padding-bottom: 20px; }}
            .header h1 {{ margin: 0; font-size: 28px; color: {primary_color}; text-transform: uppercase; }}
            .header .motto {{ font-style: italic; color: #555; margin: 4px 0; font-size: 0.9em; }}
            .header .contact {{ font-size: 0.8em; color: #777; margin-top: 8px; }}
            .section {{ margin-bottom: 25px; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 10px; }}
            th, td {{ border: 1px solid #ccc; padding: 10px; text-align: left; }}
            th {{ background: {primary_color}; color: white; text-transform: uppercase; font-size: 0.85em; }}
            .score {{ text-align: center; }}
            .footer {{ margin-top: 40px; font-size: 0.85em; color: #777; border-top: 1px solid #eee; pt: 10px; }}
            .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.8em; margin-left: 5px; font-weight: bold; }}
            .cleared {{ background: #d1fae5; color: #065f46; }}
            .not-cleared {{ background: #fee2e2; color: #991b1b; }}
            h3 {{ border-left: 4px solid {primary_color}; padding-left: 10px; margin-bottom: 15px; color: {primary_color}; }}
        </style>
    </head>
    <body>
        <div class="header">
            {f'<img src="{logo_url}" alt="Logo" style="max-height: 80px; margin-bottom: 10px;">' if logo_url else ''}
            <h1>{school_name}</h1>
            {f'<p class="motto">"{motto}"</p>' if motto else ''}
            <p>{school_county} County</p>
            <div class="contact">
                {f'<span>📞 {phone}</span>' if phone else ''}
                {f'<span style="margin-left:15px;">✉️ {email}</span>' if email else ''}
            </div>
            <h2 style="margin-top:20px; color:{primary_color}; letter-spacing: 2px; text-transform: uppercase;">Student Report Card</h2>
        </div>

        <div class="section" style="display: grid; grid-template-cols: 1fr 1fr; gap: 20px;">
            <div>
                <p><strong>Student Name:</strong> {s['name']}</p>
                <p><strong>Admission No:</strong> {s['admission_number']}</p>
            </div>
            <div>
                <p><strong>Class:</strong> {class_name}</p>
                <p><strong>Academic Term:</strong> {term}</p>
            </div>
        </div>

        <div class="section">
            <h3>Academic Performance</h3>
            <table>
                <thead>
                    <tr><th>Subject & Teacher Remarks</th><th class="score" style="width: 100px;">Score (%)</th></tr>
                </thead>
                <tbody>
                    {subject_rows}
                    <tr style="font-weight:bold; background: {secondary_color}; border-top: 2px solid {primary_color};">
                        <td style="text-align: right; padding-right: 20px;">OVERALL MEAN SCORE</td>
                        <td class="score">{mean}%</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            {attendance_html}
            {fee_html}
        </div>
        
        {remarks_html}
        {evaluation_html}

        <div class="footer">
            <div style="display: flex; justify-content: space-between;">
                <p>Official School Document</p>
                <p>Generated on: <span id="date"></span></p>
            </div>
        </div>

        <script>
            document.getElementById('date').textContent = new Date().toLocaleDateString();
            window.onload = function() {{
                window.print();
            }};
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@router.get("/fee/{student_id}", response_class=HTMLResponse)
async def print_fee_statement(student_id: str, term: str = Query(...)):
    db = get_supabase()

    student = db.table("students").select("name, admission_number, classes(name)").eq("id", student_id).single().execute()
    if not student.data:
        raise HTTPException(status_code=404, detail="Student not found")
    s = student.data
    class_name = s["classes"]["name"] if s.get("classes") else ""

    # Safe fee balance query
    balance_result = db.table("fee_balances").select("*").eq("student_id", student_id).eq("term", term).limit(1).execute()
    bal = balance_result.data[0] if balance_result.data else None

    payments = db.table("fee_payments").select("*").eq("student_id", student_id).eq("term", term).order("payment_date", desc=True).execute().data or []

    payment_rows = ""
    total_paid = 0
    for p in payments:
        payment_rows += f"<tr><td>{p['payment_date']}</td><td>{p['receipt_number']}</td><td style='text-align:right'>KES {p['amount']:,.2f}</td></tr>"
        total_paid += p['amount']

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Fee Statement - {s['name']}</title>
        <style>
            @media print {{
                body {{ margin: 0; }}
            }}
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 700px;
                margin: 20px auto;
                padding: 20px;
                color: #333;
            }}
            .header {{ text-align: center; margin-bottom: 20px; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 15px; }}
            th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
            th {{ background: #f0f0f0; }}
            .total {{ font-weight: bold; background: #fafafa; }}
            .cleared {{ color: green; font-weight: bold; }}
            .outstanding {{ color: red; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>Fee Statement</h2>
        </div>
        <p><strong>Name:</strong> {s['name']}</p>
        <p><strong>Admission No:</strong> {s['admission_number']}</p>
        <p><strong>Class:</strong> {class_name}</p>
        <p><strong>Term:</strong> {term}</p>

        <h3>Payment History</h3>
        <table>
            <thead>
                <tr><th>Date</th><th>Receipt Number</th><th style="text-align:right">Amount</th></tr>
            </thead>
            <tbody>
                {payment_rows}
                <tr class="total">
                    <td colspan="2">Total Paid</td>
                    <td style="text-align:right">KES {total_paid:,.2f}</td>
                </tr>
            </tbody>
        </table>

        <h3>Balance</h3>
        <p>Outstanding Balance: <span class="{'cleared' if bal and bal['cleared'] else 'outstanding'}">KES {bal['balance'] if bal else 0:,.2f}</span></p>
        <p>Status: <strong>{'Cleared' if bal and bal['cleared'] else 'Not Cleared'}</strong></p>

        <p style="font-size:0.8em; color:#666;">Printed on: <span id="date"></span></p>
        <script>
            document.getElementById('date').textContent = new Date().toLocaleDateString();
            window.onload = function() {{
                window.print();
            }};
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)