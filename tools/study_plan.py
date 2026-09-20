#!/usr/bin/env python3
"""Study Plan Generator for the CAPM AI Study Agent.

Generates a personalized week-by-week study plan. If prior progress data
exists (data/student_progress.json), weak topics identified there receive
additional allocated study/practice time.

Domains and their order come from config/taxonomy.json (Fundamentals first,
then Predictive, Agile, Business Analysis). A priority (weakest) domain is
moved to the front. Note: the priority domain currently changes ordering only;
it does not yet receive extra weeks.

Usage:
    python tools/study_plan.py --weeks 8 --hours-per-week 10
    python tools/study_plan.py --weeks 4 --hours-per-week 6
"""

import argparse
import json
import sys

import taxonomy
from common import ProgressError, load_domain_questions, load_progress
from progress_tracker import adaptive_recommendation

# Curated curriculum topics per domain (our own study organisation, not PMI's).
CURRICULUM = {
    "Fundamentals": [
        "Projects, Operations & Project Life Cycles",
        "Process Groups & Progressive Elaboration",
        "Organizational Structures & Project Roles",
        "Project Charter & Initiation",
        "Triple Constraint & Work Breakdown Structure",
        "Stakeholder Management Basics",
    ],
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

# Which canonical bank topics each curriculum item covers (used to match weak topics).
CURRICULUM_TOPIC_MAP = {
    "Projects, Operations & Project Life Cycles": ["Project vs Operations", "Project Life Cycle"],
    "Process Groups & Progressive Elaboration": ["Process Groups", "Progressive Elaboration", "Rolling Wave Planning"],
    "Organizational Structures & Project Roles": ["Organizational Structures", "PMI Talent Triangle"],
    "Project Charter & Initiation": ["Project Charter"],
    "Triple Constraint & Work Breakdown Structure": ["Triple Constraint", "Work Breakdown Structure"],
    "Stakeholder Management Basics": ["Stakeholder Management"],
    "Project Life Cycle & Process Groups": ["Project Life Cycle", "Process Groups"],
    "Integration Management & Change Control": ["Integration Management"],
    "Scope Management & WBS": ["Work Breakdown Structure"],
    "Schedule Management & Critical Path Method": ["Schedule Management", "Schedule Compression"],
    "Cost Management & Earned Value Management (EVM)": ["Cost Management (EVM)", "Cost Estimating"],
    "Quality Management (QA vs QC)": ["Quality Management"],
    "Risk Management & Response Strategies": ["Risk Management"],
    "Procurement Management & Contract Types": ["Procurement Management"],
    "Resource & Communications Management": [],
    "Agile Manifesto & 12 Principles": ["Agile Principles", "Adaptive Life Cycle"],
    "Scrum Roles, Events, and Artifacts": ["Scrum Roles", "Scrum Ceremonies", "Definition of Done", "Backlog Refinement"],
    "Kanban & Lean Principles": ["Kanban"],
    "Agile Estimation (Story Points, Planning Poker, Velocity)": ["Estimation", "Velocity", "User Stories"],
    "Servant Leadership & Team Dynamics": ["Servant Leadership"],
    "Hybrid Approaches": ["Hybrid Approaches"],
    "Needs Assessment & Business Case": ["Business Case"],
    "Requirements Elicitation & Traceability": ["Requirements Elicitation", "Requirements Types", "Requirements Traceability"],
    "Financial Analysis (NPV, IRR, ROI, Payback Period)": ["Financial Analysis"],
    "Organizational Strategy Alignment (Portfolio/Program/Project)": ["Organizational Strategy"],
    "Change Management (ADKAR) & Benefits Realization": ["Change Management", "Benefits Realization", "Value Delivery"],
    "Stakeholder Analysis & Engagement": ["Stakeholder Engagement"],
}

DOMAIN_WEEK_WEIGHTS = taxonomy.official_weights()


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


def _weak_topics_for(week_topics, weak_topics):
    """Weak canonical topics covered by the given curriculum items."""
    covered = set()
    for label in week_topics:
        covered.update(CURRICULUM_TOPIC_MAP.get(label, []))
    return [t for t in weak_topics if t in covered]


def _practice_count(domain, hours_per_week):
    """Aim for ~2 questions per study hour, capped at what the bank can supply."""
    wanted = max(hours_per_week, 4) * 2
    available = len(load_domain_questions(domain)) if domain else 0
    return min(wanted, available) if available else wanted


def generate_plan(weeks, hours_per_week, weak_topics=None, priority_domain=None):
    if weeks < 1:
        raise ValueError("weeks must be at least 1")
    if hours_per_week < 1:
        raise ValueError("hours_per_week must be at least 1")

    weak_topics = weak_topics or []
    allocation = _allocate_weeks(weeks)
    content_weeks = allocation["content_weeks"]

    # Order domains so a weak/priority domain is covered first, then flatten
    # all (domain, topic) pairs into a single ordered list so the requested
    # content_weeks count is always respected exactly.
    domains = taxonomy.practice_domains()
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
            extra_focus = _weak_topics_for(week_topics, weak_topics)
            count = _practice_count(week_domains[0], hours_per_week)
            practice = f"~{count} practice questions (python tools/quiz_engine.py --domain \"{week_domains[0]}\" --count {count})"
        else:
            domain_focus = "Buffer / Extra Practice"
            week_topics = weak_topics if weak_topics else ["Extra practice on any topic; catch up as needed"]
            extra_focus = []
            count = max(hours_per_week, 4) * 2
            practice = f"~{count} practice questions (python tools/session.py start --count {count} --adaptive)"

        plan.append({
            "week": week_num,
            "domain_focus": domain_focus,
            "topics": week_topics,
            "learning_objectives": [f"Understand and apply: {t}" for t in week_topics],
            "practice_questions": practice,
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
            "practice_questions": f"python tools/session.py start --count {max(hours_per_week, 4) * 3} --adaptive (mixed, weighted toward weak topics)",
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
            "mock_exam": "python tools/session.py start --mode mock --count 150" if i == allocation["exam_weeks"] - 1 else "python tools/session.py start --mode mock --count 60",
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
        "notes": [
            "Mock exams return at most the number of unique questions in the bank (with a warning); "
            "the bank is still small, so a 150-question mock is not yet possible without repeats.",
        ],
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

    if args.weeks < 1 or args.hours_per_week < 1:
        print(json.dumps({"error": "--weeks and --hours-per-week must both be at least 1"}, indent=2))
        sys.exit(1)

    weak_topics = []
    priority_domain = None

    if not args.ignore_history:
        try:
            progress = load_progress()
        except ProgressError as e:
            print(json.dumps({"error": str(e)}, indent=2))
            sys.exit(1)
        if progress.get("sessions"):
            rec = adaptive_recommendation(progress)
            weak_topics = rec.get("weak_topics_to_revisit", [])
            priority_domain = rec.get("priority_domain")

    plan = generate_plan(args.weeks, args.hours_per_week, weak_topics=weak_topics, priority_domain=priority_domain)
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
