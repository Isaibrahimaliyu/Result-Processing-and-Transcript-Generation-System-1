"""
ARPS — Email Notification Engine  (v3 — production ready)
Sends HTML result notification emails to students via Flask-Mail.

Setup in .env:
    MAIL_SERVER=smtp.gmail.com
    MAIL_PORT=587
    MAIL_USE_TLS=true
    MAIL_USERNAME=youremail@gmail.com
    MAIL_PASSWORD=your_app_password     ← Gmail App Password (16 chars)
    MAIL_DEFAULT_SENDER=IBB University ARPS <youremail@gmail.com>
    MAIL_SUPPRESS_SEND=false            ← Set true to test without sending
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, List


# ── Grade / CGPA colour helpers ───────────────────────────────
def _cgpa_colour(cgpa: float) -> str:
    if cgpa >= 4.5: return "#059669"
    if cgpa >= 3.5: return "#2563EB"
    if cgpa >= 2.4: return "#D97706"
    if cgpa >= 1.5: return "#6B7280"
    return "#DC2626"


def _grade_style(grade: str) -> str:
    """Return inline CSS background/color for a grade badge."""
    styles = {
        "A": "background:#D1FAE5;color:#065F46;border:1px solid #6EE7B7",
        "B": "background:#DBEAFE;color:#1E40AF;border:1px solid #93C5FD",
        "C": "background:#FEF3C7;color:#92400E;border:1px solid #FCD34D",
        "D": "background:#FFE4E6;color:#9F1239;border:1px solid #FCA5A5",
        "E": "background:#F3F4F6;color:#374151;border:1px solid #D1D5DB",
        "F": "background:#FEE2E2;color:#B91C1C;border:1px solid #F87171",
    }
    return styles.get(grade, "background:#F3F4F6;color:#374151")


def _build_html(student, cgpa_data: dict, session_year: str,
                semester: str, portal_url: str) -> str:
    """Build the HTML email body without Jinja2 (pure Python string)."""

    # Find the specific semester data
    sem_data = None
    for sem in cgpa_data.get("semester_breakdown", []):
        if sem["session_year"] == session_year and sem["semester"] == semester:
            sem_data = sem
            break

    cgpa      = cgpa_data.get("cgpa", 0.0)
    deg_class = cgpa_data.get("degree_class", "N/A")
    cgpa_col  = _cgpa_colour(cgpa)
    sem_gpa_display = f"{sem_data['gpa']:.2f}" if sem_data else "—"

    # Build courses rows
    course_rows = ""
    if sem_data:
        for i, c in enumerate(sem_data.get("courses", [])):
            row_bg = "#F7F9FC" if i % 2 == 0 else "#ffffff"
            gs     = _grade_style(c["grade"])
            course_rows += f"""
            <tr style="background:{row_bg};">
              <td style="padding:9px 12px;font-size:12px;font-weight:700;color:#0B1F3A;border-bottom:1px solid #EEF2F8;">{c['code']}</td>
              <td style="padding:9px 12px;font-size:12px;color:#374151;border-bottom:1px solid #EEF2F8;">{c['title'][:40]}{'…' if len(c['title'])>40 else ''}</td>
              <td align="center" style="padding:9px 8px;font-size:12px;border-bottom:1px solid #EEF2F8;">{c['ca_score']:.1f}</td>
              <td align="center" style="padding:9px 8px;font-size:12px;border-bottom:1px solid #EEF2F8;">{c['exam_score']:.1f}</td>
              <td align="center" style="padding:9px 8px;font-size:13px;font-weight:700;color:#0B1F3A;border-bottom:1px solid #EEF2F8;">{c['total_score']:.1f}</td>
              <td align="center" style="padding:9px 8px;border-bottom:1px solid #EEF2F8;">
                <span style="display:inline-block;width:26px;height:26px;line-height:26px;text-align:center;border-radius:50%;font-weight:800;font-size:12px;{gs}">{c['grade']}</span>
              </td>
            </tr>"""

    sem_summary = ""
    if sem_data:
        sem_summary = f"""
        <table width="100%" cellpadding="0" cellspacing="0"
               style="border-radius:8px;overflow:hidden;margin-bottom:20px;border:1px solid #D8E0ED;">
          <tr style="background:#0B1F3A;">
            <td style="padding:9px 12px;font-size:10px;color:rgba(255,255,255,.65);font-weight:700;text-transform:uppercase;letter-spacing:.6px;">Code</td>
            <td style="padding:9px 12px;font-size:10px;color:rgba(255,255,255,.65);font-weight:700;text-transform:uppercase;letter-spacing:.6px;">Course Title</td>
            <td align="center" style="padding:9px 8px;font-size:10px;color:rgba(255,255,255,.65);font-weight:700;text-transform:uppercase;letter-spacing:.6px;">CA</td>
            <td align="center" style="padding:9px 8px;font-size:10px;color:rgba(255,255,255,.65);font-weight:700;text-transform:uppercase;letter-spacing:.6px;">Exam</td>
            <td align="center" style="padding:9px 8px;font-size:10px;color:rgba(255,255,255,.65);font-weight:700;text-transform:uppercase;letter-spacing:.6px;">Total</td>
            <td align="center" style="padding:9px 8px;font-size:10px;color:rgba(255,255,255,.65);font-weight:700;text-transform:uppercase;letter-spacing:.6px;">Grade</td>
          </tr>
          {course_rows}
          <tr style="background:#FDF3DC;">
            <td colspan="2" style="padding:9px 12px;font-size:12px;font-weight:700;color:#0B1F3A;">Semester Total</td>
            <td colspan="3" align="right" style="padding:9px 8px;font-size:12px;font-weight:700;color:#0B1F3A;">
              Units: {sem_data['total_units']}
            </td>
            <td align="center" style="padding:9px 8px;font-size:12px;font-weight:700;color:#C9922A;">
              GPA: {sem_data['gpa']:.2f}
            </td>
          </tr>
        </table>"""

    year = datetime.utcnow().year

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#EEF2F8;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#EEF2F8;padding:30px 0;">
<tr><td align="center">
<table width="620" cellpadding="0" cellspacing="0" style="max-width:620px;width:100%;">

  <!-- HEADER -->
  <tr>
    <td style="background:linear-gradient(135deg,#0B1F3A 0%,#162D50 100%);border-radius:12px 12px 0 0;padding:32px 36px;text-align:center;">
      <div style="display:inline-block;width:60px;height:60px;background:#C9922A;border-radius:50%;line-height:64px;font-size:26px;margin-bottom:14px;">🎓</div>
      <div style="font-size:19px;font-weight:800;color:#fff;letter-spacing:.3px;font-family:Georgia,serif;">
        Ibrahim Badamasi Babangida University
      </div>
      <div style="font-size:11px;color:rgba(255,255,255,.45);margin-top:3px;letter-spacing:.8px;">
        LAPAI, NIGER STATE &mdash; OFFICIAL RESULT NOTIFICATION
      </div>
      <div style="width:60px;height:3px;background:linear-gradient(90deg,#C9922A,#F5C96B);margin:14px auto 0;border-radius:2px;"></div>
    </td>
  </tr>
  <tr><td style="background:linear-gradient(90deg,#C9922A,#B8860B);height:4px;"></td></tr>

  <!-- BODY -->
  <tr>
    <td style="background:#fff;padding:32px 36px 24px;border-radius:0 0 12px 12px;box-shadow:0 4px 20px rgba(0,0,0,.08);">

      <p style="font-size:15px;color:#0B1F3A;font-weight:700;margin:0 0 5px;">Dear {student.first_name},</p>
      <p style="font-size:13.5px;color:#5A6B82;margin:0 0 24px;line-height:1.7;">
        Your academic results for <strong>{session_year} &mdash; {semester} Semester</strong>
        have been officially released. Please find your result summary below.
      </p>

      <!-- Bio card -->
      <table width="100%" cellpadding="0" cellspacing="0"
             style="background:#F7F9FC;border:1.5px solid #D8E0ED;border-radius:10px;margin-bottom:20px;">
        <tr>
          <td style="padding:18px 22px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="width:50%;padding-right:12px;padding-bottom:10px;">
                  <div style="font-size:10px;color:#8A9BB5;font-weight:700;text-transform:uppercase;letter-spacing:.7px;margin-bottom:3px;">Student Name</div>
                  <div style="font-size:13.5px;font-weight:700;color:#0B1F3A;">{student.full_name}</div>
                </td>
                <td style="width:50%;padding-left:12px;padding-bottom:10px;">
                  <div style="font-size:10px;color:#8A9BB5;font-weight:700;text-transform:uppercase;letter-spacing:.7px;margin-bottom:3px;">Matric Number</div>
                  <div style="font-size:13.5px;font-weight:700;color:#0B1F3A;">{student.matric_no}</div>
                </td>
              </tr>
              <tr>
                <td style="padding-right:12px;padding-top:6px;border-top:1px solid #D8E0ED;">
                  <div style="font-size:10px;color:#8A9BB5;font-weight:700;text-transform:uppercase;letter-spacing:.7px;margin-bottom:3px;">Academic Session</div>
                  <div style="font-size:13px;color:#0B1F3A;">{session_year} &mdash; {semester} Semester</div>
                </td>
                <td style="padding-left:12px;padding-top:6px;border-top:1px solid #D8E0ED;">
                  <div style="font-size:10px;color:#8A9BB5;font-weight:700;text-transform:uppercase;letter-spacing:.7px;margin-bottom:3px;">Department</div>
                  <div style="font-size:13px;color:#0B1F3A;">{student.department}</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

      {sem_summary}

      <!-- CGPA row -->
      <table width="100%" cellpadding="0" cellspacing="0"
             style="background:linear-gradient(135deg,#0B1F3A,#162D50);border-radius:10px;margin-bottom:24px;">
        <tr>
          <td align="center" style="padding:16px 10px;border-right:1px solid rgba(255,255,255,.1);">
            <div style="font-size:9px;color:rgba(255,255,255,.4);font-weight:700;text-transform:uppercase;letter-spacing:.7px;margin-bottom:4px;">Semester GPA</div>
            <div style="font-size:22px;font-weight:800;color:#F5C96B;font-family:Georgia,serif;">{sem_gpa_display}</div>
            <div style="font-size:10px;color:rgba(255,255,255,.35);">out of 5.00</div>
          </td>
          <td align="center" style="padding:16px 10px;border-right:1px solid rgba(255,255,255,.1);">
            <div style="font-size:9px;color:rgba(255,255,255,.4);font-weight:700;text-transform:uppercase;letter-spacing:.7px;margin-bottom:4px;">Cumulative GPA</div>
            <div style="font-size:22px;font-weight:800;color:#F5C96B;font-family:Georgia,serif;">{cgpa:.2f}</div>
            <div style="font-size:10px;color:rgba(255,255,255,.35);">overall CGPA</div>
          </td>
          <td align="center" style="padding:16px 10px;">
            <div style="font-size:9px;color:rgba(255,255,255,.4);font-weight:700;text-transform:uppercase;letter-spacing:.7px;margin-bottom:4px;">Classification</div>
            <div style="font-size:13px;font-weight:700;color:#6EE7B7;margin-top:4px;font-family:Georgia,serif;">{deg_class}</div>
          </td>
        </tr>
      </table>

      <!-- CTA -->
      <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:22px;">
        <tr>
          <td align="center">
            <a href="{portal_url}"
               style="display:inline-block;background:linear-gradient(135deg,#0B1F3A,#1E3D6B);color:#fff;font-size:13.5px;font-weight:700;padding:12px 32px;border-radius:8px;text-decoration:none;letter-spacing:.3px;">
              📊 View Full Results on Portal &rarr;
            </a>
          </td>
        </tr>
      </table>

      <!-- Notice -->
      <table width="100%" cellpadding="0" cellspacing="0"
             style="background:#EBF4FF;border:1.5px solid #BFDBFE;border-radius:8px;margin-bottom:18px;">
        <tr>
          <td style="padding:12px 16px;font-size:11.5px;color:#1D5FA8;line-height:1.7;">
            <strong>&#9432; Note:</strong> If you have any queries regarding these results, please visit
            the Examination Office within <strong>14 working days</strong> of this notification.
          </td>
        </tr>
      </table>

      <p style="font-size:11.5px;color:#8A9BB5;line-height:1.7;margin:0;">
        This is an automated notification from the Academic Result Processing System (ARPS).
        Do not reply to this email. Contact the Registrar's Office for enquiries.
      </p>
    </td>
  </tr>

  <!-- FOOTER -->
  <tr>
    <td style="padding:18px 0;text-align:center;">
      <div style="font-size:11px;color:#8A9BB5;line-height:1.8;">
        &copy; {year} Ibrahim Badamasi Babangida University, Lapai, Niger State<br>
        Academic Result Processing System (ARPS) &mdash; Dept. of Computer Science<br>
        <span style="font-size:10px;color:#B0BAC8;">Sent to: {student.email}</span>
      </div>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""
    return html


def _build_plain(student, cgpa_data: dict, session_year: str,
                 semester: str, portal_url: str) -> str:
    """Plain text fallback email."""
    cgpa = cgpa_data.get("cgpa", 0.0)
    deg  = cgpa_data.get("degree_class", "N/A")
    lines = [
        f"IBRAHIM BADAMASI BABANGIDA UNIVERSITY — RESULT NOTIFICATION",
        "=" * 60,
        f"Dear {student.first_name},",
        "",
        f"Your results for {session_year} — {semester} Semester have been released.",
        "",
        f"Student:        {student.full_name}",
        f"Matric No:      {student.matric_no}",
        f"CGPA:           {cgpa:.2f} / 5.00",
        f"Classification: {deg}",
        "",
    ]
    for sem in cgpa_data.get("semester_breakdown", []):
        if sem["session_year"] == session_year and sem["semester"] == semester:
            lines.append(f"--- {session_year} {semester} Semester (GPA: {sem['gpa']:.2f}) ---")
            for c in sem.get("courses", []):
                lines.append(
                    f"  {c['code']:<10} {c['title'][:32]:<32} "
                    f"CA:{c['ca_score']:.0f}  Exam:{c['exam_score']:.0f}  "
                    f"Total:{c['total_score']:.0f}  Grade:{c['grade']}"
                )
            lines.append(f"  Units: {sem['total_units']}   QP: {sem['quality_points']:.1f}")
    lines += ["", f"Login to view full results: {portal_url}", "",
              "Ibrahim Badamasi Babangida University, Lapai, Niger State."]
    return "\n".join(lines)


def send_result_notification(
    student,
    cgpa_data: dict,
    session_year: str,
    semester: str,
    sent_by_user_id: Optional[int] = None,
    portal_url: str = "",
) -> Dict:
    """
    Send a result notification email to a single student.
    Returns {"status": "sent"|"failed"|"suppressed", "error": None|str}.
    """
    from app import mail, db
    from models import EmailNotification
    from flask_mail import Message

    if not student.email:
        return {"status": "failed", "error": "Student has no email address on file."}

    subject  = (f"Result Notification: {session_year} {semester} Semester "
                f"— IBB University")
    html_body  = _build_html(student, cgpa_data, session_year, semester, portal_url)
    plain_body = _build_plain(student, cgpa_data, session_year, semester, portal_url)

    status = "sent"
    error  = None

    try:
        msg = Message(
            subject    = subject,
            recipients = [student.email],
            body       = plain_body,
            html       = html_body,
        )
        mail.send(msg)
    except Exception as exc:
        status = "failed"
        error  = str(exc)[:500]

    # Always log the attempt
    try:
        log = EmailNotification(
            student_id        = student.id,
            recipient_email   = student.email,
            subject           = subject,
            notification_type = "result_published",
            session_year      = session_year,
            semester          = semester,
            sent_by           = sent_by_user_id,
            status            = status,
            error_message     = error,
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        pass

    return {"status": status, "error": error}


def send_bulk_result_notifications(
    students: list,
    session_year: str,
    semester: str,
    sent_by_user_id: Optional[int] = None,
    portal_url: str = "",
) -> Dict:
    """
    Send result notifications to a list of students.
    Returns {"sent": int, "failed": int, "skipped": int, "errors": list}.
    """
    from engine import compute_cgpa

    results = {"sent": 0, "failed": 0, "skipped": 0, "errors": []}

    for student in students:
        if not student.email:
            results["skipped"] += 1
            continue

        try:
            cgpa_data = compute_cgpa(student.id, published_only=False)
            result    = send_result_notification(
                student          = student,
                cgpa_data        = cgpa_data,
                session_year     = session_year,
                semester         = semester,
                sent_by_user_id  = sent_by_user_id,
                portal_url       = portal_url,
            )
            if result["status"] == "sent":
                results["sent"] += 1
            else:
                results["failed"] += 1
                results["errors"].append(
                    f"{student.matric_no}: {result.get('error','unknown')}"
                )
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"{student.matric_no}: {str(e)[:100]}")

    return results
