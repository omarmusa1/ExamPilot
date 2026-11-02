# Project Proposal: ExamPilot

**Course:**  CS 488 - AI-First Software Engineering

**Working title:**  AI Exam Generator for Students

**Tagline:**  Upload your course. Test yourself. Improve.

## Team

| Member | Role |
|--------|------|
| Omar Musa | _Backend Developer_ |
| Nadhem Zribi | _Database Manager_ |
| Hedi Ben Daoud | _Frontend Designer_ |
| Youssef Jemaa | _Tester & Documentation_ |

## 1. Problem

Students usually study from long course PDFs and notes, but they have no quick way to check whether they actually understood the material. Writing practice questions by hand takes a lot of time, so most students only re-read their notes, which is a weak way to learn. Many quiz tools either require the content to be created manually or are built for teachers rather than for the student who just wants to revise their own course.

## 2. Target users

- **Primary:** university and high-school students who want to test themselves on their own course material.
- **Secondary (future):** study groups who want to share a quiz.

## 3. Proposed solution

A web application where the **student uploads a course file** (PDF, TXT, MD) or pastes text. An AI model generates a multiple-choice exam from that material. The student takes the exam and submits it. The system **grades it instantly**, explains each question, lets the student **retry only the questions they missed**, and shows their progress over time.

## 4. Core user stories (MVP)

1. As a student, I can create an account and log in.
2. As a student, I can upload a course file or paste text and choose the number of questions, difficulty and language.
3. As a student, I get an AI-generated multiple-choice exam based on my course.
4. As a student, I can edit or delete a question when the AI makes a mistake.
5. As a student, I can take the exam and submit it.
6. As a student, I see my score, the correct answers and an explanation for each question.
7. As a student, I can retry only the questions I got wrong, or retake the full exam.
8. As a student, I can see my attempts, average and best score, and which questions are hardest for me.

The full list with priorities is in [`requirements-and-backlog.md`](requirements-and-backlog.md).

## 5. Out of scope for the MVP

- Essay and short-answer questions with AI grading
- OCR for scanned PDFs and images
- Exam timer and anti-cheating features
- Sharing quizzes between students
- Teacher accounts and class management

## 6. How AI is used

**Inside the product:** a large language model (Claude) reads the course text and returns questions as structured JSON (question, four options, correct answer, explanation). The application validates this output before saving it. Grading is done by plain code, not by the AI, so it is instant, deterministic and free.

**During development:** an AI assistant (Claude) helped with design, code, tests and documentation. Every use is recorded in [`ai-usage-log.md`](ai-usage-log.md).

## 7. Technical approach

- Python and Flask for the backend
- SQLite for storage
- Server-rendered HTML and CSS for the interface
- Anthropic Claude API for question generation, with a rule-based demo mode so the app runs without an API key
- pytest for automated tests

Architecture and data model diagrams are in [`uml.md`](uml.md).

## 8. Risks and mitigation

| Risk | Mitigation |
|------|-----------|
| AI generates wrong or ambiguous questions | Strict JSON validation, explanations on every question, and students can edit or delete questions |
| AI service is unavailable or has no API key | Demo mode fallback so the app always runs |
| Very long courses exceed the model input | The text is truncated; chunking is planned in the backlog |
| Scanned PDFs have no text | Documented limitation; OCR is in the backlog |
| Low quality of questions in demo mode | Demo mode is only a fallback; real questions need the API |

## 9. Success criteria

- A new user can go from upload to a graded exam in under two minutes.
- The app runs by following the README only.
- Core logic is covered by automated tests.
- Students can see measurable improvement between attempts.

## 10. Plan to the final exam

| Phase | Goal |
|-------|------|
| Midterm (now) | Working MVP, demo video, repository, documentation |
| After midterm | Improve question quality, add more questions to an existing quiz, exam timer |
| Before final | Short-answer questions with AI grading, scanned-PDF support, polish and user testing |
