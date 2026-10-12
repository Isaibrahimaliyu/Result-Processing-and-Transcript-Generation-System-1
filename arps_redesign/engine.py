"""
ARPS — Computation Engine  (v2)
Respects ResultPublication gate — only published semesters visible to students.
"""
from __future__ import annotations
from typing import List, Dict, Tuple, Optional
from models import Score, Student, ResultPublication, db


DEGREE_CLASSES = [
    (4.50, "First Class Honours"),
    (3.50, "Second Class Honours (Upper Division)"),
    (2.40, "Second Class Honours (Lower Division)"),
    (1.50, "Third Class Honours"),
    (1.00, "Pass Class"),
    (0.00, "Fail — No Degree Awarded"),
]


def classify_degree(cgpa: float) -> str:
    for threshold, label in DEGREE_CLASSES:
        if cgpa >= threshold:
            return label
    return "Fail — No Degree Awarded"


from cache_utils import cached


def is_result_published(session_year: str, semester: str, level: str) -> bool:
    """Check whether admin has published results for this session/semester/level."""
    pub = ResultPublication.query.filter_by(
        session_year=session_year,
        semester=semester,
        level=level,
        is_published=True,
    ).first()
    return pub is not None


@cached(ttl=30)
def _published_set() -> set:
    """All (session_year, semester, level) combos currently published.
    Cached briefly — this table is tiny and changes only when admin
    explicitly publishes/unpublishes results, but caching it avoids
    re-querying it once per semester group for every student every
    time compute_cgpa() runs (was an N+1 query pattern).
    """
    rows = ResultPublication.query.filter_by(is_published=True).all()
    return {(r.session_year, r.semester, r.level) for r in rows}


def compute_semester_gpa(scores: List[Score]) -> Dict:
    if not scores:
        return {"total_units": 0, "quality_points": 0.0, "gpa": 0.0}
    total_units    = sum(s.course.credit_unit for s in scores)
    quality_points = sum(float(s.grade_point) * s.course.credit_unit for s in scores)
    gpa = round(quality_points / total_units, 2) if total_units else 0.0
    return {
        "total_units":    total_units,
        "quality_points": round(quality_points, 2),
        "gpa":            gpa,
    }


def compute_cgpa(student_id: int, published_only: bool = False) -> Dict:
    """
    Compute cumulative GPA for a student.
    
    Args:
        student_id:      ID of the student.
        published_only:  If True, only include semesters whose results have been
                         published by the admin. Students MUST pass published_only=True.
                         Admins pass False to see everything.
    """
    student = Student.query.get(student_id)
    if not student:
        return _empty_cgpa()

    all_scores = (
        Score.query
        .filter_by(student_id=student_id)
        .join(Score.course)
        .all()
    )

    if not all_scores:
        return _empty_cgpa()

    # Group by (session_year, semester)
    groups: Dict[Tuple[str, str], List[Score]] = {}
    for s in all_scores:
        key = (s.session_year, s.semester)
        groups.setdefault(key, []).append(s)

    breakdown = []
    grand_units = 0
    grand_qp    = 0.0

    for (session_year, semester), sem_scores in sorted(groups.items()):
        # ── RESULT GATE ──────────────────────────────────────
        if published_only:
            if (session_year, semester, student.level) not in _published_set():
                continue   # skip unpublished semesters entirely
        # ─────────────────────────────────────────────────────

        result = compute_semester_gpa(sem_scores)
        grand_units += result["total_units"]
        grand_qp    += result["quality_points"]
        breakdown.append({
            "session_year": session_year,
            "semester":     semester,
            **result,
            "courses": [
                {
                    "code":           s.course.course_code,
                    "title":          s.course.course_title,
                    "credit_unit":    s.course.credit_unit,
                    "ca_score":       float(s.ca_score),
                    "exam_score":     float(s.exam_score),
                    "total_score":    float(s.total_score),
                    "grade":          s.grade,
                    "grade_point":    float(s.grade_point),
                    "quality_points": float(s.grade_point) * s.course.credit_unit,
                }
                for s in sem_scores
            ]
        })

    cgpa = round(grand_qp / grand_units, 2) if grand_units else 0.0

    return {
        "cgpa":                 cgpa,
        "total_units":          grand_units,
        "total_quality_points": round(grand_qp, 2),
        "degree_class":         classify_degree(cgpa),
        "semester_breakdown":   breakdown,
    }


def _empty_cgpa() -> Dict:
    return {
        "cgpa": 0.0, "total_units": 0,
        "total_quality_points": 0.0, "degree_class": "N/A",
        "semester_breakdown": [],
    }


def bulk_compute_department_cgpa() -> List[Dict]:
    """Admin view — all scores, regardless of publication status."""
    students = Student.query.all()
    results = []
    for student in students:
        data = compute_cgpa(student.id, published_only=False)
        results.append({
            "student_id":  student.id,
            "matric_no":   student.matric_no,
            "full_name":   student.full_name,
            "level":       student.level,
            "cgpa":        data["cgpa"],
            "total_units": data["total_units"],
            "degree_class": data["degree_class"],
        })
    return sorted(results, key=lambda x: x["cgpa"], reverse=True)


def get_failed_courses(student_id: int) -> List[Dict]:
    """
    Return all courses a student has FAILED (grade F or E) across all semesters.
    These are the 'outstanding courses' that must be passed before graduation.
    """
    student = Student.query.get(student_id)
    if not student:
        return []

    failed = []
    scores = (
        Score.query
        .filter_by(student_id=student_id)
        .join(Score.course)
        .all()
    )
    for s in scores:
        if s.grade in ('F', 'E'):
            failed.append({
                "code":       s.course.course_code,
                "title":      s.course.course_title,
                "credit_unit": s.course.credit_unit,
                "grade":      s.grade,
                "total_score": float(s.total_score),
                "session_year": s.session_year,
                "semester":    s.semester,
            })
    return failed


def get_spillover_candidates(current_year: int) -> List[Dict]:
    """
    Return students who should be spillover:
    - entry_year + 4 < current_year  (exceeded time limit), OR
    - has any failed/outstanding course (grade F or E)
    Returns list with spillover reason detail for each student.
    """
    students = Student.query.filter(Student.entry_year.isnot(None)).all()
    candidates = []

    for student in students:
        reasons = []
        failed_courses = get_failed_courses(student.id)

        # Time-based spillover — more than 1 year overdue (1-year grace for senate clearance)
        if student.entry_year + 4 < current_year - 1:
            years_overdue = current_year - (student.entry_year + 4)
            reasons.append(f"Exceeded 4-year programme duration by {years_overdue} year(s).")

        # Course-failure spillover
        if failed_courses:
            codes = ", ".join(c["code"] for c in failed_courses)
            reasons.append(f"Failed {len(failed_courses)} course(s): {codes}.")

        if reasons:
            candidates.append({
                "student":         student,
                "reasons":         reasons,
                "failed_courses":  failed_courses,
                "is_time_overdue": student.entry_year + 4 < current_year,
                "outstanding_codes": ", ".join(c["code"] for c in failed_courses),
            })

    return candidates


def get_graduating_students(current_year: int) -> List[Dict]:
    """
    Return students who are eligible to graduate:
    - entry_year + 4 >= current_year  (within time limit OR exactly on schedule)
    - AND no failed/outstanding courses (no grade F or E)
    - AND has at least some score records (not a new student with no results)
    Returns list sorted by CGPA descending (class list order).
    """
    students = Student.query.filter(Student.entry_year.isnot(None)).all()
    graduating = []

    for student in students:
        expected_grad = (student.entry_year or 0) + 4
        # Allow 1-year grace window: if they graduated last year they can
        # still appear on this year's list (senate may not have cleared them yet).
        # A student is excluded only if more than 1 year overdue.
        if expected_grad < current_year - 1:
            continue  # significantly overdue — spillover territory

        failed = get_failed_courses(student.id)
        if failed:
            continue  # has outstanding courses

        cgpa_data = compute_cgpa(student.id, published_only=False)
        if cgpa_data["total_units"] == 0:
            continue  # no results recorded at all

        # Skip if marked as active spillover
        if (hasattr(student, 'spillover') and student.spillover
                and not student.spillover.is_cleared):
            continue

        graduating.append({
            "student":       student,
            "cgpa":          cgpa_data["cgpa"],
            "total_units":   cgpa_data["total_units"],
            "degree_class":  cgpa_data["degree_class"],
            "expected_grad": expected_grad,
        })

    return sorted(graduating, key=lambda x: x["cgpa"], reverse=True)
