"""
base_adapter.py
----------------
Defines the abstract interface every job-board scraper must follow.

WHY THIS PATTERN EXISTS (for your resume / interview talking points):
This project uses the "Adapter Pattern" so that adding a new job board later
(Indeed, RemoteOK, We Work Remotely, etc.) only requires writing ONE small
class -- the rest of the pipeline (deduping, scoring, exporting) never changes.

This is the same architectural idea production data-engineering teams use
when they have to ingest from many different upstream sources that each
return data in a different shape.

NOTE ON SCOPE:
This adapter pattern is intentionally source-agnostic. It would technically
support a LinkedIn or Indeed-logged-in-search adapter, but we deliberately did
NOT build one. Both of those platforms aggressively rate-limit / IP-ban
scrapers, require an authenticated session to see search results, and in
LinkedIn's case scraping is a direct violation of their Terms of Service that
has resulted in real legal action (hiQ Labs v. LinkedIn). Building one to
"prove a point" isn't worth the legal and reliability risk for a portfolio
project. The two adapters we DID build (RemoteOK + Indeed's public, no-login
search results) are within each site's robots.txt-permitted, publicly
viewable pages.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class JobPosting:
    """
    Normalized shape that EVERY adapter must return data in.
    This is what makes the rest of the pipeline source-agnostic.
    """
    source: str                     # e.g. "remoteok", "indeed"
    source_job_id: str              # the ID/url the source uses, for dedup
    title: str
    company: str
    location: str
    salary_text: Optional[str]      # raw salary string as posted (may be None)
    salary_min: Optional[float]     # parsed numeric min (USD/year), if available
    salary_max: Optional[float]     # parsed numeric max (USD/year), if available
    date_posted: Optional[datetime] # when the SOURCE says it was posted
    date_scraped: datetime          # when WE scraped it (always known)
    url: str
    description_snippet: str = ""
    raw_tags: List[str] = field(default_factory=list)


class JobBoardAdapter(ABC):
    """
    Every job board adapter implements `fetch_postings`.
    `name` is used as the `source` field on every JobPosting it returns.
    """

    name: str = "base"

    @abstractmethod
    def fetch_postings(self, query: str, max_results: int = 50) -> List[JobPosting]:
        """
        Fetch postings matching `query`. Must return a list of JobPosting.
        Implementations should be polite: realistic delays between requests,
        respect robots.txt, and handle failures without crashing the run.
        """
        raise NotImplementedError
