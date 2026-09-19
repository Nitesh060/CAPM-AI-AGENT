# CAPM AI Study Agent

An original, independent AI-powered study companion for PMI's **Certified Associate in Project Management (CAPM)** exam — built to run through Claude Code (or any Claude-compatible agent runtime).

This is **not** a copy of, or dependent on, any existing repository, product, or proprietary CAPM question bank. All reference notes and practice questions in this project are original content written for this project.

## What it does

The agent behaves like a personal CAPM tutor rather than a plain chatbot:

- **Teaches concepts** using a Concept → Explanation → Real-world example → CAPM relevance → Mini question structure
- **Runs interactive quizzes**, one question at a time, without leaking answers early
- **Generates full mock exams** with realistic CAPM domain weighting (Predictive ~50%, Agile ~25%, Business Analysis ~25%)
- **Analyzes performance** by domain, topic, and difficulty — identifying strengths and weaknesses
- **Tracks progress over time** in `data/student_progress.json`
- **Adapts** future quizzes and difficulty based on performance history
- **Builds personalized, week-by-week study plans** that allocate more time to weak topics
- **Supports English, Simple English, and Hinglish**, matching the student's own language register

## Project Structure

```
capm-ai-agent/
├── SKILL.md                  # Agent instruction/brain layer
├── README.md                 # This file
├── requirements.txt          # Python dependencies (stdlib only)
│
├── references/                # Knowledge layer (loaded selectively, not all at once)
│   ├── capm-exam-framework.md
│   ├── project-management-fundamentals.md
│   ├── predictive-approach.md
│   ├── agile-hybrid.md
│   ├── business-analysis.md
│   └── capm-glossary.md
│
├── question_bank/             # Original, AI-generated practice questions (JSON)
│   ├── fundamentals.json
│   ├── predictive.json
│   ├── agile.json
│   └── business-analysis.json
│
├── tools/                     # Python CLI tools
│   ├── common.py              # Shared helpers (question loading, progress I/O)
│   ├── quiz_engine.py
│   ├── score_analyzer.py
│   ├── study_plan.py
│   ├── mock_exam.py
│   └── progress_tracker.py
│
├── data/
│   └── student_progress.json  # Student performance history (starts empty)
│
└── evals/
    └── eval.md                # Evaluation criteria for this agent system
```

## Requirements

- Python 3.9+ (standard library only — no `pip install` needed)

## Usage

All commands below are run from inside the `capm-ai-agent/` directory.

### 1. Quiz yourself on a topic or domain

```bash
python tools/quiz_engine.py --topic agile --count 10
python tools/quiz_engine.py --topic "schedule management" --count 10
python tools/quiz_engine.py --difficulty hard --count 20
python tools/quiz_engine.py --domain predictive --count 10
```

By default, correct answers are hidden from the output (safe to hand directly to a student). Add `--reveal-answers` for self-grading or tool-to-tool use.

### 2. Score a completed quiz

Pipe an `attempts` JSON object (one entry per question answered) into the analyzer:

```bash
python tools/score_analyzer.py --stdin <<'EOF'
{"attempts": [
  {"question_id": "AGILE-001", "domain": "Agile", "topic": "Scrum Roles", "difficulty": "easy", "correct": true},
  {"question_id": "PRED-001", "domain": "Predictive", "topic": "Schedule Management", "difficulty": "medium", "correct": false}
]}
EOF
```

Returns overall score, domain/topic/difficulty breakdowns, strong/weak topics, and revision recommendations.

### 3. Record progress and get adaptive recommendations

```bash
python tools/progress_tracker.py --record --type quiz --stdin <<'EOF'
{"attempts": [...]}
EOF

python tools/progress_tracker.py --summary
python tools/progress_tracker.py --adaptive
```

### 4. Generate a personalized study plan

```bash
python tools/study_plan.py --weeks 8 --hours-per-week 10
```

Automatically factors in weak topics/domains from `data/student_progress.json` if a history exists. Use `--ignore-history` to generate a plan from scratch.

### 5. Take a mock exam

```bash
python tools/mock_exam.py --questions 20
python tools/mock_exam.py --questions 150
```

Distributes questions across the three official CAPM domains at roughly 50/25/25 weighting. If the requested count exceeds the current question bank size, questions repeat by default (flagged in `warnings`); pass `--no-repeats` to cap the exam at unique questions only.

## Using this with Claude Code

Point Claude Code at this project and let it read `SKILL.md` — that file defines the agent's role, teaching style, tool usage, and language behavior. Claude Code will then:

1. Load only the reference file(s) relevant to what the student is asking about
2. Call `tools/*.py` via Bash to fetch quizzes, score results, and generate plans
3. Track the student's `attempts` conversationally and persist them via `progress_tracker.py`

## Important Disclaimers

- **Not affiliated with or endorsed by PMI.** "CAPM" is a certification mark of the Project Management Institute (PMI). This is independent, original study material.
- **All questions in `question_bank/` are AI-generated practice questions**, clearly labeled `"source_type": "ai_generated"` in each file's metadata. None are claimed to be official PMI exam questions.
- **No score, study plan, or mock exam result guarantees a passing result** on the official PMI CAPM exam. Use this tool as one part of a broader preparation strategy.
- Always refer to PMI's official CAPM Examination Content Outline for the authoritative, current exam specification.

## Extending the Question Bank

To add more questions, follow the schema used throughout `question_bank/*.json`:

```json
{
  "id": "CAPM-001",
  "domain": "Predictive",
  "topic": "Schedule Management",
  "difficulty": "medium",
  "type": "scenario",
  "question": "...",
  "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
  "correct_answer": "B",
  "explanation": "...",
  "why_others_are_wrong": {"A": "...", "C": "...", "D": "..."},
  "concept_tested": "...",
  "source": "original"
}
```

Keep `domain` values consistent with the four bank files (`Fundamentals`, `Predictive`, `Agile`, `Business Analysis`) so the tools' filters continue to work correctly.
