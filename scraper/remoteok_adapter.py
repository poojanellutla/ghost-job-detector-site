"""
remoteok_adapter.py
--------------------
RemoteOK publishes a free, public JSON feed of its job listings at
https://remoteok.com/api -- this is explicitly intended for reuse (it's how
their own RSS/JSON widgets work) and requires no login, no API key, and no
aggressive bot-blocking. This makes it the most reliable REAL data source
for this project.

Run this file directly to test it:
    python remoteok_adapter.py
"""

import time
import requests
from datetime import datetime, timezone
from typing import List

from base_adapter import JobBoardAdapter, JobPosting


class RemoteOKAdapter(JobBoardAdapter):
    name = "remoteok"

    BASE_URL = "https://remoteok.com/api"

    def __init__(self, polite_delay_seconds: float = 1.5):
        self.polite_delay_seconds = polite_delay_seconds
        self.session = requests.Session()
        # A descriptive User-Agent is good scraping etiquette -- it tells
        # the site who's hitting them and why, instead of pretending to be
        # a browser.
        self.session.headers.update({
            "User-Agent": "GhostJobDetector/1.0 (student portfolio project; contact: replace-with-your-email)"
        })

    def fetch_postings(self, query: str = "", max_results: int = 100) -> List[JobPosting]:
        try:
            resp = self.session.get(self.BASE_URL, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[remoteok] request failed: {e}")
            return []

        time.sleep(self.polite_delay_seconds)  # be polite even though this endpoint is light

        try:
            raw = resp.json()
        except ValueError:
            print("[remoteok] response was not valid JSON")
            return []

        # RemoteOK's feed returns a "legal notice" dict as the FIRST element.
        # Real entries start from index 1 onward.
        entries = raw[1:] if len(raw) > 1 else []

        postings: List[JobPosting] = []
        query_lower = query.lower().strip()

        for entry in entries:
            title = entry.get("position", "") or entry.get("title", "")
            if query_lower and query_lower not in title.lower():
                continue  # simple keyword filter, mirrors how a user would search

            posted_ts = entry.get("epoch") or entry.get("date")
            date_posted = None
            if isinstance(posted_ts, (int, float)):
                try:
                    date_posted = datetime.fromtimestamp(posted_ts, tz=timezone.utc)
                except (ValueError, OSError):
                    date_posted = None

            salary_min = entry.get("salary_min")
            salary_max = entry.get("salary_max")

            postings.append(JobPosting(
                source=self.name,
                source_job_id=str(entry.get("id", entry.get("slug", ""))),
                title=title.strip(),
                company=(entry.get("company", "") or "").strip(),
                location=(entry.get("location", "") or "Remote").strip(),
                salary_text=f"{salary_min}-{salary_max}" if salary_min or salary_max else None,
                salary_min=float(salary_min) if salary_min else None,
                salary_max=float(salary_max) if salary_max else None,
                date_posted=date_posted,
                date_scraped=datetime.now(timezone.utc),
                url=entry.get("url", ""),
                description_snippet=(entry.get("description", "") or "")[:300],
                raw_tags=entry.get("tags", []) or [],
            ))

            if len(postings) >= max_results:
                break

        return postings


if __name__ == "__main__":
    adapter = RemoteOKAdapter()
    results = adapter.fetch_postings(query="business analyst", max_results=20)
    print(f"Fetched {len(results)} postings from RemoteOK")
    for p in results[:5]:
        print(f"  - {p.title} @ {p.company} ({p.location}) posted={p.date_posted}")
