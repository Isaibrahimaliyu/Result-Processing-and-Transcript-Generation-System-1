"""
ARPS — Database Models  (v2 — with ResultPublication gate)
"""
from datetime import datetime
from flask_login import UserMixin
from app import db, login_manager


@login_manager.user_loader
def load_user(user_id: str):
    return User.query.get(int(user_id))


# ─────────────────────────────────────────────────────────────
# 1. USERS
# ─────────────────────────────────────────────────────────────
class User(db.Model, UserMixin):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(50),  nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role          = db.Column(db.Enum("student", "lecturer", "admin"), nullable=False, index=True)
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    last_login    = db.Column(db.DateTime, nullable=True)

    student_profile  = db.relationship("Student",  back_populates="user", uselist=False, cascade="all, delete-orphan")
    lecturer_profile = db.relationship("Lecturer", back_populates="user", uselist=False, cascade="all, delete-orphan")

    def is_student(self)  -> bool: return self.role == "student"
    def is_lecturer(self) -> bool: return self.role == "lecturer"
    def is_admin(self)    -> bool: return self.role == "admin"
    def __repr__(self):   return f"<User {self.username} [{self.role}]>"


# ─────────────────────────────────────────────────────────────
# 2. ACADEMIC SESSION  (admin controls active session)
# ─────────────────────────────────────────────────────────────
class AcademicSession(db.Model):
    """
    Tracks the current active session and semester.
    Only one row should have is_current=True at a time.
    """
    __tablename__ = "academic_sessions"

    id           = db.Column(db.Integer, primary_key=True)
    session_year = db.Column(db.String(9),  nullable=False)   # e.g. "2023/2024"
    semester     = db.Column(db.Enum("First", "Second"), nullable=False)
    is_current   = db.Column(db.Boolean, default=False, index=True)
    registration_open = db.Column(db.Boolean, default=True)   # students can register
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self): return f"<Session {self.session_year} {self.semester}>"


# ─────────────────────────────────────────────────────────────
# 3. STUDENTS
# ─────────────────────────────────────────────────────────────
class Student(db.Model):
    __tablename__ = "students"

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    matric_no     = db.Column(db.String(30),  nullable=False, unique=True, index=True)
    first_name    = db.Column(db.String(50),  nullable=False, index=True)
    middle_name   = db.Column(db.String(50))
    last_name     = db.Column(db.String(50),  nullable=False, index=True)
    date_of_birth = db.Column(db.Date)
    department    = db.Column(db.String(100), default="Computer Science", index=True)
    level         = db.Column(db.Enum("100", "200", "300", "400"), default="100", index=True)
    entry_year    = db.Column(db.SmallInteger)
    email         = db.Column(db.String(150), nullable=True)   # for notifications
    phone         = db.Column(db.String(20),  nullable=True)
    gender        = db.Column(db.Enum("M", "F"), nullable=True)
    passport_photo= db.Column(db.String(255), nullable=True)   # relative path under static/uploads/passports/

    user          = db.relationship("User",               back_populates="student_profile")
    registrations = db.relationship("CourseRegistration", back_populates="student", cascade="all, delete-orphan")
    scores        = db.relationship("Score",              back_populates="student", cascade="all, delete-orphan")

    @property
    def full_name(self) -> str:
        return " ".join(p for p in [self.first_name, self.middle_name, self.last_name] if p)

    def __repr__(self): return f"<Student {self.matric_no}>"


# ─────────────────────────────────────────────────────────────
# 4. LECTURERS
# ─────────────────────────────────────────────────────────────
class Lecturer(db.Model):
    __tablename__ = "lecturers"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    staff_id   = db.Column(db.String(30),  nullable=False, unique=True)
    first_name = db.Column(db.String(50),  nullable=False)
    last_name  = db.Column(db.String(50),  nullable=False)
    department = db.Column(db.String(100), default="Computer Science")
    email      = db.Column(db.String(150), nullable=True)   # required for password recovery

    user    = db.relationship("User",   back_populates="lecturer_profile")
    courses = db.relationship("Course", back_populates="lecturer")
    scores  = db.relationship("Score",  back_populates="lecturer")

    @property
    def full_name(self) -> str: return f"{self.first_name} {self.last_name}"
    def __repr__(self): return f"<Lecturer {self.staff_id}>"


# ─────────────────────────────────────────────────────────────
# 5. COURSES
# ─────────────────────────────────────────────────────────────
class Course(db.Model):
    __tablename__ = "courses"

    id           = db.Column(db.Integer, primary_key=True)
    course_code  = db.Column(db.String(15),  nullable=False, unique=True, index=True)
    course_title = db.Column(db.String(150), nullable=False)
    credit_unit  = db.Column(db.SmallInteger, nullable=False)
    semester     = db.Column(db.Enum("First", "Second"), nullable=False, index=True)
    level        = db.Column(db.Enum("100", "200", "300", "400"), nullable=False, index=True)
    lecturer_id  = db.Column(db.Integer, db.ForeignKey("lecturers.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active    = db.Column(db.Boolean, default=True, index=True)

    lecturer      = db.relationship("Lecturer",           back_populates="courses")
    registrations = db.relationship("CourseRegistration", back_populates="course", cascade="all, delete-orphan")
    scores        = db.relationship("Score",              back_populates="course",  cascade="all, delete-orphan")

    def __repr__(self): return f"<Course {self.course_code}>"


# ─────────────────────────────────────────────────────────────
# 6. COURSE REGISTRATIONS
# ─────────────────────────────────────────────────────────────
class CourseRegistration(db.Model):
    __tablename__ = "course_registrations"
    __table_args__ = (
        db.UniqueConstraint("student_id", "course_id", "session_year", "semester", name="uq_reg"),
        db.Index("ix_reg_student_session", "student_id", "session_year", "semester"),
        db.Index("ix_reg_course_session",  "course_id",  "session_year", "semester"),
    )

    id            = db.Column(db.Integer, primary_key=True)
    student_id    = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    course_id     = db.Column(db.Integer, db.ForeignKey("courses.id",  ondelete="CASCADE"), nullable=False)
    session_year  = db.Column(db.String(9), nullable=False)
    semester      = db.Column(db.Enum("First", "Second"), nullable=False)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship("Student", back_populates="registrations")
    course  = db.relationship("Course",  back_populates="registrations")

    def __repr__(self): return f"<Reg {self.student_id}→{self.course_id} [{self.session_year}]>"


# ─────────────────────────────────────────────────────────────
# 7. RESULT PUBLICATION  ← THE KEY GATE
#    Admin must explicitly publish results before students see them.
#    Granular per (session_year, semester, level).
# ─────────────────────────────────────────────────────────────
class ResultPublication(db.Model):
    """
    Controls whether students can view their results.
    Admin publishes results per session/semester/level.
    Until published, students see "Results not yet released" screen.
    """
    __tablename__ = "result_publications"
    __table_args__ = (
        db.UniqueConstraint("session_year", "semester", "level", name="uq_pub"),
    )

    id           = db.Column(db.Integer, primary_key=True)
    session_year = db.Column(db.String(9), nullable=False)
    semester     = db.Column(db.Enum("First", "Second"), nullable=False)
    level        = db.Column(db.Enum("100", "200", "300", "400"), nullable=False)
    is_published = db.Column(db.Boolean, default=False)
    published_at = db.Column(db.DateTime, nullable=True)
    published_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note         = db.Column(db.String(255))  # optional remark from admin

    publisher    = db.relationship("User", foreign_keys=[published_by])

    def __repr__(self): return f"<ResultPub {self.session_year} {self.semester} L{self.level} pub={self.is_published}>"


# ─────────────────────────────────────────────────────────────
# 8. SCORES
# ─────────────────────────────────────────────────────────────
GRADE_SCALE = [
    (70, "A", 5.0),
    (60, "B", 4.0),
    (50, "C", 3.0),
    (45, "D", 2.0),
    (40, "E", 1.0),
    (0,  "F", 0.0),
]

def compute_grade(total: float):
    for threshold, letter, gp in GRADE_SCALE:
        if total >= threshold:
            return letter, gp
    return "F", 0.0


class Score(db.Model):
    __tablename__ = "scores"
    __table_args__ = (
        db.UniqueConstraint("student_id", "course_id", "session_year", "semester", name="uq_score"),
        db.Index("ix_score_student_session", "student_id", "session_year", "semester"),
        db.Index("ix_score_course_session",  "course_id",  "session_year", "semester"),
    )

    id           = db.Column(db.Integer, primary_key=True)
    student_id   = db.Column(db.Integer, db.ForeignKey("students.id",  ondelete="CASCADE"), nullable=False)
    course_id    = db.Column(db.Integer, db.ForeignKey("courses.id",   ondelete="CASCADE"), nullable=False)
    lecturer_id  = db.Column(db.Integer, db.ForeignKey("lecturers.id", ondelete="SET NULL"), nullable=True)
    session_year = db.Column(db.String(9), nullable=False)
    semester     = db.Column(db.Enum("First", "Second"), nullable=False)
    ca_score     = db.Column(db.Numeric(5, 2), default=0.00)
    exam_score   = db.Column(db.Numeric(5, 2), default=0.00)
    total_score  = db.Column(db.Numeric(5, 2), default=0.00)
    grade        = db.Column(db.String(1))
    grade_point  = db.Column(db.Numeric(3, 1))
    entered_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student  = db.relationship("Student",  back_populates="scores")
    course   = db.relationship("Course",   back_populates="scores")
    lecturer = db.relationship("Lecturer", back_populates="scores")

    def set_scores(self, ca: float, exam: float):
        self.ca_score    = round(float(ca), 2)
        self.exam_score  = round(float(exam), 2)
        self.total_score = round(self.ca_score + self.exam_score, 2)
        self.grade, self.grade_point = compute_grade(float(self.total_score))

    @property
    def quality_points(self) -> float:
        return float(self.grade_point or 0) * float(self.course.credit_unit)

    def __repr__(self): return f"<Score {self.student_id}/{self.course_id}={self.total_score}>"


# ─────────────────────────────────────────────────────────────
# 9. AUDIT LOG
# ─────────────────────────────────────────────────────────────
class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action     = db.Column(db.String(100), nullable=False, index=True)
    table_name = db.Column(db.String(50))
    record_id  = db.Column(db.Integer)
    old_value  = db.Column(db.Text)
    new_value  = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    logged_at  = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship("User", foreign_keys=[user_id])
    def __repr__(self): return f"<AuditLog {self.action} by {self.user_id}>"


# ─────────────────────────────────────────────────────────────
# 10. TRANSCRIPT TOKEN  (QR-Code Verification)
# ─────────────────────────────────────────────────────────────
class TranscriptToken(db.Model):
    """
    Each time an official transcript is generated, a unique
    cryptographically-signed token is created and embedded as a
    QR code.  Anyone who scans the QR lands on the public
    verification portal which validates the token and shows a
    read-only transcript summary — WITHOUT needing a login.

    Tokens are single-use-display (not revoked on scan) but
    can be revoked by admin at any time.
    """
    __tablename__ = "transcript_tokens"

    id             = db.Column(db.Integer, primary_key=True)
    token          = db.Column(db.String(64), nullable=False, unique=True, index=True)
    student_id     = db.Column(db.Integer,
                        db.ForeignKey("students.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    generated_by   = db.Column(db.Integer,
                        db.ForeignKey("users.id", ondelete="SET NULL"),
                        nullable=True)
    generated_at   = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at     = db.Column(db.DateTime, nullable=True)   # None = never expires
    is_revoked     = db.Column(db.Boolean, default=False)
    revoked_at     = db.Column(db.DateTime, nullable=True)
    revoked_by     = db.Column(db.Integer,
                        db.ForeignKey("users.id", ondelete="SET NULL"),
                        nullable=True)
    scan_count     = db.Column(db.Integer, default=0)
    last_scanned   = db.Column(db.DateTime, nullable=True)
    note           = db.Column(db.String(255))   # e.g. "Issued for NYSC"

    student   = db.relationship("Student", foreign_keys=[student_id])
    generator = db.relationship("User",    foreign_keys=[generated_by])
    revoker   = db.relationship("User",    foreign_keys=[revoked_by])

    @property
    def is_valid(self) -> bool:
        from datetime import datetime as dt
        if self.is_revoked:
            return False
        if self.expires_at and dt.utcnow() > self.expires_at:
            return False
        return True

    def __repr__(self):
        return f"<Token {self.token[:12]}… student={self.student_id} valid={self.is_valid}>"


# ─────────────────────────────────────────────────────────────
# 11. EMAIL NOTIFICATION LOG
# ─────────────────────────────────────────────────────────────
class EmailNotification(db.Model):
    """
    Logs every result notification email sent to a student.
    Allows admin to track delivery, resend, and audit.
    """
    __tablename__ = "email_notifications"

    id             = db.Column(db.Integer, primary_key=True)
    student_id     = db.Column(db.Integer,
                        db.ForeignKey("students.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    recipient_email= db.Column(db.String(150), nullable=False)
    subject        = db.Column(db.String(255), nullable=False)
    notification_type = db.Column(
        db.Enum("result_published", "transcript_ready", "custom"),
        default="result_published"
    )
    session_year   = db.Column(db.String(9),  nullable=True)
    semester       = db.Column(db.Enum("First", "Second"), nullable=True)
    sent_at        = db.Column(db.DateTime,   default=datetime.utcnow, index=True)
    sent_by        = db.Column(db.Integer,
                        db.ForeignKey("users.id", ondelete="SET NULL"),
                        nullable=True)
    status         = db.Column(
        db.Enum("sent", "failed", "suppressed"),
        default="sent"
    )
    error_message  = db.Column(db.Text, nullable=True)

    student = db.relationship("Student", foreign_keys=[student_id])
    sender  = db.relationship("User",    foreign_keys=[sent_by])

    def __repr__(self):
        return f"<EmailNotif to={self.recipient_email} status={self.status}>"


# ─────────────────────────────────────────────────────────────
# 12. SPILLOVER  (student failed to graduate in 4 years)
# ─────────────────────────────────────────────────────────────
class SpilloverRecord(db.Model):
    """
    Tracks students who have exceeded the normal 4-year duration.
    A student becomes a spillover when they are still enrolled
    beyond their expected graduation year (entry_year + 4).

    Admins can mark a student as spillover, specify additional
    semesters/sessions to be completed, and clear the status
    once the student has met all requirements and is cleared.
    """
    __tablename__ = "spillover_records"

    id              = db.Column(db.Integer, primary_key=True)
    student_id      = db.Column(db.Integer,
                          db.ForeignKey("students.id", ondelete="CASCADE"),
                          nullable=False, unique=True)
    reason          = db.Column(db.Text, nullable=True)           # e.g. "Failed 3 carry-over courses"
    outstanding_courses = db.Column(db.Text, nullable=True)       # comma-separated course codes
    extra_sessions  = db.Column(db.SmallInteger, default=1)       # how many extra semesters approved
    marked_at       = db.Column(db.DateTime, default=datetime.utcnow)
    marked_by       = db.Column(db.Integer,
                          db.ForeignKey("users.id", ondelete="SET NULL"),
                          nullable=True)
    is_cleared      = db.Column(db.Boolean, default=False)        # True = student has finally graduated
    cleared_at      = db.Column(db.DateTime, nullable=True)
    cleared_by      = db.Column(db.Integer,
                          db.ForeignKey("users.id", ondelete="SET NULL"),
                          nullable=True)
    note            = db.Column(db.String(255), nullable=True)

    student         = db.relationship("Student",
                          foreign_keys=[student_id],
                          backref=db.backref("spillover", uselist=False))
    marker          = db.relationship("User", foreign_keys=[marked_by])
    clearer         = db.relationship("User", foreign_keys=[cleared_by])

    @property
    def status_label(self) -> str:
        return "Cleared" if self.is_cleared else "Active Spillover"

    def __repr__(self):
        return (f"<Spillover student={self.student_id} "
                f"cleared={self.is_cleared}>")


# ─────────────────────────────────────────────────────────────
# 13. PASSWORD RESET OTP
# ─────────────────────────────────────────────────────────────
class PasswordResetOTP(db.Model):
    """
    6-digit OTP for email-based password recovery.
    Expires after 15 minutes. Single-use (consumed on successful reset).
    """
    __tablename__ = "password_reset_otps"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer,
                     db.ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False)
    otp_code   = db.Column(db.String(6),   nullable=False)
    created_at = db.Column(db.DateTime,    default=datetime.utcnow)
    expires_at = db.Column(db.DateTime,    nullable=False)
    is_used    = db.Column(db.Boolean,     default=False)
    email_sent_to = db.Column(db.String(150), nullable=True)

    user = db.relationship("User", backref=db.backref("reset_otps", lazy="dynamic",
                                                       cascade="all, delete-orphan"))

    @property
    def is_valid(self) -> bool:
        return not self.is_used and datetime.utcnow() < self.expires_at

    def __repr__(self):
        return f"<OTP user={self.user_id} valid={self.is_valid}>"
