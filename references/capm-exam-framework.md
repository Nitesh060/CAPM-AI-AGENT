# CAPM Exam Framework

## Source and verification

The exam facts and domain weights below come from PMI's own outline:

- **Document:** *PMI Certified Associate in Project Management (CAPM)® Examination Content Outline — 2023 Exam Update* (Project Management Institute)
- **URL:** https://www.pmi.org/-/media/pmi/documents/public/pdf/certifications/capm-exam-content-outline-english.pdf
- **Retrieved and read:** 2026-09-20 (the PDF itself, not a summary)
- **Caveat:** PMI's CAPM landing page returned HTTP 403 to automated fetching, so this project could not confirm there that no newer outline has been published. **Confirm on PMI's website before relying on these figures.**
- Machine-readable copy: `config/taxonomy.json` (`official` block). It is the single source of truth used by the tools.

This project keeps **official PMI information** and **our own practice material** apart:

| | Official (PMI) | Ours (practice) |
|---|---|---|
| Domains and weights | yes | — |
| Exam size, timing, formats | yes | — |
| Question bank | — | AI-generated, original |
| Topic list, aliases, curriculum | — | our own organisation |
| Mock-exam domain mix | PMI's weights | applied to our questions |

## Exam structure (official)

- **Questions:** 150 total — **135 scored + 15 unscored pretest** questions, placed randomly
- **Time:** 3 hours (about 72 seconds per question on average)
- **Break:** a 10-minute break after question 75, taken after you have reviewed your answers; you cannot go back to questions 1–75 afterwards
- **Formats:** multiple choice, drag-and-drop (enhanced matching), hot spot / hot area, and animation-video or comic-strip scenario questions (online proctored exams use comic strips only)
- **Passing score:** **not stated in the Examination Content Outline.** Do not rely on figures quoted elsewhere.
- **Eligibility:** secondary degree (high school diploma / GED / equivalent) and 23 hours of project management education
- **Attempts:** up to three attempts within a 1-year eligibility period
- **References PMI lists:** PMBOK® Guide 7th Edition; Process Groups: A Practice Guide (2022); The PMI Guide to Business Analysis (2017); Business Analysis for Practitioners: A Practice Guide, 2nd Edition; Agile Practice Guide (2017); The Project Management Answer Book, 2nd Edition; Effective Project Management: Traditional, Agile, Extreme, Hybrid, 8th Edition

## Four domains (official)

| # | Domain | Weight | Tasks |
|---|---|---|---|
| 1 | Project Management Fundamentals and Core Concepts | **36%** | 5 |
| 2 | Predictive, Plan-Based Methodologies | **17%** | 3 |
| 3 | Agile Frameworks/Methodologies | **20%** | 5 |
| 4 | Business Analysis Frameworks | **27%** | 6 |

PMI states that predictive, adaptive and business-analysis approaches "will be found throughout the four domain areas… and are not isolated to any particular domain or task", and that every exam covers all tasks of a domain at these domain-level percentages.

### Domain 1 — Project Management Fundamentals and Core Concepts (36%)
1. Understand the various project life cycles and processes (project vs. program vs. portfolio, project vs. operations, predictive vs. adaptive, issues/risks/assumptions/constraints, scope, code of ethics, a project as a vehicle for change)
2. Understand project management planning (cost, quality, risk, schedule; project vs. product management plan; milestones vs. task durations; resources; risk and stakeholder registers; closure and transitions)
3. Understand project roles and responsibilities (project manager vs. sponsor vs. team; leadership vs. management; emotional intelligence)
4. Follow and execute planned strategies or frameworks (communication, risk; initiation and benefit planning)
5. Understand common problem-solving tools and techniques (meeting effectiveness, focus groups, stand-ups, brainstorming)

### Domain 2 — Predictive, Plan-Based Methodologies (17%)
1. When a predictive, plan-based approach is appropriate
2. A project management plan schedule (critical path, schedule variance, WBS, work packages, quality and integration management plans)
3. Documenting project controls (artifacts, cost and schedule variances)

### Domain 3 — Agile Frameworks/Methodologies (20%)
1. When an adaptive approach is appropriate
2. Planning project iterations
3. Documenting project controls for an adaptive project
4. Components of an adaptive plan (Scrum, XP, SAFe®, Kanban, ...)
5. Preparing and executing task management steps (success criteria, prioritisation)

### Domain 4 — Business Analysis Frameworks (27%)
1. Business analysis roles and responsibilities
2. Stakeholder communication
3. Gathering requirements (user stories, use cases, traceability matrix / product backlog)
4. Product roadmaps
5. How project methodologies influence business analysis
6. Validating requirements through product delivery (acceptance criteria, readiness for delivery)

## How this project maps to the official domains

| Practice domain (our bank) | Official domain |
|---|---|
| Fundamentals | 1 — Project Management Fundamentals and Core Concepts |
| Predictive | 2 — Predictive, Plan-Based Methodologies |
| Agile | 3 — Agile Frameworks/Methodologies |
| Business Analysis | 4 — Business Analysis Frameworks |

Mock exams take PMI's domain weights (36/17/20/27) and apply them to our AI-generated questions. They are **practice** exams: they do not reproduce the real exam's questions, formats or difficulty. Because the bank is small, an oversized request is capped at the unique questions available (with a warning), and the domain mix may deviate from the official weights — the tool reports any deviation.

## Background: process groups and knowledge areas (study notes, not the ECO structure)

These older PMBOK-style groupings are still useful vocabulary for the predictive material, but the 2023 outline is organised by the four domains above.

**Process groups:** Initiating (define the project, identify stakeholders, authorize work) · Planning · Executing · Monitoring & Controlling · Closing.

**Knowledge areas:** Integration · Scope · Schedule · Cost · Quality · Resource · Communications · Risk · Procurement · Stakeholder management.

## General exam-taking tips (unofficial advice)

- Read questions carefully; watch for qualifiers such as "best", "first", "most likely"
- Eliminate obviously wrong answers, then choose the most complete option
- Mark difficult questions and return; use the 10-minute break to reset
- Practise with realistic scenarios, not just definitions
- Pretest (unscored) questions look identical to scored ones, so treat every question seriously

---

**Note:** This is original study material created for learning purposes. PMI, CAPM and PMBOK are marks of the Project Management Institute; this project is not affiliated with or endorsed by PMI. Always refer to PMI's current Examination Content Outline for the authoritative specification.
