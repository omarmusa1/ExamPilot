# Requirements and Product Backlog

## Vision
Let any student turn their own course material into a practice exam in seconds, get instant explained feedback, and keep practising until the weak spots are gone.

## Actors
- **Student**: the only human user. Uploads courses, takes exams, reviews results.
- **AI service (Claude)**: generates questions from the course text.

## User stories

| ID | As a... | I want to... | So that... | Priority | Status |
|----|---------|--------------|-----------|----------|--------|
| US-1 | student | sign up and log in | my quizzes and progress are saved | Must | Done |
| US-2 | student | upload a .txt/.md/.pdf course or paste text | I do not retype my notes | Must | Done |
| US-3 | student | generate N MCQs with difficulty and language | I can test myself in minutes | Must | Done |
| US-4 | student | take the exam and submit it | I know how well I understand the course | Must | Done |
| US-5 | student | see my score, correct answers and explanations | I learn from my mistakes | Must | Done |
| US-6 | student | edit or delete a generated question | I can fix AI mistakes | Must | Done |
| US-7 | student | retry only the questions I missed | I practise my weak spots | Should | Done |
| US-8 | student | retake the full exam and see my improvement | I can track progress | Should | Done |
| US-9 | student | see a dashboard with attempts, average and best score | I see my overall progress | Should | Done |
| US-10 | student | see which questions are hardest for me | I know what to revise | Should | Done |
| US-11 | student | use the app without an API key (demo mode) | easy demo and testing | Should | Done |
| US-12 | student | add more questions to an existing quiz | I can extend coverage | Could | Backlog |
| US-13 | student | answer short-answer questions graded by AI | broader practice | Could | Backlog |
| US-14 | student | set a timer for exam simulation | exam-like conditions | Could | Backlog |
| US-15 | student | upload scanned PDFs / images (OCR) | support handwritten or scanned notes | Could | Backlog |
| US-16 | student | share a quiz with classmates via link | study groups | Could | Backlog |
| US-17 | student | export my results | keep a record | Could | Backlog |

## Functional requirements
- FR-1 Passwords are stored hashed; sessions are cookie based.
- FR-2 A user can only see and modify their own quizzes and attempts.
- FR-3 A quiz can be attempted any number of times; each attempt is stored with its answers.
- FR-4 Grading compares the chosen option with the stored correct option; unanswered counts as wrong.
- FR-5 "Missed only" mode contains exactly the questions answered wrong or skipped in the latest attempt.
- FR-6 AI output is validated (4 distinct options, one correct) before being saved.
- FR-7 If the AI call fails, the system falls back to the demo generator.

## Non-functional requirements
- NFR-1 Runs locally with `pip install` + `python app.py` only.
- NFR-2 No secret (API key) is committed; configuration via `.env`.
- NFR-3 Pages work on desktop and mobile widths.
- NFR-4 Core logic is covered by automated tests (`pytest`).
