#!/usr/bin/env python3
"""Interactive session engine for the CAPM AI Study Agent.

Grading happens here, not in the chat. A session file (data/sessions/<id>.json)
holds the full questions INCLUDING the answer key, but no command prints the key
or explanation for a question until that question's answer has been submitted.

Flow:
    start   -> creates the session, prints the first question (no key)
    answer  -> grades the current question, prints feedback + the next question
    finish  -> builds attempts from the session, scores them, records progress (idempotent)

Usage:
    python tools/session.py start --topic "critical path" --count 5 --adaptive
    python tools/session.py start --mode mock --count 30
    python tools/session.py answer --session ID --choice B --question-id PRED-001
    python tools/session.py next --session ID
    python tools/session.py status --session ID
    python tools/session.py finish --session ID [--partial]
    python tools/session.py list
    python tools/session.py abandon --session ID

Note: the answer key sits in the session file on disk. That prevents accidental
leaks and mis-grading; it is not a security boundary against someone who
deliberately opens the file. Tutors must never read data/sessions/.

All arguments are treated as untrusted data: bounded, validated, never executed.
See SECURITY.md.
"""

import argparse
import datetime
import json
import random
import re
import secrets
import sys

import quiz_engine
import mock_exam
import selector
import taxonomy
from common import (
    ProgressError,
    check_query_text,
    check_question_count,
    filter_questions,
    get_sessions_dir,
    load_all_questions,
    load_progress,
    randomize_options,
    shown,
    strip_answers,
    write_json_atomic,
)
from progress_tracker import adaptive_recommendation, record_session
from score_analyzer import AttemptError, analyze, normalize_attempts

SESSION_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")
CHOICE_RE = re.compile(r"^\s*([A-Za-z])\s*[\.\)]?\s*$")
MODES = ("quiz", "mock")
QUIZ_DISCLAIMER = "AI-generated practice questions, not official PMI exam questions."
MOCK_DISCLAIMER = "This is a practice mock exam, not an official PMI exam."


class SessionError(Exception):
    """A session command could not be completed."""


def _now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# --- storage -------------------------------------------------------------------

def _path(session_id):
    if not isinstance(session_id, str) or not SESSION_ID_RE.match(session_id):
        raise SessionError(f"Invalid session id {shown(session_id)!r}.")
    return get_sessions_dir() / f"{session_id}.json"


def _load(session_id):
    path = _path(session_id)
    if not path.exists():
        raise SessionError(f"Session {session_id} not found.")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise SessionError(f"Session file {path.name} is corrupt ({e}).") from e


def _save(session):
    session["updated_at"] = _now()
    write_json_atomic(_path(session["session_id"]), session)


def _new_id():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def _public_question(session, index):
    """The question at `index` with every answer-revealing field removed."""
    q = strip_answers(session["questions"][index])
    q["question_number"] = index + 1
    q["total_questions"] = len(session["questions"])
    return q


def _require_open(session):
    if session["status"] == "finished":
        raise SessionError("Session is already finished.")
    if session["status"] == "abandoned":
        raise SessionError("Session was abandoned.")


# --- commands ------------------------------------------------------------------

def start_session(mode="quiz", count=10, topic=None, domain=None, difficulty=None,
                  adaptive=False, seed=None, shuffle_options=True, allow_repeats=False):
    if mode not in MODES:
        raise SessionError(f"mode must be one of {', '.join(MODES)}.")
    try:
        check_question_count(count)
        check_query_text("topic", topic)
        check_query_text("domain", domain)
    except ValueError as e:
        raise SessionError(str(e)) from None
    # Allowlist, not free text: a topic must be a known topic/alias or domain.
    if topic and not (taxonomy.canonical_topic(topic) or taxonomy.canonical_domain(topic)):
        raise SessionError("Unknown topic. Use a topic or domain listed by 'python tools/quiz_engine.py --list-topics'.")

    warnings = []
    if mode == "mock":
        if topic or domain or difficulty or adaptive:
            raise SessionError("Mock exams follow the official domain weights; topic/domain/difficulty/adaptive are not supported.")
        exam = mock_exam.build_mock_exam(count, seed=seed, allow_repeats=allow_repeats)
        selected = exam["questions"]
        warnings = list(exam["warnings"])
        selection = {
            "mode": "mock",
            "domain_distribution_actual": exam["domain_distribution_actual"],
            "domain_distribution_target": exam["domain_distribution_target"],
            "official_domain_weights": exam["official_domain_weights"],
            "suggested_time_minutes": exam["suggested_time_minutes"],
        }
        disclaimer = MOCK_DISCLAIMER + " " + exam["distribution_basis"]
    else:
        if domain and not taxonomy.canonical_domain(domain):
            raise SessionError(f"Unknown domain {shown(domain)!r}. Valid: {', '.join(taxonomy.practice_domains())}.")
        if adaptive:
            pool = filter_questions(load_all_questions(), topic=topic, domain=domain, difficulty=difficulty)
            if not pool:
                raise SessionError("No questions matched the given filters.")
            rng = random.Random(seed)
            selected, selection = selector.select_questions(pool, count, load_progress(), rng)
            if shuffle_options:
                selected = [randomize_options(q, rng=rng) for q in selected]
        else:
            quiz = quiz_engine.build_quiz(count, topic=topic, domain=domain, difficulty=difficulty,
                                          shuffle_options=shuffle_options, seed=seed)
            if "error" in quiz:
                raise SessionError(quiz["error"])
            selected = quiz["questions"]
            selection = {"mode": "random"}
            if "warning" in quiz:
                warnings.append(quiz["warning"])
        if len(selected) < count and not warnings:
            warnings.append(f"Only {len(selected)} matching question(s) exist; requested {count}.")
        disclaimer = QUIZ_DISCLAIMER

    if not selected:
        raise SessionError("No questions could be selected.")

    session = {
        "schema_version": 1,
        "session_id": _new_id(),
        "mode": mode,
        "status": "in_progress",
        "created_at": _now(),
        "filters": {"topic": topic, "domain": domain, "difficulty": difficulty},
        "adaptive": bool(adaptive),
        "seed": seed,
        "selection": selection,
        "warnings": warnings,
        "questions": selected,
        "answers": [],
        "recorded": False,
    }
    _save(session)

    return {
        "session_id": session["session_id"],
        "mode": mode,
        "total_questions": len(selected),
        "selection": selection,
        "warnings": warnings,
        "disclaimer": disclaimer,
        "question": _public_question(session, 0),
        "next_step": "Show the question, wait for the student's answer, then run: session.py answer --session ID --choice X --question-id QID",
    }


def next_question(session_id):
    session = _load(session_id)
    _require_open(session)
    index = len(session["answers"])
    if index >= len(session["questions"]):
        return {"session_id": session_id, "done": True, "message": "All questions answered. Run finish."}
    return {"session_id": session_id, "done": False, "question": _public_question(session, index)}


def _feedback(session, index, already_answered):
    """Feedback for the already-answered question at `index` (safe: it has been answered)."""
    q = session["questions"][index]
    a = session["answers"][index]
    total = len(session["questions"])
    answered = len(session["answers"])
    done = answered >= total
    result = {
        "session_id": session["session_id"],
        "already_answered": already_answered,
        "question_id": q["id"],
        "question_number": index + 1,
        "total_questions": total,
        "chosen": a["chosen"],
        "correct": a["correct"],
        "correct_answer": q["correct_answer"],
        "explanation": q.get("explanation"),
        "why_others_are_wrong": q.get("why_others_are_wrong", {}),
        "concept_tested": q.get("concept_tested"),
        "domain": q["domain"],
        "topic": q["topic"],
        "difficulty": q["difficulty"],
        "progress": {
            "answered": answered,
            "correct": sum(1 for x in session["answers"] if x["correct"]),
            "remaining": total - answered,
        },
        "done": done,
        "next_question": None if done else _public_question(session, answered),
    }
    if done:
        result["next_step"] = f"All questions answered. Run: session.py finish --session {session['session_id']}"
    return result


def submit_answer(session_id, choice, question_id=None):
    session = _load(session_id)
    _require_open(session)
    questions, answers = session["questions"], session["answers"]
    index = len(answers)

    match = CHOICE_RE.match(choice or "")
    if not match:
        raise SessionError(f"Invalid choice {shown(choice)!r}; use a single option letter such as B.")
    letter = match.group(1).upper()

    current_id = questions[index]["id"] if index < len(questions) else None
    if question_id:
        # Repeated call for the question that was just answered: return the stored result.
        if index > 0 and answers[-1]["question_id"] == question_id and question_id != current_id:
            return _feedback(session, index - 1, already_answered=True)
        if question_id != current_id:
            raise SessionError(f"Question mismatch: the current question is {current_id}, not {shown(question_id)}.")
    if index >= len(questions):
        raise SessionError("All questions are already answered. Run finish.")

    q = questions[index]
    if letter not in q["options"]:
        raise SessionError(f"Option {letter} does not exist for this question (valid: {', '.join(q['options'])}).")

    answers.append({
        "index": index,
        "question_id": q["id"],
        "chosen": letter,
        "correct": letter == q["correct_answer"],
        "answered_at": _now(),
    })
    _save(session)
    return _feedback(session, index, already_answered=False)


def session_status(session_id):
    session = _load(session_id)
    total = len(session["questions"])
    answered = len(session["answers"])
    return {
        "session_id": session_id,
        "mode": session["mode"],
        "status": session["status"],
        "created_at": session["created_at"],
        "total_questions": total,
        "answered": answered,
        "remaining": total - answered,
        "recorded": session.get("recorded", False),
    }


def finish_session(session_id, partial=False):
    session = _load(session_id)
    if session["status"] == "abandoned":
        raise SessionError("Session was abandoned.")
    total, answers = len(session["questions"]), session["answers"]
    if not answers:
        raise SessionError("No questions have been answered yet.")
    if len(answers) < total and not partial:
        raise SessionError(f"{total - len(answers)} question(s) unanswered. Answer them, or pass --partial to score what was answered.")

    attempts = []
    for a in answers:
        q = session["questions"][a["index"]]
        attempts.append({
            "question_id": q["id"], "domain": q["domain"], "topic": q["topic"],
            "difficulty": q["difficulty"], "correct": a["correct"],
            "chosen": a["chosen"], "answered_at": a["answered_at"],
        })

    session_type = "mock_exam" if session["mode"] == "mock" else "quiz"
    recorded = record_session(session_type, attempts, session_id=session_id)
    normalized, _ = normalize_attempts(attempts)
    analysis = analyze(normalized)

    session["status"] = "finished"
    session["recorded"] = True
    session["finished_at"] = session.get("finished_at") or _now()
    _save(session)

    missed = []
    for a in answers:
        if not a["correct"]:
            q = session["questions"][a["index"]]
            missed.append({
                "question_id": q["id"], "topic": q["topic"], "concept_tested": q.get("concept_tested"),
                "chosen": a["chosen"], "correct_answer": q["correct_answer"],
            })

    return {
        "session_id": session_id,
        "mode": session["mode"],
        "already_recorded": bool(recorded.get("already_recorded")),
        "partial": len(answers) < total,
        "unanswered": total - len(answers),
        **analysis,
        "missed_questions": missed,
        "adaptive": adaptive_recommendation(load_progress()),
        "practice_disclaimer": MOCK_DISCLAIMER if session["mode"] == "mock" else QUIZ_DISCLAIMER,
    }


def list_sessions():
    directory = get_sessions_dir()
    sessions = []
    if directory.exists():
        for path in sorted(directory.glob("*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    s = json.load(f)
                sessions.append({
                    "session_id": s["session_id"], "mode": s["mode"], "status": s["status"],
                    "created_at": s["created_at"], "answered": len(s["answers"]), "total_questions": len(s["questions"]),
                })
            except (json.JSONDecodeError, KeyError):
                continue
    return {"sessions": sessions}


def abandon_session(session_id):
    session = _load(session_id)
    if session["status"] == "finished":
        raise SessionError("Session is already finished.")
    session["status"] = "abandoned"
    _save(session)
    return {"session_id": session_id, "status": "abandoned", "recorded": False}


# --- CLI -------------------------------------------------------------------------

def _build_parser():
    parser = argparse.ArgumentParser(description="CAPM interactive session engine")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("start", help="Start a quiz or mock-exam session")
    p.add_argument("--mode", choices=MODES, default="quiz")
    p.add_argument("--count", type=int, default=10, help="Number of questions")
    p.add_argument("--topic", default=None)
    p.add_argument("--domain", default=None)
    p.add_argument("--difficulty", choices=["easy", "medium", "hard"], default=None)
    p.add_argument("--adaptive", action="store_true", help="Pick questions using the learner's history (quiz mode)")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--no-shuffle", action="store_true")
    p.add_argument("--allow-repeats", action="store_true", help="Mock only: allow repeated questions")

    p = sub.add_parser("answer", help="Submit an answer for the current question")
    p.add_argument("--session", required=True)
    p.add_argument("--choice", required=True)
    p.add_argument("--question-id", default=None, help="Recommended: guards against out-of-sync or repeated submissions")

    for name, help_text in (("next", "Show the current unanswered question"), ("status", "Show session progress"),
                            ("abandon", "Abandon a session without recording it")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--session", required=True)

    p = sub.add_parser("finish", help="Score the session and record progress")
    p.add_argument("--session", required=True)
    p.add_argument("--partial", action="store_true", help="Score only the answered questions")

    sub.add_parser("list", help="List sessions")
    return parser


def main():
    args = _build_parser().parse_args()
    try:
        if args.command == "start":
            out = start_session(args.mode, args.count, args.topic, args.domain, args.difficulty,
                                args.adaptive, args.seed, not args.no_shuffle, args.allow_repeats)
        elif args.command == "answer":
            out = submit_answer(args.session, args.choice, args.question_id)
        elif args.command == "next":
            out = next_question(args.session)
        elif args.command == "status":
            out = session_status(args.session)
        elif args.command == "finish":
            out = finish_session(args.session, args.partial)
        elif args.command == "abandon":
            out = abandon_session(args.session)
        else:
            out = list_sessions()
    except (SessionError, ProgressError, AttemptError) as e:
        print(json.dumps({"error": str(e)}, indent=2))
        sys.exit(1)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
