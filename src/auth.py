"""
Authentication — JWT-based signup / login with SQLite
=====================================================
Lightweight auth layer using:
  - SQLite (zero-config, file-based DB)
  - bcrypt for password hashing
  - python-jose for JWT tokens
"""

from __future__ import annotations
import os
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, field_validator
from jose import jwt, JWTError
import bcrypt

# ── Config ─────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "users.db")

security = HTTPBearer()


# ── Request / Response models ──────────────────────────────────────────────
class SignupRequest(BaseModel):
    username: str
    email: str
    password: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters")
        return v

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v

    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    username: str
    email: str


# ── Database ───────────────────────────────────────────────────────────────
def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create users table if it doesn't exist."""
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


# ── Password hashing ──────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT ────────────────────────────────────────────────────────────────────
def create_token(email: str, username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": email,
        "username": username,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


# ── Auth dependency for protected routes ───────────────────────────────────
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """FastAPI dependency — extracts and validates the JWT from the Authorization header."""
    payload = decode_token(credentials.credentials)
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return {"email": email, "username": payload.get("username", "")}


# ── Signup / Login logic ───────────────────────────────────────────────────
def signup_user(req: SignupRequest) -> AuthResponse:
    conn = _get_db()
    # Check existing email
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (req.email,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=409, detail="Email already registered")

    pw_hash = hash_password(req.password)
    conn.execute(
        "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
        (req.username, req.email, pw_hash),
    )
    conn.commit()
    conn.close()

    token = create_token(req.email, req.username)
    return AuthResponse(token=token, username=req.username, email=req.email)


def login_user(req: LoginRequest) -> AuthResponse:
    conn = _get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (req.email.strip().lower(),)).fetchone()
    conn.close()

    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token(user["email"], user["username"])
    return AuthResponse(token=token, username=user["username"], email=user["email"])
