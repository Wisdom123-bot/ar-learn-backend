import os
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional
from passlib.context import CryptContext

# Use the secret key from environment variables
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_YEARS = 10

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash a password using passlib."""
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(password, hashed)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a signed JWT token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_admin_token(username: str):
    """
    Create a signed JWT token for admin users.
    Embeds role='admin' so the admin auth dependency can validate it.
    Uses a longer expiry (8 hours) suitable for an admin session.
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=8)
    to_encode = {
        "sub": username,
        "role": "admin",
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict):
    """Create a very long-lived refresh token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=365 * REFRESH_TOKEN_EXPIRE_YEARS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str):
    """Decode and validate a JWT token (access or refresh)."""
    try:
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if decoded_token["exp"] < datetime.now(timezone.utc).timestamp():
            return None
        return decoded_token
    except jwt.PyJWTError:
        return None

def is_admin_token(token: str) -> bool:
    """Returns True if the token is a valid admin token."""
    payload = decode_token(token)
    return payload is not None and payload.get("role") == "admin"