import io
import csv
import openpyxl
import random
import string
from PyPDF2 import PdfReader
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, status
from app.core.database import get_supabase

router = APIRouter(prefix="/import", tags=["bulk-import"])


def extract_names_from_pdf(file_bytes: bytes) -> list[dict]:
    """Extract student info from PDF. Returns list of dicts with name, admission_number (optional), year (optional)."""
    reader = PdfReader(io.BytesIO(file_bytes))
    extracted = []
    for page in reader.pages:
        text = page.extract_text()
        if not text:
            continue
        lines = text.split("\n")
        current_student = {}
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Check if line contains a label like "Name:", "Admission:", "Year:"
            if line.lower().startswith("name"):
                current_student["name"] = line.split(":", 1)[1].strip()
            elif line.lower().startswith("admission"):
                adm = line.split(":", 1)[1].strip()
                current_student["admission_number"] = adm if adm else None
            elif line.lower().startswith("year"):
                yr = line.split(":", 1)[1].strip()
                current_student["year"] = yr if yr else None
            else:
                # If no colon, treat whole line as a name (if it doesn't look like a number)
                if ":" not in line and not line.replace(" ", "").isdigit():
                    current_student["name"] = line
            # When we have at least a name, finalize and start a new student
            if "name" in current_student:
                extracted.append({
                    "name": current_student["name"],
                    "admission_number": current_student.get("admission_number"),
                    "year": current_student.get("year"),
                })
                current_student = {}
    # Fallback: if no structured data found, treat each non-empty line as a name
    if not extracted:
        for page in reader.pages:
            text = page.extract_text()
            if text:
                for line in text.split("\n"):
                    line = line.strip()
                    if line and not line.replace(" ", "").isdigit() and len(line) > 2:
                        cleaned = " ".join(w for w in line.split() if not w.isdigit())
                        if cleaned:
                            extracted.append({"name": cleaned, "admission_number": None, "year": None})
    return extracted


def extract_names_from_excel(file_bytes: bytes) -> list[str]:
    """Read first column of Excel file (names)."""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
    sheet = wb.active
    names = []
    for row in sheet.iter_rows(min_row=1, max_col=1, values_only=True):
        if row and row[0] and isinstance(row[0], str):
            name = row[0].strip()
            if name.lower() not in ("name", "student name", "names", ""):
                names.append(name)
    return names


def extract_names_from_csv(file_bytes: bytes) -> list[str]:
    """Read first column of CSV (names)."""
    text = file_bytes.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    names = []
    for row in reader:
        if row and row[0].strip():
            name = row[0].strip()
            if name.lower() not in ("name", "student name", "names", ""):
                names.append(name)
    return names


@router.post("/students")
async def import_students(
    school_id: str = Form(...),
    class_id: str = Form(...),
    file: UploadFile = File(...),
):
    db = get_supabase()

    # Validate school and class
    school = db.table("schools").select("id").eq("id", school_id).execute()
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")
    cls = db.table("classes").select("id").eq("id", class_id).eq("school_id", school_id).execute()
    if not cls.data:
        raise HTTPException(status_code=404, detail="Class not found or not in this school")

    file_bytes = await file.read()
    filename = file.filename.lower() if file.filename else ""

    inserted = 0
    if filename.endswith(".pdf"):
        # Extract structured student data
        student_data = extract_names_from_pdf(file_bytes)
        for student in student_data:
            name = student["name"]
            admission_number = student.get("admission_number")
            # Generate admission number if missing
            if not admission_number:
                prefix = school_id[:4].upper()
                count = db.table("students").select("id", count="exact").eq("school_id", school_id).execute().count or 0
                admission_number = f"{prefix}{count + inserted + 1:04d}"
            access_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            data = {
                "school_id": school_id,
                "class_id": class_id,
                "admission_number": admission_number,
                "name": name,
                "access_code": access_code,
            }
            try:
                db.table("students").insert(data).execute()
                inserted += 1
            except Exception:
                continue

    elif filename.endswith(".xlsx") or filename.endswith(".xls"):
        names = extract_names_from_excel(file_bytes)
        for name in names:
            prefix = school_id[:4].upper()
            count = db.table("students").select("id", count="exact").eq("school_id", school_id).execute().count or 0
            admission_number = f"{prefix}{count + inserted + 1:04d}"
            access_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            data = {
                "school_id": school_id,
                "class_id": class_id,
                "admission_number": admission_number,
                "name": name,
                "access_code": access_code,
            }
            try:
                db.table("students").insert(data).execute()
                inserted += 1
            except Exception:
                continue

    elif filename.endswith(".csv"):
        names = extract_names_from_csv(file_bytes)
        for name in names:
            prefix = school_id[:4].upper()
            count = db.table("students").select("id", count="exact").eq("school_id", school_id).execute().count or 0
            admission_number = f"{prefix}{count + inserted + 1:04d}"
            access_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            data = {
                "school_id": school_id,
                "class_id": class_id,
                "admission_number": admission_number,
                "name": name,
                "access_code": access_code,
            }
            try:
                db.table("students").insert(data).execute()
                inserted += 1
            except Exception:
                continue
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use PDF, Excel (.xlsx) or CSV.")

    if inserted == 0:
        return {"message": "No students were imported. Check the file format.", "count": 0}

    return {"message": f"{inserted} students imported successfully", "count": inserted}
@router.post("/results")
async def import_results(
    school_id: str = Form(...),
    teacher_id: str = Form(...),
    file: UploadFile = File(...),
    class_id: Optional[str] = Form(None),
):
    db = get_supabase()

    # Validate school and teacher
    school = db.table("schools").select("id").eq("id", school_id).execute()
    if not school.data:
        raise HTTPException(status_code=404, detail="School not found")
    teacher = db.table("teachers").select("id, school_id").eq("id", teacher_id).eq("school_id", school_id).execute()
    if not teacher.data:
        raise HTTPException(status_code=403, detail="Teacher not in this school")

    file_bytes = await file.read()
    filename = file.filename.lower() if file.filename else ""

    rows = []
    if filename.endswith(".csv"):
        text = file_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    elif filename.endswith(".xlsx") or filename.endswith(".xls"):
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
        sheet = wb.active
        headers = [cell.value for cell in sheet[1]]  # first row as headers
        for row in sheet.iter_rows(min_row=2, values_only=True):
            rows.append(dict(zip(headers, row)))
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use CSV or Excel (.xlsx)")

    if not rows:
        raise HTTPException(status_code=400, detail="No data found in file")

    # Normalize column names (lowercase, strip)
    normalized = []
    for r in rows:
        nr = {k.strip().lower(): v for k, v in r.items() if k}
        normalized.append(nr)

    # Expected columns: admission_number (or student_id), subject, score, exam_type (CAT/EXAM), term, academic_year
    inserted = 0
    for row in normalized:
        # Find student
        admission = row.get("admission_number") or row.get("admission no") or row.get("adm")
        student_id = row.get("student_id") or row.get("student id")
        if not admission and not student_id:
            continue  # skip rows without identifier

        if admission:
            student = db.table("students").select("id, class_id").eq("admission_number", str(admission)).eq("school_id", school_id).single().execute()
        else:
            student = db.table("students").select("id, class_id").eq("id", str(student_id)).eq("school_id", school_id).single().execute()

        if not student.data:
            continue

        # If class_id is specified, verify student belongs to that class (optional enforcement)
        if class_id and student.data["class_id"] != class_id:
            continue

        # Subject
        subject_name = row.get("subject") or row.get("subject_name")
        if not subject_name:
            continue
        subject = db.table("subjects").select("id").ilike("name", str(subject_name).strip()).single().execute()
        if not subject.data:
            continue

        # Score
        score_str = row.get("score") or row.get("marks") or row.get("percentage")
        if score_str is None:
            continue
        try:
            score = float(score_str)
        except ValueError:
            continue

        # Exam type
        exam_type = row.get("exam_type") or row.get("exam") or "EXAM"
        if exam_type.upper() not in ("CAT", "EXAM"):
            exam_type = "EXAM"  # default

        term = row.get("term") or "Unknown Term"
        academic_year = row.get("academic_year") or row.get("year") or "2024"

        data = {
            "student_id": student.data["id"],
            "subject_id": subject.data["id"],
            "class_id": student.data["class_id"],
            "exam_type": exam_type.upper(),
            "term": str(term).strip(),
            "academic_year": str(academic_year).strip(),
            "score": score,
            "remarks": row.get("remarks") or "",
            "submitted_by": teacher_id,
        }
        try:
            db.table("results").insert(data).execute()
            inserted += 1
        except Exception:
            continue

    return {"message": f"{inserted} results imported successfully", "count": inserted}    