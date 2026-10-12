"""
ARPS — Admin Blueprint  (v2)
Adds: Session management, Result Publication control, password reset.
"""
import io, csv
from datetime import date, datetime
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, Response
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
from app import db, bcrypt
from models import (User, Student, Lecturer, Course, CourseRegistration,
                    Score, AuditLog, AcademicSession, ResultPublication)
from engine import compute_cgpa, bulk_compute_department_cgpa
from cache_utils import cached, invalidate
from backup_engine import get_backup_dir

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash("Access denied.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper


def log_action(action, table_name=None, record_id=None, old_value=None, new_value=None):
    db.session.add(AuditLog(
        user_id=current_user.id, action=action, table_name=table_name,
        record_id=record_id, old_value=old_value, new_value=new_value,
        ip_address=request.remote_addr,
    ))


# ── DASHBOARD ─────────────────────────────────────────────────
@cached(ttl=30)
def _dashboard_counts():
    level_counts = dict(
        db.session.query(Student.level, db.func.count(Student.id))
        .group_by(Student.level).all()
    )
    return {
        "total_students":  Student.query.count(),
        "total_lecturers": Lecturer.query.count(),
        "total_courses":   Course.query.filter_by(is_active=True).count(),
        "total_scores":    Score.query.count(),
        "level_counts":    {lvl: level_counts.get(lvl, 0) for lvl in ["100", "200", "300", "400"]},
    }


@admin_bp.route("/dashboard")
@login_required
@admin_required
def dashboard():
    active_sess = AcademicSession.query.filter_by(is_current=True).first()
    pubs        = ResultPublication.query.all()
    counts = _dashboard_counts()

    return render_template("admin/dashboard.html",
        total_students  = counts["total_students"],
        total_lecturers = counts["total_lecturers"],
        total_courses   = counts["total_courses"],
        total_scores    = counts["total_scores"],
        recent_logs     = AuditLog.query.options(joinedload(AuditLog.user)).order_by(AuditLog.logged_at.desc()).limit(10).all(),
        active_session  = active_sess,
        publications    = pubs,
        level_counts    = counts["level_counts"],
    )


# ══════════════════════════════════════════════════════════════
# SESSION MANAGEMENT
# ══════════════════════════════════════════════════════════════
@admin_bp.route("/sessions")
@login_required
@admin_required
def sessions():
    all_sessions = AcademicSession.query.order_by(AcademicSession.id.desc()).all()
    return render_template("admin/sessions.html", sessions=all_sessions)


@admin_bp.route("/sessions/add", methods=["POST"])
@login_required
@admin_required
def add_session():
    session_year = request.form.get("session_year", "").strip()
    semester     = request.form.get("semester")
    if not session_year or not semester:
        flash("Session year and semester are required.", "danger")
        return redirect(url_for("admin.sessions"))

    existing = AcademicSession.query.filter_by(
        session_year=session_year, semester=semester
    ).first()
    if existing:
        flash(f"Session {session_year} {semester} already exists.", "warning")
        return redirect(url_for("admin.sessions"))

    sess = AcademicSession(session_year=session_year, semester=semester)
    db.session.add(sess)
    log_action("SESSION_ADD", "academic_sessions", new_value=f"{session_year} {semester}")
    db.session.commit()
    flash(f"Session {session_year} — {semester} Semester added.", "success")
    return redirect(url_for("admin.sessions"))


@admin_bp.route("/sessions/<int:sess_id>/activate", methods=["POST"])
@login_required
@admin_required
def activate_session(sess_id):
    # deactivate all first
    AcademicSession.query.update({"is_current": False})
    sess = AcademicSession.query.get_or_404(sess_id)
    sess.is_current = True
    log_action("SESSION_ACTIVATE", "academic_sessions", sess_id,
               new_value=f"{sess.session_year} {sess.semester}")
    db.session.commit()
    flash(f"Active session set to: {sess.session_year} — {sess.semester} Semester.", "success")
    return redirect(url_for("admin.sessions"))


@admin_bp.route("/sessions/<int:sess_id>/toggle-registration", methods=["POST"])
@login_required
@admin_required
def toggle_registration(sess_id):
    sess = AcademicSession.query.get_or_404(sess_id)
    sess.registration_open = not sess.registration_open
    state = "opened" if sess.registration_open else "closed"
    log_action("REGISTRATION_TOGGLE", "academic_sessions", sess_id,
               new_value=f"Registration {state} for {sess.session_year}")
    db.session.commit()
    flash(f"Course registration {state} for {sess.session_year} — {sess.semester}.", "success")
    return redirect(url_for("admin.sessions"))


# ══════════════════════════════════════════════════════════════
# RESULT PUBLICATION  ← CORE FEATURE
# ══════════════════════════════════════════════════════════════
@admin_bp.route("/publications")
@login_required
@admin_required
def publications():
    pubs  = ResultPublication.query.order_by(
        ResultPublication.session_year.desc(),
        ResultPublication.semester,
        ResultPublication.level
    ).all()
    sessions = AcademicSession.query.order_by(AcademicSession.id.desc()).all()
    return render_template("admin/publications.html", publications=pubs, sessions=sessions)


@admin_bp.route("/publications/create", methods=["POST"])
@login_required
@admin_required
def create_publication():
    session_year = request.form.get("session_year", "").strip()
    semester     = request.form.get("semester")
    level        = request.form.get("level")
    note         = request.form.get("note", "").strip()

    if not all([session_year, semester, level]):
        flash("All fields are required.", "danger")
        return redirect(url_for("admin.publications"))

    existing = ResultPublication.query.filter_by(
        session_year=session_year, semester=semester, level=level
    ).first()
    if existing:
        flash(f"A publication record already exists for {session_year} {semester} {level}L.", "warning")
        return redirect(url_for("admin.publications"))

    pub = ResultPublication(
        session_year=session_year, semester=semester, level=level,
        is_published=False, note=note,
    )
    db.session.add(pub)
    log_action("PUBLICATION_CREATE", "result_publications",
               new_value=f"{session_year} {semester} L{level}")
    db.session.commit()
    flash("Publication record created. Toggle 'Publish' when ready to release to students.", "success")
    return redirect(url_for("admin.publications"))


@admin_bp.route("/publications/<int:pub_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_publication(pub_id):
    pub = ResultPublication.query.get_or_404(pub_id)
    pub.is_published = not pub.is_published
    if pub.is_published:
        pub.published_at = datetime.utcnow()
        pub.published_by = current_user.id
        action = "RESULTS_PUBLISHED"
        msg = (f"Results for {pub.session_year} — {pub.semester} Semester "
               f"({pub.level} Level) are now LIVE to students.")
    else:
        pub.published_at = None
        action = "RESULTS_UNPUBLISHED"
        msg = (f"Results for {pub.session_year} — {pub.semester} Semester "
               f"({pub.level} Level) have been withdrawn from student view.")

    log_action(action, "result_publications", pub_id,
               new_value=f"{pub.session_year} {pub.semester} L{pub.level} published={pub.is_published}")
    db.session.commit()
    invalidate("engine._published_set")
    flash(msg, "success" if pub.is_published else "warning")

    # Auto-send email notifications when publishing results
    if pub.is_published:
        auto_send = request.form.get("auto_notify", "off") == "on"
        if auto_send:
            from email_notify import send_bulk_result_notifications
            from flask import url_for as _url_for
            students = Student.query.filter_by(level=pub.level).all()
            portal_url = _url_for("auth.login", _external=True)
            results = send_bulk_result_notifications(
                students=students,
                session_year=pub.session_year,
                semester=pub.semester,
                sent_by_user_id=current_user.id,
                portal_url=portal_url,
            )
            flash(
                f"📧 Auto-notification: {results['sent']} email(s) sent, "
                f"{results['failed']} failed, {results['skipped']} skipped (no email).",
                "info"
            )

    return redirect(url_for("admin.publications"))


# ══════════════════════════════════════════════════════════════
# COURSES
# ══════════════════════════════════════════════════════════════
@admin_bp.route("/courses")
@login_required
@admin_required
def courses():
    return render_template("admin/courses.html",
        courses   = Course.query.order_by(Course.level, Course.semester, Course.course_code).all(),
        lecturers = Lecturer.query.order_by(Lecturer.last_name).all(),
    )


@admin_bp.route("/courses/add", methods=["POST"])
@login_required
@admin_required
def add_course():
    code = request.form.get("course_code", "").strip().upper()
    if Course.query.filter_by(course_code=code).first():
        flash(f"Course code '{code}' already exists.", "danger")
        return redirect(url_for("admin.courses"))
    course = Course(
        course_code  = code,
        course_title = request.form.get("course_title", "").strip(),
        credit_unit  = int(request.form.get("credit_unit", 3)),
        semester     = request.form.get("semester"),
        level        = request.form.get("level"),
        lecturer_id  = int(request.form.get("lecturer_id")) if request.form.get("lecturer_id") else None,
    )
    db.session.add(course)
    db.session.flush()
    log_action("COURSE_ADD", "courses", course.id, new_value=f"{code}")
    db.session.commit()
    invalidate("routes.admin._dashboard_counts")
    flash(f"Course '{code}' added.", "success")
    return redirect(url_for("admin.courses"))


@admin_bp.route("/courses/<int:course_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    old    = course.course_code
    course.course_code  = request.form.get("course_code", "").strip().upper()
    course.course_title = request.form.get("course_title", "").strip()
    course.credit_unit  = int(request.form.get("credit_unit", 3))
    course.semester     = request.form.get("semester")
    course.level        = request.form.get("level")
    lid = request.form.get("lecturer_id") or None
    course.lecturer_id  = int(lid) if lid else None
    log_action("COURSE_EDIT", "courses", course_id, old_value=old, new_value=course.course_code)
    db.session.commit()
    flash(f"Course '{course.course_code}' updated.", "success")
    return redirect(url_for("admin.courses"))


@admin_bp.route("/courses/<int:course_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    course.is_active = False
    log_action("COURSE_DEACTIVATE", "courses", course_id, old_value=course.course_code)
    db.session.commit()
    invalidate("routes.admin._dashboard_counts")
    flash(f"Course '{course.course_code}' deactivated.", "warning")
    return redirect(url_for("admin.courses"))


# ══════════════════════════════════════════════════════════════
# STUDENTS
# ══════════════════════════════════════════════════════════════
@admin_bp.route("/students")
@login_required
@admin_required
def students():
    level_filter = request.args.get("level", "")
    search       = request.args.get("q", "").strip()
    page         = request.args.get("page", 1, type=int)
    per_page     = request.args.get("per_page", 25, type=int)
    per_page     = min(max(per_page, 10), 100)   # clamp to a sane range

    # Eager-load the linked User row so the template's s.user.is_active
    # checks don't fire one extra query per row (N+1).
    q = Student.query.options(joinedload(Student.user))

    if level_filter:
        q = q.filter_by(level=level_filter)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            Student.matric_no.ilike(like),
            Student.first_name.ilike(like),
            Student.last_name.ilike(like),
        ))

    q = q.order_by(Student.last_name)
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    return render_template("admin/students.html",
        students=pagination.items,
        pagination=pagination,
        level_filter=level_filter,
        search=search,
        per_page=per_page,
    )


@admin_bp.route("/students/<int:student_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_student(student_id):
    student = Student.query.get_or_404(student_id)
    student.user.is_active = not student.user.is_active
    state = "ACTIVATED" if student.user.is_active else "DEACTIVATED"
    log_action(f"STUDENT_{state}", "users", student.user_id, new_value=student.matric_no)
    db.session.commit()
    flash(f"Student '{student.matric_no}' {state.lower()}.", "info")
    return redirect(url_for("admin.students"))


@admin_bp.route("/students/<int:student_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_student(student_id):
    """Admin edits a student's profile — level, entry_year, dob, email, dept."""
    student = Student.query.get_or_404(student_id)
    from datetime import date as _date

    old_vals = (f"level={student.level}, entry_year={student.entry_year}, "
                f"email={student.email}")

    level = request.form.get("level", student.level)
    if level in ("100","200","300","400"):
        student.level = level

    ey = request.form.get("entry_year","").strip()
    student.entry_year = int(ey) if ey.isdigit() and len(ey)==4 else student.entry_year

    dob_raw = request.form.get("date_of_birth","").strip()
    if dob_raw:
        try:
            student.date_of_birth = _date.fromisoformat(dob_raw)
        except ValueError:
            pass

    email = request.form.get("email","").strip().lower()
    student.email = email or student.email

    dept = request.form.get("department","").strip()
    if dept:
        student.department = dept

    fn = request.form.get("first_name","").strip()
    ln = request.form.get("last_name","").strip()
    mn = request.form.get("middle_name","").strip()
    if fn: student.first_name = fn
    if ln: student.last_name  = ln
    student.middle_name = mn or None

    new_vals = (f"level={student.level}, entry_year={student.entry_year}, "
                f"email={student.email}")
    log_action("STUDENT_EDIT","students", student_id,
               old_value=old_vals, new_value=new_vals)
    db.session.commit()
    flash(f"Student {student.matric_no} profile updated.", "success")
    return redirect(url_for("admin.students"))


@admin_bp.route("/students/<int:student_id>/reset-password", methods=["POST"])
@login_required
@admin_required
def reset_student_password(student_id):
    student  = Student.query.get_or_404(student_id)
    new_hash = bcrypt.generate_password_hash("arps1234").decode("utf-8")
    student.user.password_hash = new_hash
    log_action("PASSWORD_RESET", "users", student.user_id, new_value=student.matric_no)
    db.session.commit()
    flash(f"Password for {student.matric_no} reset to 'arps1234'. Inform the student.", "success")
    return redirect(url_for("admin.students"))


# ── Bulk import ────────────────────────────────────────────────
@admin_bp.route("/students/bulk", methods=["GET", "POST"])
@login_required
@admin_required
def bulk_students():
    errors = []; imported = 0
    if request.method == "POST":
        file = request.files.get("csv_file")
        if not file or file.filename == "":
            flash("No file selected.", "danger")
            return render_template("admin/bulk_students.html", errors=[], imported=0)
        if not file.filename.endswith(".csv"):
            flash("Only .csv files are accepted.", "danger")
            return render_template("admin/bulk_students.html", errors=[], imported=0)

        stream  = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
        reader  = csv.DictReader(stream)
        req_cols = {"matric_no", "first_name", "last_name"}
        if not req_cols.issubset(set(reader.fieldnames or [])):
            flash(f"CSV must include: {', '.join(req_cols)}", "danger")
            return render_template("admin/bulk_students.html", errors=[], imported=0)

        default_pw = bcrypt.generate_password_hash("arps1234").decode("utf-8")
        for i, row in enumerate(reader, 2):
            matric = row.get("matric_no","").strip()
            fn = row.get("first_name","").strip()
            ln = row.get("last_name","").strip()
            mn = row.get("middle_name","").strip()
            lvl = row.get("level","100").strip()
            ey  = row.get("entry_year","").strip()

            if not all([matric, fn, ln]):
                errors.append(f"Row {i}: matric_no, first_name, last_name required."); continue
            if lvl not in ("100","200","300","400"):
                errors.append(f"Row {i}: invalid level '{lvl}'."); continue
            if User.query.filter_by(username=matric).first():
                errors.append(f"Row {i}: '{matric}' already exists — skipped."); continue

            u = User(username=matric, password_hash=default_pw, role="student")
            db.session.add(u); db.session.flush()
            db.session.add(Student(
                user_id=u.id, matric_no=matric, first_name=fn,
                middle_name=mn or None, last_name=ln, level=lvl,
                entry_year=int(ey) if ey.isdigit() else None,
            ))
            imported += 1

        if errors and imported == 0:
            db.session.rollback()
        else:
            log_action("BULK_IMPORT", "students", new_value=f"{imported} imported")
            db.session.commit()
            invalidate("routes.admin._dashboard_counts")
            flash(f"{imported} student(s) imported. {len(errors)} skipped.", "success" if not errors else "warning")

    return render_template("admin/bulk_students.html", errors=errors, imported=imported)


@admin_bp.route("/students/template")
@login_required
@admin_required
def download_student_template():
    csv_content = "matric_no,first_name,last_name,middle_name,level,entry_year\nU22/FNS/CSC/001,Amina,Bello,Grace,100,2022\n"
    return Response(csv_content, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=student_template.csv"})


# ── Registrations ──────────────────────────────────────────────
@admin_bp.route("/registrations")
@login_required
@admin_required
def registrations():
    active = AcademicSession.query.filter_by(is_current=True).first()
    sy  = request.args.get("session", active.session_year if active else "2023/2024")
    sem = request.args.get("semester", active.semester    if active else "First")
    lvl = request.args.get("level", "")
    page     = request.args.get("page", 1, type=int)
    per_page = min(max(request.args.get("per_page", 50, type=int), 20), 200)

    q = (CourseRegistration.query
         .options(joinedload(CourseRegistration.student), joinedload(CourseRegistration.course))
         .filter_by(session_year=sy, semester=sem)
         .join(Student).join(Course))
    if lvl: q = q.filter(Course.level == lvl)
    q = q.order_by(Student.last_name, Course.course_code)
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    return render_template("admin/registrations.html",
        registrations = pagination.items,
        pagination=pagination,
        session_year=sy, semester=sem, level=lvl,
        all_students = Student.query.order_by(Student.last_name).all(),
        all_courses  = Course.query.filter_by(is_active=True).order_by(Course.course_code).all(),
    )


@admin_bp.route("/registrations/add", methods=["POST"])
@login_required
@admin_required
def add_registration():
    sid = int(request.form.get("student_id"))
    cid = int(request.form.get("course_id"))
    sy  = request.form.get("session_year","2023/2024")
    sem = request.form.get("semester","First")
    if CourseRegistration.query.filter_by(student_id=sid, course_id=cid, session_year=sy, semester=sem).first():
        flash("Already registered.", "warning")
    else:
        db.session.add(CourseRegistration(student_id=sid, course_id=cid, session_year=sy, semester=sem))
        s = Student.query.get(sid); c = Course.query.get(cid)
        log_action("REG_ADD","course_registrations", new_value=f"{s.matric_no}→{c.course_code}")
        db.session.commit()
        flash("Registration added.", "success")
    return redirect(url_for("admin.registrations", session=sy, semester=sem))


@admin_bp.route("/registrations/<int:reg_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_registration(reg_id):
    reg = CourseRegistration.query.get_or_404(reg_id)
    info = f"{reg.student.matric_no}→{reg.course.course_code}"
    log_action("REG_DELETE","course_registrations", reg_id, old_value=info)
    db.session.delete(reg); db.session.commit()
    flash(f"Registration removed: {info}", "warning")
    return redirect(url_for("admin.registrations"))


# ── Compute ────────────────────────────────────────────────────
@admin_bp.route("/compute")
@login_required
@admin_required
def compute():
    results     = bulk_compute_department_cgpa()
    student_map = {s.matric_no: s.id for s in Student.query.all()}
    return render_template("admin/compute.html", results=results, student_map=student_map)


# ── Transcripts ────────────────────────────────────────────────
@admin_bp.route("/transcript/<int:student_id>")
@login_required
@admin_required
def view_transcript(student_id):
    student   = Student.query.get_or_404(student_id)
    cgpa_data = compute_cgpa(student.id, published_only=False)   # admin sees all
    log_action("TRANSCRIPT_VIEW","students", student_id, new_value=student.matric_no)
    db.session.commit()
    return render_template("admin/transcript.html", student=student,
                           cgpa_data=cgpa_data, now=date.today())


@admin_bp.route("/transcript/<int:student_id>/pdf")
@login_required
@admin_required
def download_transcript(student_id):
    from transcript_pdf import generate_transcript_pdf
    from qr_verify import create_transcript_token
    student   = Student.query.get_or_404(student_id)
    cgpa_data = compute_cgpa(student.id, published_only=False)

    # Auto-generate a QR verification token for this transcript
    note = request.args.get("note", "Official Transcript")
    tt   = create_transcript_token(
        student_id=student.id,
        generated_by_user_id=current_user.id,
        note=note,
    )
    log_action("TRANSCRIPT_DOWNLOAD","students", student_id, new_value=student.matric_no)
    db.session.commit()

    # Use SERVER_URL from config if set, otherwise detect from request
    from flask import current_app
    base_url = (current_app.config.get("SERVER_URL","").rstrip("/")
                or request.host_url.rstrip("/"))
    pdf_bytes = generate_transcript_pdf(student, cgpa_data, token=tt, base_url=base_url, doc_type="transcript")
    buf = io.BytesIO(pdf_bytes); buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name=f"Transcript_{student.matric_no.replace('/','_')}.pdf")


# ── Audit ──────────────────────────────────────────────────────
@admin_bp.route("/audit")
@login_required
@admin_required
def audit_log():
    page     = request.args.get("page", 1, type=int)
    per_page = min(max(request.args.get("per_page", 50, type=int), 20), 200)
    action_filter = request.args.get("action", "").strip()

    q = AuditLog.query.options(joinedload(AuditLog.user))
    if action_filter:
        q = q.filter(AuditLog.action == action_filter)
    q = q.order_by(AuditLog.logged_at.desc())

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    # Distinct action list for the filter dropdown — cheap, cached briefly.
    @cached(ttl=120)
    def _distinct_actions():
        return [r[0] for r in db.session.query(AuditLog.action).distinct().all()]

    return render_template("admin/audit_log.html",
        logs=pagination.items,
        pagination=pagination,
        action_filter=action_filter,
        distinct_actions=_distinct_actions(),
    )


# ══════════════════════════════════════════════════════════════
# QR-CODE TRANSCRIPT TOKENS  (admin management)
# ══════════════════════════════════════════════════════════════
@admin_bp.route("/tokens")
@login_required
@admin_required
def tokens():
    """List all issued transcript tokens."""
    from models import TranscriptToken
    page     = request.args.get("page", 1, type=int)
    per_page = min(max(request.args.get("per_page", 30, type=int), 10), 100)

    q = (TranscriptToken.query
         .options(joinedload(TranscriptToken.student))
         .order_by(TranscriptToken.generated_at.desc()))
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    # Accurate totals via COUNT queries — NOT the paginated page's length.
    total_count   = TranscriptToken.query.count()
    revoked_count = TranscriptToken.query.filter_by(is_revoked=True).count()
    valid_count   = total_count - revoked_count
    total_scans   = db.session.query(db.func.coalesce(db.func.sum(TranscriptToken.scan_count), 0)).scalar()

    return render_template("admin/tokens.html", tokens=pagination.items, pagination=pagination,
                            total_count=total_count, valid_count=valid_count, revoked_count=revoked_count,
                            total_scans=total_scans)


@admin_bp.route("/tokens/generate/<int:student_id>", methods=["POST"])
@login_required
@admin_required
def generate_token(student_id):
    """Generate a new QR transcript token for a student."""
    from qr_verify import create_transcript_token
    student = Student.query.get_or_404(student_id)
    note    = request.form.get("note", "Official Transcript").strip()
    expires = request.form.get("expires_in_days", "").strip()
    expires_days = int(expires) if expires.isdigit() and int(expires) > 0 else None

    tt = create_transcript_token(
        student_id=student.id,
        generated_by_user_id=current_user.id,
        expires_in_days=expires_days,
        note=note,
    )
    log_action("TOKEN_GENERATE", "transcript_tokens", tt.id,
               new_value=f"{student.matric_no} — {note}")
    db.session.commit()

    flash(f"✅ QR token generated for {student.matric_no}. "
          f"Token: {tt.token[:16]}…", "success")
    return redirect(url_for("admin.view_transcript", student_id=student.id))


@admin_bp.route("/tokens/<int:token_id>/revoke", methods=["POST"])
@login_required
@admin_required
def revoke_token(token_id):
    """Revoke a transcript token — makes the QR code invalid."""
    from models import TranscriptToken
    tt = TranscriptToken.query.get_or_404(token_id)
    from datetime import datetime as dt
    tt.is_revoked = True
    tt.revoked_at = dt.utcnow()
    tt.revoked_by = current_user.id
    log_action("TOKEN_REVOKE", "transcript_tokens", token_id,
               old_value=f"Student: {tt.student.matric_no}",
               new_value="REVOKED")
    db.session.commit()
    flash(f"Token for {tt.student.matric_no} has been revoked. "
          f"The QR code is now invalid.", "warning")
    return redirect(url_for("admin.tokens"))


@admin_bp.route("/tokens/<int:token_id>/qr")
@login_required
@admin_required
def download_token_qr(token_id):
    """Return the QR code PNG for a token."""
    from models import TranscriptToken
    from qr_verify import generate_qr_png, build_verify_url
    tt = TranscriptToken.query.get_or_404(token_id)
    from flask import current_app
    base_url = (current_app.config.get("SERVER_URL","").rstrip("/")
                or request.host_url.rstrip("/"))
    url = build_verify_url(tt.token, base_url=base_url)
    png = generate_qr_png(url, box_size=8)
    return send_file(
        io.BytesIO(png),
        mimetype="image/png",
        as_attachment=True,
        download_name=f"QR_{tt.student.matric_no.replace('/','_')}.png",
    )


# ══════════════════════════════════════════════════════════════
# EMAIL NOTIFICATIONS
# ══════════════════════════════════════════════════════════════

@admin_bp.route("/notifications")
@login_required
@admin_required
def notifications():
    """Email notification log and send interface."""
    from models import EmailNotification
    page     = request.args.get("page", 1, type=int)
    per_page = min(max(request.args.get("per_page", 40, type=int), 20), 200)

    q = (EmailNotification.query
         .options(joinedload(EmailNotification.student))
         .order_by(EmailNotification.sent_at.desc()))
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    total_count  = EmailNotification.query.count()
    sent_count   = EmailNotification.query.filter_by(status="sent").count()
    failed_count = EmailNotification.query.filter_by(status="failed").count()
    unique_students = db.session.query(EmailNotification.student_id).distinct().count()

    sessions_list = AcademicSession.query.order_by(AcademicSession.id.desc()).all()
    levels = ['100','200','300','400']
    return render_template("admin/notifications.html",
                           logs=pagination.items,
                           pagination=pagination,
                           total_count=total_count,
                           sent_count=sent_count,
                           failed_count=failed_count,
                           unique_students=unique_students,
                           sessions=sessions_list,
                           levels=levels)


@admin_bp.route("/notifications/send-bulk", methods=["POST"])
@login_required
@admin_required
def send_bulk_notifications():
    """Send result notification emails to all students of a level/session."""
    from email_notify import send_bulk_result_notifications
    from flask import request, url_for

    session_year = request.form.get("session_year", "").strip()
    semester     = request.form.get("semester", "First")
    level        = request.form.get("level", "")

    if not session_year:
        flash("Session year is required.", "danger")
        return redirect(url_for("admin.notifications"))

    # Find target students
    q = Student.query
    if level:
        q = q.filter_by(level=level)
    students = q.filter(Student.email.isnot(None)).all()

    if not students:
        flash("No students with email addresses found for the selected filter.", "warning")
        return redirect(url_for("admin.notifications"))

    portal_url = url_for("auth.login", _external=True)

    results = send_bulk_result_notifications(
        students=students,
        session_year=session_year,
        semester=semester,
        sent_by_user_id=current_user.id,
        portal_url=portal_url,
    )

    log_action("BULK_EMAIL_SENT", "email_notifications",
               new_value=f"{session_year} {semester} L{level} — sent:{results['sent']} failed:{results['failed']}")
    db.session.commit()

    msg = (f"✅ Notifications sent: {results['sent']} delivered, "
           f"{results['failed']} failed, {results['skipped']} skipped (no email).")
    flash(msg, "success" if results["failed"] == 0 else "warning")
    return redirect(url_for("admin.notifications"))


@admin_bp.route("/notifications/send-single/<int:student_id>", methods=["POST"])
@login_required
@admin_required
def send_single_notification(student_id):
    """Send result notification to one student."""
    from email_notify import send_result_notification
    from engine import compute_cgpa
    from flask import url_for

    student      = Student.query.get_or_404(student_id)
    session_year = request.form.get("session_year", "").strip()
    semester     = request.form.get("semester", "First")

    if not student.email:
        flash(f"Student {student.matric_no} has no email address. Update their profile first.", "danger")
        return redirect(url_for("admin.students"))

    cgpa_data  = compute_cgpa(student.id, published_only=False)
    portal_url = url_for("auth.login", _external=True)

    result = send_result_notification(
        student=student,
        cgpa_data=cgpa_data,
        session_year=session_year,
        semester=semester,
        sent_by_user_id=current_user.id,
        portal_url=portal_url,
    )

    if result["status"] == "sent":
        flash(f"✅ Result notification sent to {student.email}.", "success")
    else:
        flash(f"❌ Failed to send email to {student.email}: {result['error']}", "danger")

    return redirect(url_for("admin.students"))


@admin_bp.route("/students/<int:student_id>/update-email", methods=["POST"])
@login_required
@admin_required
def update_student_email(student_id):
    """Update a student's email address."""
    student = Student.query.get_or_404(student_id)
    new_email = request.form.get("email", "").strip().lower()
    old_email = student.email or "—"

    student.email = new_email or None
    log_action("STUDENT_EMAIL_UPDATE", "students", student_id,
               old_value=old_email, new_value=new_email or "removed")
    db.session.commit()
    flash(f"Email for {student.matric_no} updated to: {new_email or '(removed)'}.", "success")
    return redirect(url_for("admin.students"))


# ── Test Email Configuration ──────────────────────────────────
@admin_bp.route("/email/test", methods=["POST"])
@login_required
@admin_required
def test_email():
    """Send a test email to verify SMTP configuration is working."""
    from flask_mail import Message
    from app import mail

    recipient = request.form.get("test_email", "").strip()
    if not recipient:
        flash("Please enter an email address to send the test to.", "danger")
        return redirect(url_for("admin.notifications"))

    test_html = """
    <div style="font-family:Arial,sans-serif;max-width:500px;margin:20px auto;
                padding:30px;border:1px solid #D8E0ED;border-radius:12px;">
      <div style="background:#0B1F3A;padding:20px;border-radius:8px 8px 0 0;text-align:center;">
        <span style="font-size:20px;">&#127891;</span>
        <h2 style="color:#fff;margin:8px 0 0;font-family:Georgia,serif;">IBB University ARPS</h2>
        <p style="color:rgba(255,255,255,.5);font-size:12px;margin:4px 0 0;">Email Configuration Test</p>
      </div>
      <div style="background:#D1FAE5;border:1.5px solid #6EE7B7;border-radius:8px;
                  padding:16px;margin-top:20px;">
        <strong style="color:#065F46;">&#10003; Email is working correctly!</strong>
        <p style="color:#065F46;font-size:13px;margin:6px 0 0;">
          Your SMTP configuration is set up correctly. Students will receive
          result notifications at this address.
        </p>
      </div>
      <p style="font-size:12px;color:#8A9BB5;text-align:center;margin-top:20px;">
        Ibrahim Badamasi Babangida University, Lapai, Niger State
      </p>
    </div>
    """

    try:
        msg = Message(
            subject="ARPS Test Email — IBB University",
            recipients=[recipient],
            body=(
                "This is a test email from the ARPS system of Ibrahim Badamasi "
                "Babangida University, Lapai, Niger State. If you received this, "
                "your email configuration is working correctly."
            ),
            html=test_html,
        )
        mail.send(msg)
        flash(f"✅ Test email sent successfully to {recipient}. Check your inbox.", "success")
        log_action("EMAIL_TEST", "email_notifications", new_value=f"Test sent to {recipient}")
        db.session.commit()
    except Exception as e:
        flash(f"❌ Email failed: {str(e)[:200]}. Check your SMTP settings in .env", "danger")

    return redirect(url_for("admin.notifications"))


# ══════════════════════════════════════════════════════════════
# SPILLOVER MANAGEMENT
# ══════════════════════════════════════════════════════════════

@admin_bp.route("/spillover")
@login_required
@admin_required
def spillover():
    """List spillover students — auto-detects by time overdue AND failed courses."""
    from models import SpilloverRecord
    from datetime import datetime as dt
    from engine import get_spillover_candidates

    all_spillovers  = SpilloverRecord.query.order_by(
        SpilloverRecord.is_cleared, SpilloverRecord.marked_at.desc()
    ).all()
    existing_ids = {sp.student_id for sp in all_spillovers}

    # Smart auto-detection: time overdue OR failed courses
    current_year = dt.utcnow().year
    all_candidates = get_spillover_candidates(current_year)
    # Only show candidates not yet formally marked
    auto_candidates = [c for c in all_candidates if c["student"].id not in existing_ids]

    return render_template("admin/spillover.html",
                           spillovers=all_spillovers,
                           auto_candidates=auto_candidates)


@admin_bp.route("/spillover/mark/<int:student_id>", methods=["POST"])
@login_required
@admin_required
def mark_spillover(student_id):
    """Mark a student as spillover — auto-populates failed courses from actual grades."""
    from models import SpilloverRecord
    from engine import get_failed_courses
    from datetime import datetime as dt

    student = Student.query.get_or_404(student_id)

    existing = SpilloverRecord.query.filter_by(student_id=student_id).first()
    if existing and not existing.is_cleared:
        flash(f"{student.matric_no} is already marked as spillover.", "warning")
        return redirect(url_for("admin.spillover"))

    reason     = request.form.get("reason", "").strip()
    extra      = request.form.get("extra_sessions", "2").strip()
    note       = request.form.get("note", "").strip()

    # Auto-detect outstanding courses from actual FAILED grades in Score table
    failed = get_failed_courses(student_id)
    auto_outstanding = ", ".join(c["code"] for c in failed) if failed else ""
    # Admin can override, but auto-detect is the default
    outstanding = request.form.get("outstanding_courses", "").strip() or auto_outstanding

    # Build reason if not provided
    if not reason:
        current_year = dt.utcnow().year
        reasons = []
        if student.entry_year and student.entry_year + 4 < current_year:
            reasons.append(f"Exceeded 4-year programme duration.")
        if failed:
            reasons.append(f"Has {len(failed)} failed course(s): {auto_outstanding}.")
        reason = " ".join(reasons) or "Student did not meet graduation requirements."

    rec = SpilloverRecord(
        student_id          = student_id,
        reason              = reason,
        outstanding_courses = outstanding,
        extra_sessions      = int(extra) if extra.isdigit() else 2,
        marked_by           = current_user.id,
        note                = note,
    )
    db.session.add(rec)
    log_action("SPILLOVER_MARK", "spillover_records", student_id,
               new_value=f"{student.matric_no} — {reason[:80]}")
    db.session.commit()
    flash(f"✅ {student.matric_no} ({student.full_name}) marked as spillover. "
          f"Outstanding: {outstanding or 'none recorded'}.", "warning")
    return redirect(url_for("admin.spillover"))


@admin_bp.route("/spillover/clear/<int:student_id>", methods=["POST"])
@login_required
@admin_required
def clear_spillover(student_id):
    """Clear spillover status — student has met all requirements."""
    from models import SpilloverRecord
    from datetime import datetime as dt
    student = Student.query.get_or_404(student_id)
    rec = SpilloverRecord.query.filter_by(student_id=student_id).first()
    if not rec:
        flash("No spillover record found for this student.", "danger")
        return redirect(url_for("admin.spillover"))

    rec.is_cleared = True
    rec.cleared_at = dt.utcnow()
    rec.cleared_by = current_user.id
    rec.note       = (request.form.get("note", "") or rec.note or "Cleared by admin.")
    log_action("SPILLOVER_CLEAR", "spillover_records", student_id,
               new_value=f"{student.matric_no} cleared")
    db.session.commit()
    flash(f"✅ {student.matric_no} spillover status cleared — student is now graduated.", "success")
    return redirect(url_for("admin.spillover"))


# ══════════════════════════════════════════════════════════════
# GRADUATING STUDENTS LIST
# ══════════════════════════════════════════════════════════════

@admin_bp.route("/graduating")
@login_required
@admin_required
def graduating_students():
    """View list of students eligible to graduate."""
    from engine import get_graduating_students
    from datetime import datetime as dt

    current_year = dt.utcnow().year
    graduating   = get_graduating_students(current_year)

    return render_template("admin/graduating.html",
                           graduating=graduating,
                           current_year=current_year)


@admin_bp.route("/graduating/download")
@login_required
@admin_required
def download_graduating_list():
    """Download graduating students list as CSV."""
    from engine import get_graduating_students
    from datetime import datetime as dt
    import csv, io

    current_year = dt.utcnow().year
    graduating   = get_graduating_students(current_year)

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "S/N", "Matric Number", "Full Name", "Department",
        "Level", "Entry Year", "Expected Graduation",
        "Total Credit Units", "CGPA", "Degree Classification",
        "Email", "Phone"
    ])

    # Rows
    for i, g in enumerate(graduating, 1):
        s = g["student"]
        writer.writerow([
            i,
            s.matric_no,
            s.full_name,
            s.department or "Computer Science",
            s.level,
            s.entry_year or "—",
            g["expected_grad"],
            g["total_units"],
            f"{g['cgpa']:.2f}",
            g["degree_class"],
            s.email or "—",
            s.phone or "—",
        ])

    log_action("GRADUATING_LIST_DOWNLOAD", "students",
               new_value=f"{len(graduating)} students, {current_year}")
    db.session.commit()

    output.seek(0)
    from flask import make_response
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=Graduating_Students_{current_year}.csv"
    )
    return response


@admin_bp.route("/graduating/download-pdf")
@login_required
@admin_required
def download_graduating_pdf():
    """Download graduating students list as a printable PDF."""
    from engine import get_graduating_students
    from datetime import datetime as dt, date
    from io import BytesIO

    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer, HRFlowable)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    current_year = dt.utcnow().year
    graduating   = get_graduating_students(current_year)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1.8*cm, rightMargin=1.8*cm,
                            topMargin=1.8*cm, bottomMargin=1.8*cm)

    styles = getSampleStyleSheet()
    NAVY   = colors.HexColor("#1A5C2A")
    GOLD   = colors.HexColor("#A5D6A7")
    PALE   = colors.HexColor("#F1F8F2")
    WHITE  = colors.white
    BLACK  = colors.black
    TEXT   = colors.HexColor("#374151")

    def P(text, size=9, bold=False, align=TA_LEFT, color=BLACK):
        fn = "Helvetica-Bold" if bold else "Helvetica"
        return Paragraph(text, ParagraphStyle("p", fontName=fn, fontSize=size,
                                              textColor=color, alignment=align))

    story = []

    # Header
    story.append(P("IBRAHIM BADAMASI BABANGIDA UNIVERSITY, LAPAI",
                   14, bold=True, align=TA_CENTER, color=NAVY))
    story.append(P("Faculty of Science — Department of Computer Science",
                   9, align=TA_CENTER, color=TEXT))
    story.append(Spacer(1, 4))
    story.append(P(f"LIST OF GRADUATING STUDENTS — {current_year}",
                   11, bold=True, align=TA_CENTER, color=NAVY))
    story.append(P(f"Generated: {date.today().strftime('%d %B %Y')}   "
                   f"Total Graduating Students: {len(graduating)}",
                   8, align=TA_CENTER, color=TEXT))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=2, color=NAVY))
    story.append(Spacer(1, 6))

    if not graduating:
        story.append(P("No students currently eligible for graduation.", 10, align=TA_CENTER))
    else:
        # Table
        col_w = [1*cm, 3.5*cm, 5.5*cm, 2*cm, 2*cm, 2.5*cm, 5*cm]
        rows  = [[
            P("S/N",     8, bold=True, align=TA_CENTER, color=WHITE),
            P("Matric No",8, bold=True, color=WHITE),
            P("Full Name",8, bold=True, color=WHITE),
            P("Level",   8, bold=True, align=TA_CENTER, color=WHITE),
            P("CGPA",    8, bold=True, align=TA_CENTER, color=WHITE),
            P("Units",   8, bold=True, align=TA_CENTER, color=WHITE),
            P("Degree Classification", 8, bold=True, color=WHITE),
        ]]

        for i, g in enumerate(graduating, 1):
            s    = g["student"]
            bg   = PALE if i % 2 == 0 else WHITE
            rows.append([
                P(str(i),        8, align=TA_CENTER),
                P(s.matric_no,   8, bold=True),
                P(s.full_name,   8),
                P(s.level,       8, align=TA_CENTER),
                P(f"{g['cgpa']:.2f}", 8, bold=True, align=TA_CENTER, color=NAVY),
                P(str(g["total_units"]), 8, align=TA_CENTER),
                P(g["degree_class"], 7),
            ])

        tbl = Table(rows, colWidths=col_w, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,0),  NAVY),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, PALE]),
            ("GRID",         (0,0), (-1,-1), .3, colors.HexColor("#C8E6C9")),
            ("TOPPADDING",   (0,0), (-1,-1), 5),
            ("BOTTOMPADDING",(0,0), (-1,-1), 5),
            ("LEFTPADDING",  (0,0), (-1,-1), 5),
            ("FONTSIZE",     (0,0), (-1,-1), 8),
            ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(tbl)

    # Footer
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#C8E6C9")))
    story.append(Spacer(1, 4))
    story.append(P("This list is generated from the ARPS system of Ibrahim Badamasi Babangida "
                   "University, Lapai, Niger State. For official graduation clearance, "
                   "students must present their clearance form to the Registry.",
                   7, align=TA_CENTER, color=TEXT))

    doc.build(story)
    buf.seek(0)

    log_action("GRADUATING_PDF_DOWNLOAD", "students",
               new_value=f"{len(graduating)} students, {current_year}")
    db.session.commit()

    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name=f"Graduating_Students_{current_year}.pdf")


# ══════════════════════════════════════════════════════════════
# BACKUP & RESTORE
# ══════════════════════════════════════════════════════════════

@admin_bp.route("/backup")
@login_required
@admin_required
def backup_page():
    """Backup & Restore management page."""
    import os, glob
    backup_dir = get_backup_dir()
    files = []
    for f in sorted(glob.glob(os.path.join(backup_dir, "*.sql")), reverse=True)[:20]:
        stat  = os.stat(f)
        files.append({
            "name":    os.path.basename(f),
            "size":    stat.st_size,
            "size_kb": f"{stat.st_size/1024:.1f} KB",
            "modified": __import__("datetime").datetime.fromtimestamp(stat.st_mtime),
        })
    return render_template("admin/backup.html", backups=files)


@admin_bp.route("/backup/create", methods=["POST"])
@login_required
@admin_required
def create_backup():
    """Run mysqldump and save the .sql file to the backups/ folder."""
    import subprocess, os
    from datetime import datetime as dt
    from flask import current_app

    cfg       = current_app.config
    db_host   = os.environ.get("DB_HOST", "localhost")
    db_port   = os.environ.get("DB_PORT", "3306")
    db_user   = os.environ.get("DB_USER", "root")
    db_pass   = os.environ.get("DB_PASSWORD", "")
    db_name   = os.environ.get("DB_NAME", "arps_db")

    backup_dir = get_backup_dir()

    ts       = dt.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"arps_backup_{ts}.sql"
    filepath = os.path.join(backup_dir, filename)

    env = os.environ.copy()
    env["MYSQL_PWD"] = db_pass   # Avoid password in command line

    cmd = [
        "mysqldump",
        f"--host={db_host}",
        f"--port={db_port}",
        f"--user={db_user}",
        "--single-transaction",
        "--routines",
        "--triggers",
        db_name,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
        if result.returncode != 0:
            flash(f"❌ Backup failed: {result.stderr[:200]}", "danger")
            return redirect(url_for("admin.backup_page"))

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(result.stdout)

        size_kb = os.path.getsize(filepath) / 1024
        log_action("DB_BACKUP", "backup", new_value=f"{filename} ({size_kb:.1f} KB)")
        db.session.commit()
        flash(f"✅ Backup created: {filename} ({size_kb:.1f} KB)", "success")
    except FileNotFoundError:
        flash("❌ mysqldump not found. Make sure MySQL is installed and in your PATH.", "danger")
    except subprocess.TimeoutExpired:
        flash("❌ Backup timed out. Database may be too large — try again.", "danger")
    except Exception as e:
        flash(f"❌ Backup error: {str(e)[:200]}", "danger")

    return redirect(url_for("admin.backup_page"))


@admin_bp.route("/backup/download/<filename>")
@login_required
@admin_required
def download_backup(filename):
    """Download a backup file."""
    import os
    from flask import send_from_directory

    # Security: only allow .sql files with safe filenames
    if not filename.endswith(".sql") or "/" in filename or ".." in filename:
        flash("Invalid backup file name.", "danger")
        return redirect(url_for("admin.backup_page"))

    backup_dir = get_backup_dir()
    log_action("DB_BACKUP_DOWNLOAD", "backup", new_value=filename)
    db.session.commit()
    return send_from_directory(backup_dir, filename, as_attachment=True)


@admin_bp.route("/backup/delete/<filename>", methods=["POST"])
@login_required
@admin_required
def delete_backup(filename):
    """Delete a backup file from disk."""
    import os

    if not filename.endswith(".sql") or "/" in filename or ".." in filename:
        flash("Invalid backup file name.", "danger")
        return redirect(url_for("admin.backup_page"))

    backup_dir = get_backup_dir()
    filepath   = os.path.join(backup_dir, filename)

    if os.path.exists(filepath):
        os.remove(filepath)
        log_action("DB_BACKUP_DELETE", "backup", new_value=filename)
        db.session.commit()
        flash(f"Backup {filename} deleted.", "success")
    else:
        flash("Backup file not found.", "warning")

    return redirect(url_for("admin.backup_page"))


@admin_bp.route("/backup/restore/<filename>", methods=["POST"])
@login_required
@admin_required
def restore_backup(filename):
    """Restore the database from a backup file using mysql command."""
    import subprocess, os

    if not filename.endswith(".sql") or "/" in filename or ".." in filename:
        flash("Invalid backup file name.", "danger")
        return redirect(url_for("admin.backup_page"))

    backup_dir = get_backup_dir()
    filepath   = os.path.join(backup_dir, filename)

    if not os.path.exists(filepath):
        flash("Backup file not found.", "danger")
        return redirect(url_for("admin.backup_page"))

    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = os.environ.get("DB_PORT", "3306")
    db_user = os.environ.get("DB_USER", "root")
    db_pass = os.environ.get("DB_PASSWORD", "")
    db_name = os.environ.get("DB_NAME", "arps_db")

    env = os.environ.copy()
    env["MYSQL_PWD"] = db_pass

    cmd = ["mysql", f"--host={db_host}", f"--port={db_port}",
           f"--user={db_user}", db_name]

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            result = subprocess.run(cmd, stdin=f, capture_output=True, text=True,
                                    env=env, timeout=180)
        if result.returncode != 0:
            flash(f"❌ Restore failed: {result.stderr[:200]}", "danger")
        else:
            log_action("DB_RESTORE", "backup", new_value=filename)
            db.session.commit()
            flash(f"✅ Database restored from {filename}. Please verify your data.", "success")
    except FileNotFoundError:
        flash("❌ mysql command not found. Ensure MySQL client is installed.", "danger")
    except subprocess.TimeoutExpired:
        flash("❌ Restore timed out.", "danger")
    except Exception as e:
        flash(f"❌ Restore error: {str(e)[:200]}", "danger")

    return redirect(url_for("admin.backup_page"))


# ══════════════════════════════════════════════════════════════
# ADMIN / EXAM OFFICER — PROFILE & CHANGE PASSWORD
# ══════════════════════════════════════════════════════════════

@admin_bp.route("/profile", methods=["GET", "POST"])
@login_required
@admin_required
def admin_profile():
    """Admin can update their own profile details."""
    lecturer = current_user.lecturer_profile
    if not lecturer:
        flash("Profile not found.", "danger")
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        lecturer.first_name = request.form.get("first_name", lecturer.first_name).strip() or lecturer.first_name
        lecturer.last_name  = request.form.get("last_name",  lecturer.last_name).strip()  or lecturer.last_name
        email = request.form.get("email", "").strip().lower()
        if hasattr(lecturer, 'email'):
            lecturer.email = email or None
        log_action("ADMIN_PROFILE_UPDATE", "users", current_user.id)
        db.session.commit()
        flash("✅ Profile updated successfully.", "success")
        return redirect(url_for("admin.admin_profile"))

    return render_template("admin/profile.html", lecturer=lecturer)


@admin_bp.route("/change-password", methods=["GET", "POST"])
@login_required
@admin_required
def admin_change_password():
    """Admin changes their own password."""
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw     = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if not bcrypt.check_password_hash(current_user.password_hash, current_pw):
            flash("Current password is incorrect.", "danger")
            return redirect(url_for("admin.admin_change_password"))
        if len(new_pw) < 6:
            flash("New password must be at least 6 characters.", "danger")
            return redirect(url_for("admin.admin_change_password"))
        if new_pw != confirm_pw:
            flash("New passwords do not match.", "danger")
            return redirect(url_for("admin.admin_change_password"))

        current_user.password_hash = bcrypt.generate_password_hash(new_pw).decode("utf-8")
        log_action("ADMIN_PASSWORD_CHANGE", "users", current_user.id)
        db.session.commit()
        flash("✅ Password changed successfully.", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/change_password.html")
