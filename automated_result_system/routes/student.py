"""
ARPS — Student Blueprint  (v2)
Results are only visible AFTER admin publishes them per session/semester/level.
"""
import io
from functools import wraps
from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from app import db, bcrypt
from models import Student, Score, CourseRegistration, Course, AcademicSession, ResultPublication
from engine import compute_cgpa, is_result_published

student_bp = Blueprint("student", __name__)

MIN_UNITS = 15
MAX_UNITS = 24


def student_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_student():
            flash("Access denied.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper


def _active_session():
    """Return the active AcademicSession or None."""
    return AcademicSession.query.filter_by(is_current=True).first()


# ── DASHBOARD ────────────────────────────────────────────────
@student_bp.route("/dashboard")
@login_required
@student_required
def dashboard():
    student      = current_user.student_profile
    active_sess  = _active_session()
    # Only show published results on dashboard
    cgpa_data    = compute_cgpa(student.id, published_only=True)
    return render_template(
        "student/dashboard.html",
        student=student,
        cgpa_data=cgpa_data,
        active_session=active_sess,
    )


# ── VIEW ACADEMIC RECORDS ─────────────────────────────────────
@student_bp.route("/results")
@login_required
@student_required
def results():
    student = current_user.student_profile
    # Only published results
    cgpa_data = compute_cgpa(student.id, published_only=True)

    # Build per-semester publication status for UI
    pub_statuses = {}
    all_scores = Score.query.filter_by(student_id=student.id).all()
    seen = set()
    for s in all_scores:
        key = (s.session_year, s.semester)
        if key not in seen:
            seen.add(key)
            pub_statuses[key] = is_result_published(s.session_year, s.semester, student.level)

    return render_template(
        "student/results.html",
        student=student,
        cgpa_data=cgpa_data,
        pub_statuses=pub_statuses,
    )


# ── MY COURSES ────────────────────────────────────────────────
@student_bp.route("/courses")
@login_required
@student_required
def my_courses():
    student      = current_user.student_profile
    active_sess  = _active_session()
    session_year = request.args.get("session", active_sess.session_year if active_sess else "2023/2024")
    semester     = request.args.get("semester", active_sess.semester    if active_sess else "First")

    registrations = (
        CourseRegistration.query
        .filter_by(student_id=student.id)
        .join(Course)
        .order_by(CourseRegistration.session_year.desc(), Course.semester)
        .all()
    )
    current_regs  = [r for r in registrations if r.session_year == session_year and r.semester == semester]
    current_units = sum(r.course.credit_unit for r in current_regs)

    return render_template(
        "student/courses.html",
        student=student,
        registrations=registrations,
        current_regs=current_regs,
        current_units=current_units,
        session_year=session_year,
        semester=semester,
        min_units=MIN_UNITS,
        max_units=MAX_UNITS,
        active_session=active_sess,
    )


# ── REGISTER COURSES ──────────────────────────────────────────
@student_bp.route("/register-courses", methods=["GET", "POST"])
@login_required
@student_required
def register_courses():
    student     = current_user.student_profile
    active_sess = _active_session()

    if not active_sess:
        flash("No active academic session has been set by the Examination Officer.", "warning")
        return redirect(url_for("student.dashboard"))

    if not active_sess.registration_open:
        flash("Course registration is currently closed. Contact the Examination Officer.", "warning")
        return redirect(url_for("student.my_courses"))

    session_year = active_sess.session_year
    semester     = active_sess.semester

    available_courses = Course.query.filter_by(
        level=student.level, semester=semester, is_active=True
    ).order_by(Course.course_code).all()

    existing_regs = CourseRegistration.query.filter_by(
        student_id=student.id, session_year=session_year, semester=semester,
    ).all()
    registered_ids = {r.course_id for r in existing_regs}
    current_units  = sum(r.course.credit_unit for r in existing_regs)

    if request.method == "POST":
        selected_ids = request.form.getlist("course_ids")
        if not selected_ids:
            flash("You must select at least one course.", "danger")
            return redirect(request.url)

        selected_courses = Course.query.filter(
            Course.id.in_([int(i) for i in selected_ids]),
            Course.level    == student.level,
            Course.semester == semester,
            Course.is_active == True
        ).all()

        if len(selected_courses) != len(selected_ids):
            flash("One or more selected courses are invalid.", "danger")
            return redirect(request.url)

        new_units   = sum(c.credit_unit for c in selected_courses if c.id not in registered_ids)
        total_units = current_units + new_units

        if total_units > MAX_UNITS:
            flash(
                f"Total units ({total_units}) exceeds the NUC maximum of {MAX_UNITS} per semester. "
                f"You already have {current_units} unit(s).",
                "danger"
            )
            return redirect(request.url)

        added = 0
        for course in selected_courses:
            if course.id not in registered_ids:
                db.session.add(CourseRegistration(
                    student_id=student.id, course_id=course.id,
                    session_year=session_year, semester=semester,
                ))
                added += 1

        db.session.commit()
        if added:
            flash(f"Successfully registered {added} course(s). Total units: {total_units}/{MAX_UNITS}.", "success")
        else:
            flash("All selected courses were already registered.", "info")

        return redirect(url_for("student.my_courses", session=session_year, semester=semester))

    return render_template(
        "student/register_courses.html",
        student=student,
        available_courses=available_courses,
        registered_ids=registered_ids,
        current_units=current_units,
        session_year=session_year,
        semester=semester,
        min_units=MIN_UNITS,
        max_units=MAX_UNITS,
        active_session=active_sess,
    )


# ── DROP COURSE ───────────────────────────────────────────────
@student_bp.route("/drop-course/<int:reg_id>", methods=["POST"])
@login_required
@student_required
def drop_course(reg_id):
    student = current_user.student_profile
    reg     = CourseRegistration.query.get_or_404(reg_id)

    if reg.student_id != student.id:
        flash("Access denied.", "danger")
        return redirect(url_for("student.my_courses"))

    # Check registration is still open
    active_sess = _active_session()
    if not active_sess or not active_sess.registration_open:
        flash("Course drop period is closed.", "warning")
        return redirect(url_for("student.my_courses"))

    # Block if scores already entered
    score = Score.query.filter_by(
        student_id=student.id, course_id=reg.course_id,
        session_year=reg.session_year, semester=reg.semester,
    ).first()
    if score:
        flash(f"Cannot drop {reg.course.course_code} — results have already been entered by the lecturer.", "warning")
        return redirect(url_for("student.my_courses", session=reg.session_year, semester=reg.semester))

    code, yr, sem = reg.course.course_code, reg.session_year, reg.semester
    db.session.delete(reg)
    db.session.commit()
    flash(f"Course {code} dropped successfully.", "success")
    return redirect(url_for("student.my_courses", session=yr, semester=sem))


# ── STATEMENT OF RESULTS ──────────────────────────────────────
@student_bp.route("/statement")
@login_required
@student_required
def statement():
    student   = current_user.student_profile
    cgpa_data = compute_cgpa(student.id, published_only=True)
    if not cgpa_data["semester_breakdown"]:
        flash("No published results available for your statement yet.", "info")
        return redirect(url_for("student.dashboard"))
    return render_template("student/statement.html", student=student,
                           cgpa_data=cgpa_data, now=date.today())


@student_bp.route("/statement/pdf")
@login_required
@student_required
def statement_pdf():
    from transcript_pdf import generate_transcript_pdf
    from qr_verify import create_transcript_token
    student   = current_user.student_profile
    cgpa_data = compute_cgpa(student.id, published_only=True)
    if not cgpa_data["semester_breakdown"]:
        flash("No published results to generate a statement for.", "warning")
        return redirect(url_for("student.dashboard"))

    # Generate a QR verification token for this statement
    tt = create_transcript_token(
        student_id=student.id,
        generated_by_user_id=current_user.id,
        note="Statement of Results (self-printed)",
    )
    db.session.commit()

    from flask import current_app
    base_url  = (current_app.config.get("SERVER_URL","").rstrip("/")
                 or request.host_url.rstrip("/"))
    pdf_bytes = generate_transcript_pdf(student, cgpa_data, token=tt, base_url=base_url, doc_type="statement")
    buf = io.BytesIO(pdf_bytes)
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name=f"Statement_{student.matric_no.replace('/','_')}.pdf")


# ── CHANGE PASSWORD ───────────────────────────────────────────
@student_bp.route("/change-password", methods=["GET", "POST"])
@login_required
@student_required
def change_password():
    if request.method == "POST":
        current_pw  = request.form.get("current_password", "")
        new_pw      = request.form.get("new_password", "")
        confirm_pw  = request.form.get("confirm_password", "")

        if not bcrypt.check_password_hash(current_user.password_hash, current_pw):
            flash("Current password is incorrect.", "danger")
            return redirect(request.url)
        if len(new_pw) < 6:
            flash("New password must be at least 6 characters.", "danger")
            return redirect(request.url)
        if new_pw != confirm_pw:
            flash("New passwords do not match.", "danger")
            return redirect(request.url)

        current_user.password_hash = bcrypt.generate_password_hash(new_pw).decode("utf-8")
        db.session.commit()
        flash("Password changed successfully.", "success")
        return redirect(url_for("student.dashboard"))

    return render_template("student/change_password.html",
                           student=current_user.student_profile)


# ── UPDATE PROFILE (email/phone) ──────────────────────────────
@student_bp.route("/update-profile", methods=["GET", "POST"])
@login_required
@student_required
def update_profile():
    """Student updates their own email, phone, and passport photo."""
    student = current_user.student_profile
    if request.method == "POST":
        new_email = request.form.get("email", "").strip().lower()
        new_phone = request.form.get("phone", "").strip()
        dob_raw   = request.form.get("date_of_birth","").strip()
        ey_raw    = request.form.get("entry_year","").strip()
        gender    = request.form.get("gender", "").strip().upper()

        # Basic email validation
        if new_email and "@" not in new_email:
            flash("Please enter a valid email address.", "danger")
            return redirect(request.url)

        student.email = new_email or None
        student.phone = new_phone or None
        if gender in ("M", "F"):
            student.gender = gender

        # Update entry_year
        if ey_raw.isdigit() and len(ey_raw) == 4:
            student.entry_year = int(ey_raw)

        # Update date of birth
        if dob_raw:
            try:
                from datetime import date as _date
                student.date_of_birth = _date.fromisoformat(dob_raw)
            except ValueError:
                pass

        # ── Passport photo upload ──────────────────────────────
        photo_file = request.files.get("passport_photo")
        if photo_file and photo_file.filename:
            saved_name, error = _save_passport_photo(student, photo_file)
            if error:
                flash(error, "danger")
                return redirect(request.url)
            student.passport_photo = saved_name

        db.session.commit()
        flash("Profile updated successfully. You will receive result notifications at this email.", "success")
        return redirect(url_for("student.dashboard"))

    return render_template("student/update_profile.html", student=student)


def _save_passport_photo(student, file_storage):
    """
    Validate and save an uploaded passport photo.
    Returns (saved_filename, None) on success, or (None, error_message) on failure.

    Validates the upload is a genuine image (not just a renamed file), enforces
    a size limit, and normalises it to a standard passport photo size so every
    student's photo renders consistently on the transcript.
    """
    import os
    from PIL import Image as PILImage, UnidentifiedImageError

    ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}
    MAX_BYTES   = 3 * 1024 * 1024  # 3 MB

    filename = file_storage.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXT:
        return None, "Photo must be a JPG, PNG, or WEBP image."

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > MAX_BYTES:
        return None, "Photo must be smaller than 3 MB."
    if size == 0:
        return None, "That file appears to be empty."

    # Verify it's a genuine image, not just a file with an image-like extension
    try:
        img = PILImage.open(file_storage.stream)
        img.verify()
        file_storage.stream.seek(0)
        img = PILImage.open(file_storage.stream)  # reopen after verify()
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError):
        return None, "That file isn't a valid image. Please upload a JPG or PNG photo."

    # Center-crop to a standard passport aspect ratio (35mm x 45mm ≈ 0.777),
    # then resize to a consistent print resolution used on the transcript.
    target_ratio = 35 / 45
    w, h = img.size
    current_ratio = w / h
    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))
    img = img.resize((413, 531))  # ~35x45mm at 300dpi

    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "uploads", "passports")
    upload_dir = os.path.abspath(upload_dir)
    os.makedirs(upload_dir, exist_ok=True)

    # Deterministic filename tied to matric number — re-uploads simply overwrite
    # the previous photo instead of accumulating orphaned files.
    safe_matric = "".join(c if c.isalnum() else "_" for c in student.matric_no)
    saved_name = f"{safe_matric}.jpg"
    img.save(os.path.join(upload_dir, saved_name), format="JPEG", quality=88)

    return saved_name, None


# ══════════════════════════════════════════════════════════════
# CGPA PREDICTOR
# ══════════════════════════════════════════════════════════════

@student_bp.route("/predict", methods=["GET", "POST"])
@login_required
def predict_cgpa():
    """
    CGPA Prediction tool.
    Student selects hypothetical grades for upcoming/current courses
    and the system predicts their future CGPA and degree class.
    """
    from engine import compute_cgpa
    from models import CourseRegistration, Course

    student   = current_user.student_profile
    cgpa_data = compute_cgpa(student.id, published_only=True)

    # Get courses registered in current session (not yet scored)
    from models import AcademicSession, Score
    active_session = AcademicSession.query.filter_by(is_current=True).first()

    registered_courses = []
    if active_session:
        regs = CourseRegistration.query.filter_by(
            student_id=student.id,
            session_year=active_session.session_year,
            semester=active_session.semester,
        ).all()
        for reg in regs:
            # Only include courses without a score yet
            existing_score = Score.query.filter_by(
                student_id=student.id,
                course_id=reg.course_id,
                session_year=active_session.session_year,
                semester=active_session.semester,
            ).first()
            if not existing_score:
                registered_courses.append(reg.course)

    # Also offer all courses in student's level as options
    all_level_courses = Course.query.filter_by(level=student.level).all()

    prediction = None
    if request.method == "POST":
        # Collect hypothetical grades from the form
        hypothetical = []
        for key, val in request.form.items():
            if key.startswith("grade_") and val:
                try:
                    course_id = int(key.replace("grade_", ""))
                    course    = Course.query.get(course_id)
                    if course and val in ("A","B","C","D","E","F"):
                        gp_map = {"A":5.0,"B":4.0,"C":3.0,"D":2.0,"E":1.0,"F":0.0}
                        hypothetical.append({
                            "code":        course.course_code,
                            "title":       course.course_title,
                            "credit_unit": course.credit_unit,
                            "grade":       val,
                            "grade_point": gp_map[val],
                            "quality_points": gp_map[val] * course.credit_unit,
                        })
                except (ValueError, TypeError):
                    continue

        if hypothetical:
            # Current totals from published results
            current_units = cgpa_data["total_units"]
            current_qp    = cgpa_data["total_quality_points"]

            # Add hypothetical
            hypo_units = sum(c["credit_unit"]    for c in hypothetical)
            hypo_qp    = sum(c["quality_points"] for c in hypothetical)

            future_units = current_units + hypo_units
            future_qp    = current_qp    + hypo_qp
            future_cgpa  = round(future_qp / future_units, 2) if future_units > 0 else 0.0

            from engine import classify_degree
            prediction = {
                "current_cgpa":   cgpa_data["cgpa"],
                "current_class":  cgpa_data["degree_class"],
                "future_cgpa":    future_cgpa,
                "future_class":   classify_degree(future_cgpa),
                "hypo_courses":   hypothetical,
                "hypo_units":     hypo_units,
                "future_units":   future_units,
                "cgpa_change":    round(future_cgpa - cgpa_data["cgpa"], 2),
            }

    return render_template("student/predict.html",
                           student=student,
                           cgpa_data=cgpa_data,
                           registered_courses=registered_courses,
                           all_courses=all_level_courses,
                           prediction=prediction,
                           active_session=active_session)
