"""Taxonomy helpers for the CAPM AI Study Agent.

Loads config/taxonomy.json, which keeps two clearly separated blocks:
  * official  - facts from PMI's CAPM Examination Content Outline
  * practice  - our own domains/topics/aliases for AI-generated practice questions

Everything that needs domain names, domain weights, or topic names should go
through this module instead of hard-coding them.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "config" / "taxonomy.json"


def _norm(text):
    """Lowercase and collapse every non-alphanumeric run to a single space."""
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


@lru_cache(maxsize=1)
def load_taxonomy():
    with open(TAXONOMY_PATH, encoding="utf-8") as f:
        data = json.load(f)
    _validate(data)
    return data


def _validate(data):
    official = {d["id"]: d for d in data["official"]["domains"]}
    total = round(sum(d["weight"] for d in official.values()), 6)
    if total != 1.0:
        raise ValueError(f"Official domain weights sum to {total}, expected 1.0")
    keys = [d["key"] for d in data["practice"]["domains"]]
    for d in data["practice"]["domains"]:
        if d["official_id"] not in official:
            raise ValueError(f"Practice domain {d['key']} maps to unknown official id {d['official_id']}")
    seen_topics = {}
    for t in data["practice"]["topics"]:
        if t["domain"] not in keys:
            raise ValueError(f"Topic {t['name']} has unknown domain {t['domain']}")
        for label in [t["name"]] + t.get("aliases", []):
            n = _norm(label)
            if n in seen_topics and seen_topics[n] != t["name"]:
                raise ValueError(f"Topic alias {label!r} is used by both {seen_topics[n]} and {t['name']}")
            seen_topics[n] = t["name"]


@lru_cache(maxsize=1)
def _indexes():
    data = load_taxonomy()
    official = {d["id"]: d for d in data["official"]["domains"]}
    domain_lookup = {}
    for d in data["practice"]["domains"]:
        labels = [d["key"], d["official_id"], official[d["official_id"]]["name"]] + d.get("aliases", [])
        for label in labels:
            domain_lookup[_norm(label)] = d["key"]
    topic_lookup = {}
    for t in data["practice"]["topics"]:
        for label in [t["name"]] + t.get("aliases", []):
            topic_lookup[_norm(label)] = t["name"]
    return {"domain": domain_lookup, "topic": topic_lookup}


# --- domains ---------------------------------------------------------------

def practice_domains():
    """Practice domain keys in canonical order."""
    return [d["key"] for d in load_taxonomy()["practice"]["domains"]]


def canonical_domain(name):
    """Return the canonical practice domain for a name/alias, or None."""
    if not name:
        return None
    return _indexes()["domain"].get(_norm(name))


def domain_file(domain):
    for d in load_taxonomy()["practice"]["domains"]:
        if d["key"] == domain:
            return d["bank_file"]
    return None


def official_domain(domain):
    """Official ECO domain record (id, name, weight, tasks) for a practice domain."""
    data = load_taxonomy()
    official = {d["id"]: d for d in data["official"]["domains"]}
    for d in data["practice"]["domains"]:
        if d["key"] == domain:
            return official[d["official_id"]]
    return None


def official_weights():
    """{practice_domain: PMI published weight} in canonical order."""
    return {d: official_domain(d)["weight"] for d in practice_domains()}


def exam_facts():
    return load_taxonomy()["official"]["exam"]


def official_source():
    return load_taxonomy()["official"]["source"]


def practice_disclaimer():
    return load_taxonomy()["practice"]["disclaimer"]


# --- topics ----------------------------------------------------------------

def topic_records():
    return list(load_taxonomy()["practice"]["topics"])


def topic_names():
    return [t["name"] for t in topic_records()]


def topics_for_domain(domain):
    return [t["name"] for t in topic_records() if t["domain"] == domain]


def topic_domain(topic):
    for t in topic_records():
        if t["name"] == topic:
            return t["domain"]
    return None


def canonical_topic(name):
    """Exact (case/punctuation-insensitive) topic name or alias match, or None."""
    if not name:
        return None
    return _indexes()["topic"].get(_norm(name))


def search_topics(query):
    """Topics whose name or any alias contains the query (needs >= 3 chars)."""
    q = _norm(query)
    if len(q) < 3:
        return []
    found = []
    for label, topic in _indexes()["topic"].items():
        if q in label and topic not in found:
            found.append(topic)
    return found
