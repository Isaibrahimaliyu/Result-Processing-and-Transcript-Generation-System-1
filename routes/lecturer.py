"""
ARPS — Lecturer Blueprint
Routes: dashboard, manage courses, enter scores, bulk CSV upload (pipelining)
"""
import io, csv
from functools import wraps
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from models import Lecturer, Course, Student, Score, AuditLog

lecturer_bp = Blueprint("lecturer", __name__)


def lecturer_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_lecturer():
            flash("Access denied.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper


# ── DASHBOARD ────────────────────────────────────────────────
@lecturer_bp.route("/dashboard")
@login_required
@lecturer_required
def dashboard():
    lecturer = current_user.lecturer_profile
    courses  = Course.query.filter_by(lecturer_id=lecturer.id, is_active=True).all()
    return render_template("lecturer/dashboard.html", lecturer=lecturer, courses=courses)


# ── COURSE SCORE LIST ────────────────────────────────────────
@lecturer_bp.route("/course/<int:course_id>/scores")
@login_required
@lecturer_required
def course_scores(course_id):
    lecturer = current_user.lecturer_profile
    course   = Course.query.get_or_404(course_id)

    if course.lecturer_id != lecturer.id:
        flash("You are not assigned to this course.", "danger")
        return redirect(url_for("lecturer.dashboard"))

    session_year = request.args.get("session", "2023/2024")
    semester     = request.args.get("semester", course.semester)

    scores = (
        Score.query
        .filter_by(course_id=course.id, session_year=session_year, semester=semester)
        .join(Student, Score.student_id == Student.id)
        .all()
    )
    return render_template(
        "lecturer/course_scores.html",
        course=course,
        scores=scores,
        session_year=session_year,
        semester=semester,
    )


# ── ENTER / EDIT SINGLE SCORE ────────────────────────────────
@lecturer_bp.route("/course/<int:course_id>/score/enter", methods=["GET", "POST"])
@login_required
@lecturer_required
def enter_score(course_id):
    lecturer = current_user.lecturer_profile
    course   = Course.query.get_or_404(course_id)

    if course.lecturer_id != lecturer.id:
        flash("Access denied.", "danger")
        return redirect(url_for("lecturer.dashboard"))

    if request.method == "POST":
        matric_no    = request.form.get("matric_no", "").strip()
        ca_score     = float(request.form.get("ca_score", 0))
        exam_score   = float(request.form.get("exam_score", 0))
        session_year = request.form.get("session_year", "2023/2024")
        semester     = request.form.get("semester", course.semester)

        student = Student.query.filter_by(matric_no=matric_no).first()
        if not student:
            flash(f"Student '{matric_no}' not found.", "danger")
            return redirect(request.url)

        if not (0 <= ca_score <= 30 and 0 <= exam_score <= 70):
            flash("CA must be 0–30 and Exam must be 0–70.", "danger")
            return redirect(request.url)

        # Upsert score
        score = Score.query.filter_by(
            student_id=student.id, course_id=course.id,
            session_year=session_year, semester=semester
        ).first()

        old_val = None
        if score:
            old_val = f"CA={score.ca_score}, Exam={score.exam_score}"
        else:
            score = Score(
                student_id=student.id, course_id=course.id,
                lecturer_id=lecturer.id, session_year=session_year,
                semester=semester,
            )
            db.session.add(score)

        score.set_scores(ca_score, exam_score)
        db.session.flush()

        # Audit trail
        log = AuditLog(
            user_id=current_user.id,
            action="SCORE_ENTRY",
            table_name="scores",
            record_id=score.id,
            old_value=old_val,
            new_value=f"CA={score.ca_score}, Exam={score.exam_score}, Total={score.total_score}",
            ip_address=request.remote_addr,
        )
        db.session.add(log)
        db.session.commit()

        flash(f"Score saved for {student.full_name} — {score.grade} ({score.total_score})", "success")
        return redirect(url_for("lecturer.course_scores", course_id=course.id))

    return render_template("lecturer/enter_score.html", course=course)


# ── BULK CSV UPLOAD (Pipelining) ─────────────────────────────
@lecturer_bp.route("/course/<int:course_id>/upload", methods=["GET", "POST"])
@login_required
@lecturer_required
def bulk_upload(course_id):
    lecturer = current_user.lecturer_profile
    course   = Course.query.get_or_404(course_id)

    if course.lecturer_id != lecturer.id:
        flash("Access denied.", "danger")
        return redirect(url_for("lecturer.dashboard"))

    if request.method == "POST":
        if "csv_file" not in request.files:
            flash("No file selected.", "danger")
            return redirect(request.url)

        file = request.files["csv_file"]
        session_year = request.form.get("session_year", "2023/2024")
        semester     = request.form.get("semester", course.semester)

        if not file.filename.endswith(".csv"):
            flash("Only CSV files are accepted.", "danger")
            return redirect(request.url)

        # ── Parse CSV ─────────────────────────────────────────
        # Expected columns: matric_no, ca_score, exam_score
        stream    = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
        reader    = csv.DictReader(stream)
        saved     = 0
        errors    = []

        required_cols = {"matric_no", "ca_score", "exam_score"}
        if not required_cols.issubset(set(reader.fieldnames or [])):
            flash(f"CSV must have columns: {', '.join(required_cols)}", "danger")
            return redirect(request.url)

        for row_num, row in enumerate(reader, start=2):
            matric_no  = row["matric_no"].strip()
            try:
                ca_score   = float(row["ca_score"])
                exam_score = float(row["exam_score"])
            except ValueError:
                errors.append(f"Row {row_num}: invalid score values for '{matric_no}'")
                continue

            if not (0 <= ca_score <= 30 and 0 <= exam_score <= 70):
                errors.append(f"Row {row_num}: scores out of range for '{matric_no}'")
                continue

            student = Student.query.filter_by(matric_no=matric_no).first()
            if not student:
                errors.append(f"Row {row_num}: student '{matric_no}' not found")
                continue

            score = Score.query.filter_by(
                student_id=student.id, course_id=course.id,
                session_year=session_year, semester=semester
            ).first()
            if not score:
                score = Score(
                    student_id=student.id, course_id=course.id,
                    lecturer_id=lecturer.id, session_year=session_year,
                    semester=semester,
                )
                db.session.add(score)

            score.set_scores(ca_score, exam_score)
            saved += 1

        if errors:
            # Rollback entirely on any error (ACID)
            db.session.rollback()
            flash(f"Upload aborted — {len(errors)} error(s) found. No records saved.", "danger")
            return render_template("lecturer/bulk_upload.html", course=course, errors=errors)

        db.session.commit()
        flash(f"✅ {saved} score(s) saved successfully via CSV upload.", "success")
        return redirect(url_for("lecturer.course_scores", course_id=course.id,
                                session=session_year, semester=semester))

    return render_template("lecturer/bulk_upload.html", course=course, errors=[])


# ══════════════════════════════════════════════════════════════
# LECTURER — PROFILE & CHANGE PASSWORD
# ══════════════════════════════════════════════════════════════

@lecturer_bp.route("/profile", methods=["GET", "POST"])
@login_required
@lecturer_required
def lecturer_profile():
    """Lecturer updates their own profile."""
    lec = current_user.lecturer_profile
    if not lec:
        flash("Profile not found.", "danger")
        return redirect(url_for("lecturer.dashboard"))

    if request.method == "POST":
        lec.first_name = request.form.get("first_name", lec.first_name).strip() or lec.first_name
        lec.last_name  = request.form.get("last_name",  lec.last_name).strip()  or lec.last_name
        if hasattr(lec, 'email'):
            email = request.form.get("email", "").strip().lower()
            lec.email = email or None
        from app import db as _db
        _db.session.commit()
        flash("✅ Profile updated.", "success")
        return redirect(url_for("lecturer.lecturer_profile"))

    return render_template("lecturer/profile.html", lec=lec)


@lecturer_bp.route("/change-password", methods=["GET", "POST"])
@login_required
@lecturer_required
def lecturer_change_password():
    """Lecturer changes their own password."""
    from app import db as _db, bcrypt as _bcrypt
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw     = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if not _bcrypt.check_password_hash(current_user.password_hash, current_pw):
            flash("Current password is incorrect.", "danger")
            return redirect(url_for("lecturer.lecturer_change_password"))
        if len(new_pw) < 6:
            flash("New password must be at least 6 characters.", "danger")
            return redirect(url_for("lecturer.lecturer_change_password"))
        if new_pw != confirm_pw:
            flash("New passwords do not match.", "danger")
            return redirect(url_for("lecturer.lecturer_change_password"))

        current_user.password_hash = _bcrypt.generate_password_hash(new_pw).decode("utf-8")
        _db.session.commit()
        flash("✅ Password changed successfully.", "success")
        return redirect(url_for("lecturer.dashboard"))

    return render_template("lecturer/change_password.html")
