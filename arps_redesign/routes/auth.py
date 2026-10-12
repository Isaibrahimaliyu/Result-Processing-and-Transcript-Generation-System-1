"""
ARPS — Authentication Blueprint
Routes: /register, /login, /logout
"""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app import db, bcrypt
from models import User, Student, Lecturer

auth_bp = Blueprint("auth", __name__)


# ── REGISTER ─────────────────────────────────────────────────
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return _redirect_dashboard()

    if request.method == "POST":
        role        = request.form.get("role")
        username    = request.form.get("username", "").strip()
        password    = request.form.get("password", "")
        confirm_pw  = request.form.get("confirm_password", "")
        first_name  = request.form.get("first_name", "").strip()
        last_name   = request.form.get("last_name",  "").strip()
        passkey     = request.form.get("passkey", "")

        # ── Validations ───────────────────────────────────────
        if not all([role, username, password, first_name, last_name]):
            flash("All fields are required.", "danger")
            return render_template("auth/register.html")

        if password != confirm_pw:
            flash("Passwords do not match.", "danger")
            return render_template("auth/register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("auth/register.html")

        if User.query.filter_by(username=username).first():
            flash("That username is already registered.", "danger")
            return render_template("auth/register.html")

        if role == "admin" and passkey != current_app.config["ADMIN_PASSKEY"]:
            flash("Invalid institutional passkey for Admin registration.", "danger")
            return render_template("auth/register.html")

        # ── Create User ───────────────────────────────────────
        hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
        user = User(username=username, password_hash=hashed_pw, role=role)
        db.session.add(user)
        db.session.flush()   # get user.id before commit

        if role == "student":
            # Parse entry_year safely
            ey_raw = request.form.get("entry_year", "").strip()
            entry_year = int(ey_raw) if ey_raw.isdigit() and len(ey_raw) == 4 else None

            # Parse date_of_birth safely
            dob = None
            dob_raw = request.form.get("date_of_birth", "").strip()
            if dob_raw:
                try:
                    from datetime import date as _date
                    dob = _date.fromisoformat(dob_raw)   # expects YYYY-MM-DD from HTML date input
                except ValueError:
                    dob = None

            level = request.form.get("level", "100")
            if level not in ("100", "200", "300", "400"):
                level = "100"

            profile = Student(
                user_id=user.id,
                matric_no=username,
                first_name=first_name,
                middle_name=request.form.get("middle_name", "").strip() or None,
                last_name=last_name,
                level=level,
                entry_year=entry_year,
                date_of_birth=dob,
                department=request.form.get("department", "Computer Science").strip() or "Computer Science",
            )
            db.session.add(profile)

        elif role in ("lecturer", "admin"):
            profile = Lecturer(
                user_id=user.id,
                staff_id=username,
                first_name=first_name,
                last_name=last_name,
            )
            db.session.add(profile)

        db.session.commit()
        flash("Account created! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


# ── LOGIN ─────────────────────────────────────────────────────
@auth_bp.route("/", methods=["GET", "POST"])
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return _redirect_dashboard()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash("Your account has been deactivated. Contact the Examination Officer.", "danger")
                return render_template("auth/login.html")
            # Record last login time
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user, remember=False)
            next_page = request.args.get("next")
            return redirect(next_page) if next_page else _redirect_dashboard()
        else:
            flash("Invalid username or password. Please check your credentials.", "danger")

    return render_template("auth/login.html")


# ── LOGOUT ────────────────────────────────────────────────────
@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


# ── Helper ────────────────────────────────────────────────────
def _redirect_dashboard():
    if current_user.is_student():
        return redirect(url_for("student.dashboard"))
    elif current_user.is_lecturer():
        return redirect(url_for("lecturer.dashboard"))
    else:
        return redirect(url_for("admin.dashboard"))


# ══════════════════════════════════════════════════════════════
# PASSWORD RECOVERY — FORGOT PASSWORD → OTP → RESET
# ══════════════════════════════════════════════════════════════

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Step 1 — User enters their username/email to receive OTP."""
    if current_user.is_authenticated:
        return _redirect_dashboard()

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        if not identifier:
            flash("Please enter your username or email address.", "danger")
            return render_template("auth/forgot_password.html")

        # Find user by username (matric/staff ID) or by associated email
        from models import Student, Lecturer
        user = User.query.filter_by(username=identifier).first()

        # Also search by student email
        if not user:
            student = Student.query.filter_by(email=identifier).first()
            if student:
                user = student.user

        # Also search by lecturer/admin email (both use the Lecturer profile)
        if not user:
            lecturer = Lecturer.query.filter_by(email=identifier).first()
            if lecturer:
                user = lecturer.user
        if not user:
            flash(
                "If that account exists and has an email registered, "
                "an OTP has been sent. Check your inbox.",
                "info"
            )
            return redirect(url_for("auth.verify_otp"))

        # Find the email to send to
        email_target = None
        if hasattr(user, "student_profile") and user.student_profile:
            email_target = user.student_profile.email
        if not email_target and hasattr(user, "lecturer_profile") and user.lecturer_profile:
            email_target = getattr(user.lecturer_profile, "email", None)

        if not email_target:
            flash(
                "No email address is registered for this account. "
                "Contact the Examination Office to reset your password.",
                "warning"
            )
            return render_template("auth/forgot_password.html")

        # Generate 6-digit OTP
        import random, string
        from datetime import timedelta
        from models import PasswordResetOTP

        # Invalidate any previous OTPs for this user
        old_otps = PasswordResetOTP.query.filter_by(user_id=user.id, is_used=False).all()
        for o in old_otps:
            o.is_used = True

        otp_code = "".join(random.choices(string.digits, k=6))
        otp = PasswordResetOTP(
            user_id      = user.id,
            otp_code     = otp_code,
            expires_at   = datetime.utcnow() + timedelta(minutes=15),
            email_sent_to = email_target,
        )
        db.session.add(otp)
        db.session.commit()

        # Send OTP email
        _send_otp_email(user, otp_code, email_target)

        # Store user_id in session for the next step (no full login yet)
        from flask import session
        session["reset_user_id"] = user.id
        session["reset_email_hint"] = email_target[:3] + "***" + email_target[email_target.find("@"):]

        flash(
            f"A 6-digit OTP has been sent to {email_target[:3]}***"
            f"{email_target[email_target.find('@'):]}. It expires in 15 minutes.",
            "info"
        )
        return redirect(url_for("auth.verify_otp"))

    return render_template("auth/forgot_password.html")


@auth_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    """Step 2 — User enters the 6-digit OTP."""
    if current_user.is_authenticated:
        return _redirect_dashboard()

    from flask import session
    from models import PasswordResetOTP

    user_id    = session.get("reset_user_id")
    email_hint = session.get("reset_email_hint", "your email")

    if not user_id:
        flash("Session expired. Please start the password reset again.", "warning")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        entered = "".join([
            request.form.get(f"otp_{i}", "") for i in range(1, 7)
        ]).strip()
        # Also accept single field
        if not entered:
            entered = request.form.get("otp_full", "").strip()

        otp = (
            PasswordResetOTP.query
            .filter_by(user_id=user_id, is_used=False)
            .order_by(PasswordResetOTP.id.desc())
            .first()
        )

        if not otp or not otp.is_valid:
            flash("OTP has expired or is invalid. Please request a new one.", "danger")
            return redirect(url_for("auth.forgot_password"))

        if otp.otp_code != entered:
            flash("Incorrect OTP. Please try again.", "danger")
            return render_template("auth/verify_otp.html", email_hint=email_hint)

        # OTP verified — mark used, allow password reset
        otp.is_used = True
        db.session.commit()
        session["reset_verified"] = True

        return redirect(url_for("auth.reset_password"))

    return render_template("auth/verify_otp.html", email_hint=email_hint)


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """Step 3 — User sets a new password after OTP verified."""
    if current_user.is_authenticated:
        return _redirect_dashboard()

    from flask import session

    user_id  = session.get("reset_user_id")
    verified = session.get("reset_verified", False)

    if not user_id or not verified:
        flash("Please complete the OTP verification step first.", "warning")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password  = request.form.get("password", "")
        confirm   = request.form.get("confirm_password", "")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("auth/reset_password.html")

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("auth/reset_password.html")

        user = User.query.get(user_id)
        if not user:
            flash("Account not found. Please try again.", "danger")
            return redirect(url_for("auth.forgot_password"))

        user.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
        db.session.commit()

        # Clear session
        session.pop("reset_user_id",  None)
        session.pop("reset_verified", None)
        session.pop("reset_email_hint", None)

        flash("✅ Password reset successfully. Please sign in with your new password.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html")


@auth_bp.route("/resend-otp")
def resend_otp():
    """Resend OTP if user didn't receive it."""
    from flask import session
    user_id = session.get("reset_user_id")
    if not user_id:
        return redirect(url_for("auth.forgot_password"))
    user = User.query.get(user_id)
    if not user:
        return redirect(url_for("auth.forgot_password"))

    # Get email
    email_target = None
    if hasattr(user, "student_profile") and user.student_profile:
        email_target = user.student_profile.email
    if not email_target:
        flash("No email address found for your account.", "warning")
        return redirect(url_for("auth.forgot_password"))

    import random, string
    from datetime import timedelta
    from models import PasswordResetOTP

    old_otps = PasswordResetOTP.query.filter_by(user_id=user_id, is_used=False).all()
    for o in old_otps: o.is_used = True

    otp_code = "".join(random.choices(string.digits, k=6))
    otp = PasswordResetOTP(
        user_id=user_id, otp_code=otp_code,
        expires_at=datetime.utcnow() + timedelta(minutes=15),
        email_sent_to=email_target,
    )
    db.session.add(otp); db.session.commit()
    _send_otp_email(user, otp_code, email_target)

    flash("A new OTP has been sent to your registered email.", "success")
    return redirect(url_for("auth.verify_otp"))


# ── OTP email helper ──────────────────────────────────────────
def _send_otp_email(user, otp_code: str, email: str):
    """Send a styled OTP email for password reset."""
    try:
        from flask_mail import Message
        from app import mail
        html = f"""
        <div style="font-family:Inter,Arial,sans-serif;max-width:480px;margin:0 auto;
                    background:#fff;border-radius:16px;overflow:hidden;
                    box-shadow:0 8px 32px rgba(13,59,26,.12);">
          <div style="background:linear-gradient(135deg,#145228,#2E7D3A);
                      padding:28px 32px;text-align:center;">
            <div style="font-size:28px;margin-bottom:8px;">🔐</div>
            <h2 style="color:#fff;margin:0;font-family:Georgia,serif;font-size:1.2rem;">
              Password Reset OTP
            </h2>
            <p style="color:rgba(255,255,255,.5);font-size:12px;margin:4px 0 0;">
              Ibrahim Badamasi Babangida University — ARPTGS
            </p>
          </div>
          <div style="padding:28px 32px;">
            <p style="color:#374151;font-size:14px;margin-bottom:20px;">
              Hi <strong>{user.username}</strong>, use the code below to reset your
              ARPTGS portal password. This code expires in <strong>15 minutes</strong>.
            </p>
            <div style="background:#F1F8F2;border:2px dashed #A5D6A7;border-radius:12px;
                        padding:20px;text-align:center;margin-bottom:20px;">
              <div style="font-size:36px;font-weight:800;letter-spacing:10px;
                          color:#1A5C2A;font-family:Georgia,monospace;">
                {otp_code}
              </div>
            </div>
            <div style="background:#FEF9C3;border:1px solid #FDE68A;border-radius:8px;
                        padding:12px 16px;font-size:12px;color:#78350F;">
              ⚠️ Never share this code with anyone. The ARPTGS team will never ask for it.
              If you did not request a password reset, ignore this email.
            </div>
          </div>
          <div style="background:#F4F7F4;padding:16px 32px;text-align:center;
                      font-size:11px;color:#9CA3AF;">
            © 2026 Ibrahim Badamasi Babangida University, Lapai, Niger State
          </div>
        </div>"""
        msg = Message(
            subject="Your ARPTGS Password Reset Code — IBB University",
            recipients=[email],
            body=f"Your ARPTGS password reset code is: {otp_code}\nIt expires in 15 minutes.",
            html=html,
        )
        mail.send(msg)
    except Exception:
        pass   # Don't crash if email fails — the OTP is still in DB
