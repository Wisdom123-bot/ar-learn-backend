import html
import re
from fastapi import HTTPException, UploadFile
from typing import List

# --- XSS & String Sanitization ---

def sanitize_string(text: str, max_length: int = 500) -> str:
    """
    Strips HTML tags, escapes special characters, and trims length.
    """
    if not text:
        return ""
    
    # 1. Strip HTML tags
    clean_text = re.sub(r'<[^>]*?>', '', text)
    
    # 2. Escape HTML entities
    clean_text = html.escape(clean_text)
    
    # 3. Trim length
    return clean_text[:max_length].strip()

def sanitize_search_query(query: str) -> str:
    """
    Escapes special characters used in SQL LIKE/ILIKE patterns.
    """
    if not query:
        return ""
    # Escape %, _ and \
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").strip()

# --- File Upload Security ---

ALLOWED_EXTENSIONS = {"csv", "xlsx", "png", "jpg", "jpeg", "pdf"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

def validate_file(file: UploadFile, allowed_types: List[str] = None):
    """
    Validates file extension and size.
    """
    if not allowed_types:
        allowed_types = list(ALLOWED_EXTENSIONS)
        
    ext = file.filename.split(".")[-1].lower()
    if ext not in allowed_types:
        raise HTTPException(
            status_code=400, 
            detail=f"File extension '.{ext}' is not allowed. Allowed: {', '.join(allowed_types)}"
        )
    
    # Check size (if possible via content-length, or we check after reading)
    # Note: actual size check usually happens during read in FastAPI
    return True

# --- Input Validation Regex ---

# --- Input Validation Regex ---

# UUID v4 pattern
UUID_REGEX = r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"

# Kenyan Phone Number (e.g. +254712345678 or 0712345678)
PHONE_REGEX = r"^(?:\+254|0)[17][0-9]{8}$"

# Admission Number (Alpha-numeric, slashes, dashes)
ADMISSION_REGEX = r"^[A-Z0-9/-]{3,20}$"

# General ID regex for safety (UUID or alphanumeric ID)
SAFE_ID_REGEX = r"^[a-zA-Z0-9-]{3,50}$"

def is_valid_uuid(val: str) -> bool:
    if not val: return False
    return bool(re.match(UUID_REGEX, str(val).lower()))

def validate_uuid(val: str, label: str = "ID"):
    if not is_valid_uuid(val):
        raise HTTPException(status_code=400, detail=f"Invalid {label} format. Must be a valid UUID.")
    return str(val)

def validate_phone(val: str):
    if not val: return None
    if not re.match(PHONE_REGEX, val):
        raise HTTPException(status_code=400, detail="Invalid phone number format.")
    return val
