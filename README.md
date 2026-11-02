# ExamPilot - AI Exam Generator for Students

A study tool for students. **You upload your course** (PDF, TXT, MD or pasted text), the AI writes a
multiple-choice exam from it, you take the exam, and you are **graded instantly** with an explanation for every
question. Then you can **retry only the questions you missed**, retake the full exam and track your progress.

**Team members:** _ Omar Musa, Nadhem Zribi, Hedi Ben Daoud, Youssef Jemaa_

## Features (MVP)

| User story | Status |
|---|---|
| Sign up / log in | Done |
| Upload a course file (.txt, .md, .pdf) or paste text | Done |
| Choose number of questions, difficulty and question language | Done |
| AI generates MCQs with the correct answer and an explanation | Done |
| Edit or delete any generated question (AI can be wrong) | Done |
| Take the exam and submit | Done |
| Instant automatic grading with explanations | Done |
| Retry only the missed questions | Done |
| Retake the full exam, see improvement vs the previous attempt | Done |
| Dashboard: quizzes, attempts, average score, best/last score | Done |
| Per-question "how hard is it for me" statistics | Done |
| Demo mode (works without an API key) | Done |

## Tech stack

- Python 3.10+ and Flask
- SQLite (single file, created automatically)
- Groq API for question generation and grading (free; falls back to an offline rule-based demo engine)
- Plain HTML templates + CSS (no build step)

## Install and run

```bash
# 1. Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate

# 2. upgrade pip
python.exe -m pip install --upgrade pip

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python app.py
```

Open http://127.0.0.1:5000

**No API key?** Nothing to configure. The app runs in *Demo mode* (badge shown in the top bar) and generates
fill-in-the-blank questions with a rule-based engine so the whole flow can be tested offline.

## Quick demo walkthrough

1. Sign up -> **New quiz from my course** -> upload a PDF/TXT (or paste a lesson) -> **Generate my exam**.
2. (Optional) **Edit questions** to fix anything the AI got wrong.
3. **Start exam** -> answer -> **Submit** -> see your score, the correct answers and explanations.
4. Click **Retry missed questions** to practise only what you got wrong.
5. Go back to **My quizzes** to see your attempts, best score and the questions that are hardest for you.

## Run the tests

```bash
pytest -q
```

## Project structure

```
app.py          Flask routes (auth, quizzes, attempts, results)
ai.py           Question generation (Groq + demo engine) and JSON validation
db.py           SQLite schema and connection helper
templates/      HTML pages
static/         CSS
tests/          Automated tests
docs/           Requirements, UML diagrams, AI usage log
```

## Design notes

- MCQ grading is done in code (chosen vs. correct letter), not by the AI: instant, free and deterministic.
- AI output is validated (4 distinct options, one valid correct index); invalid questions are dropped.
- If the Groq call fails, the app falls back to the demo engine so the student is never blocked.
- Students can edit questions because AI questions can occasionally be wrong or ambiguous.
- A quiz can be attempted many times; "missed only" retries target weak spots (spaced-repetition style practice).
- Security: hashed passwords, CSRF token on every form, per-user ownership checks on every quiz/attempt, 8 MB upload limit.

## Known limitations

- MCQ only (no essay or short-answer questions).
- Scanned PDFs without a text layer are not supported (no OCR).
- Very long courses: only the first ~12,000 characters are sent to the AI per quiz.
- Single-server SQLite, intended for a demo / personal use.

## Documentation

See the [`docs/`](docs/) folder: requirements and backlog, UML diagrams and the AI usage log.
