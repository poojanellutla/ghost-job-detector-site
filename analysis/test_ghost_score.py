"""
test_ghost_score.py
---------------------
Basic unit tests for the ghost scoring engine. Run with:
    python -m pytest test_ghost_score.py -v
or simply:
    python test_ghost_score.py

These tests don't aim for 100% coverage -- they exist to prove the core
signals behave the way the docstring in ghost_score.py claims they do,
which is exactly what you'd want to show in an interview ("I wrote tests
to validate that a frequently-reposted job actually scores higher than
a normal one, not just eyeballed it").
"""

import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scraper"))
sys.path.insert(0, os.path.dirname(__file__))

from base_adapter import JobPosting
from ghost_score import score_all, _normalize_title, _titles_match


def _make_posting(job_id, days_ago_posted, days_ago_scraped, salary_min=70000,
                   salary_max=80000, description="A reasonably detailed description " * 5,
                   company="TestCo", title="Business Analyst"):
    now = datetime(2026, 6, 17, tzinfo=timezone.utc)
    return JobPosting(
        source="test",
        source_job_id=job_id,
        title=title,
        company=company,
        location="Remote",
        salary_text=f"{salary_min}-{salary_max}",
        salary_min=salary_min,
        salary_max=salary_max,
        date_posted=now - timedelta(days=days_ago_posted),
        date_scraped=now - timedelta(days=days_ago_scraped),
        url="https://example.test/job",
        description_snippet=description,
    )


def test_normal_listing_scores_low():
    """A single posting, open for 10 days, normal salary, detailed
    description should score LOW (not flagged as a ghost job)."""
    postings = [_make_posting("id1", days_ago_posted=10, days_ago_scraped=2)]
    results = score_all(postings)
    assert len(results) == 1
    assert results[0].ghost_score < 20, f"expected low score, got {results[0].ghost_score}"
    print("PASS: test_normal_listing_scores_low")


def test_frequently_reposted_scores_high():
    """Same role, 5 different job IDs over the tracking window -> should
    trigger the repost_frequency signal heavily."""
    postings = [
        _make_posting(f"id{i}", days_ago_posted=80 - i * 15, days_ago_scraped=80 - i * 15)
        for i in range(5)
    ]
    results = score_all(postings)
    assert len(results) == 1
    assert results[0].repost_count == 4
    assert results[0].signal_breakdown["repost_frequency"] >= 50
    print("PASS: test_frequently_reposted_scores_high")


def test_wide_salary_range_flagged():
    """A $50K min / $180K max range should trigger salary_range_width."""
    postings = [_make_posting("id1", 10, 2, salary_min=50000, salary_max=180000)]
    results = score_all(postings)
    assert results[0].signal_breakdown["salary_range_width"] > 50
    assert "Implausibly wide salary range" in results[0].flags
    print("PASS: test_wide_salary_range_flagged")


def test_long_open_listing_flagged():
    """A listing posted 100 days ago and still showing up should trigger
    listing_longevity."""
    postings = [_make_posting("id1", days_ago_posted=100, days_ago_scraped=1)]
    results = score_all(postings)
    assert results[0].signal_breakdown["listing_longevity"] >= 90
    print("PASS: test_long_open_listing_flagged")


def test_vague_description_flagged():
    """A very short, generic description should trigger vague_description."""
    postings = [_make_posting("id1", 10, 2, description="Join our team and grow with us.")]
    results = score_all(postings)
    assert results[0].signal_breakdown["vague_description"] > 50
    print("PASS: test_vague_description_flagged")


def test_title_normalization_clusters_variants():
    """'Sr. Business Analyst II' and 'Senior Business Analyst 2' should be
    treated as the same underlying role."""
    assert _titles_match("Sr. Business Analyst II", "Senior Business Analyst 2")
    assert not _titles_match("Business Analyst", "Software Engineer")
    print("PASS: test_title_normalization_clusters_variants")


def test_different_companies_not_merged():
    """Same title at two different companies must NOT be grouped together."""
    postings = [
        _make_posting("id1", 10, 2, company="Company A"),
        _make_posting("id2", 10, 2, company="Company B"),
    ]
    results = score_all(postings)
    assert len(results) == 2, "Expected 2 separate groups, postings were incorrectly merged"
    print("PASS: test_different_companies_not_merged")


if __name__ == "__main__":
    test_normal_listing_scores_low()
    test_frequently_reposted_scores_high()
    test_wide_salary_range_flagged()
    test_long_open_listing_flagged()
    test_vague_description_flagged()
    test_title_normalization_clusters_variants()
    test_different_companies_not_merged()
    print("\nAll tests passed.")
