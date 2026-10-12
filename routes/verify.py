"""
ARPS — Public Transcript Verification Portal
No login required. Anyone with a QR URL can verify a transcript.
"""
from datetime import datetime
from flask import Blueprint, render_template, request
from qr_verify import verify_signed_token, lookup_token, record_scan
from engine import compute_cgpa

verify_bp = Blueprint("verify", __name__)


@verify_bp.route("/verify")
def verify_landing():
    """Public landing page — enter a token manually or scan QR."""
    return render_template("verify/landing.html", now=datetime.utcnow())


@verify_bp.route("/verify/<signed_token>")
def public_verify(signed_token: str):
    """
    Public verification endpoint embedded in QR codes.
    Validates signature, looks up token, shows read-only result.
    """
    now = datetime.utcnow()

    # 1. Validate HMAC signature
    sig_ok, raw_token = verify_signed_token(signed_token)
    if not sig_ok or not raw_token:
        return render_template("verify/result.html",
            status="invalid",
            reason="The QR code signature is invalid or has been tampered with.",
            student=None, cgpa_data=None, token=None, now=now,
        ), 400

    # 2. Look up database record
    tt = lookup_token(raw_token)
    if not tt:
        return render_template("verify/result.html",
            status="invalid",
            reason="This transcript token does not exist in our records.",
            student=None, cgpa_data=None, token=None, now=now,
        ), 404

    # 3. Check revocation
    if tt.is_revoked:
        return render_template("verify/result.html",
            status="revoked",
            reason="This transcript has been officially revoked by the institution.",
            student=tt.student, cgpa_data=None, token=tt, now=now,
        ), 410

    # 4. Check expiry
    if tt.expires_at and now > tt.expires_at:
        return render_template("verify/result.html",
            status="expired",
            reason=f"This transcript token expired on {tt.expires_at.strftime('%d %B %Y')}.",
            student=tt.student, cgpa_data=None, token=tt, now=now,
        ), 410

    # 5. Record the scan
    record_scan(tt)

    # 6. Load transcript data (admin view — all results)
    cgpa_data = compute_cgpa(tt.student_id, published_only=False)

    return render_template("verify/result.html",
        status="valid",
        reason=None,
        student=tt.student,
        cgpa_data=cgpa_data,
        token=tt,
        now=now,
    ), 200


@verify_bp.route("/verify/manual", methods=["POST"])
def manual_verify():
    """Allow anyone to paste a token string and verify it."""
    from flask import redirect, url_for
    from qr_verify import sign_token, _SIGN_SEP

    raw_input = request.form.get("token_input", "").strip()
    if not raw_input:
        return render_template("verify/landing.html", error="Please enter a token.", now=datetime.utcnow())

    # Remove any whitespace the user may have pasted accidentally
    raw_input = "".join(raw_input.split())

    # If the input already contains a signature separator (-- or legacy .),
    # treat it as a full signed token. Otherwise sign the raw token now.
    if _SIGN_SEP in raw_input or "." in raw_input:
        signed = raw_input
    else:
        signed = sign_token(raw_input)

    return redirect(url_for("verify.public_verify", signed_token=signed))
