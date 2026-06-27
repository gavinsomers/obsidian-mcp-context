from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import random
import re
import shutil


PROFILE_SPECS = {
    "small": {
        "companies": 8,
        "people": 32,
        "projects": 12,
        "daily": 48,
        "meetings": 60,
        "decisions": 24,
        "risks": 24,
        "research": 24,
        "months": 6,
    },
    "medium": {
        "companies": 30,
        "people": 150,
        "projects": 50,
        "daily": 260,
        "meetings": 320,
        "decisions": 130,
        "risks": 130,
        "research": 130,
        "months": 18,
    },
    "large": {
        "companies": 120,
        "people": 600,
        "projects": 220,
        "daily": 780,
        "meetings": 1900,
        "decisions": 760,
        "risks": 680,
        "research": 620,
        "months": 36,
    },
}

FIRST_NAMES = [
    "Alex",
    "Amara",
    "Ben",
    "Clara",
    "David",
    "Elena",
    "Farah",
    "Grace",
    "Hannah",
    "Iris",
    "Jonah",
    "Kai",
    "Lina",
    "Marcus",
    "Nadia",
    "Omar",
    "Priya",
    "Rachel",
    "Sam",
    "Tara",
    "Uma",
    "Victor",
    "Wendy",
    "Xavier",
    "Yara",
    "Zoe",
]
LAST_NAMES = [
    "Alvarez",
    "Bennett",
    "Chen",
    "Diaz",
    "Evans",
    "Foster",
    "Grant",
    "Haddad",
    "Ivanov",
    "Jenkins",
    "Kim",
    "Lee",
    "Morgan",
    "Novak",
    "Ortega",
    "Patel",
    "Quinn",
    "Rostova",
    "Shah",
    "Tan",
    "Usman",
    "Vance",
    "Walker",
    "Xu",
    "Young",
    "Zimmer",
]
COMPANY_PREFIXES = [
    "Northstar",
    "Apex",
    "Cobalt",
    "BrightWave",
    "Helio",
    "Meridian",
    "Vanguard",
    "Quantum",
    "Atlas",
    "Harbor",
    "Summit",
    "Pioneer",
    "Noble",
    "Crescent",
    "Keystone",
]
COMPANY_SUFFIXES = [
    "Labs",
    "FinTech",
    "Retail",
    "Manufacturing",
    "Health",
    "Media",
    "Logistics",
    "Analytics",
    "Systems",
    "Energy",
]
PROJECT_NAMES = [
    "Atlas",
    "Beacon",
    "Foundry",
    "Horizon",
    "Lantern",
    "Meridian",
    "Pipeline",
    "Compass",
    "Harbor",
    "Keystone",
    "Orbit",
    "Summit",
    "Venture",
    "Signal",
    "Bridge",
]
SCENARIOS = [
    "consulting_delivery",
    "sales_pipeline",
    "customer_success",
    "research_program",
    "operations_admin",
]
TOPICS = [
    "warehouse mapping",
    "stakeholder alignment",
    "security review",
    "finance approval",
    "adoption workflow",
    "metric reconciliation",
    "contract renewal",
    "lineage audit",
    "pipeline hygiene",
    "handoff readiness",
]


@dataclass(frozen=True)
class Company:
    name: str
    segment: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class Person:
    name: str
    company: Company
    role: str
    created_at: datetime


@dataclass(frozen=True)
class Project:
    name: str
    company: Company
    owner: Person
    stakeholders: list[Person]
    scenario: str
    start_date: date
    status: str


@dataclass(frozen=True)
class GeneratedNote:
    folder: str
    title: str
    note_type: str
    source_date: date | None
    source_created_at: datetime
    source_observed_at: datetime
    created_at: datetime
    updated_at: datetime
    body: str
    extra_frontmatter: dict[str, str]


def _safe_filename(title: str) -> str:
    return re.sub(r"[/:]+", " ", title).strip()


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def _link(title: str) -> str:
    return f"[[{title}]]"


def _frontmatter(note: GeneratedNote) -> str:
    lines = ["---", f"type: {note.note_type}"]
    if note.source_date:
        lines.append(f"date: {note.source_date.isoformat()}")
    lines.extend(f"{key}: {value}" for key, value in note.extra_frontmatter.items())
    lines.extend(
        [
            f"source_created_at: {_iso(note.source_created_at)}",
            f"source_observed_at: {_iso(note.source_observed_at)}",
            f"created_at: {_iso(note.created_at)}",
            f"updated_at: {_iso(note.updated_at)}",
            f"tags: [#{note.note_type}]",
            "---",
        ]
    )
    return "\n".join(lines)


def _render(note: GeneratedNote) -> str:
    return f"{_frontmatter(note)}\n# {note.title}\n\n{note.body.rstrip()}\n"


def _business_dates(start: date, months: int, count: int) -> list[date]:
    days = months * 30
    candidates = [
        start + timedelta(days=offset)
        for offset in range(days)
        if (start + timedelta(days=offset)).weekday() < 5
    ]
    if count <= len(candidates):
        step = len(candidates) / count
        return [candidates[int(index * step)] for index in range(count)]
    return [candidates[index % len(candidates)] for index in range(count)]


def _timestamp_on(day: date, rng: random.Random, earliest_hour: int = 8) -> datetime:
    return datetime.combine(day, datetime.min.time()).replace(
        hour=earliest_hour + rng.randrange(0, 9),
        minute=rng.randrange(0, 60),
    )


def _lifecycle(
    rng: random.Random,
    source_day: date,
    note_type: str,
    late_capture_rate: float,
) -> tuple[datetime, datetime, datetime, datetime]:
    source_created = _timestamp_on(source_day, rng)
    observe_lag = timedelta(minutes=rng.randrange(10, 180))
    if rng.random() < late_capture_rate:
        capture_lag = timedelta(days=rng.randrange(1, 10), hours=rng.randrange(0, 8))
    elif note_type in {"company", "person", "project", "research", "risk"}:
        capture_lag = timedelta(hours=rng.randrange(2, 48))
    else:
        capture_lag = timedelta(minutes=rng.randrange(10, 360))
    observed = source_created + observe_lag
    created = max(observed + timedelta(minutes=5), source_created + capture_lag)
    if note_type in {"company", "person", "project"}:
        update_lag = timedelta(days=rng.randrange(14, 90), hours=rng.randrange(0, 12))
    elif note_type in {"research", "risk"}:
        update_lag = timedelta(days=rng.randrange(3, 45), hours=rng.randrange(0, 12))
    elif note_type == "daily":
        update_lag = timedelta(minutes=rng.randrange(30, 360))
    else:
        update_lag = timedelta(hours=rng.randrange(1, 24))
    return source_created, observed, created, created + update_lag


def _choose_many(rng: random.Random, values: list[Person], count: int) -> list[Person]:
    if len(values) <= count:
        return values[:]
    return rng.sample(values, count)


def _build_world(
    rng: random.Random, start: date, spec: dict[str, int]
) -> tuple[list[Company], list[Person], list[Project]]:
    companies = []
    for index in range(spec["companies"]):
        name = f"{COMPANY_PREFIXES[index % len(COMPANY_PREFIXES)]} {COMPANY_SUFFIXES[(index // len(COMPANY_PREFIXES)) % len(COMPANY_SUFFIXES)]}"
        companies.append(
            Company(
                name=name,
                segment=rng.choice(["smb", "mid-market", "enterprise"]),
                status=rng.choice(["active", "active", "pipeline", "churn-risk"]),
                created_at=_timestamp_on(start + timedelta(days=index * 2), rng),
            )
        )

    people = []
    roles = [
        "Operations Lead",
        "Finance Sponsor",
        "SecOps Lead",
        "Implementation Manager",
        "VP Data Engineering",
        "Legal Counsel",
        "Product Director",
        "Customer Success Manager",
    ]
    for index in range(spec["people"]):
        name = (
            f"{FIRST_NAMES[index % len(FIRST_NAMES)]} "
            f"{LAST_NAMES[(index // len(FIRST_NAMES)) % len(LAST_NAMES)]}"
        )
        company = companies[index % len(companies)]
        people.append(
            Person(
                name=name,
                company=company,
                role=roles[index % len(roles)],
                created_at=_timestamp_on(start + timedelta(days=2 + index // 3), rng),
            )
        )

    people_by_company = {
        company.name: [person for person in people if person.company == company]
        for company in companies
    }
    projects = []
    project_dates = _business_dates(start + timedelta(days=10), spec["months"], spec["projects"])
    for index in range(spec["projects"]):
        company = companies[index % len(companies)]
        company_people = people_by_company[company.name] or people
        owner = company_people[index % len(company_people)]
        stakeholders = _choose_many(rng, company_people, min(4, len(company_people)))
        projects.append(
            Project(
                name=f"Project {PROJECT_NAMES[index % len(PROJECT_NAMES)]} {index + 1}",
                company=company,
                owner=owner,
                stakeholders=stakeholders,
                scenario=SCENARIOS[index % len(SCENARIOS)],
                start_date=project_dates[index],
                status=rng.choice(["active", "active", "planning", "blocked", "closed"]),
            )
        )
    return companies, people, projects


def _company_notes(
    rng: random.Random,
    companies: list[Company],
    people: list[Person],
    projects: list[Project],
    late_capture_rate: float,
) -> list[GeneratedNote]:
    notes = []
    for company in companies:
        source_day = company.created_at.date()
        lifecycle = _lifecycle(rng, source_day, "company", late_capture_rate)
        company_people = [person for person in people if person.company == company][:8]
        company_projects = [project for project in projects if project.company == company][:6]
        body = "\n".join(
            [
                "## Account Context",
                f"{company.name} is a {company.segment} account currently marked `{company.status}`.",
                "",
                "## Stakeholders",
                *[f"- {_link(person.name)} - {person.role}" for person in company_people],
                "",
                "## Projects",
                *[f"- {_link(project.name)}" for project in company_projects],
                "",
                "## Open Loops",
                f"- [ ] Refresh account context for {_link(company.name)} #account",
            ]
        )
        notes.append(
            GeneratedNote(
                "Companies",
                company.name,
                "company",
                None,
                *lifecycle,
                body,
                {"status": company.status, "segment": company.segment},
            )
        )
    return notes


def _person_notes(
    rng: random.Random,
    people: list[Person],
    projects: list[Project],
    late_capture_rate: float,
) -> list[GeneratedNote]:
    notes = []
    for person in people:
        source_day = person.created_at.date()
        lifecycle = _lifecycle(rng, source_day, "person", late_capture_rate)
        owned = [project for project in projects if project.owner == person][:4]
        related = owned or [project for project in projects if project.company == person.company][:2]
        body = "\n".join(
            [
                "## Role",
                f"{person.name} is the {person.role} at {_link(person.company.name)}.",
                "",
                "## Current Context",
                *[f"- Connected to {_link(project.name)}" for project in related],
                f"- [ ] Confirm next update with {_link(person.name)} #follow-up",
            ]
        )
        notes.append(
            GeneratedNote(
                "People",
                person.name,
                "person",
                None,
                *lifecycle,
                body,
                {"company": f'"{_link(person.company.name)}"', "role": f'"{person.role}"'},
            )
        )
    return notes


def _project_notes(
    rng: random.Random,
    projects: list[Project],
    late_capture_rate: float,
) -> list[GeneratedNote]:
    notes = []
    for project in projects:
        lifecycle = _lifecycle(rng, project.start_date, "project", late_capture_rate)
        body = "\n".join(
            [
                "## Overview",
                f"{project.name} supports {_link(project.company.name)} through {project.scenario.replace('_', ' ')}.",
                "",
                "## Stakeholders",
                *[f"- {_link(person.name)}" for person in project.stakeholders],
                "",
                "## Operating Notes",
                f"- Owner: {_link(project.owner.name)}",
                f"- Status: `{project.status}`",
                f"- [ ] Reconcile latest state for {_link(project.name)} #ops",
            ]
        )
        notes.append(
            GeneratedNote(
                "Projects",
                project.name,
                "project",
                None,
                *lifecycle,
                body,
                {"status": project.status, "company": f'"{_link(project.company.name)}"'},
            )
        )
    return notes


def _event_notes(
    rng: random.Random,
    projects: list[Project],
    spec: dict[str, int],
    start: date,
    late_capture_rate: float,
) -> list[GeneratedNote]:
    notes: list[GeneratedNote] = []
    event_dates = _business_dates(start + timedelta(days=14), spec["months"], spec["meetings"])
    meeting_titles: list[str] = []
    for index, event_day in enumerate(event_dates):
        project = projects[index % len(projects)]
        topic = TOPICS[index % len(TOPICS)]
        title = f"{project.name} {topic.title()} Sync {index + 1}"
        meeting_titles.append(title)
        lifecycle = _lifecycle(rng, event_day, "meeting", late_capture_rate)
        attendees = _choose_many(rng, project.stakeholders, min(3, len(project.stakeholders)))
        body = "\n".join(
            [
                "## Attendees",
                *[f"- {_link(person.name)}" for person in attendees],
                "",
                "## Notes",
                f"{topic.title()} reviewed for {_link(project.name)} at {_link(project.company.name)}.",
                f"{_link(project.owner.name)} flagged follow-up work for the next operating review.",
                "",
                "## Action Items",
                f"- [ ] Send recap for {_link(project.name)} to {_link(project.owner.name)} #follow-up",
                f"- [x] Capture meeting notes in vault #ops",
            ]
        )
        notes.append(
            GeneratedNote(
                "Meetings",
                title,
                "meeting",
                event_day,
                *lifecycle,
                body,
                {"project": f'"{_link(project.name)}"', "company": f'"{_link(project.company.name)}"'},
            )
        )

    decision_dates = _business_dates(start + timedelta(days=21), spec["months"], spec["decisions"])
    for index, event_day in enumerate(decision_dates):
        project = projects[index % len(projects)]
        topic = TOPICS[(index + 2) % len(TOPICS)]
        title = f"{project.name} {topic.title()} Decision {index + 1}"
        superseded = index % 7 == 0 and index + 1 < len(decision_dates)
        superseded_by = (
            f"{projects[(index + 1) % len(projects)].name} {TOPICS[(index + 3) % len(TOPICS)].title()} Decision {index + 2}"
            if superseded
            else None
        )
        lifecycle = _lifecycle(rng, event_day, "decision", late_capture_rate)
        body = "\n".join(
            [
                "## Decision",
                f"Proceed with {topic} for {_link(project.name)}.",
                "",
                "## Context",
                f"This decision follows {_link(meeting_titles[index % len(meeting_titles)])} and applies to {_link(project.company.name)}.",
                "",
                "## Supersession",
                (
                    f"Superseded by {_link(superseded_by)} after later stakeholder review. #superseded"
                    if superseded_by
                    else "Current decision remains active unless later evidence changes the operating picture."
                ),
                "",
                "## Action",
                f"- [ ] Review whether {_link(title)} changes open loops for {_link(project.name)} #follow-up",
            ]
        )
        notes.append(
            GeneratedNote(
                "Decisions",
                title,
                "decision",
                event_day,
                *lifecycle,
                body,
                {
                    "status": "superseded" if superseded else "active",
                    "project": f'"{_link(project.name)}"',
                    "company": f'"{_link(project.company.name)}"',
                },
            )
        )

    risk_dates = _business_dates(start + timedelta(days=18), spec["months"], spec["risks"])
    for index, event_day in enumerate(risk_dates):
        project = projects[index % len(projects)]
        topic = TOPICS[(index + 4) % len(TOPICS)]
        title = f"{project.name} {topic.title()} Risk {index + 1}"
        status = rng.choice(["open", "open", "mitigating", "closed"])
        lifecycle = _lifecycle(rng, event_day, "risk", late_capture_rate)
        body = "\n".join(
            [
                "## Risk",
                f"{topic.title()} may affect {_link(project.name)} for {_link(project.company.name)}.",
                "",
                "## Current State",
                f"- Status: `{status}`",
                f"- Owner: {_link(project.owner.name)}",
                f"- [ ] Reassess {_link(title)} during the next review #risk",
            ]
        )
        notes.append(
            GeneratedNote(
                "Risks",
                title,
                "risk",
                None,
                *lifecycle,
                body,
                {"status": status, "project": f'"{_link(project.name)}"'},
            )
        )

    research_dates = _business_dates(start + timedelta(days=7), spec["months"], spec["research"])
    for index, event_day in enumerate(research_dates):
        project = projects[index % len(projects)]
        topic = TOPICS[(index + 6) % len(TOPICS)]
        title = f"{project.name} {topic.title()} Research {index + 1}"
        lifecycle = _lifecycle(rng, event_day, "research", late_capture_rate)
        body = "\n".join(
            [
                "## Research Summary",
                f"Research on {topic} for {_link(project.name)} and {_link(project.company.name)}.",
                "",
                "## Evidence",
                f"- Interview notes from {_link(project.owner.name)}",
                f"- Related operating review: {_link(meeting_titles[index % len(meeting_titles)])}",
                "",
                "## Follow Up",
                f"- [ ] Convert findings into decision criteria for {_link(project.name)} #research",
            ]
        )
        notes.append(
            GeneratedNote(
                "Research",
                title,
                "research",
                None,
                *lifecycle,
                body,
                {"project": f'"{_link(project.name)}"', "company": f'"{_link(project.company.name)}"'},
            )
        )

    daily_dates = _business_dates(start, spec["months"], spec["daily"])
    daily_title_counts: dict[str, int] = {}
    for index, event_day in enumerate(daily_dates):
        project = projects[index % len(projects)]
        daily_title_base = event_day.isoformat()
        daily_title_count = daily_title_counts.get(daily_title_base, 0)
        daily_title_counts[daily_title_base] = daily_title_count + 1
        daily_title = (
            daily_title_base
            if daily_title_count == 0
            else f"{daily_title_base} Note {daily_title_count + 1}"
        )
        lifecycle = _lifecycle(rng, event_day, "daily", late_capture_rate)
        body = "\n".join(
            [
                "## Daily Log",
                f"Checked {_link(project.name)} for {_link(project.company.name)}.",
                f"Referenced {_link(meeting_titles[index % len(meeting_titles)])} while clearing follow-ups.",
                "",
                "## Tasks",
                f"- [ ] Update operating notes for {_link(project.name)} #ops",
                f"- [{'x' if index % 3 == 0 else ' '}] Send stakeholder recap to {_link(project.owner.name)} #follow-up",
            ]
        )
        notes.append(
            GeneratedNote(
                "Daily",
                daily_title,
                "daily",
                event_day,
                *lifecycle,
                body,
                {},
            )
        )
    return notes


def generate_synthetic_vault(
    output: Path,
    profile: str = "small",
    seed: int = 42,
    start_date: date = date(2025, 1, 6),
    months: int | None = None,
    force: bool = False,
    late_capture_rate: float = 0.12,
) -> dict[str, object]:
    if profile not in PROFILE_SPECS:
        raise ValueError(f"Unknown profile: {profile}")
    spec = dict(PROFILE_SPECS[profile])
    if months is not None:
        spec["months"] = months
    if output.exists():
        if not force:
            raise FileExistsError(f"{output} already exists; pass force=True to replace it")
        for child in output.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    output.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)
    companies, people, projects = _build_world(rng, start_date, spec)
    notes = []
    notes.extend(_company_notes(rng, companies, people, projects, late_capture_rate))
    notes.extend(_person_notes(rng, people, projects, late_capture_rate))
    notes.extend(_project_notes(rng, projects, late_capture_rate))
    notes.extend(_event_notes(rng, projects, spec, start_date, late_capture_rate))

    counts: dict[str, int] = {}
    for note in notes:
        folder = output / note.folder
        folder.mkdir(exist_ok=True)
        path = folder / f"{_safe_filename(note.title)}.md"
        path.write_text(_render(note), encoding="utf-8")
        counts[note.folder] = counts.get(note.folder, 0) + 1

    manifest = {
        "profile": profile,
        "seed": seed,
        "generated_at": f"{start_date.isoformat()}T00:00:00Z",
        "simulated_start": start_date.isoformat(),
        "simulated_end": (start_date + timedelta(days=spec["months"] * 30)).isoformat(),
        "counts": {**counts, "Total_Files": len(notes)},
        "scenario_packs": SCENARIOS,
        "late_capture_rate": late_capture_rate,
        "lifecycle_timestamp_fields": {
            "source_created_at": "When the underlying source artifact hypothetically came into existence.",
            "source_observed_at": "When the source artifact was hypothetically seen by the operator.",
            "created_at": "When the note was hypothetically added to the Obsidian vault.",
            "updated_at": "When the vault note was hypothetically last edited.",
        },
        "known_test_queries": [
            "timeline for Project Atlas 1",
            "open risks for active projects",
            "stakeholder follow-ups by company",
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obsidian-mcp-context-generate-vault",
        description="Generate a deterministic synthetic Obsidian vault for pipeline stress testing.",
    )
    parser.add_argument("--output", required=True, help="Directory to write the generated vault.")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_SPECS),
        default="small",
        help="Scale profile to generate.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Deterministic generation seed.")
    parser.add_argument(
        "--start-date",
        default="2025-01-06",
        help="Simulated start date in YYYY-MM-DD format.",
    )
    parser.add_argument("--months", type=int, help="Override simulated month span.")
    parser.add_argument(
        "--late-capture-rate",
        type=float,
        default=0.12,
        help="Probability that a note is added days after the source artifact appears.",
    )
    parser.add_argument("--force", action="store_true", help="Replace the output directory if it exists.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    manifest = generate_synthetic_vault(
        output=Path(args.output),
        profile=args.profile,
        seed=args.seed,
        start_date=date.fromisoformat(args.start_date),
        months=args.months,
        force=args.force,
        late_capture_rate=args.late_capture_rate,
    )
    print(json.dumps(manifest["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
