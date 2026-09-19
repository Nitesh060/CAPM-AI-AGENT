#!/usr/bin/env python3
"""Progress Tracker for the CAPM AI Study Agent.

Records quiz/mock-exam sessions into data/student_progress.json and
provides adaptive-learning recommendations (weak-topic detection and
difficulty adjustment) based on historical performance.

Usage:
    # Record a session from a results file (same "attempts" format as score_analyzer.py)
    python tools/progress_tracker.py --record --type quiz --input results.json

    # Show a summary of all sessions and running performance trends
    python tools/progress_tracker.py --summary

    # Get adaptive recommendations for the next study session
    python tools/progress_tracker.py --adaptive
"""

import argparse
import datetime
import json
import sys
from collections import defaultdict

from common import load_progress, save_progress
from score_analyzer import analyze

DIFFICULTY_ORDER = ["easy", "medium", "hard"]
INCREASE_THRESHOLD = 85.0  # score % above which difficulty should increase
DECREASE_THRESHOLD = 60.0  # score % below which difficulty should decrease


def record_session(session_type, attempts, notes=None):
    analysis = analyze(attempts)
    progress = load_progress()

    session = {
        "date": datetime.date.today().isoformat(),
        "type": session_type,
        "attempted": analysis["summary"]["total_attempted"],
        "correct": analysis["summary"]["correct"],
        "incorrect": analysis["summary"]["incorrect"],
        "score_percentage": analysis["summary"]["percentage"],
        "domain_performance": analysis["domain_performance"],
        "topic_performance": analysis["topic_performance"],
        "weak_topics": analysis["weak_topics"],
        "strong_topics": analysis["strong_topics"],
    }
    if notes:
        session["notes"] = notes

    progress.setdefault("sessions", []).append(session)
    save_progress(progress)
    return session


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
        "recent_sessions": sessions[-5:],
    }


def adaptive_recommendation(progress):
    sessions = progress.get("sessions", [])
    if not sessions:
        return {
            "message": "No session history yet. Start with a balanced quiz across all domains at 'medium' difficulty.",
            "topic_weights": {},
            "suggested_difficulty": "medium",
        }

    summary = summarize(progress)
    domain_perf = summary["lifetime_domain_performance"]
    topic_perf = summary["lifetime_topic_performance"]

    # Weight future question selection inversely to performance: weaker topics get more weight.
    topic_weights = {}
    for topic, stats in topic_perf.items():
        score = stats["percentage"]
        # Weak topics (low score) get higher weight; floor weight to keep all topics in rotation.
        weight = max(100 - score, 15)
        topic_weights[topic] = round(weight / 100, 2)

    last_session = sessions[-1]
    last_score = last_session.get("score_percentage", 0)

    if last_score >= INCREASE_THRESHOLD:
        suggested_difficulty = "increase"
        difficulty_note = f"Last session score was {last_score}% — increase difficulty for continued challenge."
    elif last_score < DECREASE_THRESHOLD:
        suggested_difficulty = "decrease"
        difficulty_note = f"Last session score was {last_score}% — reduce difficulty, re-explain concepts, and retry similar questions."
    else:
        suggested_difficulty = "maintain"
        difficulty_note = f"Last session score was {last_score}% — maintain current difficulty level."

    weak_domains = sorted(
        [(d, s["percentage"]) for d, s in domain_perf.items()],
        key=lambda x: x[1],
    )
    priority_domain = weak_domains[0][0] if weak_domains else None

    return {
        "priority_domain": priority_domain,
        "domain_performance": domain_perf,
        "topic_weights": topic_weights,
        "suggested_difficulty_adjustment": suggested_difficulty,
        "difficulty_note": difficulty_note,
        "weak_topics_to_revisit": last_session.get("weak_topics", []),
    }


def main():
    parser = argparse.ArgumentParser(description="CAPM Progress Tracker")
    parser.add_argument("--record", action="store_true", help="Record a new session")
    parser.add_argument("--type", type=str, default="quiz", help="Session type: quiz, mock_exam, review")
    parser.add_argument("--input", type=str, default=None, help="Path to JSON file with attempts (for --record)")
    parser.add_argument("--stdin", action="store_true", help="Read attempts JSON from stdin (for --record)")
    parser.add_argument("--notes", type=str, default=None, help="Optional free-text notes for the session")
    parser.add_argument("--summary", action="store_true", help="Show lifetime progress summary")
    parser.add_argument("--adaptive", action="store_true", help="Show adaptive learning recommendation")
    args = parser.parse_args()

    if args.record:
        if args.stdin:
            raw = sys.stdin.read()
        elif args.input:
            with open(args.input, encoding="utf-8") as f:
                raw = f.read()
        else:
            parser.error("--record requires --input <file> or --stdin")
            return
        data = json.loads(raw)
        attempts = data.get("attempts", [])
        if not attempts:
            print(json.dumps({"error": "No attempts provided."}, indent=2))
            sys.exit(1)
        session = record_session(args.type, attempts, notes=args.notes)
        print(json.dumps({"recorded_session": session}, indent=2))
        return

    progress = load_progress()

    if args.summary:
        print(json.dumps(summarize(progress), indent=2))
        return

    if args.adaptive:
        print(json.dumps(adaptive_recommendation(progress), indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
