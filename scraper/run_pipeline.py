"""
run_pipeline.py
-----------------
THE SCRIPT YOU RUN GOING FORWARD to keep collecting REAL data.

What it does each time you run it:
  1. Scrapes current postings from RemoteOK (and optionally Indeed) for
     your chosen search query.
  2. Appends today's results to data/job_postings_raw.csv (building real
     history day by day -- this is what eventually lets the ghost score
     reflect REAL repost/longevity patterns instead of the seeded demo).
  3. Re-runs the ghost scoring algorithm across ALL accumulated history
     (seed + real) and rewrites scored_postings.csv + company_ghost_index.csv.

HOW TO USE THIS FOR REAL, ONGOING TRACKING:
  - Run this once a day (e.g. via Windows Task Scheduler, a cron job, or
    just manually) for a few weeks.
  - Each run adds one more day of REAL observations on top of the seed data.
  - Within ~2-3 weeks you'll have enough real repost/longevity signal that
    you could optionally drop the seed data entirely and rebuild on 100%
    real data -- at that point your dashboard is fully real-world.

USAGE:
    python run_pipeline.py --query "business analyst" --sources remoteok
    python run_pipeline.py --query "business analyst" --sources remoteok,indeed
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", "analysis"))

from base_adapter import JobPosting
from remoteok_adapter import RemoteOKAdapter
from indeed_adapter import IndeedAdapter
from ghost_score import score_all, company_ghost_index
from generate_seed_dataset import write_scored_csv, write_company_index_csv

DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
RAW_CSV = os.path.join(DATA_DIR, "job_postings_raw.csv")
SCORED_CSV = os.path.join(DATA_DIR, "scored_postings.csv")
COMPANY_CSV = os.path.join(DATA_DIR, "company_ghost_index.csv")


def load_existing_raw_postings():
    """Reads back everything already in job_postings_raw.csv (seed + prior
    real runs) so today's scoring considers full history, not just today."""
    if not os.path.exists(RAW_CSV):
        return []

    postings = []
    with open(RAW_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            postings.append(JobPosting(
                source=row["source"],
                source_job_id=row["source_job_id"],
                title=row["title"],
                company=row["company"],
                location=row["location"],
                salary_text=row["salary_text"] or None,
                salary_min=float(row["salary_min"]) if row["salary_min"] else None,
                salary_max=float(row["salary_max"]) if row["salary_max"] else None,
                date_posted=datetime.fromisoformat(row["date_posted"]).replace(tzinfo=timezone.utc) if row["date_posted"] else None,
                date_scraped=datetime.fromisoformat(row["date_scraped"]).replace(tzinfo=timezone.utc) if row["date_scraped"] else None,
                url=row["url"],
                description_snippet=row.get("description_snippet", ""),
            ))
    return postings


def append_raw_postings(new_postings):
    file_exists = os.path.exists(RAW_CSV)
    with open(RAW_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "source", "source_job_id", "title", "company", "location",
                "salary_text", "salary_min", "salary_max",
                "date_posted", "date_scraped", "url", "description_snippet"
            ])
        for p in new_postings:
            writer.writerow([
                p.source, p.source_job_id, p.title, p.company, p.location,
                p.salary_text, p.salary_min, p.salary_max,
                p.date_posted.date().isoformat() if p.date_posted else "",
                p.date_scraped.date().isoformat() if p.date_scraped else "",
                p.url, p.description_snippet,
            ])


def main():
    parser = argparse.ArgumentParser(description="Run one day's ghost-job scraping + scoring cycle.")
    parser.add_argument("--query", default="business analyst", help="Search keyword(s)")
    parser.add_argument("--sources", default="remoteok", help="Comma-separated: remoteok,indeed")
    parser.add_argument("--max-results", type=int, default=50)
    args = parser.parse_args()

    sources = [s.strip().lower() for s in args.sources.split(",")]
    new_postings = []

    if "remoteok" in sources:
        print("Scraping RemoteOK...")
        new_postings.extend(RemoteOKAdapter().fetch_postings(args.query, args.max_results))

    if "indeed" in sources:
        print("Scraping Indeed (this one is slower/politer by design)...")
        new_postings.extend(IndeedAdapter().fetch_postings(args.query, args.max_results))

    print(f"Scraped {len(new_postings)} postings today.")

    if new_postings:
        append_raw_postings(new_postings)
        print(f"Appended to {RAW_CSV}")

    print("Re-scoring full history (seed + all real runs so far)...")
    all_postings = load_existing_raw_postings()
    scored = score_all(all_postings)
    write_scored_csv(scored, SCORED_CSV)
    index = company_ghost_index(scored)
    write_company_index_csv(index, scored, COMPANY_CSV)

    print(f"Done. {len(scored)} role groups scored across {len(all_postings)} total observations.")
    print("Top 5 ghostiest roles right now:")
    for s in scored[:5]:
        print(f"  {s.ghost_score:>5.1f}  {s.posting.company} - {s.posting.title}")


if __name__ == "__main__":
    main()
