"""
ghost_score.py
---------------
THE CORE ALGORITHM OF THIS PROJECT.

Takes a deduplicated history of job postings (one company can post the
"same" job multiple times over weeks/months) and computes a 0-100
"Ghost Score" per posting + an aggregated per-company "Ghost Index".

WHAT MAKES A POSTING LOOK LIKE A "GHOST JOB"?
This is based on patterns reported by labor researchers, journalists, and
job seekers (e.g. resume.io's 2024 ghost job survey, Clarify Capital's 2023
hiring manager survey, MIT Sloan reporting on the phenomenon). We turn each
documented pattern into a measurable signal:

  1. REPOST FREQUENCY  -- same/near-identical title+company reposted many
     times over the period we track it. Real signal: companies sometimes
     keep a posting "evergreen" to build a resume pipeline without ever
     intending to hire right now.

  2. LISTING LONGEVITY  -- posting has been up far longer than the typical
     listing for that role/seniority. Real signal: most genuine roles get
     filled or pulled within a few weeks; a posting open 90+ days is unusual.

  3. SALARY RANGE WIDTH  -- the gap between posted salary_min and salary_max
     is implausibly wide (e.g. $50K-$150K for the same title). Real signal:
     pay-transparency-law postings sometimes use absurd ranges to satisfy
     the legal requirement without committing to real numbers.

  4. VAGUE / BOILERPLATE DESCRIPTION -- description is very short or reuses
     generic corporate language with few concrete role details. Real
     signal: postings meant mainly to "collect resumes" tend to be vague
     since no one is actually scoping a real role.

  5. RAPID REPOST AFTER "CLOSING" -- a posting disappears and a
     near-identical one reappears within days under a new ID. Real signal:
     some companies cycle postings to keep them appearing "fresh" in search
     rankings/algorithms.

Each signal is scored 0-100 individually, then combined with weights into
one Ghost Score. Weights are deliberately exposed as constants at the top
of the file so you can justify/tune them in an interview ("I weighted
repost frequency highest because it's the single most cited red flag in
hiring-manager surveys").
"""

from __future__ import annotations
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Dict, List, Optional

from base_adapter import JobPosting


# ---------------------------------------------------------------------------
# TUNABLE WEIGHTS -- these sum to 1.0. Adjust and justify in your write-up.
# ---------------------------------------------------------------------------
WEIGHTS = {
    "repost_frequency": 0.30,
    "listing_longevity": 0.25,
    "salary_range_width": 0.20,
    "vague_description": 0.15,
    "rapid_repost": 0.10,
}

# Thresholds used by individual signal scorers (tune as you collect real data)
TYPICAL_LISTING_LIFESPAN_DAYS = 30        # "normal" listings close within ~30 days
EXTREME_LISTING_LIFESPAN_DAYS = 90        # 90+ days open = max longevity score
PLAUSIBLE_SALARY_SPREAD_RATIO = 1.5       # max/min above this ratio looks suspicious
EXTREME_SALARY_SPREAD_RATIO = 3.0         # max/min above this = max width score
VAGUE_DESCRIPTION_WORD_THRESHOLD = 40     # fewer words than this = looks vague
TITLE_SIMILARITY_THRESHOLD = 0.85         # SequenceMatcher ratio to call titles "the same job"
RAPID_REPOST_WINDOW_DAYS = 10             # disappearing + reappearing within this window


@dataclass
class ScoredPosting:
    posting: JobPosting
    repost_count: int
    days_active: int
    ghost_score: float
    signal_breakdown: Dict[str, float]
    flags: List[str]


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation/seniority noise so 'Sr. Business Analyst II'
    and 'Senior Business Analyst 2' cluster as the same role."""
    t = title.lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\b(sr|senior|jr|junior|i|ii|iii|iv|v|level\s*\d)\b", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _titles_match(a: str, b: str) -> bool:
    return SequenceMatcher(None, _normalize_title(a), _normalize_title(b)).ratio() >= TITLE_SIMILARITY_THRESHOLD


def group_postings_by_role(postings: List[JobPosting]) -> Dict[str, List[JobPosting]]:
    """
    Groups raw postings into 'the same underlying job' clusters, keyed by
    (company, normalized_title). This is what lets us detect a job being
    reposted under a slightly different title or a new posting ID.
    """
    groups: Dict[str, List[JobPosting]] = defaultdict(list)
    for p in postings:
        key = f"{p.company.strip().lower()}::{_normalize_title(p.title)}"
        groups[key].append(p)
    return groups


def _score_repost_frequency(group: List[JobPosting]) -> float:
    """More distinct repost events -> higher score. Caps at 6+ reposts = 100."""
    distinct_ids = len({p.source_job_id for p in group})
    reposts = max(distinct_ids - 1, 0)  # first posting doesn't count as a "repost"
    return min(reposts / 6 * 100, 100)


def _score_listing_longevity(group: List[JobPosting]) -> float:
    """Looks at the earliest known post date vs the most recent scrape date."""
    dates_posted = [p.date_posted for p in group if p.date_posted]
    dates_scraped = [p.date_scraped for p in group if p.date_scraped]
    if not dates_posted or not dates_scraped:
        return 0.0
    earliest = min(dates_posted)
    latest_seen = max(dates_scraped)
    days_active = (latest_seen - earliest).days
    if days_active <= TYPICAL_LISTING_LIFESPAN_DAYS:
        return 0.0
    if days_active >= EXTREME_LISTING_LIFESPAN_DAYS:
        return 100.0
    span = EXTREME_LISTING_LIFESPAN_DAYS - TYPICAL_LISTING_LIFESPAN_DAYS
    return (days_active - TYPICAL_LISTING_LIFESPAN_DAYS) / span * 100


def _score_salary_width(group: List[JobPosting]) -> float:
    spreads = []
    for p in group:
        if p.salary_min and p.salary_max and p.salary_min > 0:
            spreads.append(p.salary_max / p.salary_min)
    if not spreads:
        return 0.0  # no salary disclosed -- can't penalize what we can't measure
    ratio = statistics.mean(spreads)
    if ratio <= PLAUSIBLE_SALARY_SPREAD_RATIO:
        return 0.0
    if ratio >= EXTREME_SALARY_SPREAD_RATIO:
        return 100.0
    span = EXTREME_SALARY_SPREAD_RATIO - PLAUSIBLE_SALARY_SPREAD_RATIO
    return (ratio - PLAUSIBLE_SALARY_SPREAD_RATIO) / span * 100


def _score_vague_description(group: List[JobPosting]) -> float:
    word_counts = [len(p.description_snippet.split()) for p in group if p.description_snippet]
    if not word_counts:
        return 50.0  # missing description entirely is itself a mild flag
    avg_words = statistics.mean(word_counts)
    if avg_words >= VAGUE_DESCRIPTION_WORD_THRESHOLD:
        return 0.0
    return max(0.0, (VAGUE_DESCRIPTION_WORD_THRESHOLD - avg_words) / VAGUE_DESCRIPTION_WORD_THRESHOLD * 100)


def _score_rapid_repost(group: List[JobPosting]) -> float:
    """Detects gaps in scrape coverage where a posting vanished then a new
    ID for 'the same job' appeared again shortly after -- the classic
    'closed and immediately reopened' ghost pattern."""
    sorted_group = sorted(group, key=lambda p: p.date_scraped)
    ids_seen_order = []
    for p in sorted_group:
        if not ids_seen_order or ids_seen_order[-1][0] != p.source_job_id:
            ids_seen_order.append((p.source_job_id, p.date_scraped))

    if len(ids_seen_order) < 2:
        return 0.0

    rapid_gaps = 0
    for i in range(1, len(ids_seen_order)):
        gap_days = (ids_seen_order[i][1] - ids_seen_order[i - 1][1]).days
        if 0 <= gap_days <= RAPID_REPOST_WINDOW_DAYS:
            rapid_gaps += 1

    return min(rapid_gaps / 3 * 100, 100)  # 3+ rapid re-appearances = max score


def score_all(postings: List[JobPosting]) -> List[ScoredPosting]:
    """
    Main entry point. Returns one ScoredPosting per ROLE GROUP (not per raw
    row), since the ghost pattern only shows up when you look across reposts.
    """
    groups = group_postings_by_role(postings)
    results: List[ScoredPosting] = []

    for key, group in groups.items():
        signals = {
            "repost_frequency": _score_repost_frequency(group),
            "listing_longevity": _score_listing_longevity(group),
            "salary_range_width": _score_salary_width(group),
            "vague_description": _score_vague_description(group),
            "rapid_repost": _score_rapid_repost(group),
        }
        ghost_score = sum(signals[k] * WEIGHTS[k] for k in WEIGHTS)

        flags = []
        if signals["repost_frequency"] >= 50:
            flags.append("Frequently reposted")
        if signals["listing_longevity"] >= 50:
            flags.append("Open far longer than typical")
        if signals["salary_range_width"] >= 50:
            flags.append("Implausibly wide salary range")
        if signals["vague_description"] >= 50:
            flags.append("Vague / boilerplate description")
        if signals["rapid_repost"] >= 50:
            flags.append("Closed and reopened rapidly")

        dates_posted = [p.date_posted for p in group if p.date_posted]
        dates_scraped = [p.date_scraped for p in group if p.date_scraped]
        days_active = (max(dates_scraped) - min(dates_posted)).days if dates_posted and dates_scraped else 0

        # representative posting = most recent one, for display purposes
        representative = max(group, key=lambda p: p.date_scraped)

        results.append(ScoredPosting(
            posting=representative,
            repost_count=max(len({p.source_job_id for p in group}) - 1, 0),
            days_active=days_active,
            ghost_score=round(ghost_score, 1),
            signal_breakdown={k: round(v, 1) for k, v in signals.items()},
            flags=flags,
        ))

    return sorted(results, key=lambda r: r.ghost_score, reverse=True)


def company_ghost_index(scored: List[ScoredPosting]) -> Dict[str, float]:
    """Aggregates role-level ghost scores up to a single per-company score,
    for the 'leaderboard of shadiest employers' view in Power BI."""
    by_company: Dict[str, List[float]] = defaultdict(list)
    for s in scored:
        by_company[s.posting.company].append(s.ghost_score)
    return {
        company: round(statistics.mean(scores), 1)
        for company, scores in by_company.items()
    }
