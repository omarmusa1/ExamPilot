# UML Diagrams

Diagrams use Mermaid (rendered automatically by GitHub).

## Use case diagram

```mermaid
flowchart LR
    S([Student])
    AI([Claude API])
    subgraph ExamAI
        UC1(Register / Log in)
        UC2(Upload course or paste text)
        UC3(Generate quiz)
        UC4(Edit or delete questions)
        UC5(Take exam)
        UC6(View graded result and explanations)
        UC7(Retry missed questions)
        UC8(View dashboard and progress)
    end
    S --- UC1
    S --- UC2
    S --- UC4
    S --- UC5
    S --- UC6
    S --- UC7
    S --- UC8
    UC2 --> UC3
    UC3 --- AI
```

## Class / data model diagram

```mermaid
classDiagram
    class User {
        +int id
        +string name
        +string email
        +string password_hash
    }
    class Quiz {
        +int id
        +string title
        +string source_text
        +string generated_by
    }
    class Question {
        +int id
        +int position
        +string text
        +string option_a
        +string option_b
        +string option_c
        +string option_d
        +char correct
        +string explanation
    }
    class Attempt {
        +int id
        +int score
        +int total
        +string mode  // full | missed
        +datetime created_at
    }
    class Answer {
        +int id
        +char chosen
        +bool is_correct
    }
    User "1" --> "*" Quiz : owns
    Quiz "1" *-- "*" Question
    User "1" --> "*" Attempt : makes
    Quiz "1" --> "*" Attempt
    Attempt "1" *-- "*" Answer
    Question "1" --> "*" Answer
```

## Sequence diagram: generate a quiz

```mermaid
sequenceDiagram
    actor Student
    participant Web as Flask app
    participant Gen as ai.py
    participant LLM as Claude API
    participant DB as SQLite
    Student->>Web: POST /quizzes/new (file or text, options)
    Web->>Web: extract text (txt / md / pdf)
    Web->>Gen: generate_questions(text, n, difficulty, language)
    alt API key configured
        Gen->>LLM: prompt (JSON-only output)
        LLM-->>Gen: JSON questions
        Gen->>Gen: validate and clean
    else no key or API error
        Gen->>Gen: demo rule-based generator
    end
    Gen-->>Web: questions, engine
    Web->>DB: insert quiz + questions
    Web-->>Student: redirect to quiz page
```

## Sequence diagram: take an exam and retry missed questions

```mermaid
sequenceDiagram
    actor Student
    participant Web as Flask app
    participant DB as SQLite
    Student->>Web: GET /quizzes/ID/take
    Web->>DB: load questions
    Web-->>Student: exam form
    Student->>Web: POST answers
    Web->>Web: grade (chosen == correct)
    Web->>DB: insert attempt + answers
    Web-->>Student: result page with explanations
    Student->>Web: GET /quizzes/ID/take?mode=missed
    Web->>DB: wrong answers of latest attempt
    Web-->>Student: exam with only missed questions
```

## Architecture

```mermaid
flowchart TB
    Browser[Browser: HTML + CSS] --> Flask[Flask app.py]
    Flask --> AI[ai.py]
    Flask --> DB[(SQLite db.py)]
    AI -->|optional| Claude[Anthropic API]
    AI --> Demo[Demo generator]
```
