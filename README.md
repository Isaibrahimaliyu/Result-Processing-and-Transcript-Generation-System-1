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
├── run.py               ← Entry point (local)
├── api/index.py         ← Entry point (Vercel serverless)
├── vercel.json          ← Vercel build/routing config
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

### 4. Configure environment (copy .env.example to .env)
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

## Deploying to Vercel

> Netlify cannot run this app — Netlify Functions don't support Python/Flask. Use Vercel
> (or a Python host such as Render, Railway or PythonAnywhere).

1. **Create a hosted MySQL database.** Vercel cannot reach a MySQL server on your own PC.
   Free/cheap options: Aiven for MySQL, TiDB Cloud Serverless, Railway. Copy the host,
   port, user, password and database name (or the full connection URL).
2. **Import the repo in Vercel** (Framework Preset: *Other*, Root Directory: repo root).
   `vercel.json` routes every request to `api/index.py`.
3. **Set Environment Variables** (Vercel → Project → Settings → Environment Variables):

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | `mysql+pymysql://USER:PASSWORD@HOST:PORT/DBNAME?charset=utf8mb4` *(or set `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` separately)* |
   | `DB_SSL` | `true` (hosted MySQL providers require TLS) |
   | `SECRET_KEY` | a long random string — **required**, sessions can be forged without it |
   | `ADMIN_PASSKEY` | your own passkey for Exam Officer registration |
   | `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER` | Gmail address + App Password (optional — emails/OTP) |
   | `SERVER_URL` | optional — leave empty to auto-detect the Vercel URL for transcript QR codes |

4. **Redeploy.** Tables are created automatically on first start. Then open `/register`
   and create the Exam Officer account with your `ADMIN_PASSKEY`.

**Serverless limitations:** the Backup & Restore page (`mysqldump`) and the automatic daily
backup do not work on Vercel — use your database provider's backup feature instead.
Passport photos are stored in the database so they persist across deployments.

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
