# CAPM AI Study Agent

An original, independent AI-powered study companion for PMI's **Certified Associate in Project Management (CAPM)** exam — built to run through Claude Code (or any Claude-compatible agent runtime).

This is **not** a copy of, or dependent on, any existing repository, product, or proprietary CAPM question bank. All reference notes and practice questions in this project are original content written for this project.

## What it does

The agent behaves like a personal CAPM tutor rather than a plain chatbot:

- **Teaches concepts** using a Concept → Explanation → Real-world example → CAPM relevance → Mini question structure
- **Runs interactive quizzes**, one question at a time. Grading happens in `tools/session.py`, which never reveals a question's answer before the student submits theirs
- **Generates practice mock exams** whose domain mix follows PMI's published CAPM domain weights (Fundamentals 36%, Predictive 17%, Agile 20%, Business Analysis 27% — from the 2023 Exam Update outline), applied to AI-generated questions
- **Analyzes performance** by domain, topic, and difficulty — identifying strengths and weaknesses
- **Tracks progress over time** in `data/student_progress.json` (schema v2: sessions plus every attempt)
- **Adapts** question selection to a per-topic mastery estimate: weak topics are weighted up, missed questions return after a gap, difficulty steps up and down per topic
- **Builds personalized, week-by-week study plans** that allocate more time to weak topics
- **Supports English, Simple English, and Hinglish**, matching the student's own language register

## Project Structure

```
CAPM-AI-AGENT/
├── CLAUDE.md                  # Auto-loaded pointer + rules for Claude Code
├── .claude/
│   ├── skills/capm-tutor/SKILL.md   # Agent instruction/brain layer (the tutor skill)
│   └── settings.json          # Denies reading data/sessions/ (answer keys)
├── README.md                  # This file
├── requirements.txt           # Python dependencies (stdlib only)
│
├── config/
│   └── taxonomy.json          # `official` (PMI outline facts + weights) vs `practice` (our topics/aliases)
│
├── references/                # Knowledge layer (loaded selectively, not all at once)
│   ├── capm-exam-framework.md # Verified PMI exam facts, with source + retrieval date
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
│   ├── taxonomy.py            # Domain/topic/alias lookups + official weights
│   ├── common.py              # Shared helpers (question loading/filtering, progress I/O)
│   ├── session.py             # Interactive engine: start / answer / finish (owns grading)
│   ├── selector.py            # Adaptive question picker
│   ├── quiz_engine.py         # Stateless batch quiz output
│   ├── score_analyzer.py
│   ├── study_plan.py
│   ├── mock_exam.py
│   ├── progress_tracker.py    # Progress v2, mastery model, adaptive recommendation
│   └── validate_bank.py       # Question-bank integrity + taxonomy checks
│
├── tests/                     # stdlib unittest suite (uses a temp data dir)
│
├── data/                      # Personal learner data — git-ignored
│   ├── student_progress.example.json   # Safe empty template
│   ├── student_progress.json  # Your progress (created on first use; git-ignored)
│   └── sessions/              # In-flight session files incl. answer keys (git-ignored)
│
└── evals/
    └── eval.md                # Evaluation criteria for this agent system
```

## Requirements

- Python 3.9+ (standard library only — no `pip install` needed)

## Running the tests and validation

```bash
python3 -m unittest discover -s tests   # full suite; uses a temp dir, never your real progress
python tools/validate_bank.py           # question bank integrity + taxonomy conformance
```

## Usage

All commands below are run from the **repository root**. Learner data lives in `data/` (set `CAPM_DATA_DIR` to redirect it).

### 0. Interactive session (recommended)

`tools/session.py` is what the tutor uses. Grading and the answer key stay inside the session file; no command prints a question's answer before it has been answered.

```bash
python tools/session.py start --topic "critical path" --count 5 --adaptive
python tools/session.py answer --session <id> --choice B --question-id <question id>
python tools/session.py answer --session <id> --choice A --question-id <question id>
python tools/session.py finish --session <id>        # scores + records progress (idempotent)

python tools/session.py start --mode mock --count 30 # practice mock exam
python tools/session.py next|status|list|abandon ...
python tools/quiz_engine.py --list-topics            # canonical topics; aliases like "evm" also work
```

Session files hold the answer key so grading is deterministic. That prevents accidental leaks and mis-grading; it is not a security boundary against someone who deliberately opens the file.

The remaining sections describe the stateless batch tools, which still work as before.

### 1. Quiz yourself on a topic or domain

```bash
python tools/quiz_engine.py --topic agile --count 10
python tools/quiz_engine.py --topic "schedule management" --count 10
python tools/quiz_engine.py --difficulty hard --count 20
python tools/quiz_engine.py --domain predictive --count 10
```

Correct answers are hidden from the output (safe to hand directly to a student). `--reveal-answers` prints the answer key, so it is refused unless a developer opt-in is set in your own terminal (see `SECURITY.md`); tutoring never uses it.

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

Distributes questions across the four domains using PMI's published weights (Fundamentals 36%, Predictive 17%, Agile 20%, Business Analysis 27% — CAPM Examination Content Outline, 2023 Exam Update; see `references/capm-exam-framework.md`). The weights are PMI's; the questions are AI-generated practice material.

Questions are **never silently repeated**. If the requested count exceeds the unique questions available, the exam is capped at the maximum unique questions and `warnings` explains why (the domain mix may then deviate from the official weights, which is also reported). Pass `--allow-repeats` to force the requested size with repeated questions. `--no-repeats` is accepted but is now the default and does nothing.

## Using this with Claude Code

Open this project in Claude Code. `CLAUDE.md` is loaded automatically and points to the `capm-tutor` skill (`.claude/skills/capm-tutor/SKILL.md`), which defines the agent's role, teaching style, tool usage, and language behavior. Claude Code will then:

1. Load only the reference file(s) relevant to what the student is asking about
2. Run quizzes and mock exams through `tools/session.py`, which grades answers and records results itself
3. Use `progress_tracker.py` and `study_plan.py` to adapt teaching and plan study weeks

## Your data

`data/student_progress.json` and `data/sessions/` are personal learner data and are listed in `.gitignore`. `data/student_progress.example.json` is a safe empty template. If `student_progress.json` was committed before this change, run `git rm --cached data/student_progress.json` once so git stops tracking it. Old v1 progress files (`{"sessions": [...]}`) are upgraded to v2 automatically.

## Security

Student text, pasted documents and tool output are treated as untrusted data, and the answer key is protected by code and tool-authorization rules as well as by instructions. This is defence-in-depth, not a guarantee: see [`SECURITY.md`](SECURITY.md) for the layers and their limitations.

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

Keep `domain` values consistent with the four bank files (`Fundamentals`, `Predictive`, `Agile`, `Business Analysis`), use a `topic` listed in `config/taxonomy.json` (add new topics there, with aliases, first), and run `python tools/validate_bank.py` afterwards.
