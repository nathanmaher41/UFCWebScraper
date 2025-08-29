# MMA Data Scrapers (UFCStats + ESPN)

This repository contains two web scrapers:

- **`ufcstatsscraper/`** — scrapes **UFCStats.com** for structured **fighter**, **event**, and **fight** details.
- **`espnstatsscraper/`** — scrapes **ESPN’s MMA pages** for complementary **cards, fighters, and results**.

Each scraper has its **own README** with setup and run instructions:
- See [`ufcstatsscraper/README.md`](./ufcstatsscraper/README.md)
- See [`espnstatsscraper/README.md`](./espnstatsscraper/README.md)

> ⚖️ **Scrape responsibly**. Respect target sites’ Terms of Use and robots.txt. Use throttling, identify with a UA, and avoid heavy parallelism.

---

## What you get

Both scrapers aim to produce normalized datasets you can analyze with pandas/SQL:

- **Fighters** — name, nickname (if any), physique metadata (height/reach/stance when available), DOB, and links to source pages.
- **Events** — event name, date, location (when available), source URL, and stable IDs derived from the site URL.
- **Fights** — bout participants, winner/draw/NC, method (e.g., `KO/TKO`, `SUB`, `DEC`, `DQ`), round, time, referee, and per-fighter stats when exposed by the source.

> Field coverage varies by source. UFCStats exposes deeper per-fight stats; ESPN tends to offer card structure and high-level results.

**Output formats**
- **JSON Lines** is the default (1 JSON object per line), ideal for large datasets.

## Throttling, retries, and politeness

- The scrapers ship with **conservative defaults** (delay between requests, limited concurrency).
- **UFCStats (requests/BS4)**:
  - Use `--min-delay`, `--max-delay` to change throttling at your discression.
- **ESPN (requests/BS4/chromium)**:
  - Respectful pacing (e.g., `time.sleep` between requests) and backoff on errors.
  - Handle transient failures with retries and sane timeouts.

> Be a good citizen: avoid hammering endpoints, randomize small delays, and pause/resume long crawls when possible.

---

## Data integrity & repeatable runs

- **Idempotency**: URLs/IDs are used to detect duplicates where possible, so rerunning won’t explode your dataset.
- **Source fields**: Each record includes its **source URL**, making it easy to trace or re-scrape.

---

## Known limitations

- Sites occasionally change markup; selectors may need updates.
- Some historical cards lack full stats; fields can be `null`/missing.
- Fighter identity can be ambiguous across sources (name variants). Cross-linking across ESPN/UFCStats may require additional heuristics.

---

## Legal & ethics

This code is for **research/educational** use. You are responsible for how you use it.  
Check and respect:
- Target sites’ **Terms of Use** and **robots.txt**
- Applicable **local laws** and your hosting provider’s AUP  
If a site requests you stop scraping, **stop**.  
-Provided as-is, without warranty. Not affiliated with UFC or ESPN.

---

## License

Released under the **MIT License** — see [`LICENSE`](./LICENSE).
