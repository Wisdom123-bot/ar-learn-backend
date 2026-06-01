import io
import pickle
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from app.core.database import get_supabase
from app.utils.cache import get_cache, set_cache, redis_available
import threading
import time

MODEL_FILENAME = "risk_model.pkl"
STORAGE_BUCKET = "models"

def _get_storage():
    """Return Supabase storage client."""
    db = get_supabase()
    return db.storage()

def load_model():
    """Load model from storage, or None if not available."""
    try:
        storage = _get_storage()
        # Check if file exists
        # For now, we can try to download; if fails, return None.
        file_bytes = storage.from_(STORAGE_BUCKET).download(MODEL_FILENAME)
        return pickle.loads(file_bytes)
    except Exception:
        return None

def save_model(model):
    """Save model to storage."""
    try:
        storage = _get_storage()
        model_bytes = pickle.dumps(model)
        # Upload to bucket; create bucket if needed
        storage.from_(STORAGE_BUCKET).upload(MODEL_FILENAME, model_bytes, {"upsert": "true"})
    except Exception as e:
        print(f"ML: Failed to save model: {e}")

def prepare_features(student_id, subject_id, term, db):
    """Extract feature vector for a single student-subject pair."""
    # Fetch student data
    student = db.table("students").select("id, class_id").eq("id", student_id).single().execute().data
    if not student:
        return None
    class_id = student["class_id"]

    # Current term results for this subject
    curr_result = db.table("results").select("score").eq("student_id", student_id).eq("subject_id", subject_id).eq("term", term).maybe_single().execute()
    current_score = curr_result.data["score"] if curr_result.data else 0

    # Previous term – we need to calculate previous term name
    parts = term.split(" ")
    term_num = int(parts[1])
    year = int(parts[2])
    if term_num > 1:
        prev_term = f"Term {term_num-1} {year}"
    else:
        prev_term = f"Term 3 {year-1}"
    prev_result = db.table("results").select("score").eq("student_id", student_id).eq("subject_id", subject_id).eq("term", prev_term).maybe_single().execute()
    previous_score = prev_result.data["score"] if prev_result.data else 0

    score_change = current_score - previous_score

    # Attendance percentage
    att_records = db.table("attendance").select("status").eq("student_id", student_id).execute().data or []
    present = sum(1 for a in att_records if a["status"].lower() == "present")
    total = len(att_records)
    att_pct = (present / total) * 100 if total > 0 else 100

    # Discipline counts
    disc_records = db.table("discipline_records").select("category").eq("student_id", student_id).execute().data or []
    minor = sum(1 for d in disc_records if d["category"] == "Minor")
    major = sum(1 for d in disc_records if d["category"] == "Major")
    positive = sum(1 for d in disc_records if d["category"] == "Positive")

    # CBC competency average (if table exists)
    cbc_avg = 0
    try:
        cbc = db.table("cbc_assessments").select("level").eq("student_id", student_id).eq("subject_id", subject_id).execute().data or []
        mapping = {"EE": 4, "ME": 3, "AE": 2, "BE": 1}
        cbc_avg = sum(mapping.get(c["level"], 0) for c in cbc) / len(cbc) if cbc else 0
    except:
        pass

    # Class mean for this subject
    class_students = db.table("students").select("id").eq("class_id", class_id).execute().data
    class_ids = [s["id"] for s in class_students]
    class_results = db.table("results").select("score").in_("student_id", class_ids).eq("subject_id", subject_id).eq("term", term).execute().data or []
    class_mean = sum(r["score"] for r in class_results) / len(class_results) if class_results else 0

    # Student overall mean
    overall = db.table("results").select("score").eq("student_id", student_id).eq("term", term).execute().data or []
    overall_mean = sum(r["score"] for r in overall) / len(overall) if overall else 0

    return [
        current_score,
        previous_score,
        score_change,
        att_pct,
        minor,
        major,
        positive,
        cbc_avg,
        class_mean,
        overall_mean,
    ]

def train_model_async(school_id: str):
    """Train model in a background thread."""
    def _train():
        db = get_supabase()
        # Get all students of school
        students = db.table("students").select("id, class_id").eq("school_id", school_id).execute().data
        if not students or len(students) < 50:
            # Not enough data
            return

        # We need historical data: for each student-subject pair, we need current term and next term result (to create label)
        # This requires at least two terms of data. We'll use the most recent two terms in the database for this school.
        terms = db.table("results").select("term").eq("student_id", students[0]["id"]).order("term").limit(2).execute().data  # not ideal
        # Simpler: fetch all results for school, group by student+subject, try to find pairs where we have term T and term T+1.
        # For demo, we'll assume we have at least two terms and use a simple approach: term1 and term2 (the two most common terms).
        # We'll implement a robust term pairing later, but for now, we just skip if less than 2 distinct terms exist.
        all_results = db.table("results").select("student_id, subject_id, term, score").in_("student_id", [s["id"] for s in students]).execute().data
        unique_terms = list(set(r["term"] for r in all_results))
        if len(unique_terms) < 2:
            return

        # Choose the two most recent terms (based on term ordering - we need a function to sort terms)
        sorted_terms = sorted(unique_terms, key=lambda t: (int(t.split(" ")[2]), int(t.split(" ")[1])))
        current_term = sorted_terms[-1]
        previous_term = sorted_terms[-2]

        X = []
        y = []
        subjects = db.table("subjects").select("id").execute().data
        subject_ids = [s["id"] for s in subjects]

        for student in students:
            for subj in subject_ids:
                # Features from previous_term
                features = prepare_features(student["id"], subj, previous_term, db)
                if features is None:
                    continue
                # Label: did student fail this subject in current_term?
                curr_score = db.table("results").select("score").eq("student_id", student["id"]).eq("subject_id", subj).eq("term", current_term).maybe_single().execute()
                if curr_score.data is None:
                    continue
                label = 1 if curr_score.data["score"] < 50 else 0
                X.append(features)
                y.append(label)

        if len(X) < 50:
            return  # need minimum samples

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        model = LogisticRegression(max_iter=1000)
        model.fit(X_train, y_train)
        accuracy = model.score(X_test, y_test)
        print(f"ML: Model trained with accuracy {accuracy:.2f} on {len(X)} samples.")
        save_model(model)

        # Cache model in Redis for fast inference (if available)
        if redis_available:
            set_cache("ml_risk_model", pickle.dumps(model).hex(), ttl=86400*30)  # 30 days

    thread = threading.Thread(target=_train)
    thread.daemon = True
    thread.start()

def predict_risk(student_id, subject_id, term):
    """Return risk probability (0-1) for a student in a subject, or None if model not available."""
    model = None
    # Try Redis first
    if redis_available:
        cached = get_cache("ml_risk_model")
        if cached:
            model = pickle.loads(bytes.fromhex(cached))
    if model is None:
        model = load_model()
        if model and redis_available:
            set_cache("ml_risk_model", pickle.dumps(model).hex(), ttl=86400*30)

    if model is None:
        return None

    db = get_supabase()
    features = prepare_features(student_id, subject_id, term, db)
    if features is None:
        return None
    proba = model.predict_proba([features])[0]
    return float(proba[1])  # probability of class 1 (fail)