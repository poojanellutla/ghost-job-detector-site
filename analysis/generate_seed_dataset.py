"""
generate_seed_dataset.py
--------------------------
Generates a REALISTIC historical dataset simulating ~90 days of daily
scraping runs, so the Power BI dashboard has enough time-series depth to
show ghost-job patterns immediately -- without you having to wait 90 real
days for the live scraper to accumulate that history.

WHY THIS IS HONEST TO USE:
This produces data in the EXACT same JobPosting structure the real
scrapers (remoteok_adapter.py / indeed_adapter.py) produce. The ghost_score
algorithm in ghost_score.py runs IDENTICALLY on this seed data and on real
scraped data -- nothing about the scoring logic is faked or hardcoded for
this dataset. You're simulating the RAW INPUT (what postings looked like
each day), not the ANALYSIS (which is 100% the same real algorithm).

This mirrors a totally standard real-world practice: data engineers
generate synthetic data with known properties to test/demo a pipeline
before enough real production data has accumulated.

OUTPUT:
  data/job_postings_raw.csv       -- one row per (posting, day scraped) --
                                      mimics raw daily scraper output
  data/scored_postings.csv        -- one row per role group, ghost-scored
  data/company_ghost_index.csv    -- one row per company, aggregated score
"""

import csv
import random
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scraper"))
sys.path.insert(0, os.path.dirname(__file__))

from base_adapter import JobPosting
from ghost_score import score_all, company_ghost_index

random.seed(42)  # reproducible output

TITLES = [
    "Business Analyst", "Senior Business Analyst", "Data Analyst",
    "Business Intelligence Analyst", "Junior Business Analyst",
    "Business Systems Analyst", "Product Analyst", "Operations Analyst",
]

LOCATIONS = ["Remote", "New York, NY", "Chicago, IL", "Austin, TX",
             "St. Louis, MO", "San Francisco, CA", "Atlanta, GA"]

# Companies with an assigned "ghost tendency" -- the probability-driving
# parameter that shapes how that company's postings behave in the simulation.
# Real companies are NOT named here on purpose (avoids defamation risk in
# a public portfolio project) -- use clearly fictional company names.
COMPANIES = {
    "Nimbus Retail Group":       {"ghost_tendency": 0.85, "num_roles": 3},
    "Vantage Data Solutions":    {"ghost_tendency": 0.80, "num_roles": 2},
    "BrightPath Consulting":     {"ghost_tendency": 0.75, "num_roles": 2},
    "Continental Freight Co.":   {"ghost_tendency": 0.20, "num_roles": 2},
    "Lakeside Health Systems":   {"ghost_tendency": 0.15, "num_roles": 3},
    "Granite Peak Financial":    {"ghost_tendency": 0.65, "num_roles": 2},
    "Maple & Co. Insurance":     {"ghost_tendency": 0.10, "num_roles": 2},
    "Orbit Software Inc.":       {"ghost_tendency": 0.55, "num_roles": 3},
    "Harbor Logistics":          {"ghost_tendency": 0.30, "num_roles": 1},
    "Summit Manufacturing":      {"ghost_tendency": 0.05, "num_roles": 2},
    "Pinnacle Retail Analytics": {"ghost_tendency": 0.90, "num_roles": 2},
    "Cedarwood Bank":            {"ghost_tendency": 0.40, "num_roles": 2},
    "BlueRiver Tech":            {"ghost_tendency": 0.70, "num_roles": 2},
    "Meridian Healthcare Group": {"ghost_tendency": 0.25, "num_roles": 2},
    "Falcon Aerospace":          {"ghost_tendency": 0.10, "num_roles": 2},
}

SOURCES = ["indeed", "remoteok"]

SIM_START = datetime(2026, 3, 19, tzinfo=timezone.utc)  # ~90 days before "today" in-story
SIM_DAYS = 90

VAGUE_SNIPPET = (
    "Join our team and make an impact. We are looking for talented "
    "individuals to help drive our business forward. Great culture, "
    "competitive pay."
)
DETAILED_SNIPPET = (
    "You will own the weekly KPI reporting cycle for the merchandising "
    "org, partner directly with category managers to define requirements, "
    "build and maintain Power BI dashboards used by 40+ stakeholders, and "
    "lead a quarterly deep-dive analysis presented to VP-level leadership. "
    "Requires SQL, Power BI or Tableau, and 2+ years in a similar role."
)


def make_role_id(company, title):
    return f"{company}::{title}"


def simulate_company_role(company, tendency, title, role_index):
    """
    Simulates ~90 days of scrape history for ONE role at ONE company.
    Returns a list of JobPosting (one row per day it was observed live).
    """
    postings = []
    location = random.choice(LOCATIONS)

    # Salary band realism: ghostier companies are more likely to post an
    # absurdly wide range (a commonly reported pay-transparency-law workaround)
    base_min = random.randint(55, 75) * 1000
    if random.random() < tendency:
        spread_ratio = random.uniform(2.2, 3.5)   # wide / suspicious
    else:
        spread_ratio = random.uniform(1.05, 1.4)  # tight / normal
    base_max = round(base_min * spread_ratio, -2)  # round to nearest $100 for clean display

    description = VAGUE_SNIPPET if random.random() < tendency else DETAILED_SNIPPET

    # Decide how many times this role gets "reposted" (new job ID issued)
    # across the 90-day window, driven by ghost tendency.
    if tendency > 0.6:
        num_repost_cycles = random.randint(3, 6)
    elif tendency > 0.3:
        num_repost_cycles = random.randint(1, 3)
    else:
        num_repost_cycles = random.randint(0, 1)

    # Build the timeline of "posting cycles" -- each cycle is a fresh job ID
    # appearing, staying live for some days, then either closing for good
    # or (for ghosty companies) reopening quickly.
    cycles = []
    day_cursor = random.randint(0, 10)  # first appearance, near start of window
    for cycle_num in range(num_repost_cycles + 1):
        if day_cursor >= SIM_DAYS:
            break
        if tendency > 0.6:
            lifespan = random.randint(35, 70)   # stays open a long time
        elif tendency > 0.3:
            lifespan = random.randint(20, 45)
        else:
            lifespan = random.randint(7, 28)    # closes at a normal pace

        lifespan = min(lifespan, SIM_DAYS - day_cursor)
        cycles.append((day_cursor, lifespan))

        if tendency > 0.6:
            gap = random.randint(1, 8)   # rapid reopen = ghost signal
        else:
            gap = random.randint(10, 40)  # long gap or never reopens
        day_cursor += lifespan + gap

    for cycle_idx, (start_day, lifespan) in enumerate(cycles):
        job_id = f"{company[:4].upper()}-{role_index}-{cycle_idx}-{random.randint(1000,9999)}"
        date_posted = SIM_START + timedelta(days=start_day)
        source = random.choice(SOURCES)

        # Simulate the scraper "seeing" this posting periodically while live
        # (every 4-7 days, like a scheduled scrape job would run)
        scrape_day = start_day
        while scrape_day <= start_day + lifespan and scrape_day <= SIM_DAYS:
            postings.append(JobPosting(
                source=source,
                source_job_id=job_id,
                title=title,
                company=company,
                location=location,
                salary_text=f"${base_min:,.0f} - ${base_max:,.0f}",
                salary_min=round(base_min, 0),
                salary_max=round(base_max, 0),
                date_posted=date_posted,
                date_scraped=SIM_START + timedelta(days=scrape_day),
                url=f"https://example-jobboard.test/job/{job_id}",
                description_snippet=description,
                raw_tags=[],
            ))
            scrape_day += random.randint(4, 7)

    return postings


def generate_all_postings():
    all_postings = []
    for company, cfg in COMPANIES.items():
        for role_index in range(cfg["num_roles"]):
            title = random.choice(TITLES)
            all_postings.extend(
                simulate_company_role(company, cfg["ghost_tendency"], title, role_index)
            )
    return all_postings


def write_raw_csv(postings, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "source", "source_job_id", "title", "company", "location",
            "salary_text", "salary_min", "salary_max",
            "date_posted", "date_scraped", "url", "description_snippet"
        ])
        for p in postings:
            writer.writerow([
                p.source, p.source_job_id, p.title, p.company, p.location,
                p.salary_text, p.salary_min, p.salary_max,
                p.date_posted.date().isoformat() if p.date_posted else "",
                p.date_scraped.date().isoformat() if p.date_scraped else "",
                p.url, p.description_snippet,
            ])


def ghost_tier(score):
    if score >= 60:
        return "Critical"
    elif score >= 40:
        return "High"
    elif score >= 20:
        return "Medium"
    else:
        return "Low"


def write_scored_csv(scored, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "company", "title", "location", "source",
            "repost_count", "days_active", "ghost_score", "ghost_tier",
            "repost_frequency_signal", "listing_longevity_signal",
            "salary_range_width_signal", "vague_description_signal",
            "rapid_repost_signal", "flags", "salary_min", "salary_max",
            "url", "last_seen_date",
        ])
        for s in scored:
            p = s.posting
            writer.writerow([
                p.company, p.title, p.location, p.source,
                s.repost_count, s.days_active, s.ghost_score, ghost_tier(s.ghost_score),
                s.signal_breakdown["repost_frequency"],
                s.signal_breakdown["listing_longevity"],
                s.signal_breakdown["salary_range_width"],
                s.signal_breakdown["vague_description"],
                s.signal_breakdown["rapid_repost"],
                "; ".join(s.flags) if s.flags else "None",
                p.salary_min, p.salary_max, p.url,
                p.date_scraped.date().isoformat() if p.date_scraped else "",
            ])


def write_company_index_csv(index_dict, scored, path):
    # also compute total roles tracked + total reposts per company for context
    roles_per_company = {}
    reposts_per_company = {}
    first_seen_per_company = {}
    for s in scored:
        c = s.posting.company
        roles_per_company[c] = roles_per_company.get(c, 0) + 1
        reposts_per_company[c] = reposts_per_company.get(c, 0) + s.repost_count
        seen_date = s.posting.date_posted.date().isoformat() if s.posting.date_posted else None
        if seen_date and (c not in first_seen_per_company or seen_date < first_seen_per_company[c]):
            first_seen_per_company[c] = seen_date

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["company", "ghost_index", "ghost_tier", "roles_tracked",
                          "total_reposts_detected", "earliest_posting_tracked"])
        for company, score in sorted(index_dict.items(), key=lambda x: x[1], reverse=True):
            writer.writerow([
                company, score, ghost_tier(score),
                roles_per_company.get(company, 0),
                reposts_per_company.get(company, 0),
                first_seen_per_company.get(company, ""),
            ])


if __name__ == "__main__":
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(out_dir, exist_ok=True)

    print("Simulating 90 days of scrape history across", len(COMPANIES), "companies...")
    postings = generate_all_postings()
    print(f"  -> generated {len(postings)} raw posting-observation rows")

    write_raw_csv(postings, os.path.join(out_dir, "job_postings_raw.csv"))

    scored = score_all(postings)
    write_scored_csv(scored, os.path.join(out_dir, "scored_postings.csv"))

    index = company_ghost_index(scored)
    write_company_index_csv(index, scored, os.path.join(out_dir, "company_ghost_index.csv"))

    print(f"  -> scored {len(scored)} distinct role groups")
    print(f"  -> wrote job_postings_raw.csv, scored_postings.csv, company_ghost_index.csv to {out_dir}")
    print()
    print("Top 5 ghostiest roles:")
    for s in scored[:5]:
        print(f"  {s.ghost_score:>5.1f}  {s.posting.company} - {s.posting.title}  [{', '.join(s.flags)}]")
