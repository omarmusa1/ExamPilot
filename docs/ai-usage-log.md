# AI Usage Log

Honest record of where AI was used in this project. **Team: fill the "Reviewed / changed by us" column with what you actually did.**

## AI inside the product
| Where | What | Notes |
|-------|------|-------|
| `ai.py` | Claude generates MCQs from the student's course text (JSON output) | Output is validated; the student can edit/delete questions |
| `ai.py` | Rule-based demo engine | Not AI; offline fallback so the app always runs |

## AI used to build the project (Claude)
| Date | Task | Prompt summary | Reviewed / changed by us |
|------|------|----------------|--------------------------|
| 2026-11-01 | Idea validation | Asked whether an AI exam generator is feasible and practical | |
| 2026-11-01 | Submission requirements | Asked for translation of the midterm brief and a plan | |
| 2026-11-01 | Stack decision | Chose Flask + SQLite, English UI, demo mode without API key | |
| 2026-11-01 | First version | Generated a teacher + student version (codes, publishing, analytics) | |
| 2026-11-01 | Product pivot | We decided the product should be for students only: the student uploads the course and takes the exam. Claude rewrote the data model, routes, templates, tests and docs | |
| 2026-11-01 | Tests and docs | Generated tests, README, requirements, UML | |

## Lessons learned
- AI-generated questions can be wrong or ambiguous, so editing questions is part of the design.
- Asking the model for strict JSON and validating it prevents broken exams.
- Grading MCQs in plain code is cheaper and more reliable than using AI.
- Rethinking who the real user is changed the product: we moved from a teacher tool to a student self-study tool.
