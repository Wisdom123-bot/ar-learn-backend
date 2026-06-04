import io
import pickle
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from app.core.database import get_supabase
from app.utils.cache import get_cache, set_cache, redis_available
import threading
import time

MODEL_FILENAME = "risk_model_global.pkl"       # single global model
STORAGE_BUCKET = "models"
CACHE_KEY = "ml_risk_model_global"             # Redis cache key for the global model

def _get_storage():
    """Return Supabase storage client."""
    db = get_supabase()
    return db.storage()

def load_model():
    """Load global model from storage, or None if not available."""
    try:
        storage = _get_storage()
        file_bytes = storage.from_(STORAGE_BUCKET).download(MODEL_FILENAME)
        return pickle.loads(file_bytes)
    except Exception:
        return None

def save_model(model):
    """Save global model to storage."""
    try:
        storage = _get_storage()
        model_bytes = pickle.dumps(model)
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

    # Previous term – calculate previous term name
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

def train_model_async(school_id: str = None):
    """
    Train a global model on data from ALL schools.
    The school_id parameter is kept for backward compatibility but is ignored;
    training always uses every available school.
    """
    def _train():
        db = get_supabase()
        # Get ALL students from every school
        students = db.table("students").select("id, class_id").execute().data
        if not students or len(students) < 50:
            print("ML: Not enough total students to train (need ≥50).")
            return

        # Fetch all results for those students
        student_ids = [s["id"] for s in students]
        all_results = db.table("results").select("student_id, subject_id, term, score").in_("student_id", student_ids).execute().data
        if not all_results:
            return

        unique_terms = list(set(r["term"] for r in all_results))
        if len(unique_terms) < 2:
            return

        # Sort terms chronologically
        sorted_terms = sorted(unique_terms, key=lambda t: (int(t.split(" ")[2]), int(t.split(" ")[1])))
        current_term = sorted_terms[-1]
        previous_term = sorted_terms[-2]

        subjects = db.table("subjects").select("id").execute().data
        subject_ids = [s["id"] for s in subjects]

        X = []
        y = []

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
            print("ML: Not enough training samples (need ≥50).")
            return

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        model = LogisticRegression(max_iter=1000)
        model.fit(X_train, y_train)
        accuracy = model.score(X_test, y_test)
        print(f"ML: Global model trained with accuracy {accuracy:.2f} on {len(X)} samples from all schools.")

        # Save globally
        save_model(model)

        # Cache in Redis (if available)
        if redis_available:
            set_cache(CACHE_KEY, pickle.dumps(model).hex(), ttl=86400*30)  # 30 days

    thread = threading.Thread(target=_train)
    thread.daemon = True
    thread.start()

def predict_risk(student_id, subject_id, term):
    """Return risk probability (0-1) for a student in a subject, or None if model not available."""
    model = None
    # Try Redis first
    if redis_available:
        cached = get_cache(CACHE_KEY)
        if cached:
            model = pickle.loads(bytes.fromhex(cached))
    if model is None:
        model = load_model()
        if model and redis_available:
            set_cache(CACHE_KEY, pickle.dumps(model).hex(), ttl=86400*30)

    if model is None:
        return None

    db = get_supabase()
    features = prepare_features(student_id, subject_id, term, db)
    if features is None:
        return None
    proba = model.predict_proba([features])[0]
    return float(proba[1])  # probability of class 1 (fail)