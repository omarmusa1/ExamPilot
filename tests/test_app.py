import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

LESSON = (
    "Photosynthesis is the process by which green plants convert sunlight into chemical energy. "
    "Chlorophyll inside the chloroplasts absorbs sunlight during the light reactions. "
    "The Calvin cycle uses carbon dioxide and energy to build glucose molecules. "
    "Oxygen is released into the atmosphere as a by-product of photosynthesis. "
    "Plants store the extra glucose as starch inside their roots, stems and leaves. "
    "Stomata are tiny pores on leaves that allow gases to enter and leave the plant. "
    "Water is absorbed by the roots and transported upward through the xylem vessels."
)


@pytest.fixture()
def client(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("EXAMAI_DB", path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import importlib

    import db
    importlib.reload(db)
    import app as app_module
    importlib.reload(app_module)
    app_module.app.config["TESTING"] = True
    yield app_module.app.test_client()
    os.remove(path)


def register(client, name="Stu", email="s@x.com"):
    return client.post("/register", data={"name": name, "email": email, "password": "secret123"})


def create_quiz(client, n=4):
    resp = client.post("/quizzes/new", data={"title": "Bio", "text": LESSON, "num_questions": n})
    assert resp.status_code == 302
    return int(resp.headers["Location"].rstrip("/").split("/")[-1])


def quiz_questions(quiz_id):
    import db
    with db.get_conn() as conn:
        return conn.execute("SELECT * FROM questions WHERE quiz_id = ? ORDER BY position", (quiz_id,)).fetchall()


def answer_form(questions, right):
    """right = set of question positions (0-based) to answer correctly; others get a wrong option."""
    form = {"qid": [str(q["id"]) for q in questions]}
    for i, q in enumerate(questions):
        wrong = next(l for l in "ABCD" if l != q["correct"])
        form[f"q{q['id']}"] = q["correct"] if i in right else wrong
    return form


# ---------------------------------------------------------------- AI layer

def test_parse_ai_json_valid_and_invalid():
    import ai

    good = '```json\n{"questions":[{"text":"Q?","options":["a","b","c","d"],"correct":2,"explanation":"x"}]}\n```'
    assert ai.parse_ai_json(good)[0]["correct"] == "C"
    with pytest.raises(ValueError):
        ai.parse_ai_json('{"questions":[{"text":"Q?","options":["a","a","c","d"],"correct":0}]}')
    with pytest.raises(ValueError):
        ai.parse_ai_json("not json at all")


def test_demo_generator_makes_valid_questions():
    import ai

    questions, engine = ai.generate_questions(LESSON, 4)
    assert engine == "demo"
    assert 1 <= len(questions) <= 4
    for q in questions:
        assert len(q["options"]) == 4 and len(set(q["options"])) == 4
        assert q["correct"] in "ABCD"


def test_short_text_rejected():
    import ai

    with pytest.raises(ai.GenerationError):
        ai.generate_questions("too short")


# ------------------------------------------------------------------ app

def test_register_login_logout(client):
    assert register(client).status_code == 302
    client.get("/logout")
    assert client.get("/dashboard").status_code == 302  # login required
    assert client.post("/login", data={"email": "s@x.com", "password": "wrong"}).status_code == 401
    assert client.post("/login", data={"email": "s@x.com", "password": "secret123"}).status_code == 302
    assert client.get("/dashboard").status_code == 200


def test_duplicate_email_rejected(client):
    register(client)
    client.get("/logout")
    assert register(client).status_code == 400


def test_upload_txt_file_generates_quiz(client):
    import io

    register(client)
    resp = client.post(
        "/quizzes/new",
        data={"title": "From file", "num_questions": 3, "file": (io.BytesIO(LESSON.encode()), "course.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 302


def test_bad_upload_type_rejected(client):
    import io

    register(client)
    resp = client.post(
        "/quizzes/new",
        data={"title": "x", "file": (io.BytesIO(b"data"), "course.exe")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_full_student_flow_with_retries(client):
    register(client)
    quiz_id = create_quiz(client, 4)
    questions = quiz_questions(quiz_id)
    n = len(questions)
    assert n >= 2

    # 1st attempt: only the first question right
    resp = client.post(f"/quizzes/{quiz_id}/take", data=answer_form(questions, {0}))
    assert resp.status_code == 302 and "/attempts/" in resp.headers["Location"]
    page = client.get(resp.headers["Location"])
    assert page.status_code == 200 and f"1 / {n}".encode() in page.data

    # retry-missed mode only shows the questions that were wrong
    retry = client.get(f"/quizzes/{quiz_id}/take?mode=missed")
    assert retry.status_code == 200 and retry.data.count(b'name="qid"') == n - 1

    # submit the retry, all correct
    missed = questions[1:]
    resp = client.post(f"/quizzes/{quiz_id}/take", data=answer_form(missed, set(range(len(missed)))))
    assert resp.status_code == 302
    import db
    with db.get_conn() as conn:
        attempts = conn.execute("SELECT * FROM attempts ORDER BY id").fetchall()
    assert [a["mode"] for a in attempts] == ["full", "missed"]
    assert attempts[1]["score"] == attempts[1]["total"] == n - 1

    # full retake, all correct -> improvement shown vs previous full attempt
    resp = client.post(f"/quizzes/{quiz_id}/take", data=answer_form(questions, set(range(n))))
    page = client.get(resp.headers["Location"])
    assert b"points" in page.data

    # quiz page and dashboard render with history
    assert client.get(f"/quizzes/{quiz_id}").status_code == 200
    assert b"Bio" in client.get("/dashboard").data


def test_unanswered_counts_as_wrong(client):
    register(client)
    quiz_id = create_quiz(client, 3)
    questions = quiz_questions(quiz_id)
    resp = client.post(f"/quizzes/{quiz_id}/take", data={"qid": [str(q["id"]) for q in questions]})
    import db
    with db.get_conn() as conn:
        att = conn.execute("SELECT * FROM attempts").fetchone()
    assert att["score"] == 0 and att["total"] == len(questions)
    assert resp.status_code == 302


def test_edit_and_delete_question(client):
    register(client)
    quiz_id = create_quiz(client, 3)
    q = quiz_questions(quiz_id)[0]
    resp = client.post(
        f"/quizzes/{quiz_id}/questions/{q['id']}",
        data={"action": "save", "text": "New?", "a": "1", "b": "2", "c": "3", "d": "4",
              "correct": "D", "explanation": "because"},
    )
    assert resp.status_code == 302
    updated = quiz_questions(quiz_id)[0]
    assert updated["text"] == "New?" and updated["correct"] == "D"
    client.post(f"/quizzes/{quiz_id}/questions/{q['id']}", data={"action": "delete"})
    assert all(x["id"] != q["id"] for x in quiz_questions(quiz_id))


def test_users_cannot_access_each_others_quizzes(client):
    register(client, "A", "a@x.com")
    quiz_id = create_quiz(client, 3)
    questions = quiz_questions(quiz_id)
    resp = client.post(f"/quizzes/{quiz_id}/take", data=answer_form(questions, {0}))
    attempt_url = resp.headers["Location"]
    client.get("/logout")

    register(client, "B", "b@x.com")
    assert client.get(f"/quizzes/{quiz_id}").status_code == 404
    assert client.get(f"/quizzes/{quiz_id}/take").status_code == 404
    assert client.get(f"/quizzes/{quiz_id}/edit").status_code == 404
    assert client.post(f"/quizzes/{quiz_id}/delete").status_code == 404
    assert client.get(attempt_url).status_code == 404


def test_delete_quiz_cascades(client):
    register(client)
    quiz_id = create_quiz(client, 3)
    questions = quiz_questions(quiz_id)
    client.post(f"/quizzes/{quiz_id}/take", data=answer_form(questions, {0}))
    assert client.post(f"/quizzes/{quiz_id}/delete").status_code == 302
    import db
    with db.get_conn() as conn:
        for table in ("quizzes", "questions", "attempts", "answers"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
