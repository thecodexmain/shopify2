import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, abort, flash, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

APP_NAME = "Learn with Jaskaran"
DB_PATH = "learn_with_jaskaran.db"
DEFAULT_DEMO_VIDEO = "https://www.youtube.com/embed/1RkI6cQ6B0M"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))


def utcnow_iso():
    return datetime.now(timezone.utc).isoformat()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                expires_at TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                syllabus TEXT NOT NULL,
                instructor TEXT NOT NULL,
                original_price REAL NOT NULL,
                sale_price REAL NOT NULL,
                category TEXT NOT NULL,
                demo_youtube_url TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS course_contents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                content_type TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                is_premium INTEGER NOT NULL DEFAULT 1,
                display_order INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(course_id) REFERENCES courses(id)
            );

            CREATE TABLE IF NOT EXISTS enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                payment_id TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, course_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(course_id) REFERENCES courses(id)
            );

            CREATE TABLE IF NOT EXISTS lesson_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content_id INTEGER NOT NULL,
                completed_at TEXT NOT NULL,
                UNIQUE(user_id, content_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(content_id) REFERENCES course_contents(id)
            );

            CREATE TABLE IF NOT EXISTS quiz_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                options_json TEXT NOT NULL,
                correct_index INTEGER NOT NULL,
                solution TEXT NOT NULL,
                FOREIGN KEY(course_id) REFERENCES courses(id)
            );

            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                score INTEGER NOT NULL,
                total INTEGER NOT NULL,
                answers_json TEXT NOT NULL,
                attempted_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(course_id) REFERENCES courses(id)
            );
            """
        )

        admin = conn.execute("SELECT id FROM users WHERE email = ?", ("admin@learnwithjaskaran.com",)).fetchone()
        if not admin:
            conn.execute(
                "INSERT INTO users (name, email, password_hash, is_admin, created_at) VALUES (?, ?, ?, 1, ?)",
                (
                    "Admin",
                    "admin@learnwithjaskaran.com",
                    generate_password_hash("admin123"),
                    utcnow_iso(),
                ),
            )

        course = conn.execute("SELECT id FROM courses WHERE title = ?", (
            "Comprehensive Geography for Punjab Competitive Exams",
        )).fetchone()
        if not course:
            cur = conn.execute(
                """
                INSERT INTO courses
                    (title, description, syllabus, instructor, original_price, sale_price, category, demo_youtube_url, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    "Comprehensive Geography for Punjab Competitive Exams",
                    "Bilingual (English/Punjabi) geography course for Master Cadre, PCS, Group A/B/C.",
                    "Punjab geography basics, Indian geography linkage, map practice, environment and current affairs integration.",
                    "Jaskaran Singh",
                    5000,
                    2499,
                    "Punjab Exams",
                    DEFAULT_DEMO_VIDEO,
                ),
            )
            course_id = cur.lastrowid

            default_content = [
                (course_id, "video", "3D Animation Lecture 1", "https://www.youtube.com/embed/1RkI6cQ6B0M", 1, 1),
                (course_id, "notes", "Syllabus Short Notes (PDF)", "https://example.com/notes.pdf", 1, 2),
                (course_id, "pyq", "Previous Year Questions (PDF)", "https://example.com/pyq.pdf", 1, 3),
                (course_id, "mock_test", "Mock Test Set 1", "", 1, 4),
                (course_id, "live_doubt", "Weekly Live Doubt Class Schedule", "https://example.com/live-class", 1, 5),
            ]
            conn.executemany(
                """
                INSERT INTO course_contents
                    (course_id, content_type, title, url, is_premium, display_order)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                default_content,
            )

            questions = [
                (
                    course_id,
                    "Which river is known as the lifeline of Punjab agriculture?",
                    json.dumps(["Sutlej", "Narmada", "Godavari", "Krishna"]),
                    0,
                    "Sutlej is one of the major rivers supporting irrigation in Punjab.",
                ),
                (
                    course_id,
                    "Punjab falls under which major physiographic division?",
                    json.dumps(["Deccan Plateau", "Great Plains", "Western Ghats", "Coastal Plains"]),
                    1,
                    "Most of Punjab lies in the Indo-Gangetic Great Plains region.",
                ),
            ]
            conn.executemany(
                """
                INSERT INTO quiz_questions (course_id, question, options_json, correct_index, solution)
                VALUES (?, ?, ?, ?, ?)
                """,
                questions,
            )


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Please login first.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user or not user["is_admin"]:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def render_page(title, body):
    user = current_user()
    nav = [f'<a href="{url_for("home")}">Home</a>', f'<a href="{url_for("courses")}">Courses</a>']
    if user:
        nav.append(f'<a href="{url_for("dashboard")}">Dashboard</a>')
        if user["is_admin"]:
            nav.append(f'<a href="{url_for("admin")}">Admin</a>')
        nav.append(f'<a href="{url_for("logout")}">Logout</a>')
    else:
        nav.append(f'<a href="{url_for("login")}">Login</a>')
        nav.append(f'<a href="{url_for("signup")}">Sign up</a>')

    template = """
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width,initial-scale=1" />
      <title>{{ title }} - {{ app_name }}</title>
      <style>
        body { font-family: Arial, sans-serif; margin: 0; background: #f6f8fb; color: #111; }
        header { background: #0d2f6f; color: #fff; padding: 14px 20px; }
        header a { color: #fff; margin-right: 12px; text-decoration: none; }
        main { max-width: 980px; margin: 20px auto; background: #fff; padding: 22px; border-radius: 8px; }
        .card { border: 1px solid #e1e6ef; border-radius: 8px; padding: 12px; margin-bottom: 12px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(260px,1fr)); gap: 12px; }
        .muted { color: #666; font-size: 14px; }
        .strike { text-decoration: line-through; color: #888; }
        .price { color: #0e8a2c; font-size: 20px; font-weight: bold; }
        .btn { background: #0d2f6f; color: #fff; border: 0; border-radius: 6px; padding: 8px 12px; cursor: pointer; }
        input, select, textarea { width: 100%; margin-top: 4px; margin-bottom: 10px; padding: 8px; }
        .flash { padding: 8px; margin-bottom: 10px; border-radius: 5px; background: #edf3ff; }
      </style>
    </head>
    <body>
      <header>
        <strong>{{ app_name }}</strong>
        <div style="margin-top:8px">{{ nav|safe }}</div>
      </header>
      <main>
        {% for category, message in messages %}<div class="flash">{{ message }}</div>{% endfor %}
        {{ body|safe }}
      </main>
    </body>
    </html>
    """
    from flask import get_flashed_messages

    messages = get_flashed_messages(with_categories=True)
    return render_template_string(template, title=title, app_name=APP_NAME, nav=" | ".join(nav), body=body, messages=messages)


@app.route("/")
def home():
    body = f"""
    <h1>Welcome to {APP_NAME} / Learn with Jaskaran में आपका स्वागत है</h1>
    <p>Affordable exam preparation platform with recorded lectures, notes, PYQs, mock tests, and weekly live doubt class schedules.</p>
    <h3>Demo Video (10-15 min)</h3>
    <iframe width="100%" height="380" src="{DEFAULT_DEMO_VIDEO}" title="Demo" frameborder="0" allowfullscreen></iframe>
    <div class="card">
      <h3>MVP User Flow</h3>
      <p>Homepage → Browse Courses → Course Details → Purchase Course → Dashboard → Watch Videos + Download Notes + Take Tests</p>
    </div>
    """
    return render_page("Home", body)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 6:
            flash("Name, email, and password (min 6 chars) are required.", "error")
        else:
            try:
                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO users (name, email, password_hash, is_admin, created_at) VALUES (?, ?, ?, 0, ?)",
                        (name, email, generate_password_hash(password), utcnow_iso()),
                    )
                flash("Account created. Please login.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("Email already registered.", "error")

    body = """
    <h2>Create account</h2>
    <form method="post">
      <label>Name<input name="name" required></label>
      <label>Email<input name="email" type="email" required></label>
      <label>Password<input name="password" type="password" minlength="6" required></label>
      <button class="btn" type="submit">Sign up</button>
    </form>
    """
    return render_page("Sign up", body)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with get_db() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            flash("Logged in successfully.", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")

    body = """
    <h2>Login</h2>
    <form method="post">
      <label>Email<input name="email" type="email" required></label>
      <label>Password<input name="password" type="password" required></label>
      <button class="btn" type="submit">Login</button>
    </form>
    <p><a href="/forgot-password">Forgot password?</a></p>
    """
    return render_page("Login", body)


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("home"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    reset_link = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        with get_db() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user:
                token = secrets.token_urlsafe(24)
                expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
                conn.execute(
                    "INSERT INTO password_reset_tokens (user_id, token, expires_at, used) VALUES (?, ?, ?, 0)",
                    (user["id"], token, expires),
                )
                reset_link = url_for("reset_password", token=token, _external=True)
        flash("If account exists, reset link has been generated.", "success")

    body = f"""
    <h2>Password reset</h2>
    <form method="post">
      <label>Email<input name="email" type="email" required></label>
      <button class="btn" type="submit">Generate reset link</button>
    </form>
    {'<p><strong>Reset Link:</strong> <a href="'+reset_link+'">'+reset_link+'</a></p>' if reset_link else ''}
    """
    return render_page("Forgot password", body)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    with get_db() as conn:
        token_row = conn.execute(
            "SELECT * FROM password_reset_tokens WHERE token = ? AND used = 0", (token,)
        ).fetchone()
        if not token_row:
            flash("Invalid or used token.", "error")
            return redirect(url_for("forgot_password"))

        expires = datetime.fromisoformat(token_row["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            flash("Token expired.", "error")
            return redirect(url_for("forgot_password"))

        if request.method == "POST":
            password = request.form.get("password", "")
            if len(password) < 6:
                flash("Password must be at least 6 characters.", "error")
            else:
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(password), token_row["user_id"]),
                )
                conn.execute("UPDATE password_reset_tokens SET used = 1 WHERE id = ?", (token_row["id"],))
                flash("Password updated. Please login.", "success")
                return redirect(url_for("login"))

    body = """
    <h2>Set new password</h2>
    <form method="post">
      <label>New password<input name="password" type="password" minlength="6" required></label>
      <button class="btn" type="submit">Reset password</button>
    </form>
    """
    return render_page("Reset password", body)


@app.route("/courses")
def courses():
    q = request.args.get("q", "").strip().lower()
    category = request.args.get("category", "").strip()
    sql = "SELECT * FROM courses WHERE is_active = 1"
    params = []
    if q:
        sql += " AND (lower(title) LIKE ? OR lower(description) LIKE ?)"
        like_q = f"%{q}%"
        params.extend([like_q, like_q])
    if category:
        sql += " AND category = ?"
        params.append(category)

    with get_db() as conn:
        courses_data = conn.execute(sql, params).fetchall()
        categories = conn.execute("SELECT DISTINCT category FROM courses WHERE is_active = 1").fetchall()

    cards = []
    for c in courses_data:
        cards.append(
            f"""
            <div class='card'>
              <h3>{c['title']}</h3>
              <p>{c['description']}</p>
              <p><span class='strike'>₹{int(c['original_price'])}</span> <span class='price'>₹{int(c['sale_price'])}</span></p>
              <a class='btn' href='/course/{c['id']}'>View details</a>
            </div>
            """
        )

    opts = ["<option value=''>All categories</option>"]
    for c in categories:
        selected = "selected" if category == c["category"] else ""
        opts.append(f"<option {selected} value='{c['category']}'>{c['category']}</option>")

    body = f"""
    <h2>Course Catalog</h2>
    <form method='get'>
      <label>Search<input name='q' value='{q}' placeholder='Search courses'></label>
      <label>Exam category filter<select name='category'>{''.join(opts)}</select></label>
      <button class='btn' type='submit'>Apply</button>
    </form>
    <div class='grid'>{''.join(cards) if cards else '<p>No courses found.</p>'}</div>
    """
    return render_page("Courses", body)


@app.route("/course/<int:course_id>")
def course_details(course_id):
    with get_db() as conn:
        course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            abort(404)
        contents = conn.execute(
            "SELECT * FROM course_contents WHERE course_id = ? ORDER BY display_order ASC", (course_id,)
        ).fetchall()

    content_list = "".join([f"<li>{row['content_type'].upper()}: {row['title']}</li>" for row in contents])
    body = f"""
    <h2>{course['title']}</h2>
    <p>{course['description']}</p>
    <p><strong>Instructor:</strong> {course['instructor']}</p>
    <p><strong>Syllabus:</strong> {course['syllabus']}</p>
    <p><span class='strike'>₹{int(course['original_price'])}</span> <span class='price'>₹{int(course['sale_price'])}</span></p>
    <iframe width='100%' height='330' src='{course['demo_youtube_url']}' frameborder='0' allowfullscreen></iframe>
    <h3>Included content / कोर्स में शामिल</h3>
    <ul>{content_list}</ul>
    <form method='post' action='/purchase/{course['id']}'>
      <button class='btn' type='submit'>Purchase course</button>
    </form>
    """
    return render_page("Course details", body)


@app.route("/purchase/<int:course_id>", methods=["POST", "GET"])
@login_required
def purchase(course_id):
    user = current_user()
    with get_db() as conn:
        course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            abort(404)

        existing = conn.execute(
            "SELECT * FROM enrollments WHERE user_id = ? AND course_id = ?", (user["id"], course_id)
        ).fetchone()

        if request.method == "POST" and not existing:
            payment_id = f"PAY-{secrets.token_hex(6).upper()}"
            conn.execute(
                "INSERT INTO enrollments (user_id, course_id, status, payment_id, amount, created_at) VALUES (?, ?, 'paid', ?, ?, ?)",
                (user["id"], course_id, payment_id, course["sale_price"], utcnow_iso()),
            )
            flash(f"Payment successful. Order confirmed. Payment ID: {payment_id}", "success")
            return redirect(url_for("dashboard"))

    if existing:
        flash("Course already purchased.", "success")
        return redirect(url_for("dashboard"))

    body = f"""
    <h2>Checkout</h2>
    <p>Course: <strong>{course['title']}</strong></p>
    <p>Amount: <span class='price'>₹{int(course['sale_price'])}</span> (Gateway simulation for MVP)</p>
    <form method='post'>
      <button class='btn' type='submit'>Pay now</button>
    </form>
    """
    return render_page("Purchase", body)


@app.route("/progress/<int:content_id>/complete", methods=["POST"])
@login_required
def mark_completed(content_id):
    user = current_user()
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO lesson_progress (user_id, content_id, completed_at) VALUES (?, ?, ?)",
            (user["id"], content_id, utcnow_iso()),
        )
        content = conn.execute("SELECT course_id FROM course_contents WHERE id = ?", (content_id,)).fetchone()
    if content:
        flash("Lesson marked as completed.", "success")
        return redirect(url_for("dashboard", course_id=content["course_id"]))
    return redirect(url_for("dashboard"))


@app.route("/quiz/<int:course_id>", methods=["GET", "POST"])
@login_required
def quiz(course_id):
    user = current_user()
    with get_db() as conn:
        enrolled = conn.execute(
            "SELECT 1 FROM enrollments WHERE user_id = ? AND course_id = ?", (user["id"], course_id)
        ).fetchone()
        if not enrolled:
            flash("Purchase the course first.", "error")
            return redirect(url_for("course_details", course_id=course_id))

        questions = conn.execute("SELECT * FROM quiz_questions WHERE course_id = ?", (course_id,)).fetchall()

        if request.method == "POST" and questions:
            score = 0
            answer_map = {}
            for q in questions:
                selected = request.form.get(f"q_{q['id']}")
                answer_map[str(q["id"])] = selected
                if selected and selected.isdigit() and int(selected) == q["correct_index"]:
                    score += 1

            conn.execute(
                "INSERT INTO quiz_attempts (user_id, course_id, score, total, answers_json, attempted_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user["id"], course_id, score, len(questions), json.dumps(answer_map), utcnow_iso()),
            )
            flash(f"Quiz submitted. Score: {score}/{len(questions)}", "success")
            return redirect(url_for("quiz", course_id=course_id))

        attempts = conn.execute(
            "SELECT * FROM quiz_attempts WHERE user_id = ? AND course_id = ? ORDER BY attempted_at DESC",
            (user["id"], course_id),
        ).fetchall()

    q_html = []
    for q in questions:
        options = json.loads(q["options_json"])
        inputs = []
        for idx, opt in enumerate(options):
            inputs.append(f"<label><input type='radio' name='q_{q['id']}' value='{idx}'> {opt}</label><br>")
        q_html.append(f"<div class='card'><p><strong>{q['question']}</strong></p>{''.join(inputs)}<p class='muted'>Solution: {q['solution']}</p></div>")

    attempt_html = "".join([f"<li>{a['attempted_at']}: {a['score']}/{a['total']}</li>" for a in attempts])
    body = f"""
    <h2>Practice Test</h2>
    <form method='post'>{''.join(q_html)}<button class='btn' type='submit'>Submit quiz</button></form>
    <h3>Past Scores</h3>
    <ul>{attempt_html if attempt_html else '<li>No attempts yet.</li>'}</ul>
    """
    return render_page("Quiz", body)


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    with get_db() as conn:
        enrolled_courses = conn.execute(
            """
            SELECT c.*, e.payment_id, e.created_at
            FROM enrollments e
            JOIN courses c ON c.id = e.course_id
            WHERE e.user_id = ?
            ORDER BY e.created_at DESC
            """,
            (user["id"],),
        ).fetchall()

    cards = []
    for course in enrolled_courses:
        with get_db() as conn:
            contents = conn.execute(
                "SELECT * FROM course_contents WHERE course_id = ? ORDER BY display_order ASC", (course["id"],)
            ).fetchall()
            done = conn.execute(
                """
                SELECT content_id FROM lesson_progress
                WHERE user_id = ? AND content_id IN (
                    SELECT id FROM course_contents WHERE course_id = ? AND content_type = 'video'
                )
                """,
                (user["id"], course["id"]),
            ).fetchall()
        completed_ids = {r["content_id"] for r in done}
        video_items = [x for x in contents if x["content_type"] == "video"]
        progress = f"{len(completed_ids)}/{len(video_items)}" if video_items else "0/0"

        content_lines = []
        for item in contents:
            if item["content_type"] == "video":
                mark_button = ""
                if item["id"] not in completed_ids:
                    mark_button = (
                        f"<form method='post' action='/progress/{item['id']}/complete' style='display:inline'>"
                        "<button class='btn' type='submit'>Mark completed</button></form>"
                    )
                content_lines.append(
                    f"<li>VIDEO: {item['title']} - <a href='{item['url']}' target='_blank'>Watch</a> {mark_button}</li>"
                )
            elif item["content_type"] in {"notes", "pyq"}:
                content_lines.append(f"<li>{item['content_type'].upper()}: {item['title']} - <a href='{item['url']}' target='_blank'>Download</a></li>")
            else:
                content_lines.append(f"<li>{item['content_type'].upper()}: {item['title']}</li>")

        cards.append(
            f"""
            <div class='card'>
              <h3>{course['title']}</h3>
              <p class='muted'>Payment ID: {course['payment_id']} | Purchased: {course['created_at']}</p>
              <p><strong>Video progress:</strong> {progress}</p>
              <ul>{''.join(content_lines)}</ul>
              <a class='btn' href='/quiz/{course['id']}'>Take practice test</a>
            </div>
            """
        )

    body = f"""
    <h2>Student Dashboard</h2>
    <p>Purchased courses, learning progress, videos, study material, and tests.</p>
    {'<div class="grid">'+''.join(cards)+'</div>' if cards else '<p>No purchased courses yet. Browse <a href="/courses">courses</a>.</p>'}
    """
    return render_page("Dashboard", body)


@app.route("/admin")
@admin_required
def admin():
    with get_db() as conn:
        courses_data = conn.execute("SELECT * FROM courses ORDER BY id DESC").fetchall()
        enrollments = conn.execute(
            """
            SELECT e.id, e.payment_id, e.amount, e.created_at, u.name AS student_name, u.email, c.title
            FROM enrollments e
            JOIN users u ON u.id = e.user_id
            JOIN courses c ON c.id = e.course_id
            ORDER BY e.created_at DESC
            """
        ).fetchall()

    course_items = "".join(
        [
            f"<li>{c['title']} ({c['category']}) - <a href='/admin/course/{c['id']}/edit'>Edit</a> | <a href='/admin/course/{c['id']}/content/new'>Add content</a> | <a href='/admin/course/{c['id']}/quiz/new'>Add quiz</a></li>"
            for c in courses_data
        ]
    )
    enrollment_items = "".join(
        [
            f"<li>{e['student_name']} ({e['email']}) enrolled in {e['title']} - ₹{int(e['amount'])} [{e['payment_id']}]</li>"
            for e in enrollments
        ]
    )

    body = f"""
    <h2>Admin Panel</h2>
    <p><a class='btn' href='/admin/course/new'>Create new course</a></p>
    <h3>Manage Courses</h3>
    <ul>{course_items if course_items else '<li>No courses yet.</li>'}</ul>
    <h3>Enrolled Students</h3>
    <ul>{enrollment_items if enrollment_items else '<li>No enrollments yet.</li>'}</ul>
    """
    return render_page("Admin", body)


@app.route("/admin/course/new", methods=["GET", "POST"])
@admin_required
def admin_course_new():
    if request.method == "POST":
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO courses
                    (title, description, syllabus, instructor, original_price, sale_price, category, demo_youtube_url, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.form.get("title", "").strip(),
                    request.form.get("description", "").strip(),
                    request.form.get("syllabus", "").strip(),
                    request.form.get("instructor", "").strip(),
                    float(request.form.get("original_price", "0") or 0),
                    float(request.form.get("sale_price", "0") or 0),
                    request.form.get("category", "").strip(),
                    request.form.get("demo_youtube_url", "").strip() or DEFAULT_DEMO_VIDEO,
                    1 if request.form.get("is_active") == "on" else 0,
                ),
            )
        flash("Course created.", "success")
        return redirect(url_for("admin"))

    body = """
    <h2>Create Course</h2>
    <form method='post'>
      <label>Title<input name='title' required></label>
      <label>Description<textarea name='description' required></textarea></label>
      <label>Syllabus<textarea name='syllabus' required></textarea></label>
      <label>Instructor<input name='instructor' required></label>
      <label>Original Price<input name='original_price' type='number' step='0.01' required></label>
      <label>Sale Price<input name='sale_price' type='number' step='0.01' required></label>
      <label>Category<input name='category' required></label>
      <label>Demo YouTube URL<input name='demo_youtube_url'></label>
      <label><input type='checkbox' name='is_active' checked> Active</label>
      <button class='btn' type='submit'>Save</button>
    </form>
    """
    return render_page("Create course", body)


@app.route("/admin/course/<int:course_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_course_edit(course_id):
    with get_db() as conn:
        course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            abort(404)

        if request.method == "POST":
            conn.execute(
                """
                UPDATE courses
                SET title=?, description=?, syllabus=?, instructor=?, original_price=?, sale_price=?, category=?, demo_youtube_url=?, is_active=?
                WHERE id=?
                """,
                (
                    request.form.get("title", "").strip(),
                    request.form.get("description", "").strip(),
                    request.form.get("syllabus", "").strip(),
                    request.form.get("instructor", "").strip(),
                    float(request.form.get("original_price", "0") or 0),
                    float(request.form.get("sale_price", "0") or 0),
                    request.form.get("category", "").strip(),
                    request.form.get("demo_youtube_url", "").strip() or DEFAULT_DEMO_VIDEO,
                    1 if request.form.get("is_active") == "on" else 0,
                    course_id,
                ),
            )
            flash("Course updated.", "success")
            return redirect(url_for("admin"))

    checked = "checked" if course["is_active"] else ""
    body = f"""
    <h2>Edit Course</h2>
    <form method='post'>
      <label>Title<input name='title' value="{course['title']}" required></label>
      <label>Description<textarea name='description' required>{course['description']}</textarea></label>
      <label>Syllabus<textarea name='syllabus' required>{course['syllabus']}</textarea></label>
      <label>Instructor<input name='instructor' value="{course['instructor']}" required></label>
      <label>Original Price<input name='original_price' type='number' step='0.01' value='{course['original_price']}' required></label>
      <label>Sale Price<input name='sale_price' type='number' step='0.01' value='{course['sale_price']}' required></label>
      <label>Category<input name='category' value="{course['category']}" required></label>
      <label>Demo YouTube URL<input name='demo_youtube_url' value="{course['demo_youtube_url']}"></label>
      <label><input type='checkbox' name='is_active' {checked}> Active</label>
      <button class='btn' type='submit'>Update</button>
    </form>
    """
    return render_page("Edit course", body)


@app.route("/admin/course/<int:course_id>/content/new", methods=["GET", "POST"])
@admin_required
def admin_content_new(course_id):
    with get_db() as conn:
        course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            abort(404)

        if request.method == "POST":
            conn.execute(
                """
                INSERT INTO course_contents
                    (course_id, content_type, title, url, is_premium, display_order)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    course_id,
                    request.form.get("content_type", "video"),
                    request.form.get("title", "").strip(),
                    request.form.get("url", "").strip(),
                    1 if request.form.get("is_premium") == "on" else 0,
                    int(request.form.get("display_order", "1") or 1),
                ),
            )
            flash("Content added.", "success")
            return redirect(url_for("admin"))

    body = f"""
    <h2>Add Content - {course['title']}</h2>
    <form method='post'>
      <label>Type<select name='content_type'>
        <option value='video'>Video</option><option value='notes'>Notes</option>
        <option value='pyq'>PYQ</option><option value='mock_test'>Mock Test</option>
        <option value='live_doubt'>Live Doubt</option>
      </select></label>
      <label>Title<input name='title' required></label>
      <label>URL (video/pdf/live link)<input name='url'></label>
      <label>Display Order<input type='number' name='display_order' value='1'></label>
      <label><input type='checkbox' name='is_premium' checked> Premium</label>
      <button class='btn' type='submit'>Add content</button>
    </form>
    """
    return render_page("Add content", body)


@app.route("/admin/course/<int:course_id>/quiz/new", methods=["GET", "POST"])
@admin_required
def admin_quiz_new(course_id):
    with get_db() as conn:
        course = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            abort(404)

        if request.method == "POST":
            options = [
                request.form.get("opt0", "").strip(),
                request.form.get("opt1", "").strip(),
                request.form.get("opt2", "").strip(),
                request.form.get("opt3", "").strip(),
            ]
            conn.execute(
                """
                INSERT INTO quiz_questions (course_id, question, options_json, correct_index, solution)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    course_id,
                    request.form.get("question", "").strip(),
                    json.dumps(options),
                    int(request.form.get("correct_index", "0") or 0),
                    request.form.get("solution", "").strip(),
                ),
            )
            flash("Quiz question added.", "success")
            return redirect(url_for("admin"))

    body = f"""
    <h2>Add Quiz Question - {course['title']}</h2>
    <form method='post'>
      <label>Question<textarea name='question' required></textarea></label>
      <label>Option 1<input name='opt0' required></label>
      <label>Option 2<input name='opt1' required></label>
      <label>Option 3<input name='opt2' required></label>
      <label>Option 4<input name='opt3' required></label>
      <label>Correct Option Index (0-3)<input name='correct_index' type='number' min='0' max='3' value='0' required></label>
      <label>Solution<textarea name='solution' required></textarea></label>
      <button class='btn' type='submit'>Add question</button>
    </form>
    """
    return render_page("Add quiz", body)


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
