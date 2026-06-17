# Ghost Job Detector

**Live site:** add your GitHub Pages URL here once deployed

Detects "ghost jobs" — postings companies keep open (or repeatedly repost) without any real intent to hire soon — using a real Python web scraper, an original weighted scoring algorithm, and a public dashboard.

## What's in this repo

This repo contains the full project end to end: the live website, the Python scraper that collects job posting data, the scoring engine that flags suspicious listings, and the data it has produced so far.
## How it works

Every job posting is scored 0–100 based on five signals, each tied to a documented real-world ghost-job pattern: how often a role gets reposted, how long it stays open, how wide its salary range is, how vague its description is, and whether it disappears and reappears suspiciously fast. The five scores combine into one Ghost Score, and roles are bucketed into Low / Medium / High / Critical tiers.

Full methodology, weights, and reasoning are documented in `analysis/ghost_score.py`.

## Running it yourself

```bash
pip install -r requirements.txt
cd analysis && python test_ghost_score.py      # confirm everything works
cd ../scraper && python run_pipeline.py --query "business analyst" --sources remoteok
```

## A note on the data

This project combines a generated 90-day simulated history (so the dashboard has enough depth to be useful immediately) with real, ongoing scrapes from public job boards. The scoring algorithm runs identically on both — nothing about the analysis itself is simulated, only some of the historical raw input. The scraper is actively designed to keep collecting real data over time, gradually replacing the simulated portion.

LinkedIn was deliberately not scraped: it requires login to view search results, aggressively blocks automated scraping, and has pursued legal action against scrapers in the past (hiQ Labs v. LinkedIn). That tradeoff felt worth naming rather than ignoring.

## Also available

A companion Power BI dashboard (.pbix) built on the same data is available on request / linked separately — built and screenshot-ready for walkthroughs in interviews.
