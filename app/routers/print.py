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
    show_attendance = True
    show_fee_status = True
    show_teacher_remarks = True
    show_overall_evaluation = True

    if template_id:
        template = db.table("report_templates").select("*").eq("id", template_id).eq("school_id", school_id).single().execute()
        if template.data:
            t = template.data
            primary_color = t.get("primary_color", "#1e3a8a")
            secondary_color = t.get("secondary_color", "#f0f4ff")
            logo_url = t.get("logo_url", "")
            show_attendance = t.get("show_attendance", True)
            show_fee_status = t.get("show_fee_status", True)
            show_teacher_remarks = t.get("show_teacher_remarks", True)
            show_overall_evaluation = t.get("show_overall_evaluation", True)

    # Results
    results = db.table("results").select("*, subjects(name)").eq("student_id", student_id).eq("term", term).eq("approval_status", "approved").execute().data or []
    total = sum(r["score"] for r in results)
    mean = round(total / len(results), 2) if results else 0

    subject_rows = ""
    for r in results:
        subj = r["subjects"]["name"] if r.get("subjects") else "Unknown"
        subject_rows += f"<tr><td>{subj}</td><td style='text-align:center'>{r['score']}</td></tr>"

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

    # Fee status (conditionally)
    fee_html = ""
    if show_fee_status:
        fee = db.table("fee_balances").select("balance, cleared").eq("student_id", student_id).eq("term", term).single().execute()
        balance = fee.data["balance"] if fee.data else 0
        cleared = fee.data["cleared"] if fee.data else False
        fee_html = f"""
        <div class="section">
            <h3>Fee Status</h3>
            <p>Balance: KES {balance:,.2f} <span class="badge {'cleared' if cleared else 'not-cleared'}">{'Cleared' if cleared else 'Not Cleared'}</span></p>
        </div>"""

    # AI overall remark (conditionally)
    evaluation_html = ""
    if show_overall_evaluation:
        ai_remark = generate_professional_remark(s["name"], "overall performance", mean)
        evaluation_html = f"""
        <div class="section">
            <h3>Overall Evaluation</h3>
            <p>{ai_remark}</p>
        </div>"""

    # Teacher remarks (conditionally)
    remarks_html = ""
    if show_teacher_remarks:
        remark_entries = db.table("class_teacher_remarks").select("remark").eq("student_id", student_id).eq("class_id", s["classes"]["id"] if s.get("classes") else "").eq("term", term).execute().data or []
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
            .header {{ text-align: center; margin-bottom: 20px; }}
            .header h1 {{ margin: 0; font-size: 24px; color: {primary_color}; }}
            .header p {{ margin: 4px 0; color: #666; }}
            .section {{ margin-bottom: 20px; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 10px; }}
            th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
            th {{ background: {primary_color}; color: white; }}
            .score {{ text-align: center; }}
            .footer {{ margin-top: 30px; font-size: 0.9em; color: #555; }}
            .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.8em; margin-left: 5px; }}
            .cleared {{ background: #d4edda; color: #155724; }}
            .not-cleared {{ background: #f8d7da; color: #721c24; }}
        </style>
    </head>
    <body>
        <div class="header">
            {f'<img src="{logo_url}" alt="Logo" style="max-height: 60px; margin-bottom: 10px;">' if logo_url else ''}
            <h1>{school_name}</h1>
            <p>{school_county} County</p>
            <h2 style="color:{primary_color};">Student Report Card</h2>
        </div>

        <div class="section">
            <p><strong>Name:</strong> {s['name']}</p>
            <p><strong>Admission No:</strong> {s['admission_number']}</p>
            <p><strong>Class:</strong> {class_name}</p>
            <p><strong>Term:</strong> {term}</p>
        </div>

        <div class="section">
            <h3 style="color:{primary_color};">Subject Scores</h3>
            <table>
                <thead>
                    <tr><th>Subject</th><th class="score">Score (%)</th></tr>
                </thead>
                <tbody>
                    {subject_rows}
                    <tr style="font-weight:bold; background: {secondary_color};">
                        <td>Mean Score</td>
                        <td class="score">{mean}</td>
                    </tr>
                </tbody>
            </table>
        </div>

        {attendance_html}
        {fee_html}
        {remarks_html}
        {evaluation_html}

        <div class="footer">
            <p>Printed on: <span id="date"></span></p>
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

    balance = db.table("fee_balances").select("*").eq("student_id", student_id).eq("term", term).single().execute()
    bal = balance.data if balance.data else None

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