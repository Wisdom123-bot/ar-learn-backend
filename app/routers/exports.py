import io
import csv
import openpyxl
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from app.core.database import get_supabase

router = APIRouter(prefix="/exports", tags=["exports"])


def make_csv_response(data: list[dict], filename: str) -> StreamingResponse:
    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def make_excel_response(data: list[dict], filename: str) -> StreamingResponse:
    wb = openpyxl.Workbook()
    ws = wb.active
    if data:
        headers = list(data[0].keys())
        ws.append(headers)
        for row in data:
            ws.append([row[h] for h in headers])
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/students/{school_id}")
async def export_students(
    school_id: str,
    format: str = Query("csv", regex="^(csv|xlsx)$"),
):
    db = get_supabase()
    students = (
        db.table("students")
        .select("name, admission_number, access_code, classes(name)")
        .eq("school_id", school_id)
        .order("name")
        .execute()
        .data or []
    )
    for s in students:
        s["class"] = s["classes"]["name"] if s.get("classes") else ""
        del s["classes"]
    if format == "xlsx":
        return make_excel_response(students, "students.xlsx")
    return make_csv_response(students, "students.csv")


@router.get("/results/{school_id}")
async def export_results(
    school_id: str,
    term: str = Query(...),
    format: str = Query("csv", regex="^(csv|xlsx)$"),
):
    db = get_supabase()
    student_ids = [s["id"] for s in db.table("students").select("id").eq("school_id", school_id).execute().data]
    if not student_ids:
        return make_csv_response([], "results.csv")
    results = (
        db.table("results")
        .select("student_id, students(name), subjects(name), exam_type, term, score")
        .in_("student_id", student_ids)
        .eq("term", term)
        .execute()
        .data or []
    )
    flat = []
    for r in results:
        flat.append({
            "student": r["students"]["name"] if r.get("students") else r["student_id"],
            "subject": r["subjects"]["name"] if r.get("subjects") else r["subject_id"],
            "exam_type": r["exam_type"],
            "term": r["term"],
            "score": r["score"],
        })
    if format == "xlsx":
        return make_excel_response(flat, "results.xlsx")
    return make_csv_response(flat, "results.csv")


@router.get("/fees/{school_id}")
async def export_fees(
    school_id: str,
    term: str = Query(...),
    format: str = Query("csv", regex="^(csv|xlsx)$"),
):
    db = get_supabase()
    student_ids = [s["id"] for s in db.table("students").select("id").eq("school_id", school_id).execute().data]
    if not student_ids:
        return make_csv_response([], "fees.csv")
    balances = (
        db.table("fee_balances")
        .select("student_id, students(name), balance, cleared")
        .in_("student_id", student_ids)
        .eq("term", term)
        .execute()
        .data or []
    )
    flat = []
    for b in balances:
        flat.append({
            "student": b["students"]["name"] if b.get("students") else b["student_id"],
            "balance": b["balance"],
            "cleared": b["cleared"],
        })
    if format == "xlsx":
        return make_excel_response(flat, "fees.xlsx")
    return make_csv_response(flat, "fees.csv")