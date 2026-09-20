#!/usr/bin/env python3
"""Progress Tracker for the CAPM AI Study Agent (progress schema v2).

Records quiz/mock-exam sessions into data/student_progress.json and provides
adaptive-learning recommendations (weak-topic detection and difficulty
adjustment) based on the learner's history.

Progress file (v2):
    {"schema_version": 2,
     "sessions": [ {session_id, date, timestamp, type, score, per-domain/topic/difficulty stats, ...} ],
     "attempts": [ {session_id, question_id, domain, topic, difficulty, correct, chosen?, ts} ]}
v1 files ({"sessions": [...]}) are upgraded automatically on load.

Preferred way to record progress is tools/session.py (finish), which builds the
attempts from the session file. `--record` remains for backward compatibility.

Everything stored here is read back to the tutor later (--summary), so stored text is
treated as untrusted: attempt fields are strictly validated (score_analyzer) and
free-text notes are stripped of control characters and capped.

Usage:
    python tools/progress_tracker.py --record --type quiz --input results.json
    python tools/progress_tracker.py --summary
    python tools/progress_tracker.py --adaptive
"""

import argparse
import datetime
import json
import secrets
import sys
from collections import defaultdict

from common import MAX_NOTE_CHARS, ProgressError, clean_text, load_progress, read_text_limited, save_progress
from score_analyzer import AttemptError, analyze, normalize_attempts

DIFFICULTY_ORDER = ["easy", "medium", "hard"]
INCREASE_THRESHOLD = 85.0  # last-session score % above which difficulty should increase
DECREASE_THRESHOLD = 60.0  # last-session score % below which difficulty should decrease

MASTERY_DECAY = 0.8        # weight multiplier per older attempt (recency weighting)
CONFIDENCE_ATTEMPTS = 5    # attempts needed before a topic's own history is fully trusted
MASTERY_PRIOR = 0.5        # assumed mastery of a topic with no history
WEAK_MASTERY = 0.60        # estimated mastery below this => weak topic
STRONG_DOMAIN_PERCENT = 75.0
WEIGHT_FLOOR = 0.15        # every topic stays in rotation
STREAK_TO_MOVE = 2         # consecutive right/wrong answers before target difficulty moves


def _now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def record_session(session_type, attempts, notes=None, session_id=None):
    """Append a session (+ its attempts) to the progress file.

    `attempts` are validated/normalised first (see score_analyzer.normalize_attempts).
    If `session_id` is given and already recorded, nothing is written and the
    stored session is returned with already_recorded=True (idempotent).
    Returns the session dict; normalisation warnings, if any, are added under "warnings".
    """
    normalized, warnings = normalize_attempts(attempts)
    progress = load_progress()

    if session_id:
        for existing in progress["sessions"]:
            if existing.get("session_id") == session_id:
                return dict(existing, already_recorded=True)

    now = _now()
    sid = session_id or f"legacy-{now.replace(':', '').replace('-', '')[:15]}-{secrets.token_hex(2)}"
    analysis = analyze(normalized)

    session = {
        "session_id": sid,
        "date": datetime.date.today().isoformat(),
        "timestamp": now,
        "type": session_type,
        "attempted": analysis["summary"]["total_attempted"],
        "correct": analysis["summary"]["correct"],
        "incorrect": analysis["summary"]["incorrect"],
        "score_percentage": analysis["summary"]["percentage"],
        "domain_performance": analysis["domain_performance"],
        "topic_performance": analysis["topic_performance"],
        "difficulty_performance": analysis["difficulty_performance"],
        "weak_topics": analysis["weak_topics"],
        "strong_topics": analysis["strong_topics"],
    }
    if notes:
        session["notes"] = clean_text(notes, MAX_NOTE_CHARS)

    progress["sessions"].append(session)
    for a in normalized:
        record = {"session_id": sid, **a}
        record["ts"] = record.pop("answered_at", now)
        progress["attempts"].append(record)
    save_progress(progress)

    return dict(session, warnings=warnings) if warnings else session


def _agent_view(session):
    """A session record as shown to the tutor: stored free-text notes are never surfaced."""
    return {k: v for k, v in session.items() if k != "notes"}


def summarize(progress):
    sessions = progress.get("sessions", [])
    if not sessions:
        return {"message": "No sessions recorded yet.", "sessions": []}

    domain_totals = defaultdict(lambda: {"attempted": 0, "correct": 0})
    topic_totals = defaultdict(lambda: {"attempted": 0, "correct": 0})

    for s in sessions:
        for domain, stats in s.get("domain_performance", {}).items():
            domain_totals[domain]["attempted"] += stats["attempted"]
            domain_totals[domain]["correct"] += stats["correct"]
        for topic, stats in s.get("topic_performance", {}).items():
            topic_totals[topic]["attempted"] += stats["attempted"]
            topic_totals[topic]["correct"] += stats["correct"]

    def pct(c, a):
        return round((c / a) * 100, 1) if a else 0.0

    lifetime_domain = {
        d: {**v, "percentage": pct(v["correct"], v["attempted"])} for d, v in domain_totals.items()
    }
    lifetime_topic = {
        t: {**v, "percentage": pct(v["correct"], v["attempted"])} for t, v in topic_totals.items()
    }

    total_attempted = sum(s["attempted"] for s in sessions)
    total_correct = sum(s["correct"] for s in sessions)

    return {
        "total_sessions": len(sessions),
        "lifetime_attempted": total_attempted,
        "lifetime_correct": total_correct,
        "lifetime_percentage": pct(total_correct, total_attempted),
        "lifetime_domain_performance": lifetime_domain,
        "lifetime_topic_performance": lifetime_topic,
        "recent_sessions": [_agent_view(s) for s in sessions[-5:]],
    }


# --- mastery model -------------------------------------------------------------

def outcome_events(progress):
    """Chronological (topic, difficulty, correct, question_id) events.

    v2 attempts are used as-is. Sessions that predate attempt logging (v1) are
    expanded from their per-topic aggregates (order within such a session is
    unknown, so misses are placed first) and put before all logged attempts.
    """
    attempts = progress.get("attempts", [])
    logged = {a.get("session_id") for a in attempts}
    events = []
    for s in progress.get("sessions", []):
        if s.get("session_id") in logged:
            continue
        for topic, st in s.get("topic_performance", {}).items():
            events += [(topic, None, False, None)] * (st["attempted"] - st["correct"])
            events += [(topic, None, True, None)] * st["correct"]
    for a in attempts:
        events.append((a["topic"], a.get("difficulty"), bool(a["correct"]), a.get("question_id")))
    return events


def topic_mastery(progress):
    """Per-topic recency-weighted accuracy with a confidence shrink toward the prior.

    estimate = confidence * recency_weighted_accuracy + (1 - confidence) * 0.5
    """
    by_topic = defaultdict(list)
    for topic, _, correct, _ in outcome_events(progress):
        by_topic[topic].append(correct)

    result = {}
    for topic, outcomes in by_topic.items():
        n = len(outcomes)
        weights = [MASTERY_DECAY ** (n - 1 - i) for i in range(n)]
        mastery = sum(w for w, c in zip(weights, outcomes) if c) / sum(weights)
        confidence = min(1.0, n / CONFIDENCE_ATTEMPTS)
        estimate = confidence * mastery + (1 - confidence) * MASTERY_PRIOR
        result[topic] = {
            "attempted": n,
            "correct": sum(outcomes),
            "mastery": round(mastery, 3),
            "confidence": round(confidence, 2),
            "estimate": round(estimate, 3),
        }
    return result


def topic_target_difficulty(progress):
    """Per-topic difficulty target: a staircase that starts at 'medium', moves up
    after STREAK_TO_MOVE correct answers in a row and down after as many misses.
    """
    level = {}
    streak = {}
    for topic, _, correct, _ in outcome_events(progress):
        lv = level.get(topic, 1)
        right, wrong = streak.get(topic, (0, 0))
        if correct:
            right, wrong = right + 1, 0
            if right >= STREAK_TO_MOVE:
                lv, right = min(lv + 1, len(DIFFICULTY_ORDER) - 1), 0
        else:
            right, wrong = 0, wrong + 1
            if wrong >= STREAK_TO_MOVE:
                lv, wrong = max(lv - 1, 0), 0
        level[topic], streak[topic] = lv, (right, wrong)
    return {t: DIFFICULTY_ORDER[lv] for t, lv in level.items()}


def adaptive_recommendation(progress):
    sessions = progress.get("sessions", [])
    if not sessions:
        return {
            "message": "No session history yet. Start with a balanced quiz across all domains at 'medium' difficulty.",
            "priority_domain": None,
            "domain_performance": {},
            "topic_weights": {},
            "topic_mastery": {},
            "topic_target_difficulty": {},
            "suggested_difficulty": "medium",
            "suggested_difficulty_adjustment": "maintain",
            "weak_topics_to_revisit": [],
        }

    summary = summarize(progress)
    domain_perf = summary["lifetime_domain_performance"]
    mastery = topic_mastery(progress)

    # Weaker topics get more weight; the floor keeps every topic in rotation.
    topic_weights = {
        t: round(max(1 - m["estimate"], WEIGHT_FLOOR), 2) for t, m in mastery.items()
    }
    weak_topics = [
        t for t, m in sorted(mastery.items(), key=lambda kv: kv[1]["estimate"]) if m["estimate"] < WEAK_MASTERY
    ]

    last_score = sessions[-1].get("score_percentage", 0)
    if last_score >= INCREASE_THRESHOLD:
        adjustment, suggested = "increase", "hard"
        note = f"Last session score was {last_score}% — increase difficulty for continued challenge."
    elif last_score < DECREASE_THRESHOLD:
        adjustment, suggested = "decrease", "easy"
        note = f"Last session score was {last_score}% — reduce difficulty, re-explain concepts, and retry similar questions."
    else:
        adjustment, suggested = "maintain", "medium"
        note = f"Last session score was {last_score}% — maintain current difficulty level."

    weakest = sorted(((d, s["percentage"]) for d, s in domain_perf.items()), key=lambda x: x[1])
    priority_domain = weakest[0][0] if weakest and weakest[0][1] < STRONG_DOMAIN_PERCENT else None

    return {
        "priority_domain": priority_domain,
        "domain_performance": domain_perf,
        "topic_weights": topic_weights,
        "topic_mastery": mastery,
        "topic_target_difficulty": topic_target_difficulty(progress),
        "suggested_difficulty": suggested,
        "suggested_difficulty_adjustment": adjustment,
        "difficulty_note": note,
        "weak_topics_to_revisit": weak_topics,
    }


def _fail(message):
    print(json.dumps({"error": message}, indent=2))
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="CAPM Progress Tracker")
    parser.add_argument("--record", action="store_true", help="Record a new session (legacy; prefer tools/session.py finish)")
    parser.add_argument("--type", type=str, default="quiz", help="Session type: quiz, mock_exam, review")
    parser.add_argument("--input", type=str, default=None, help="Path to JSON file with attempts (for --record)")
    parser.add_argument("--stdin", action="store_true", help="Read attempts JSON from stdin (for --record)")
    parser.add_argument("--notes", type=str, default=None, help="Optional free-text notes for the session")
    parser.add_argument("--summary", action="store_true", help="Show lifetime progress summary")
    parser.add_argument("--adaptive", action="store_true", help="Show adaptive learning recommendation")
    args = parser.parse_args()

    try:
        if args.record:
            if args.stdin:
                raw = read_text_limited(sys.stdin)
            elif args.input:
                raw = read_text_limited(args.input)
            else:
                parser.error("--record requires --input <file> or --stdin")
                return
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                _fail(f"Input is not valid JSON: {e}")
            except RecursionError:
                _fail("Input is nested too deeply.")
            if not isinstance(data, dict) or not data.get("attempts"):
                _fail("No attempts provided.")
            session = record_session(args.type, data["attempts"], notes=args.notes)
            print(json.dumps({
                "recorded_session": _agent_view(session),
                "note": "Legacy path: prefer 'python tools/session.py' so attempts are graded and recorded automatically.",
            }, indent=2))
            return

        progress = load_progress()

        if args.summary:
            print(json.dumps(summarize(progress), indent=2))
            return

        if args.adaptive:
            print(json.dumps(adaptive_recommendation(progress), indent=2))
            return
    except (ValueError, ProgressError) as e:  # ValueError covers AttemptError and unreadable/oversized input
        _fail(str(e))

    parser.print_help()


if __name__ == "__main__":
    main()
