"""
ARPS — QR-Code Transcript Verification Engine  (v3 — fixed)

KEY FIXES:
  1. URL generation no longer uses url_for(_external=True) inside PDF.
     Instead, the base URL is passed in at call time so it works correctly
     whether the PDF is generated on localhost or a production server.

  2. Token separator changed from "." to "--" so URL-encoding never
     corrupts the signed token string in QR codes.

  3. hmac.new() → hmac.new() is correct Python — kept as-is.
"""
from __future__ import annotations
import io
import secrets
import hashlib
import hmac as _hmac
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict

import qrcode
from PIL import Image as PILImage

# Separator between token and HMAC signature — must not appear in hex tokens
# Using "--" instead of "." avoids URL-encoding issues with some QR scanners
_SIGN_SEP = "--"


def _get_secret() -> bytes:
    """Derive a stable signing secret from the Flask app SECRET_KEY."""
    try:
        from flask import current_app
        key = current_app.config.get("SECRET_KEY", "arps-secret-fallback")
    except RuntimeError:
        # Outside app context (e.g. during testing)
        key = "arps-secret-fallback"
    return hashlib.sha256(f"arps-transcript-sign:{key}".encode()).digest()


def generate_token() -> str:
    """Return a cryptographically random 64-char hex token."""
    return secrets.token_hex(32)


def sign_token(token: str) -> str:
    """
    Return  token--HMAC  (the value embedded in QR URLs).
    Uses first 20 hex chars of HMAC-SHA256 for the signature.
    """
    sig = _hmac.new(_get_secret(), token.encode(), hashlib.sha256).hexdigest()[:20]
    return f"{token}{_SIGN_SEP}{sig}"


def verify_signed_token(signed: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a signed token from the QR URL.
    Accepts both '--' and '.' as separator for backwards compatibility.
    Returns (is_valid, raw_token) or (False, None).
    """
    # Normalise: support old '.' separator from previous versions
    if _SIGN_SEP in signed:
        sep = _SIGN_SEP
    elif "." in signed:
        sep = "."
    else:
        return False, None

    try:
        token, provided_sig = signed.rsplit(sep, 1)
    except ValueError:
        return False, None

    if not token:
        return False, None

    expected_sig = _hmac.new(
        _get_secret(), token.encode(), hashlib.sha256
    ).hexdigest()[:20]

    # Also check 16-char sig for backwards compatibility with v1 tokens
    expected_sig_16 = _hmac.new(
        _get_secret(), token.encode(), hashlib.sha256
    ).hexdigest()[:16]

    if _hmac.compare_digest(expected_sig, provided_sig):
        return True, token
    if _hmac.compare_digest(expected_sig_16, provided_sig):
        return True, token

    return False, None


def build_verify_url(token: str, base_url: str = "") -> str:
    """
    Build the full public verification URL for a token.

    Args:
        token:    Raw (unsigned) token string.
        base_url: The base URL of your server, e.g. "http://192.168.1.5:5000"
                  or "https://arps.ibbul.edu.ng".
                  If empty, tries to get it from Flask request context.
                  Falls back to a placeholder the admin must configure.
    """
    signed = sign_token(token)

    if not base_url:
        # Try to get from Flask request context (works during HTTP requests)
        try:
            from flask import request as _req
            base_url = _req.host_url.rstrip("/")
        except RuntimeError:
            base_url = "http://localhost:5000"

    return f"{base_url}/verify/{signed}"


def generate_qr_png(verify_url: str, box_size: int = 6) -> bytes:
    """
    Generate a high-quality PNG QR code.
    Returns raw PNG bytes.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,   # 30% damage tolerance
        box_size=box_size,
        border=4,
    )
    qr.add_data(verify_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0B1F14", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


def create_transcript_token(
    student_id: int,
    generated_by_user_id: Optional[int] = None,
    expires_in_days: Optional[int] = None,
    note: str = "",
) -> "TranscriptToken":
    """
    Create and persist a new TranscriptToken.
    Returns the model instance (not yet committed — caller must commit).
    """
    from app import db
    from models import TranscriptToken

    raw_token  = generate_token()
    expires_at = (
        datetime.utcnow() + timedelta(days=expires_in_days)
        if expires_in_days else None
    )
    tt = TranscriptToken(
        token        = raw_token,
        student_id   = student_id,
        generated_by = generated_by_user_id,
        generated_at = datetime.utcnow(),
        expires_at   = expires_at,
        note         = note or "Official Transcript",
    )
    db.session.add(tt)
    db.session.flush()
    return tt


def lookup_token(raw_token: str) -> Optional["TranscriptToken"]:
    """Fetch TranscriptToken by its raw token string."""
    from models import TranscriptToken
    return TranscriptToken.query.filter_by(token=raw_token).first()


def record_scan(tt: "TranscriptToken"):
    """Increment scan count and record timestamp."""
    from app import db
    tt.scan_count   += 1
    tt.last_scanned  = datetime.utcnow()
    db.session.commit()
