#!/usr/bin/env python3
"""Study Plan Generator for the CAPM AI Study Agent.

Generates a personalized week-by-week study plan. If prior progress data
exists (data/student_progress.json), weak topics identified there receive
additional allocated study/practice time.

Usage:
    python tools/study_plan.py --weeks 8 --hours-per-week 10
    python tools/study_plan.py --weeks 4 --hours-per-week 6
"""

import argparse
import json

from common import load_progress
from progress_tracker import adaptive_recommendation

# Curated curriculum topics per domain, roughly matching CAPM exam weighting.
CURRICULUM = {
    "Predictive": [
        "Project Life Cycle & Process Groups",
        "Integration Management & Change Control",
        "Scope Management & WBS",
        "Schedule Management & Critical Path Method",
        "Cost Management & Earned Value Management (EVM)",
        "Quality Management (QA vs QC)",
        "Risk Management & Response Strategies",
        "Procurement Management & Contract Types",
        "Resource & Communications Management",
    ],
    "Agile": [
        "Agile Manifesto & 12 Principles",
        "Scrum Roles, Events, and Artifacts",
        "Kanban & Lean Principles",
        "Agile Estimation (Story Points, Planning Poker, Velocity)",
        "Servant Leadership & Team Dynamics",
        "Hybrid Approaches",
    ],
    "Business Analysis": [
        "Needs Assessment & Business Case",
        "Requirements Elicitation & Traceability",
        "Financial Analysis (NPV, IRR, ROI, Payback Period)",
        "Organizational Strategy Alignment (Portfolio/Program/Project)",
        "Change Management (ADKAR) & Benefits Realization",
        "Stakeholder Analysis & Engagement",
    ],
}

DOMAIN_WEEK_WEIGHTS = {"Predictive": 0.50, "Agile": 0.25, "Business Analysis": 0.25}


def _allocate_weeks(total_weeks):
    """Reserve the final weeks for revision + mock exam; distribute the rest
    across domains proportional to exam weighting.
    """
    if total_weeks <= 2:
        return {"content_weeks": max(total_weeks - 1, 1), "revision_weeks": 0, "exam_weeks": 1 if total_weeks > 1 else 0}
    if total_weeks <= 4:
        return {"content_weeks": total_weeks - 2, "revision_weeks": 1, "exam_weeks": 1}
    return {"content_weeks": total_weeks - 3, "revision_weeks": 1, "exam_weeks": 2}


def _chunk_evenly(items, n_chunks):
    """Split items into exactly n_chunks lists (some may be empty if
    n_chunks > len(items)), as evenly sized as possible.
    """
    n_items = len(items)
    if n_chunks <= 0:
        return []
    base, remainder = divmod(n_items, n_chunks)
    chunks = []
    idx = 0
    for w in range(n_chunks):
        size = base + (1 if w < remainder else 0)
        chunks.append(items[idx: idx + size])
        idx += size
    return chunks


def generate_plan(weeks, hours_per_week, weak_topics=None, priority_domain=None):
    weak_topics = weak_topics or []
    allocation = _allocate_weeks(weeks)
    content_weeks = allocation["content_weeks"]

    # Order domains so a weak/priority domain is covered first, then flatten
    # all (domain, topic) pairs into a single ordered list so the requested
    # content_weeks count is always respected exactly, even when it's smaller
    # than the number of domains.
    domains = list(DOMAIN_WEEK_WEIGHTS.keys())
    if priority_domain and priority_domain in domains:
        domains = [priority_domain] + [d for d in domains if d != priority_domain]

    flat_items = [(domain, topic) for domain in domains for topic in CURRICULUM[domain]]

    if content_weeks >= len(flat_items):
        # More weeks than topics: one topic per week, plus buffer weeks at the end.
        topic_chunks = [[item] for item in flat_items]
        topic_chunks += [[] for _ in range(content_weeks - len(flat_items))]
    else:
        topic_chunks = _chunk_evenly(flat_items, content_weeks)

    plan = []
    week_num = 1

    for chunk in topic_chunks:
        if chunk:
            week_domains = sorted(set(d for d, _ in chunk), key=domains.index)
            domain_focus = " / ".join(week_domains)
            week_topics = [t for _, t in chunk]
        else:
            domain_focus = "Buffer / Extra Practice"
            week_topics = weak_topics if weak_topics else ["Extra practice on any topic; catch up as needed"]

        extra_focus = [t for t in weak_topics if any(t.lower() in wt.lower() or wt.lower() in t.lower() for wt in week_topics)]

        plan.append({
            "week": week_num,
            "domain_focus": domain_focus,
            "topics": week_topics,
            "learning_objectives": [f"Understand and apply: {t}" for t in week_topics],
            "practice_questions": f"~{max(hours_per_week, 4) * 2} practice questions (python tools/quiz_engine.py --domain \"{week_domains[0] if chunk else 'all'}\" --count {max(hours_per_week, 4) * 2})",
            "revision": "Review glossary terms and reference notes for this week's topics" + (
                f"; EXTRA revision recommended for weak topic(s): {', '.join(extra_focus)}" if extra_focus else ""
            ),
            "mock_exam": None,
            "hours_allocated": hours_per_week,
        })
        week_num += 1

    for _ in range(allocation["revision_weeks"]):
        plan.append({
            "week": week_num,
            "domain_focus": "All Domains - Revision",
            "topics": weak_topics if weak_topics else ["Full review of all domains"],
            "learning_objectives": ["Reinforce weak topics identified from quiz/mock exam performance"],
            "practice_questions": f"python tools/quiz_engine.py --count {max(hours_per_week, 4) * 3} (mixed, weighted toward weak topics)",
            "revision": "Focused review of all flagged weak topics: " + (", ".join(weak_topics) if weak_topics else "general review"),
            "mock_exam": None,
            "hours_allocated": hours_per_week,
        })
        week_num += 1

    for i in range(allocation["exam_weeks"]):
        plan.append({
            "week": week_num,
            "domain_focus": "Mock Exam & Final Review",
            "topics": ["Full-length mock exam", "Targeted revision based on mock exam results"],
            "learning_objectives": ["Simulate exam conditions", "Identify remaining gaps before the real exam"],
            "practice_questions": None,
            "revision": "Review all incorrect answers from mock exam with explanations",
            "mock_exam": "python tools/mock_exam.py --questions 150" if i == allocation["exam_weeks"] - 1 else "python tools/mock_exam.py --questions 60",
            "hours_allocated": hours_per_week,
        })
        week_num += 1

    return {
        "total_weeks": weeks,
        "hours_per_week": hours_per_week,
        "total_study_hours": weeks * hours_per_week,
        "weak_topics_considered": weak_topics,
        "priority_domain": priority_domain,
        "plan": plan,
        "disclaimer": (
            "This study plan is a personalized guide based on available practice data. "
            "Completing it does not guarantee a passing score on the official PMI CAPM exam. "
            "Actual study needs vary by individual background and experience."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description="CAPM Study Plan Generator")
    parser.add_argument("--weeks", type=int, required=True, help="Number of weeks to plan for")
    parser.add_argument("--hours-per-week", type=int, required=True, help="Study hours available per week")
    parser.add_argument("--ignore-history", action="store_true", help="Ignore prior progress data even if present")
    args = parser.parse_args()

    weak_topics = []
    priority_domain = None

    if not args.ignore_history:
        progress = load_progress()
        if progress.get("sessions"):
            rec = adaptive_recommendation(progress)
            weak_topics = rec.get("weak_topics_to_revisit", [])
            priority_domain = rec.get("priority_domain")

    plan = generate_plan(args.weeks, args.hours_per_week, weak_topics=weak_topics, priority_domain=priority_domain)
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
