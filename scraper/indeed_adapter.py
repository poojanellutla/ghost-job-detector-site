"""
indeed_adapter.py
------------------
Scrapes Indeed's PUBLIC, no-login search results pages.

IMPORTANT CONTEXT (read before running):
Indeed's public search results (the page you get when you search without
being logged in) are HTML, not a clean API, so this adapter does real
HTML parsing -- this is "actual scraping" in the traditional sense, unlike
the RemoteOK adapter which just calls a JSON feed.

Because it's HTML scraping against a major site, expect:
  - Occasional CAPTCHA/verification walls if you request too fast or too
    often from the same IP. The delay + header settings below reduce this
    but cannot eliminate it.
  - Indeed's page structure (CSS class names, layout) changes periodically.
    If this stops returning results, the most likely cause is the HTML
    structure changed and the CSS selectors below need updating -- that's
    normal scraper maintenance, not a sign anything is "broken" with your
    approach.
  - Run this from your own machine/network (NOT a shared cloud sandbox IP),
    with reasonable delays, and don't hammer it with thousands of requests.

This script respects a polite delay between requests and only scrapes
the publicly rendered search result page (no login, no bypassing any
paywall or auth wall).
"""

import re
import time
import random
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from base_adapter import JobBoardAdapter, JobPosting


class IndeedAdapter(JobBoardAdapter):
    name = "indeed"

    SEARCH_URL = "https://www.indeed.com/jobs"

    def __init__(self, polite_delay_range=(2.5, 5.0)):
        self.polite_delay_range = polite_delay_range
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        })

    def _parse_relative_date(self, text: str) -> Optional[datetime]:
        """Indeed shows dates like 'Posted 3 days ago', 'Just posted', 'Today'."""
        if not text:
            return None
        text = text.lower().strip()
        now = datetime.now(timezone.utc)
        if "just posted" in text or "today" in text:
            return now
        match = re.search(r"(\d+)\s*day", text)
        if match:
            return now - timedelta(days=int(match.group(1)))
        match = re.search(r"(\d+)\s*\+?\s*day", text)
        if match:
            return now - timedelta(days=int(match.group(1)))
        if "30+" in text:
            return now - timedelta(days=30)
        return None

    def _parse_salary(self, text: str):
        """Parses strings like '$60,000 - $80,000 a year' into (min, max)."""
        if not text:
            return None, None
        nums = re.findall(r"\$?([\d,]+(?:\.\d+)?)", text)
        nums = [float(n.replace(",", "")) for n in nums]
        if not nums:
            return None, None
        if "hour" in text.lower():
            nums = [n * 40 * 52 for n in nums]  # rough annualization
        if len(nums) == 1:
            return nums[0], nums[0]
        return min(nums), max(nums)

    def fetch_postings(self, query: str, max_results: int = 50,
                        location: str = "") -> List[JobPosting]:
        postings: List[JobPosting] = []
        start = 0

        while len(postings) < max_results:
            params = {"q": query, "l": location, "start": start}
            try:
                resp = self.session.get(self.SEARCH_URL, params=params, timeout=15)
            except requests.RequestException as e:
                print(f"[indeed] request failed: {e}")
                break

            if resp.status_code == 403 or "captcha" in resp.text.lower():
                print("[indeed] hit a bot-check wall. Stop and retry later "
                      "with a longer delay, or reduce request volume.")
                break

            if resp.status_code != 200:
                print(f"[indeed] unexpected status {resp.status_code}, stopping")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("div.job_seen_beacon, div.cardOutline")
            if not cards:
                print("[indeed] no job cards found on page -- either no more "
                      "results, or Indeed changed their HTML structure and "
                      "selectors need updating.")
                break

            for card in cards:
                title_el = card.select_one("h2.jobTitle span")
                company_el = card.select_one("span.companyName")
                location_el = card.select_one("div.companyLocation")
                salary_el = card.select_one("div.salary-snippet-container, div.metadata.salary-snippet-container")
                date_el = card.select_one("span.date")
                link_el = card.select_one("h2.jobTitle a")
                snippet_el = card.select_one("div.job-snippet")

                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue  # skip malformed cards rather than crash

                salary_text = salary_el.get_text(strip=True) if salary_el else None
                salary_min, salary_max = self._parse_salary(salary_text) if salary_text else (None, None)

                job_id = link_el.get("data-jk") if link_el else None
                url = f"https://www.indeed.com/viewjob?jk={job_id}" if job_id else self.SEARCH_URL

                postings.append(JobPosting(
                    source=self.name,
                    source_job_id=job_id or f"{title}-{company_el.get_text(strip=True) if company_el else ''}",
                    title=title,
                    company=company_el.get_text(strip=True) if company_el else "Unknown",
                    location=location_el.get_text(strip=True) if location_el else location,
                    salary_text=salary_text,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    date_posted=self._parse_relative_date(date_el.get_text(strip=True) if date_el else ""),
                    date_scraped=datetime.now(timezone.utc),
                    url=url,
                    description_snippet=snippet_el.get_text(strip=True) if snippet_el else "",
                ))

                if len(postings) >= max_results:
                    break

            start += 10
            # Randomized delay -- this is what "polite scraping" means in practice.
            # A fixed delay is easy for bot-detection to fingerprint; randomizing
            # within a range looks more like natural browsing.
            time.sleep(random.uniform(*self.polite_delay_range))

        return postings


if __name__ == "__main__":
    adapter = IndeedAdapter()
    results = adapter.fetch_postings(query="business analyst", max_results=20)
    print(f"Fetched {len(results)} postings from Indeed")
    for p in results[:5]:
        print(f"  - {p.title} @ {p.company} ({p.location}) posted={p.date_posted}")
