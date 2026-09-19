"""Shared utilities for CAPM AI Study Agent tools.

Provides question bank loading/filtering and progress data I/O used by
quiz_engine.py, mock_exam.py, score_analyzer.py, study_plan.py, and
progress_tracker.py.
"""

import json
import random
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTION_BANK_DIR = PROJECT_ROOT / "question_bank"
PROGRESS_FILE = PROJECT_ROOT / "data" / "student_progress.json"

DOMAIN_FILES = {
    "fundamentals": "fundamentals.json",
    "predictive": "predictive.json",
    "agile": "agile.json",
    "business analysis": "business-analysis.json",
    "business-analysis": "business-analysis.json",
}

DOMAIN_EXAM_WEIGHTS = {
    "predictive": 0.50,
    "agile": 0.25,
    "business analysis": 0.25,
}


def load_all_questions():
    """Load every question from every question bank file."""
    questions = []
    for path in sorted(QUESTION_BANK_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        questions.extend(data.get("questions", []))
    return questions


def load_domain_questions(domain):
    """Load questions for a single domain by name (case-insensitive)."""
    key = domain.strip().lower()
    filename = DOMAIN_FILES.get(key)
    if not filename:
        return []
    path = QUESTION_BANK_DIR / filename
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("questions", [])


def filter_questions(questions, topic=None, domain=None, difficulty=None):
    """Filter a list of question dicts by optional topic/domain/difficulty."""
    result = questions
    if domain:
        d = domain.strip().lower()
        result = [q for q in result if q.get("domain", "").strip().lower() == d]
    if topic:
        t = topic.strip().lower()
        result = [q for q in result if t in q.get("topic", "").strip().lower()]
    if difficulty:
        diff = difficulty.strip().lower()
        result = [q for q in result if q.get("difficulty", "").strip().lower() == diff]
    return result


def randomize_options(question, rng=None):
    """Return a copy of the question with options shuffled and correct_answer
    letter remapped to match the new order.
    """
    rng = rng or random
    letters = list(question["options"].keys())
    values = list(question["options"].values())
    correct_value = question["options"][question["correct_answer"]]

    paired = list(zip(letters, values))
    rng.shuffle(paired)

    new_options = {}
    new_correct_letter = None
    new_why_wrong = {}
    old_why_wrong = question.get("why_others_are_wrong", {})
    # map old letter -> value -> new letter, to carry explanations along
    old_letter_by_value = {v: k for k, v in question["options"].items()}

    for new_letter, (_, value) in zip(letters, paired):
        new_options[new_letter] = value
        if value == correct_value:
            new_correct_letter = new_letter
        else:
            old_letter = old_letter_by_value[value]
            if old_letter in old_why_wrong:
                new_why_wrong[new_letter] = old_why_wrong[old_letter]

    new_question = dict(question)
    new_question["options"] = new_options
    new_question["correct_answer"] = new_correct_letter
    new_question["why_others_are_wrong"] = new_why_wrong
    return new_question


def load_progress():
    """Load student progress data, returning a default structure if absent."""
    if not PROGRESS_FILE.exists():
        return {"sessions": []}
    with open(PROGRESS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_progress(data):
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def strip_answers(question):
    """Return a question dict with answer-revealing fields removed,
    safe to show a student before they respond.
    """
    safe_keys = ("id", "domain", "topic", "difficulty", "type", "question", "options")
    return {k: question[k] for k in safe_keys if k in question}
