"""P0 tests: taxonomy, filters, validation, scoring, mock exam, study plan."""

import json
import unittest

from helpers import ROOT, attempt, bank_question, run_json

import common
import mock_exam
import score_analyzer
import study_plan
import taxonomy
import validate_bank


class TestBankAndTaxonomy(unittest.TestCase):
    def test_bank_validates(self):
        errors, _, count = validate_bank.validate_bank()
        self.assertEqual(errors, [])
        self.assertEqual(count, 48)

    def test_validator_cli_exit_code(self):
        code, out = run_json("validate_bank.py")
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])

    def test_exactly_the_four_verified_domains(self):
        self.assertEqual(taxonomy.practice_domains(), ["Fundamentals", "Predictive", "Agile", "Business Analysis"])
        official = taxonomy.load_taxonomy()["official"]["domains"]
        self.assertEqual([d["id"] for d in official], ["D1", "D2", "D3", "D4"])

    def test_official_weights_match_pmi_outline(self):
        weights = taxonomy.official_weights()
        self.assertEqual(weights, {"Fundamentals": 0.36, "Predictive": 0.17, "Agile": 0.20, "Business Analysis": 0.27})
        self.assertAlmostEqual(sum(weights.values()), 1.0)

    def test_official_exam_facts_and_source_recorded(self):
        facts = taxonomy.exam_facts()
        self.assertEqual((facts["total_questions"], facts["scored_questions"], facts["pretest_unscored_questions"]), (150, 135, 15))
        self.assertEqual(facts["duration_minutes"], 180)
        self.assertIsNone(facts["passing_score"])
        source = taxonomy.official_source()
        self.assertTrue(source["url"].startswith("https://www.pmi.org/"))
        self.assertRegex(source["retrieved"], r"^\d{4}-\d{2}-\d{2}$")

    def test_official_and_practice_blocks_are_separate(self):
        data = taxonomy.load_taxonomy()
        self.assertIn("disclaimer", data["practice"])
        self.assertNotIn("topics", data["official"])

    def test_domain_lookup_variants(self):
        for name in ("business-analysis", "Business Analysis", "BUSINESS_ANALYSIS", "ba", "Business Analysis Frameworks"):
            self.assertEqual(taxonomy.canonical_domain(name), "Business Analysis", name)
        self.assertEqual(taxonomy.canonical_domain("Predictive, Plan-Based Methodologies"), "Predictive")
        self.assertIsNone(taxonomy.canonical_domain("business acumen"))
        self.assertIsNone(taxonomy.canonical_domain(""))

    def test_topic_aliases(self):
        self.assertEqual(taxonomy.canonical_topic("critical path"), "Schedule Management")
        self.assertEqual(taxonomy.canonical_topic("scrum roles"), "Scrum Roles")
        self.assertEqual(taxonomy.canonical_topic("Cost Management"), "Cost Management (EVM)")
        self.assertIsNone(taxonomy.canonical_topic("xyz-nonexistent"))
        self.assertIn("Stakeholder Engagement", taxonomy.search_topics("stakeholder"))

    def test_every_loaded_question_has_canonical_topic(self):
        names = set(taxonomy.topic_names())
        for q in common.load_all_questions():
            self.assertIn(q["topic"], names)


class TestFilters(unittest.TestCase):
    def setUp(self):
        self.questions = common.load_all_questions()

    def test_readme_topic_agile_returns_domain(self):
        hits = common.filter_questions(self.questions, topic="agile")
        self.assertEqual(len(hits), 12)
        self.assertTrue(all(q["domain"] == "Agile" for q in hits))

    def test_critical_path_alias(self):
        hits = common.filter_questions(self.questions, topic="critical path")
        self.assertTrue(hits)
        self.assertTrue(all(q["topic"] == "Schedule Management" for q in hits))

    def test_schedule_management_exact(self):
        hits = common.filter_questions(self.questions, topic="schedule management")
        self.assertEqual({q["topic"] for q in hits}, {"Schedule Management"})

    def test_domain_hyphen_and_case(self):
        self.assertEqual(len(common.filter_questions(self.questions, domain="business-analysis")), 11)
        self.assertEqual(len(common.filter_questions(self.questions, domain="FUNDAMENTALS")), 12)

    def test_difficulty_filter(self):
        hits = common.filter_questions(self.questions, difficulty="hard")
        self.assertTrue(hits and all(q["difficulty"] == "hard" for q in hits))

    def test_no_match(self):
        self.assertEqual(common.filter_questions(self.questions, topic="xyz-nonexistent"), [])


class TestQuizEngineCLI(unittest.TestCase):
    def test_answers_hidden_by_default(self):
        code, quiz = run_json("quiz_engine.py", "--count", "3")
        self.assertEqual(code, 0)
        for q in quiz["questions"]:
            self.assertFalse({"correct_answer", "explanation", "why_others_are_wrong", "concept_tested"} & set(q))

    def test_answers_revealed_on_request(self):
        _, quiz = run_json("quiz_engine.py", "--count", "3", "--reveal-answers", reveal=True)
        for q in quiz["questions"]:
            self.assertIn("correct_answer", q)
            self.assertIn("explanation", q)

    def test_seed_reproducible_and_shuffle_keeps_correct_text(self):
        _, a = run_json("quiz_engine.py", "--count", "5", "--reveal-answers", "--seed", "1", reveal=True)
        _, b = run_json("quiz_engine.py", "--count", "5", "--reveal-answers", "--seed", "1", reveal=True)
        self.assertEqual(a, b)
        originals = {q["id"]: q for q in common.load_all_questions()}
        for q in a["questions"]:
            orig = originals[q["id"]]
            self.assertEqual(q["options"][q["correct_answer"]], orig["options"][orig["correct_answer"]])

    def test_no_match_exits_nonzero(self):
        code, out = run_json("quiz_engine.py", "--topic", "xyz-nonexistent", "--count", "5")
        self.assertEqual(code, 1)
        self.assertIn("error", out)

    def test_unknown_domain_exits_nonzero(self):
        code, out = run_json("quiz_engine.py", "--domain", "business acumen")
        self.assertEqual(code, 1)
        self.assertIn("valid_domains", out)

    def test_shortfall_warning(self):
        _, quiz = run_json("quiz_engine.py", "--domain", "business analysis", "--count", "50")
        self.assertEqual(quiz["quiz_size"], 11)
        self.assertEqual(quiz["shortfall"], 39)
        self.assertIn("warning", quiz)

    def test_list_topics(self):
        code, out = run_json("quiz_engine.py", "--list-topics")
        self.assertEqual(code, 0)
        self.assertEqual(list(out["domains"]), taxonomy.practice_domains())


class TestScoreAnalyzer(unittest.TestCase):
    def test_basic_scoring_and_thresholds(self):
        q_weak, q_strong = bank_question("Kanban"), bank_question("Scrum Roles")
        attempts = [attempt(q_weak, False), attempt(q_weak, False), attempt(q_strong, True), attempt(q_strong, True)]
        norm, warnings = score_analyzer.normalize_attempts(attempts)
        result = score_analyzer.analyze(norm)
        self.assertEqual(result["summary"]["percentage"], 50.0)
        self.assertIn("Kanban", result["weak_topics"])
        self.assertIn("Scrum Roles", result["strong_topics"])
        self.assertIn("does not guarantee", result["disclaimer"])
        self.assertEqual(warnings, [])

    def test_correct_must_be_a_real_boolean(self):
        bad = attempt(bank_question("Kanban"), False)
        bad["correct"] = "false"
        with self.assertRaises(score_analyzer.AttemptError):
            score_analyzer.normalize_attempts([bad])

    def test_topic_variants_merge(self):
        raw = [
            {"question_id": "EXT-1", "domain": "agile", "topic": "scrum roles", "difficulty": "easy", "correct": True},
            {"question_id": "EXT-2", "domain": "Agile", "topic": "Scrum Roles", "difficulty": "easy", "correct": False},
        ]
        norm, warnings = score_analyzer.normalize_attempts(raw)
        self.assertEqual({a["topic"] for a in norm}, {"Scrum Roles"})
        self.assertEqual(len(warnings), 2)  # external (non-bank) question ids

    def test_bank_id_fills_and_overrides_metadata(self):
        q = bank_question("Kanban")
        norm, _ = score_analyzer.normalize_attempts([{"question_id": q["id"], "correct": True}])
        self.assertEqual((norm[0]["domain"], norm[0]["topic"]), (q["domain"], q["topic"]))

    def test_rejects_malformed_input(self):
        ext = {"correct": True, "question_id": "E", "domain": "Agile", "topic": "Kanban", "difficulty": "easy"}
        for bad in ([], "x", [1],
                    [dict(ext, domain="Nope")],
                    [dict(ext, topic="Nope")],
                    [dict(ext, domain="Predictive")],       # topic belongs to another domain
                    [dict(ext, difficulty="extreme")]):
            with self.assertRaises(score_analyzer.AttemptError, msg=repr(bad)):
                score_analyzer.normalize_attempts(bad)

    def test_cli_errors_are_json_not_tracebacks(self):
        for stdin in ("not json", "[1, 2]", '{"attempts": ["x"]}', '{"attempts": []}'):
            code, out = run_json("score_analyzer.py", "--stdin", stdin=stdin)
            self.assertEqual(code, 1, stdin)
            self.assertIn("error", out)


class TestMockExam(unittest.TestCase):
    def test_weights_at_20_questions(self):
        exam = mock_exam.build_mock_exam(20, seed=1)
        self.assertEqual(exam["actual_questions"], 20)
        for domain, weight in taxonomy.official_weights().items():
            self.assertLessEqual(abs(exam["domain_distribution_actual"][domain] - 20 * weight), 1, domain)
        self.assertGreater(exam["domain_distribution_actual"]["Fundamentals"], 0)

    def test_faithful_when_pool_allows(self):
        exam = mock_exam.build_mock_exam(30, seed=1)
        self.assertEqual(exam["warnings"], [])
        self.assertEqual(exam["domain_distribution_actual"], exam["domain_distribution_target"])

    def test_oversized_request_is_capped_with_warning_not_repeated(self):
        exam = mock_exam.build_mock_exam(150, seed=1)
        self.assertEqual(exam["actual_questions"], 48)
        self.assertEqual(exam["unique_questions"], 48)
        self.assertEqual(len({q["id"] for q in exam["questions"]}), 48)
        self.assertTrue(any("Requested 150" in w for w in exam["warnings"]))

    def test_deviation_from_official_weights_is_reported(self):
        exam = mock_exam.build_mock_exam(40, seed=1)
        self.assertEqual(exam["actual_questions"], 40)
        self.assertEqual(sum(exam["domain_distribution_actual"].values()), 40)
        self.assertNotEqual(exam["domain_distribution_actual"], exam["domain_distribution_target"])
        self.assertTrue(any("deviates" in w for w in exam["warnings"]))

    def test_allow_repeats_is_explicit(self):
        exam = mock_exam.build_mock_exam(150, seed=1, allow_repeats=True)
        self.assertEqual(exam["actual_questions"], 150)
        self.assertEqual(exam["unique_questions"], 48)
        self.assertTrue(any("repeated" in w for w in exam["warnings"]))
        self.assertEqual(sum(exam["domain_distribution_actual"].values()), 150)

    def test_metadata_separates_official_from_practice(self):
        exam = mock_exam.build_mock_exam(20, seed=1)
        self.assertEqual(exam["official_domain_weights"], taxonomy.official_weights())
        self.assertIn("not PMI's question distribution", exam["distribution_basis"])
        self.assertIn("not produced or endorsed by PMI", exam["disclaimer"])
        self.assertEqual(exam["suggested_time_minutes"], 24)  # 180 min / 150 questions = 1.2 min each

    def test_seed_is_deterministic(self):
        a = mock_exam.build_mock_exam(20, seed=7)
        b = mock_exam.build_mock_exam(20, seed=7)
        self.assertEqual([q["id"] for q in a["questions"]], [q["id"] for q in b["questions"]])

    def test_largest_remainder_sums(self):
        for n in (1, 7, 20, 60, 150, 1000):
            self.assertEqual(sum(mock_exam._largest_remainder(n, taxonomy.official_weights()).values()), n)

    def test_cli_flags(self):
        code, exam = run_json("mock_exam.py", "--questions", "150")
        self.assertEqual((code, exam["actual_questions"]), (0, 48))
        code, exam = run_json("mock_exam.py", "--questions", "150", "--no-repeats")  # deprecated no-op
        self.assertEqual((code, exam["actual_questions"]), (0, 48))
        code, exam = run_json("mock_exam.py", "--questions", "150", "--allow-repeats")
        self.assertEqual((code, exam["actual_questions"]), (0, 150))
        code, _ = run_json("mock_exam.py", "--questions", "5", "--allow-repeats", "--no-repeats")
        self.assertEqual(code, 1)
        code, _ = run_json("mock_exam.py", "--questions", "0")
        self.assertEqual(code, 1)

    def test_cli_hides_answers(self):
        _, exam = run_json("mock_exam.py", "--questions", "10")
        for q in exam["questions"]:
            self.assertNotIn("correct_answer", q)


class TestStudyPlan(unittest.TestCase):
    def test_week_count_integrity(self):
        for weeks in range(1, 13):
            self.assertEqual(len(study_plan.generate_plan(weeks, 5)["plan"]), weeks, weeks)

    def test_covers_all_four_domains(self):
        plan = study_plan.generate_plan(8, 10)["plan"]
        focus = " ".join(w["domain_focus"] for w in plan)
        for domain in taxonomy.practice_domains():
            self.assertIn(domain, focus)

    def test_priority_domain_first_including_fundamentals(self):
        for domain in ("Fundamentals", "Business Analysis"):
            plan = study_plan.generate_plan(8, 10, priority_domain=domain)["plan"]
            self.assertTrue(plan[0]["domain_focus"].startswith(domain), domain)

    def test_rejects_invalid_inputs(self):
        for weeks, hours in ((0, 5), (-3, 5), (4, 0)):
            with self.assertRaises(ValueError):
                study_plan.generate_plan(weeks, hours)
        code, _ = run_json("study_plan.py", "--weeks", "0", "--hours-per-week", "5", "--ignore-history")
        self.assertEqual(code, 1)

    def test_weak_topic_matching_uses_canonical_topics(self):
        weeks = study_plan.generate_plan(20, 5, weak_topics=["Cost Management (EVM)", "Schedule Compression"])["plan"]
        text = json.dumps(weeks)
        self.assertIn("EXTRA revision recommended for weak topic(s): Cost Management (EVM)", text)
        self.assertIn("Schedule Compression", text)

    def test_every_taxonomy_topic_is_in_the_curriculum(self):
        covered = {t for topics in study_plan.CURRICULUM_TOPIC_MAP.values() for t in topics}
        self.assertEqual(set(taxonomy.topic_names()) - covered, set())
        for labels in study_plan.CURRICULUM.values():
            for label in labels:
                self.assertIn(label, study_plan.CURRICULUM_TOPIC_MAP)

    def test_disclaimer(self):
        self.assertIn("does not guarantee", study_plan.generate_plan(4, 5)["disclaimer"])


class TestRepoHygiene(unittest.TestCase):
    def test_gitignore_protects_learner_data(self):
        lines = (ROOT / ".gitignore").read_text().splitlines()
        for entry in ("data/student_progress.json", "data/sessions/", "__pycache__/", ".venv/"):
            self.assertIn(entry, lines)

    def test_example_progress_template_is_empty_v2(self):
        data = json.loads((ROOT / "data" / "student_progress.example.json").read_text())
        self.assertEqual(data, {"schema_version": 2, "sessions": [], "attempts": []})


if __name__ == "__main__":
    unittest.main()
