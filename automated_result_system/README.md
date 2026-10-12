# ARPS — Automated Result Processing & Transcript Generation System

**By:** Isa Ibrahim Aliyu & Abdulaziz Abdullahi  
**Department of Computer Science | Supervisor: Dr. Abdullahi Ibrahim**

---

## Tech Stack
| Layer | Technology |
|---|---|
| Backend | Python 3.10+, Flask 3.0 |
| Database | MySQL 8.0 (via SQLAlchemy + PyMySQL) |
| Frontend | HTML5, Bootstrap 5, Jinja2 Templates |
| PDF Generation | ReportLab |
| Auth | Flask-Login + Flask-Bcrypt |

---

## Project Structure
```
arps/
├── run.py               ← Entry point
├── app.py               ← Flask app factory
├── config.py            ← Configuration (dev/prod)
├── models.py            ← Database models (SQLAlchemy)
├── engine.py            ← GPA/CGPA computation engine
├── transcript_pdf.py    ← PDF transcript generator (ReportLab)
├── requirements.txt
├── schema.sql           ← Raw SQL schema (reference)
├── routes/
│   ├── auth.py          ← /login, /register, /logout
│   ├── student.py       ← /student/*
│   ├── lecturer.py      ← /lecturer/*
│   └── admin.py         ← /admin/*
└── templates/
    ├── base.html
    ├── auth/            (login.html, register.html)
    ├── student/         (dashboard.html, results.html, courses.html)
    ├── lecturer/        (dashboard.html, course_scores.html, enter_score.html, bulk_upload.html)
    └── admin/           (dashboard.html, students.html, courses.html, compute.html, transcript.html, audit_log.html)
```

---

## Setup Instructions

### 1. Create and activate virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Create MySQL database
```sql
CREATE DATABASE arps_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 4. Configure environment (optional — edit config.py or use .env)
```
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=arps_db
SECRET_KEY=your-secret-key
ADMIN_PASSKEY=DEPT-CS-ADMIN-2024
```

### 5. Run the app
```bash
python run.py
```
Visit: **http://localhost:5000**

---

## CSV Upload Format (Bulk Score Pipelining)
```
matric_no,ca_score,exam_score
U22/FNS/CSC/1290,25,60
U22/FNS/CSC/1013,28,55
```
- `ca_score`: 0–30
- `exam_score`: 0–70
- Full ACID rollback on any error

---

## NUC Grading Scale (5.0 System)
| Score | Grade | GP | Class |
|---|---|---|---|
| 70–100 | A | 5.0 | First Class |
| 60–69  | B | 4.0 | 2nd Class Upper |
| 50–59  | C | 3.0 | 2nd Class Lower |
| 45–49  | D | 2.0 | Third Class |
| 40–44  | E | 1.0 | Pass |
| 0–39   | F | 0.0 | Fail |

---

## User Roles
| Role | Access |
|---|---|
| **Student** | View results, GPA/CGPA, statement of results |
| **Lecturer** | Enter scores, bulk CSV upload |
| **Admin/Exam Officer** | Manage courses, trigger computation, generate transcripts, audit log |
