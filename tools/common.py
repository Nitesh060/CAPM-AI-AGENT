"""Shared utilities for CAPM AI Study Agent tools.

Provides question bank loading/filtering and progress data I/O used by
quiz_engine.py, mock_exam.py, score_analyzer.py, study_plan.py,
progress_tracker.py, selector.py and session.py.

Set the CAPM_DATA_DIR environment variable to redirect all learner data
(progress + sessions) to another directory, e.g. for tests.
"""

import json
import os
import random
from pathlib import Path

import taxonomy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTION_BANK_DIR = PROJECT_ROOT / "question_bank"
DATA_DIR = PROJECT_ROOT / "data"
PROGRESS_FILE = DATA_DIR / "student_progress.json"
SESSIONS_DIR = DATA_DIR / "sessions"
DATA_DIR_ENV = "CAPM_DATA_DIR"

PROGRESS_SCHEMA_VERSION = 2

# Kept for backward compatibility; derived from the taxonomy (PMI published weights).
DOMAIN_FILES = {d.lower(): taxonomy.domain_file(d) for d in taxonomy.practice_domains()}
DOMAIN_FILES["business-analysis"] = DOMAIN_FILES["business analysis"]
DOMAIN_EXAM_WEIGHTS = {d.lower(): w for d, w in taxonomy.official_weights().items()}


class ProgressError(Exception):
    """Learner progress data could not be read safely."""


# --- data locations ----------------------------------------------------------

def get_progress_file():
    env = os.environ.get(DATA_DIR_ENV)
    if env:
        return Path(env) / "student_progress.json"
    return PROGRESS_FILE


def get_sessions_dir():
    env = os.environ.get(DATA_DIR_ENV)
    if env:
        return Path(env) / "sessions"
    return SESSIONS_DIR


def write_json_atomic(path, data):
    """Write JSON to a temp file in the same directory, then atomically replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


# --- question bank -----------------------------------------------------------

def _normalize_question(q):
    """Copy of the question with domain/topic mapped to canonical taxonomy names."""
    q = dict(q)
    domain = taxonomy.canonical_domain(q.get("domain"))
    if domain:
        q["domain"] = domain
    topic = taxonomy.canonical_topic(q.get("topic"))
    if topic:
        q["topic"] = topic
    return q


def _read_bank_file(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [_normalize_question(q) for q in data.get("questions", [])]


def load_all_questions():
    """Load every question from every question bank file."""
    questions = []
    for path in sorted(QUESTION_BANK_DIR.glob("*.json")):
        questions.extend(_read_bank_file(path))
    return questions


def load_domain_questions(domain):
    """Load questions for a single domain by name or alias (case-insensitive)."""
    canonical = taxonomy.canonical_domain(domain)
    filename = taxonomy.domain_file(canonical) if canonical else None
    if not filename:
        return []
    path = QUESTION_BANK_DIR / filename
    if not path.exists():
        return []
    return _read_bank_file(path)


def filter_questions(questions, topic=None, domain=None, difficulty=None):
    """Filter a list of question dicts by optional topic/domain/difficulty.

    Domain accepts names/aliases in any case ("business-analysis" works).
    Topic is resolved in tiers, first tier with results wins:
      1. exact topic name or alias   ("critical path" -> Schedule Management)
      2. a domain name/alias         ("agile" -> the Agile domain)
      3. topic/alias substring       ("stakeholder" -> Stakeholder Management + Engagement)
      4. raw topic substring         (legacy behaviour)
      5. concept_tested / question text substring
    """
    result = list(questions)
    if domain:
        canonical = taxonomy.canonical_domain(domain)
        wanted = canonical or domain.strip().lower()
        result = [q for q in result if q.get("domain", "").strip().lower() == wanted.lower()]
    if difficulty:
        diff = difficulty.strip().lower()
        result = [q for q in result if q.get("difficulty", "").strip().lower() == diff]
    if topic:
        result = _filter_by_topic(result, topic)
    return result


def _filter_by_topic(questions, topic):
    t = topic.strip().lower()

    exact = taxonomy.canonical_topic(topic)
    if exact:
        hits = [q for q in questions if q.get("topic") == exact]
        if hits:
            return hits

    dom = taxonomy.canonical_domain(topic)
    if dom:
        hits = [q for q in questions if q.get("domain") == dom]
        if hits:
            return hits

    names = set(taxonomy.search_topics(topic))
    if names:
        hits = [q for q in questions if q.get("topic") in names]
        if hits:
            return hits

    hits = [q for q in questions if t in q.get("topic", "").strip().lower()]
    if hits:
        return hits

    return [
        q for q in questions
        if t in q.get("concept_tested", "").lower() or t in q.get("question", "").lower()
    ]


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


def strip_answers(question):
    """Return a question dict with answer-revealing fields removed,
    safe to show a student before they respond.
    """
    safe_keys = ("id", "domain", "topic", "difficulty", "type", "question", "options")
    return {k: question[k] for k in safe_keys if k in question}


# --- progress ----------------------------------------------------------------

def new_progress():
    return {"schema_version": PROGRESS_SCHEMA_VERSION, "sessions": [], "attempts": []}


def upgrade_progress(data):
    """Upgrade a v1 progress dict ({"sessions": [...]}) to v2 in memory."""
    if not isinstance(data, dict):
        raise ProgressError("Progress file must contain a JSON object.")
    upgraded = {"schema_version": PROGRESS_SCHEMA_VERSION}
    upgraded.update({k: v for k, v in data.items() if k != "schema_version"})
    upgraded.setdefault("sessions", [])
    upgraded.setdefault("attempts", [])
    return upgraded


def load_progress():
    """Load student progress (always returned in v2 shape).

    A missing file yields an empty history. A corrupt file raises ProgressError
    rather than being silently replaced.
    """
    path = get_progress_file()
    if not path.exists():
        return new_progress()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ProgressError(
            f"{path} is not valid JSON ({e}). Fix or move the file; it was not overwritten."
        ) from e
    return upgrade_progress(data)


def save_progress(data):
    write_json_atomic(get_progress_file(), upgrade_progress(data))
