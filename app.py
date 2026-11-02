import io
import os
import secrets
import sqlite3
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

import ai  # noqa: E402
import db  # noqa: E402

app = Flask(__name__)
# Without SECRET_KEY in .env a random key is used (sessions reset on restart) instead of a guessable default.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB uploads

db.init_db()

TYPE_LABELS = {"mcq": "Multiple choice", "true_false": "True / False", "use_case": "Use case"}

@app.template_filter("pts")
def fmt_points(value):
    """3.0 -> '3', 2.5 -> '2.5'"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return value
    return str(int(v)) if v == int(v) else f"{v:.1f}"


# ------------------------------------------------------------- helpers

@app.context_processor
def inject_globals():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return {
        "csrf_token": session["csrf_token"],
        "current_user": g.get("user"),
        "ai_engine": ai.engine_name(g.get("user")),
        "type_labels": TYPE_LABELS,
    }


@app.before_request
def load_user_and_check_csrf():
    g.user = None
    if "user_id" in session:
        with db.get_conn() as conn:
            g.user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if request.method == "POST" and not app.config.get("TESTING"):
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or token != session.get("csrf_token"):
            abort(400, "Invalid or missing CSRF token. Reload the page and try again.")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def get_own_quiz(conn, quiz_id):
    quiz = conn.execute(
        "SELECT * FROM quizzes WHERE id = ? AND user_id = ?", (quiz_id, g.user["id"])
    ).fetchone()
    if quiz is None:
        abort(404)
    return quiz


def extract_text(upload):
    """Read text from an uploaded .txt / .md / .pdf file."""
    if not upload or not upload.filename:
        return ""
    name = upload.filename.lower()
    data = upload.read()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="ignore")
    raise ValueError("Unsupported file type. Upload a .txt, .md or .pdf file.")


def missed_question_ids(conn, quiz_id, user_id):
    """Questions the student got wrong (or skipped, or scored below the pass mark) in the latest attempt."""
    last = conn.execute(
        "SELECT id FROM attempts WHERE quiz_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
        (quiz_id, user_id),
    ).fetchone()
    if last is None:
        return []
    rows = conn.execute(
        """SELECT a.question_id FROM answers a
           JOIN questions q ON q.id = a.question_id
           WHERE a.attempt_id = ? AND a.is_correct = 0 ORDER BY q.position""",
        (last["id"],),
    ).fetchall()
    return [r["question_id"] for r in rows]


# ---------------------------------------------------------------- auth

@app.route("/")
def index():
    if g.user:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or "@" not in email or len(password) < 6:
            flash("Fill all fields correctly (password: 6+ characters).", "error")
            return render_template("register.html"), 400
        try:
            with db.get_conn() as conn:
                cur = conn.execute(
                    "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                    (name, email, generate_password_hash(password)),
                )
            session.clear()
            session["user_id"] = cur.lastrowid
            return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError:
            flash("That email is already registered.", "error")
            return render_template("register.html"), 400
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with db.get_conn() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        flash("Wrong email or password.", "error")
        return render_template("login.html"), 401
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


# ------------------------------------------------------------ settings & API Test

@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        api_key = request.form.get("api_key", "").strip()
        action = request.form.get("action", "save")
        provider = "groq"

        if action == "test":
            ok, msg = ai.test_api_key(provider, api_key)
            flash(msg, "success" if ok else "error")
            return render_template("settings.html", entered_key=api_key)

        with db.get_conn() as conn:
            conn.execute(
                "UPDATE users SET ai_provider = ?, api_key = ? WHERE id = ?",
                ("groq" if api_key else "demo", api_key, g.user["id"]),
            )
            g.user = conn.execute("SELECT * FROM users WHERE id = ?", (g.user["id"],)).fetchone()
        if api_key:
            flash("Groq API key saved.", "success")
        else:
            flash("API key removed. The app is now in offline demo mode.", "success")
        return redirect(url_for("dashboard"))
    return render_template("settings.html", entered_key=g.user["api_key"])


@app.route("/api/test-key", methods=["POST"])
@login_required
def api_test_key():
    api_key = request.form.get("api_key", "").strip()
    ok, msg = ai.test_api_key("groq", api_key)
    return jsonify({"ok": ok, "message": msg})


# ------------------------------------------------------------ dashboard

@app.route("/dashboard")
@login_required
def dashboard():
    with db.get_conn() as conn:
        quizzes = conn.execute(
            """SELECT z.*,
                      (SELECT COUNT(*) FROM questions q WHERE q.quiz_id = z.id) AS n_questions,
                      (SELECT COUNT(*) FROM attempts a WHERE a.quiz_id = z.id) AS n_attempts,
                      (SELECT MAX(100.0 * a.score / a.total) FROM attempts a
                         WHERE a.quiz_id = z.id AND a.total > 0) AS best_pct,
                      (SELECT 100.0 * a.score / a.total FROM attempts a
                         WHERE a.quiz_id = z.id AND a.total > 0 ORDER BY a.id DESC LIMIT 1) AS last_pct
               FROM quizzes z WHERE z.user_id = ? ORDER BY z.id DESC""",
            (g.user["id"],),
        ).fetchall()
        totals = conn.execute(
            """SELECT COUNT(*) AS n, AVG(100.0 * score / total) AS avg_pct
               FROM attempts WHERE user_id = ? AND total > 0""",
            (g.user["id"],),
        ).fetchone()
    stats = {
        "quizzes": len(quizzes),
        "attempts": totals["n"],
        "average": totals["avg_pct"] or 0,
    }
    return render_template("dashboard.html", quizzes=quizzes, stats=stats)


# ----------------------------------------------------------- quizzes

@app.route("/quizzes/new", methods=["GET", "POST"])
@login_required
def new_quiz():
    if request.method == "POST":
        title = request.form.get("title", "").strip() or "Untitled quiz"
        text = request.form.get("text", "").strip()
        try:
            uploaded = extract_text(request.files.get("file"))
        except Exception as exc:
            flash(f"Could not read the file: {exc}", "error")
            return render_template("new_quiz.html"), 400
        if uploaded:
            text = (text + "\n\n" + uploaded).strip()
        try:
            num = int(request.form.get("num_questions", 5))
        except ValueError:
            num = 5
        qtype = request.form.get("qtype", "mcq")
        if qtype not in ai.CHOICES:
            qtype = "mcq"
        difficulty = request.form.get("difficulty", "medium")
        language = request.form.get("language", "").strip()[:60] or "same as the text"
        try:
            questions, engine, note = ai.generate_questions(
                text, num, difficulty, language, qtype, user=g.user
            )
        except ai.GenerationError as exc:
            flash(str(exc), "error")
            return render_template("new_quiz.html"), 400

        with db.get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO quizzes (user_id, title, source_text, generated_by) VALUES (?, ?, ?, ?)",
                (g.user["id"], title, text, engine),
            )
            quiz_id = cur.lastrowid
            for i, q in enumerate(questions, start=1):
                conn.execute(
                    """INSERT INTO questions
                       (quiz_id, position, qtype, scenario, text, option_a, option_b, option_c, option_d,
                        correct, model_answer, explanation)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (quiz_id, i, q["qtype"], q["scenario"], q["text"], *q["options"],
                     q["correct"], q["model_answer"], q["explanation"]),
                )
        flash(f"Your quiz is ready: {len(questions)} questions ({engine} engine).", "success")
        if note:
            flash(note, "error")
        if qtype == "use_case" and num > ai.MAX_USE_CASES:
            flash(f"Use-case quizzes are limited to {ai.MAX_USE_CASES} questions.", "error")
        return redirect(url_for("quiz_detail", quiz_id=quiz_id))
    return render_template("new_quiz.html")


@app.route("/quizzes/<int:quiz_id>")
@login_required
def quiz_detail(quiz_id):
    with db.get_conn() as conn:
        quiz = get_own_quiz(conn, quiz_id)
        n_questions = conn.execute(
            "SELECT COUNT(*) FROM questions WHERE quiz_id = ?", (quiz_id,)
        ).fetchone()[0]
        attempts = conn.execute(
            "SELECT * FROM attempts WHERE quiz_id = ? AND user_id = ? ORDER BY id DESC",
            (quiz_id, g.user["id"]),
        ).fetchall()
        per_question = conn.execute(
            """SELECT q.position, q.text, q.qtype,
                      COUNT(a.id) AS tries,
                      COALESCE(SUM(a.is_correct), 0) AS right_count
               FROM questions q
               LEFT JOIN answers a ON a.question_id = q.id
                    AND a.attempt_id IN (SELECT id FROM attempts WHERE user_id = ?)
               WHERE q.quiz_id = ? GROUP BY q.id ORDER BY q.position""",
            (g.user["id"], quiz_id),
        ).fetchall()
        missed = missed_question_ids(conn, quiz_id, g.user["id"])
    return render_template(
        "quiz_detail.html", quiz=quiz, n_questions=n_questions, attempts=attempts,
        per_question=per_question, n_missed=len(missed),
    )


@app.route("/quizzes/<int:quiz_id>/delete", methods=["POST"])
@login_required
def delete_quiz(quiz_id):
    with db.get_conn() as conn:
        get_own_quiz(conn, quiz_id)
        conn.execute("DELETE FROM quizzes WHERE id = ?", (quiz_id,))
    flash("Quiz deleted.", "success")
    return redirect(url_for("dashboard"))


@app.route("/quizzes/<int:quiz_id>/edit")
@login_required
def edit_quiz(quiz_id):
    with db.get_conn() as conn:
        quiz = get_own_quiz(conn, quiz_id)
        questions = conn.execute(
            "SELECT * FROM questions WHERE quiz_id = ? ORDER BY position", (quiz_id,)
        ).fetchall()
    return render_template("edit_quiz.html", quiz=quiz, questions=questions)


@app.route("/quizzes/<int:quiz_id>/questions/<int:qid>", methods=["POST"])
@login_required
def update_question(quiz_id, qid):
    action = request.form.get("action", "save")
    form = request.form
    with db.get_conn() as conn:
        get_own_quiz(conn, quiz_id)
        question = conn.execute(
            "SELECT qtype FROM questions WHERE id = ? AND quiz_id = ?", (qid, quiz_id)
        ).fetchone()
        if question is None:
            abort(404)
        if action == "delete":
            conn.execute("DELETE FROM questions WHERE id = ? AND quiz_id = ?", (qid, quiz_id))
            flash("Question deleted.", "success")
        else:
            qtype = question["qtype"]
            text = form.get("text", "").strip()
            explanation = form.get("explanation", "").strip()
            if qtype == "use_case":
                scenario = form.get("scenario", "").strip()
                model_answer = form.get("model_answer", "").strip()
                if not (text and scenario and model_answer):
                    flash("Scenario, question and reference answer are required.", "error")
                else:
                    conn.execute(
                        "UPDATE questions SET scenario=?, text=?, model_answer=?, explanation=? "
                        "WHERE id=? AND quiz_id=?",
                        (scenario, text, model_answer, explanation, qid, quiz_id),
                    )
                    flash("Question saved.", "success")
            elif qtype == "true_false":
                correct = form.get("correct", "A")
                if correct not in ("A", "B") or not text:
                    flash("The statement is required and the answer must be True or False.", "error")
                else:
                    conn.execute(
                        "UPDATE questions SET text=?, correct=?, explanation=? WHERE id=? AND quiz_id=?",
                        (text, correct, explanation, qid, quiz_id),
                    )
                    flash("Question saved.", "success")
            else:
                correct = form.get("correct", "A")
                options = [form.get(k, "").strip() for k in ("a", "b", "c", "d")]
                if correct not in ("A", "B", "C", "D") or not text or not all(options):
                    flash("Question text and all four options are required.", "error")
                else:
                    conn.execute(
                        """UPDATE questions SET text=?, option_a=?, option_b=?, option_c=?, option_d=?,
                           correct=?, explanation=? WHERE id=? AND quiz_id=?""",
                        (text, *options, correct, explanation, qid, quiz_id),
                    )
                    flash("Question saved.", "success")
    return redirect(url_for("edit_quiz", quiz_id=quiz_id))


# -------------------------------------------------------- taking a quiz

@app.route("/quizzes/<int:quiz_id>/take", methods=["GET", "POST"])
@login_required
def take_quiz(quiz_id):
    with db.get_conn() as conn:
        quiz = get_own_quiz(conn, quiz_id)
        all_questions = conn.execute(
            "SELECT * FROM questions WHERE quiz_id = ? ORDER BY position", (quiz_id,)
        ).fetchall()
        if not all_questions:
            flash("This quiz has no questions. Add or regenerate some first.", "error")
            return redirect(url_for("quiz_detail", quiz_id=quiz_id))

        if request.method == "POST":
            posted = {int(x) for x in request.form.getlist("qid") if x.isdigit()}
            questions = [q for q in all_questions if q["id"] in posted] or list(all_questions)
            mode = "full" if len(questions) == len(all_questions) else "missed"

            written, items = {}, []
            for q in questions:
                if q["qtype"] == "use_case":
                    answer = (request.form.get(f"t{q['id']}") or "").strip()[:4000]
                    written[q["id"]] = answer
                    if answer:
                        items.append({"id": q["id"], "scenario": q["scenario"], "question": q["text"],
                                      "model_answer": q["model_answer"], "answer": answer})
            ai_results, _engine, grade_note = ai.grade_use_cases(items, user=g.user) if items else ({}, None, None)

            graded, total_points = [], 0.0
            for q in questions:
                if q["qtype"] == "use_case":
                    answer = written.get(q["id"], "")
                    if answer:
                        res = ai_results.get(q["id"]) or {"score": 0.0, "feedback": "Could not be graded automatically."}
                        points, feedback = res["score"], res["feedback"]
                    else:
                        points, feedback = 0.0, "No answer given."
                    ok = 1 if points >= ai.PASS_MARK else 0
                    graded.append((q["id"], None, answer, ok, points, feedback))
                else:
                    chosen = request.form.get(f"q{q['id']}")
                    if chosen not in ("A", "B", "C", "D"):
                        chosen = None
                    ok = 1 if chosen == q["correct"] else 0
                    points = float(ok)
                    graded.append((q["id"], chosen, "", ok, points, ""))
                total_points += points

            score = round(total_points, 1)
            if float(score).is_integer():
                score = int(score)
            cur = conn.execute(
                "INSERT INTO attempts (quiz_id, user_id, score, total, mode) VALUES (?, ?, ?, ?, ?)",
                (quiz_id, g.user["id"], score, len(questions), mode),
            )
            for qid, chosen, answer, ok, points, feedback in graded:
                conn.execute(
                    """INSERT INTO answers (attempt_id, question_id, chosen, answer_text, is_correct, points, feedback)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (cur.lastrowid, qid, chosen, answer, ok, points, feedback),
                )
            if grade_note:
                flash(grade_note, "error")
            return redirect(url_for("result", attempt_id=cur.lastrowid))

        retry_missed = request.args.get("mode") == "missed"
        questions = list(all_questions)
        if retry_missed:
            missed = set(missed_question_ids(conn, quiz_id, g.user["id"]))
            if missed:
                questions = [q for q in all_questions if q["id"] in missed]
    has_use_case = any(q["qtype"] == "use_case" for q in questions)
    return render_template("take_quiz.html", quiz=quiz, questions=questions,
                           retry_missed=retry_missed, has_use_case=has_use_case)


@app.route("/attempts/<int:attempt_id>")
@login_required
def result(attempt_id):
    with db.get_conn() as conn:
        attempt = conn.execute(
            "SELECT * FROM attempts WHERE id = ? AND user_id = ?", (attempt_id, g.user["id"])
        ).fetchone()
        if attempt is None:
            abort(404)
        quiz = conn.execute("SELECT * FROM quizzes WHERE id = ?", (attempt["quiz_id"],)).fetchone()
        rows = conn.execute(
            """SELECT q.*, a.chosen, a.answer_text, a.is_correct, a.points, a.feedback
               FROM answers a JOIN questions q ON q.id = a.question_id
               WHERE a.attempt_id = ? ORDER BY q.position""",
            (attempt_id,),
        ).fetchall()
        previous = conn.execute(
            """SELECT 100.0 * score / total AS pct FROM attempts
               WHERE quiz_id = ? AND user_id = ? AND id < ? AND mode = 'full' AND total > 0
               ORDER BY id DESC LIMIT 1""",
            (attempt["quiz_id"], g.user["id"], attempt_id),
        ).fetchone()
    pct = round(100.0 * attempt["score"] / attempt["total"]) if attempt["total"] else 0
    n_wrong = sum(1 for r in rows if not r["is_correct"])
    delta = None
    if previous is not None and attempt["mode"] == "full":
        delta = pct - round(previous["pct"])
    return render_template("result.html", quiz=quiz, attempt=attempt, rows=rows, pct=pct,
                           n_wrong=n_wrong, delta=delta)


@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", code=403, message="You do not have access to this page."), 403


@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="Page not found."), 404


@app.errorhandler(400)
def bad_request(e):
    return render_template("error.html", code=400, message=getattr(e, "description", "Bad request.")), 400


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
