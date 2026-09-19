# Evaluation Suite — CAPM AI Study Agent

This document defines how to evaluate whether the agent (guided by `SKILL.md`) and its supporting tools are behaving correctly. It covers both **tool-level correctness** (deterministic, scriptable) and **agent-behavior quality** (judged against rubrics).

---

## 1. Tool-Level Tests (Deterministic)

These can be run directly and checked against expected outcomes. Run from `capm-ai-agent/`.

### 1.1 Quiz Engine

| Test | Command | Expected |
|---|---|---|
| Domain filter | `python tools/quiz_engine.py --domain agile --count 5` | `quiz_size` ≤ 5, all questions have `"domain": "Agile"` |
| Topic filter | `python tools/quiz_engine.py --topic "schedule management" --count 5` | All returned questions' `topic` contains "Schedule Management" |
| Difficulty filter | `python tools/quiz_engine.py --difficulty hard --count 20` | All returned questions have `"difficulty": "hard"` |
| No match | `python tools/quiz_engine.py --topic "xyz-nonexistent" --count 5` | Returns `{"error": ...}`, exits non-zero |
| Answers hidden by default | `python tools/quiz_engine.py --count 3` | No question object contains `correct_answer` or `explanation` keys |
| Answers revealed on request | `python tools/quiz_engine.py --count 3 --reveal-answers` | Every question contains `correct_answer` and `explanation` |
| Option randomization integrity | `python tools/quiz_engine.py --count 5 --reveal-answers --seed 1` (repeat with same seed) | Same seed → identical output (reproducibility); `correct_answer` always points to the option matching the original correct text |

### 1.2 Mock Exam

| Test | Command | Expected |
|---|---|---|
| Domain weighting | `python tools/mock_exam.py --questions 20 --seed 1` | Distribution ≈ 50% Predictive / 25% Agile / 25% Business Analysis (±1 due to rounding) |
| Large exam with limited bank | `python tools/mock_exam.py --questions 150` | Completes without error; `warnings` non-empty explaining repeats; `actual_questions == 150` |
| No-repeats mode | `python tools/mock_exam.py --questions 150 --no-repeats` | `actual_questions` capped at total unique questions available; warnings explain shortfall |
| Disclaimer present | any mock exam run | Output JSON includes a `disclaimer` field stating it is not an official PMI exam |

### 1.3 Score Analyzer

| Test | Input | Expected |
|---|---|---|
| Basic scoring | 6 attempts, 3 correct | `summary.percentage == 50.0` |
| Weak topic detection | A topic with 0% correct | Appears in `weak_topics` and `recommended_revision` |
| Strong topic detection | A topic with 100% correct (≥ threshold) | Appears in `strong_topics` |
| Disclaimer present | any run | Output includes a disclaimer that the score doesn't guarantee passing |

### 1.4 Progress Tracker

| Test | Command | Expected |
|---|---|---|
| Record session | `--record --type quiz --stdin` with valid attempts | Appends a session to `data/student_progress.json` with today's date |
| Empty history summary | `--summary` on fresh `{"sessions": []}` | Returns `{"message": "No sessions recorded yet.", ...}` |
| Adaptive with no history | `--adaptive` on fresh data | Returns default balanced recommendation, `suggested_difficulty: "medium"` |
| Adaptive after weak session | `--adaptive` after recording a session with one very weak domain | `priority_domain` equals the weakest-performing domain; `suggested_difficulty_adjustment` reflects last session's score band |

### 1.5 Study Plan

| Test | Command | Expected |
|---|---|---|
| Week count integrity | `--weeks 2 --hours-per-week 5 --ignore-history` | `len(plan) == 2` (regression test — a prior bug caused extra weeks to be generated) |
| Week count integrity (larger) | `--weeks 8 --hours-per-week 10 --ignore-history` | `len(plan) == 8` |
| Domain coverage | any run with `--ignore-history` | All three domains (Predictive, Agile, Business Analysis) appear across `domain_focus` fields |
| Weak topic boost | run after recording a session with a clearly weak domain | `priority_domain` matches the weak domain; that domain receives proportionally more weeks than a balanced default |
| Disclaimer present | any run | Output includes a disclaimer that the plan doesn't guarantee passing |

**Regression note:** An earlier version of `study_plan.py` allocated a minimum of one week per domain regardless of `content_weeks`, causing `--weeks 2` to produce 4 total weeks instead of 2. Fixed by flattening all (domain, topic) pairs into a single ordered list and chunking it into exactly `content_weeks` groups. Any future change to the week-allocation logic should re-run the "Week count integrity" tests above before merging.

---

## 2. Question Bank Integrity Checks

Run against all files in `question_bank/*.json`:

- [ ] Every question has all required schema fields (`id`, `domain`, `topic`, `difficulty`, `type`, `question`, `options`, `correct_answer`, `explanation`, `why_others_are_wrong`, `concept_tested`, `source`)
- [ ] `correct_answer` is one of the keys in `options` (A/B/C/D)
- [ ] `why_others_are_wrong` has an entry for every option key except `correct_answer`
- [ ] `id` values are unique across the entire question bank
- [ ] Every file's `metadata.source_type` is `"ai_generated"` (or another explicitly-labeled value) — never silently implies official PMI sourcing
- [ ] `difficulty` is one of `easy`, `medium`, `hard`
- [ ] `domain` matches one of the four canonical domains used by `tools/common.py`'s `DOMAIN_FILES`

Quick check script:
```bash
python3 -c "
import json, glob
ids = set()
for f in glob.glob('question_bank/*.json'):
    data = json.load(open(f))
    for q in data['questions']:
        assert q['id'] not in ids, f'Duplicate id: {q[\"id\"]}'
        ids.add(q['id'])
        assert q['correct_answer'] in q['options']
        for k in q['options']:
            if k != q['correct_answer']:
                assert k in q['why_others_are_wrong'], f'{q[\"id\"]} missing wrong-answer explanation for {k}'
print(f'OK: {len(ids)} unique questions validated across', len(glob.glob('question_bank/*.json')), 'files')
"
```

---

## 3. Agent Behavior Rubric (Qualitative)

Evaluate transcripts of the agent (following `SKILL.md`) against these criteria. Score each 1–5.

### 3.1 Teaching Quality
- [ ] Follows Concept → Explanation → Real-world example → CAPM relevance → Mini question structure when teaching a new concept
- [ ] Explanation avoids unexplained jargon on first use
- [ ] Real-world example is concrete and relatable, not abstract
- [ ] Mini question actually checks understanding of what was just taught

### 3.2 Quiz Mode Integrity
- [ ] Never reveals `correct_answer` or `explanation` before the student responds
- [ ] Presents exactly one question at a time
- [ ] Gives explanation + why-others-are-wrong + concept tested immediately after each answer
- [ ] Automatically advances to the next question without requiring the student to ask
- [ ] At the end of a batch, provides a score summary and calls `score_analyzer.py` / `progress_tracker.py`

### 3.3 Adaptive Behavior
- [ ] Checks `progress_tracker.py --adaptive` before building a new quiz/plan for a returning student
- [ ] Weak topics/domains visibly receive more focus in the next session or study plan
- [ ] Difficulty is adjusted per the adaptive recommendation (increased after strong performance, decreased with re-teaching after weak performance)

### 3.4 Language Adaptation
- [ ] Responds in Hinglish when the student writes in Hinglish, without being asked to switch explicitly
- [ ] Keeps CAPM technical terms in English even within Hinglish responses
- [ ] Simplifies language further when asked for "simple English" / beginner explanations

### 3.5 Honesty & Disclaimers
- [ ] Never claims an AI-generated question is an official PMI exam question
- [ ] Never claims a score or study plan guarantees passing/failing the real exam
- [ ] Clearly labels mock exams as practice, not official PMI simulations
- [ ] If asked to verify an externally-provided question as "official," declines to certify authenticity

### 3.6 Knowledge Loading Discipline
- [ ] Loads only the reference file(s) relevant to the current topic, not the entire `references/` directory, for a single-topic question

---

## 4. How to Run a Full Eval Pass

1. Run all commands in Section 1 and confirm outputs match expectations.
2. Run the integrity check script in Section 2.
3. Conduct (or review transcripts of) at least 3 representative agent sessions:
   - A "teach me a new concept" session
   - A "quiz me on X" session (10+ questions, mixed correct/incorrect answers)
   - A "build me a study plan" session after some quiz history exists
4. Score each session against the Section 3 rubric.
5. Log any failures with enough detail (command, input, actual vs. expected output) to reproduce and fix.
