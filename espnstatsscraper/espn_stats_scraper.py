import requests
import time
import random
import json
import re
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Optional, Tuple, Any
import argparse
import os
import logging
from datetime import datetime
import unicodedata

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Warning: Playwright not installed. Browser automation will not be available.")
    print("Install with: pip install playwright && playwright install chromium")

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
}

class ESPNMMAScraper:
    def __init__(self, delay_range=(1, 3), use_browser=False, out_dir="espn_out", allowed_leagues=("ufc",)):
        """
        ESPN MMA scraper with optional browser automation
        """
        self.base_url = "https://www.espn.com"
        self.delay_range = delay_range
        self.use_browser = use_browser and PLAYWRIGHT_AVAILABLE
        self.out_dir = out_dir
        self.allowed_leagues = {l.lower() for l in (allowed_leagues or [])}
        
        # Always create requests session - needed even in browser mode for schedule scraping
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Setup logging and progress tracking
        self._setup_logging()
        self._setup_progress_tracking()
            
        if use_browser and not PLAYWRIGHT_AVAILABLE:
            print("Warning: Browser automation requested but Playwright not available. Falling back to requests.")

    def _strip_accents(self, s: str) -> str:
        return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    
    def _header_map(self, table) -> Dict[str, int]:
        """Lower-cased header text -> column index."""
        headers = [self._clean_text(th.get_text()).lower() for th in table.select("thead th")]
        return {h: i for i, h in enumerate(headers)}


    def _names_match_fotn(self, names: List[str], fotn_text: str) -> bool:
        """Heuristic: consider a match if both fighter last names are present in fotn_text."""
        if not fotn_text or len(names) != 2:
            return False
        def last_name(n: str) -> str:
            parts = self._strip_accents(n).lower().split()
            return parts[-1] if parts else ""
        ln1, ln2 = last_name(names[0]), last_name(names[1])
        ftxt = self._strip_accents(fotn_text).lower()
        return (ln1 and ln1 in ftxt) and (ln2 and ln2 in ftxt)
    
    def _slug_to_name(self, href: str) -> str:
        """Fallback: derive 'robert-whittaker' -> 'Robert Whittaker' from URL."""
        if not href:
            return ""
        parts = href.rstrip('/').split('/')
        try:
            i = parts.index('id')
            if i + 2 < len(parts):
                slug = parts[i + 2]
                if slug and slug != '':  # avoid ID-only URLs ending with 'id/<num>/'
                    words = slug.replace('-', ' ').split()
                    return ' '.join(w.capitalize() for w in words)
        except ValueError:
            pass
        return ""
    
    

    def _extract_name_near_anchor(self, a) -> str:
        """
        Given a fighter <a>, find the human-readable name in nearby containers.
        ESPN often places the text in sibling/ancestor nodes, not inside <a>.
        """
        if not a:
            return ""
        # 1) Search up to the nearest competitor container, then look for name nodes
        container = a.find_parent(class_=re.compile(r'(MMACompetitor|Competitor)'))
        if container:
            for sel in [
                '.MMACompetitor__Name', '.Competitor__Name',
                '.MMACompetitor__Detail h2', '.Competitor__Detail h2',
                'h2', 'h3', 'span'
            ]:
                el = container.select_one(sel)
                if el:
                    txt = self._clean_text(el.get_text())
                    if txt and txt.lower() not in ('full profile', 'profile'):
                        return txt

        # 2) Try close siblings under the same card node
        card = a.find_parent(class_=re.compile(r'(MMAFightCard|MMAFightCard__Gamestrip|Gamestrip)'))
        if card:
            for sel in [
                '.MMACompetitor__Name', '.Competitor__Name',
                '.MMACompetitor__Detail h2', '.Competitor__Detail h2',
                'h2', 'h3', 'span'
            ]:
                el = card.select_one(sel)
                if el:
                    txt = self._clean_text(el.get_text())
                    if txt and txt.lower() not in ('full profile', 'profile'):
                        return txt

        # 3) Last resort: the anchor’s own text
        link_txt = self._clean_text(a.get_text())
        if link_txt and link_txt.lower() not in ('full profile', 'profile'):
            return link_txt

        return ""

    def _build_id_to_name_map(self, soup: BeautifulSoup) -> Dict[str, str]:
        """
        Build a mapping {fighter_id -> best name} from all fighter links on the page,
        using nearby text or falling back to the URL slug.
        """
        mapping: Dict[str, str] = {}
        for a in soup.select('a[href*="/mma/fighter/_/id/"]'):
            href = a.get('href', '')
            fid = self._extract_id_from_url(href)
            if not fid or fid in mapping:
                continue
            name = self._extract_name_near_anchor(a)
            if not name:
                name = self._slug_to_name(href)
            if name:
                mapping[fid] = name
        return mapping
    
    def _setup_logging(self):
        """Setup logging for progress tracking and error handling"""
        os.makedirs(self.out_dir, exist_ok=True)
        
        # Create logger
        self.logger = logging.getLogger('ESPN_MMA_Scraper')
        self.logger.setLevel(logging.INFO)
        
        # File handler for detailed logs
        log_file = os.path.join(self.out_dir, f"scraper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        
        # Console handler for progress updates
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        self.logger.info("ESPN MMA Scraper initialized")
    
    def _setup_progress_tracking(self):
        """Setup progress tracking files"""
        self.progress_file = os.path.join(self.out_dir, "progress.json")
        self.failed_events_file = os.path.join(self.out_dir, "failed_events.json")
        self.failed_fighters_file = os.path.join(self.out_dir, "failed_fighters.json")
        
        # Load existing progress
        self.completed_events = self._load_progress_file(self.progress_file, "completed_events", set)
        self.completed_fighters = self._load_progress_file(self.progress_file, "completed_fighters", set)
        self.failed_events = self._load_progress_file(self.failed_events_file, "events", list)
        self.failed_fighters = self._load_progress_file(self.failed_fighters_file, "fighters", list)
        
        self.logger.info(f"Loaded progress: {len(self.completed_events)} events, {len(self.completed_fighters)} fighters completed")
        self.logger.info(f"Failed attempts: {len(self.failed_events)} events, {len(self.failed_fighters)} fighters")
    
    def _load_progress_file(self, filepath: str, key: str, data_type):
        """Load progress from JSON file"""
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    if data_type == set:
                        return set(data.get(key, []))
                    else:
                        return data.get(key, [])
            except Exception as e:
                self.logger.warning(f"Could not load {filepath}: {e}")
        
        return data_type()
    
    def _save_progress(self):
        """Save current progress to files"""
        try:
            progress_data = {
                "completed_events": list(self.completed_events),
                "completed_fighters": list(self.completed_fighters),
                "last_updated": datetime.now().isoformat()
            }
            with open(self.progress_file, 'w') as f:
                json.dump(progress_data, f, indent=2)
            
            if self.failed_events:
                with open(self.failed_events_file, 'w') as f:
                    json.dump({"events": self.failed_events}, f, indent=2)
            
            if self.failed_fighters:
                with open(self.failed_fighters_file, 'w') as f:
                    json.dump({"fighters": self.failed_fighters}, f, indent=2)
                    
        except Exception as e:
            self.logger.error(f"Failed to save progress: {e}")
    
    def _add_failed_event(self, event_url: str, error: str):
        """Track failed event for later retry"""
        failed_entry = {
            "url": event_url,
            "error": str(error),
            "timestamp": datetime.now().isoformat(),
            "attempts": 1
        }
        
        # Check if this event already failed before
        for i, existing in enumerate(self.failed_events):
            if existing.get("url") == event_url:
                existing["attempts"] += 1
                existing["last_error"] = str(error)
                existing["last_attempt"] = datetime.now().isoformat()
                self.logger.warning(f"Event failed again (attempt {existing['attempts']}): {event_url}")
                return
        
        self.failed_events.append(failed_entry)
        self.logger.error(f"Event failed: {event_url} - {error}")
    
    def _add_failed_fighter(self, fighter_url: str, error: str):
        """Track failed fighter for later retry"""
        failed_entry = {
            "url": fighter_url,
            "error": str(error),
            "timestamp": datetime.now().isoformat(),
            "attempts": 1
        }
        
        # Check if this fighter already failed before
        for i, existing in enumerate(self.failed_fighters):
            if existing.get("url") == fighter_url:
                existing["attempts"] += 1
                existing["last_error"] = str(error)
                existing["last_attempt"] = datetime.now().isoformat()
                self.logger.warning(f"Fighter failed again (attempt {existing['attempts']}): {fighter_url}")
                return
        
        self.failed_fighters.append(failed_entry)
        self.logger.error(f"Fighter failed: {fighter_url} - {error}")
    
    def _handle_rate_limit_error(self, error: Exception, context: str):
        """Handle rate limiting with exponential backoff"""
        if any(indicator in str(error).lower() for indicator in ['rate limit', '429', 'too many requests']):
            backoff_time = random.uniform(60, 120)  # 1-2 minutes
            self.logger.warning(f"Rate limit detected in {context}. Waiting {backoff_time:.1f} seconds...")
            time.sleep(backoff_time)
            return True
        return False
    
    def _polite_delay(self):
        """Add random delay between requests with occasional longer breaks"""
        # Occasional longer break to be extra polite
        if random.random() < 0.05:  # 5% chance
            longer_delay = random.uniform(10, 20)
            self.logger.info(f"Taking extended break: {longer_delay:.1f} seconds")
            time.sleep(longer_delay)
        else:
            time.sleep(random.uniform(*self.delay_range))
    
    def _get_page(self, url: str, max_retries: int = 3) -> Optional[BeautifulSoup]:
        """Fetch and parse a page with error handling and retries"""
        for attempt in range(max_retries):
            try:
                self._polite_delay()
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return BeautifulSoup(response.content, 'html.parser')
            except requests.exceptions.RequestException as e:
                if self._handle_rate_limit_error(e, f"GET {url}"):
                    continue  # Try again after rate limit delay
                
                if attempt == max_retries - 1:
                    self.logger.error(f"Failed to fetch {url} after {max_retries} attempts: {e}")
                    return None
                else:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)  # Exponential backoff
                    self.logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}. Retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
            except Exception as e:
                self.logger.error(f"Unexpected error fetching {url}: {e}")
                return None
        return None
    
    def _extract_id_from_url(self, url: str) -> str:
        """Extract ID from ESPN URLs (works for fighters and events)"""
        if not url:
            return ""
        match = re.search(r'/id/(\d+)', url)
        return match.group(1) if match else ""
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        return re.sub(r'\s+', ' ', text.strip())

    def _parse_schedule_date(self, text: str, year: int) -> Optional[str]:
        """
        Convert 'Sep 28' -> 'YYYY-09-28' using the page's year.
        Falls back to the raw text if format is unexpected.
        """
        if not text:
            return None
        m = re.match(r'([A-Za-z]{3})\s+(\d{1,2})', text.strip())
        if not m:
            return self._clean_text(text)
        mon = MONTHS.get(m.group(1).title())
        day = int(m.group(2))
        if not mon:
            return self._clean_text(text)
        return f"{year:04d}-{mon:02d}-{day:02d}"
    
    def _normalize_header(self, text: str) -> str:
        """
        Normalize <th> text to canonical field names for Fight History.
        Handles small variations like 'Res.' vs 'Result', 'Rnd' vs 'Round', 'Decision' vs 'Method'.
        """
        t = self._clean_text(text).lower()
        # strip punctuation and spaces
        t = re.sub(r'[^a-z]', '', t)

        # Map normalized header tokens to canonical keys
        mapping = {
            'date': 'date',
            'opponent': 'opponent',
            'res': 'result',
            'result': 'result',
            'decision': 'method',   # ESPN often labels the method column as "Decision"
            'method': 'method',
            'rnd': 'round',
            'round': 'round',
            'time': 'time',
            'event': 'event',
        }
        return mapping.get(t, t)  # fallback to whatever we got

    # --------------------------- NEW: Stats-table helpers ---------------------------

    def _pick_stats_table_by_title(self, soup: BeautifulSoup, title_lower: str):
        """
        From fighter stats page, pick the <table> whose titled section matches
        'striking' | 'clinch' | 'ground'.
        """
        for box in soup.select("div.ResponsiveTable"):
            title_el = box.select_one(".Table__Title")
            if title_el and title_el.get_text(strip=True).lower() == title_lower:
                t = box.select_one("table.Table")
                if t:
                    return t
        return None

    def _parse_stats_table(self, table) -> Dict[str, Dict[str, Any]]:
        """
        Parse a Striking/Clinch/Ground table into:
        { join_key -> {'meta': {...}, 'metrics': {...}} }
        join_key prefers event_id, else "date|opponent".
        """
        out: Dict[str, Dict[str, Any]] = {}
        if not table:
            return out

        # headers as-is (keep labels like "SDBL/A", "TSL-TSA", "TK ACC")
        headers = [
            th.get_text(strip=True).replace("\xa0", " ").strip()
            for th in table.select("thead th")
        ]
        idx_to_header = {i: h for i, h in enumerate(headers)}

        def td_text(td):
            s = td.get_text(" ", strip=True).replace("\xa0", " ").strip()
            return None if s in ("", "-") else s

        def parse_event(td):
            a = td.find("a", attrs={"data-game-link": True}) or td.find("a")
            if not a or not a.get("href"):
                return None, None
            href = urljoin(self.base_url, a["href"])
            return href, self._extract_id_from_url(href)

        def parse_opponent(td):
            a = td.find("a")
            name = (a.get_text(" ", strip=True) if a else td_text(td)) or None
            href = urljoin(self.base_url, a["href"]) if a and a.get("href") else None
            oid = self._extract_id_from_url(href) if href else None
            return name, href, oid

        for tr in table.select("tbody tr"):
            tds = tr.find_all("td")
            if not tds:
                continue

            row: Dict[str, Any] = {}
            for i, td in enumerate(tds):
                col = idx_to_header.get(i, f"col_{i}")
                if col == "Date":
                    row["date"] = td_text(td)
                elif col == "Opponent":
                    name, href, oid = parse_opponent(td)
                    row.update(opponent=name, opponent_url=href, opponent_id=oid)
                elif col == "Event":
                    href, eid = parse_event(td)
                    row.update(event_url=href, event_id=eid)
                elif col in ("Res.", "Res"):
                    row["result"] = td_text(td)
                else:
                    row[col] = td_text(td)

            metrics = {
                k: v for k, v in row.items()
                if k not in {"date", "opponent", "opponent_url", "opponent_id", "event_url", "event_id", "result"}
            }
            join_key = str(row.get("event_id") or f"{row.get('date')}|{row.get('opponent')}")
            out[join_key] = {
                "meta": {k: row.get(k) for k in ("date","opponent","opponent_url","opponent_id","event_url","event_id","result")},
                "metrics": metrics
            }

        return out

    def _attach_stats_to_fights(self, fights: List[Dict[str, Any]], stats_by_section: Dict[str, Dict[str, Any]]):
        """
        Mutates each fight dict to include 'striking'/'clinch'/'ground' metrics
        by joining primarily on event_id, falling back to 'date|opponent'.
        """
        if not fights:
            return fights

        # combine sectioned stats into: {join_key -> {'striking': {...}, ...}}
        combined: Dict[str, Dict[str, Any]] = {}
        for section in ("striking", "clinch", "ground"):
            for key, payload in stats_by_section.get(section, {}).items():
                eid_or_key = str(payload["meta"].get("event_id") or key)
                combined.setdefault(eid_or_key, {})[section] = payload["metrics"]

        for f in fights:
            jkey = str(f.get("event_id") or f"{f.get('date')}|{f.get('opponent')}")
            if jkey in combined:
                # Only attach sections that exist for this fight
                for section, metrics in combined[jkey].items():
                    f[section] = metrics

        return fights

    def _extract_fight_card_segments(self, soup: BeautifulSoup) -> Dict[str, List[Dict[str, Any]]]:
        """Extract fights organized by card segment (Main Card, Prelims, etc.) with correct fighter names."""
        segments: Dict[str, List[Dict[str, Any]]] = {}
        current_segment = "Unknown"

        content_area = soup.find('div', class_='PageLayout__Main') or soup

        def _normalize_segment(title_text: str) -> str:
            t = self._clean_text(title_text).lower()
            if 'main card' in t: return "Main Card"
            if 'early' in t and 'prelim' in t: return "Early Prelims"
            if 'prelim' in t: return "Prelims"
            return self._clean_text(title_text) or "Unknown"

        def _name_from_anchor_local(a) -> str:
            # 1) nearest competitor container
            comp = a.find_parent(class_=re.compile(r'(?:^| )(?:MMA)?Competitor(?: |$)'))
            if comp:
                for sel in [
                    '.MMACompetitor__Name', '.Competitor__Name',
                    '.MMACompetitor__Detail h2', '.Competitor__Detail h2',
                    'h2', 'h3', '.name', '.player__name'
                ]:
                    el = comp.select_one(sel)
                    if el:
                        txt = self._clean_text(el.get_text())
                        if txt and txt.lower() not in ('full profile', 'profile'):
                            return txt
            # 2) fallback: within the link
            link_txt = self._clean_text(a.get_text())
            if link_txt and link_txt.lower() not in ('full profile', 'profile'):
                return link_txt
            # 3) fallback: slug
            return self._slug_to_name(a.get('href', ''))

        for el in content_area.find_all(['header', 'div'], recursive=True):
            classes = el.get('class') or []

            # Segment headers
            if el.name == 'header' and any('Card__Header' in c for c in classes):
                title_el = el.find(re.compile('^h[1-6]$'), class_=re.compile(r'Card__Header__Title'))
                if title_el:
                    current_segment = _normalize_segment(title_el.get_text())
                    segments.setdefault(current_segment, [])
                continue

            # Bout cards
            if any(s in c for c in classes for s in ('MMAFightCard', 'MMAFightCard__Gamestrip', 'Gamestrip')):
                links = el.select('a[href*="/mma/fighter/_/id/"]')
                fids, fnames = [], []
                seen = set()

                for a in links:
                    fid = self._extract_id_from_url(a.get('href', ''))
                    if not fid or fid in seen:
                        continue
                    seen.add(fid)
                    fids.append(fid)
                    fnames.append(_name_from_anchor_local(a))
                    if len(fids) == 2:
                        break

                if len(fids) == 2:
                    fight = {
                        'fighter_ids': fids,
                        'fighter_names': fnames,
                        'card_segment': current_segment,
                        'bout_order_in_segment': len(segments.get(current_segment, [])),
                    }
                    segments.setdefault(current_segment, []).append(fight)

        return segments



    def _extract_fight_bonuses(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract fight bonuses (FOTN, POTN, etc.) from event page"""
        bonuses = {}
        
        # Look for fight bonus information - ESPN sometimes puts this in various places
        bonus_indicators = [
            'fight of the night',
            'performance of the night',
            'bonus winner',
            'fight bonus',
            'performance bonus'
        ]
        
        # Check in various potential locations
        search_areas = [
            soup.find('div', class_='PageLayout__Main'),
            soup.find('section', class_='Card'),
            soup.find('div', class_='EventHeader'),
            soup  # fallback to entire page
        ]
        
        for area in search_areas:
            if not area:
                continue
                
            # Look for any text containing bonus keywords
            for element in area.find_all(text=True):
                element_text = element.strip().lower() if element else ""
                
                for indicator in bonus_indicators:
                    if indicator in element_text:
                        # Found bonus mention - try to extract more context
                        parent = element.parent if hasattr(element, 'parent') else None
                        if parent:
                            context_text = self._clean_text(parent.get_text())
                            
                            # Store what we found
                            if 'fight of the night' in element_text:
                                bonuses['fight_of_the_night'] = context_text
                            elif 'performance of the night' in element_text:
                                bonuses['performance_of_the_night'] = context_text
                            else:
                                bonuses['bonus_mention'] = context_text
        
        return bonuses

    # -------------------------------------------------------------------------------

    def scrape_schedule_year(self, year: int) -> List[Dict]:
        """
        Scrape the schedule page for a given year.
        Only process 'Past Results' tables (they include 'Fight of the Night').
        """
        url = f"{self.base_url}/mma/schedule/_/year/{year}"
        soup = self._get_page(url)
        if not soup:
            return []

        events: List[Dict[str, Any]] = []
        seen_urls = set()

        for table in soup.select('table.Table'):
            thead = table.find('thead')
            if not thead:
                continue

            header_text = thead.get_text(" ", strip=True).lower()
            if not ("event" in header_text and "location" in header_text and "date" in header_text):
                continue

            # Only keep 'Past Results' tables: they have a Fight of the Night column
            is_past_results = ("fight of the night" in header_text) or ("fotn" in header_text)
            if not is_past_results:
                continue

            hmap = self._header_map(table)
            # Find columns
            idx_date     = next((i for h, i in hmap.items() if h.startswith("date")), None)
            idx_event    = next((i for h, i in hmap.items() if h.startswith("event")), None)
            idx_location = next((i for h, i in hmap.items() if h.startswith("location")), None)
            idx_fotn     = next((i for h, i in hmap.items() if "fight of the night" in h or h == "fotn"), None)

            for tr in table.select('tbody tr'):
                tds = tr.find_all('td')
                if not tds:
                    continue

                # Event (must be clickable Fightcenter link)
                ev_td = tds[idx_event] if idx_event is not None and idx_event < len(tds) else None
                a = ev_td.find('a', href=True) if ev_td else None
                if not (a and '/mma/fightcenter/_/id/' in a['href']):
                    continue

                event_url = urljoin(self.base_url, a['href'])
                if event_url in seen_urls:
                    continue
                seen_urls.add(event_url)

                event_name = self._clean_text(a.get_text()) or (self._clean_text(ev_td.get_text()) if ev_td else "")

                # Date
                date_text = self._clean_text(tds[idx_date].get_text()) if idx_date is not None and idx_date < len(tds) else ""
                iso_date = self._parse_schedule_date(date_text, year)

                # Location
                location = self._clean_text(tds[idx_location].get_text()) if idx_location is not None and idx_location < len(tds) else ""

                # League
                league_match = re.search(r'/league/([a-z0-9-]+)', event_url)
                league = league_match.group(1).lower() if league_match else None

                if self.allowed_leagues and (league not in self.allowed_leagues):
                    continue

                # Fight of the Night (only present in Past Results)
                fotn = self._clean_text(tds[idx_fotn].get_text()) if idx_fotn is not None and idx_fotn < len(tds) else None
                fotn = fotn or None  # normalize empty -> None

                events.append({
                    'url': event_url,
                    'id': self._extract_id_from_url(event_url),
                    'name': event_name,
                    'date': iso_date,
                    'location': location,
                    'league': league,
                    'year': year,
                    'fight_of_the_night': fotn,
                })

        print(f"Found {len(events)} events for year {year}")
        return events

    
    async def scrape_event_with_browser(self, event_url: str) -> Dict:
        """Scrape event page using browser automation to expand all sections"""
        if not PLAYWRIGHT_AVAILABLE:
            print("Playwright not available, falling back to requests method")
            return self._scrape_event_requests(event_url)
            
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )
            page = await context.new_page()
            
            # Set longer timeout for slow-loading ESPN pages
            page.set_default_timeout(60000)  # 60 seconds
            
            try:
                # Navigate to the page with less strict loading requirements
                print(f"Loading event page: {event_url}")
                try:
                    await page.goto(event_url, wait_until='domcontentloaded', timeout=45000)
                    print("Page loaded (DOM ready)")
                except Exception as e:
                    print(f"Timeout during page load, but continuing anyway: {e}")
                    # Continue - page might still be partially usable
                
                # Wait for initial JavaScript to execute
                await page.wait_for_timeout(5000)  # Give more time for ESPN's JS to load
                
                # Debug: Let's examine the page structure before attempting expansion
                print("=== DEBUGGING PAGE STRUCTURE ===")
                
                # Check what fight cards exist
                try:
                    all_fight_cards = await page.query_selector_all('.MMAFightCard__Gamestrip')
                    open_fight_cards = await page.query_selector_all('.MMAFightCard__Gamestrip--open')
                    print(f"Total fight cards found: {len(all_fight_cards)}")
                    print(f"Open fight cards found: {len(open_fight_cards)}")
                    
                    # Show classes of first few cards
                    for i, card in enumerate(all_fight_cards[:5]):
                        classes = await card.get_attribute('class')
                        print(f"  Card {i} classes: {classes}")
                        
                except Exception as e:
                    print(f"Error examining fight cards: {e}")
                
                # Check for caret elements
                try:
                    caret_elements = await page.query_selector_all('[data-testid="gameStripBarCaret"]')
                    print(f"Caret elements found: {len(caret_elements)}")
                    
                    # Examine first few carets
                    for i, caret in enumerate(caret_elements[:5]):
                        is_visible = await caret.is_visible()
                        classes = await caret.get_attribute('class')
                        print(f"  Caret {i}: visible={is_visible}, classes={classes}")
                        
                        # Check for SVG icons within
                        down_arrow = await caret.query_selector('svg[data-icon="playerControls-downCarot"]')
                        up_arrow = await caret.query_selector('svg[data-icon="playerControls-upCarot"]')
                        print(f"    Down arrow: {down_arrow is not None}, Up arrow: {up_arrow is not None}")
                        
                except Exception as e:
                    print(f"Error examining carets: {e}")
                
                # Check current profile links before expansion
                try:
                    pre_expansion_profiles = await page.query_selector_all('a.MMAFightCenter__ProfileLink')
                    print(f"Profile links before expansion: {len(pre_expansion_profiles)}")
                except Exception as e:
                    print(f"Error checking pre-expansion profiles: {e}")
                
                print("=== ATTEMPTING EXPANSION ===")
                
                # Strategy 1: Try clicking all carets with detailed feedback
                expanded_count = 0
                try:
                    caret_elements = await page.query_selector_all('[data-testid="gameStripBarCaret"]')
                    print(f"Attempting to click {len(caret_elements)} carets")
                    
                    for i, caret in enumerate(caret_elements):
                        try:
                            print(f"Processing caret {i}...")
                            
                            # Check visibility
                            is_visible = await caret.is_visible()
                            if not is_visible:
                                print(f"  Caret {i} not visible, skipping")
                                continue
                            
                            # Get current state
                            down_arrow = await caret.query_selector('svg[data-icon="playerControls-downCarot"]')
                            up_arrow = await caret.query_selector('svg[data-icon="playerControls-upCarot"]')
                            
                            print(f"  Caret {i} state - Down: {down_arrow is not None}, Up: {up_arrow is not None}")
                            
                            # Only click if it has a down arrow (collapsed state)
                            if down_arrow:
                                print(f"  Clicking collapsed caret {i}...")
                                await caret.click()
                                expanded_count += 1
                                
                                # Wait and check if state changed
                                await page.wait_for_timeout(1500)
                                
                                # Check new state
                                new_down_arrow = await caret.query_selector('svg[data-icon="playerControls-downCarot"]')
                                new_up_arrow = await caret.query_selector('svg[data-icon="playerControls-upCarot"]')
                                
                                print(f"  After click - Down: {new_down_arrow is not None}, Up: {new_up_arrow is not None}")
                                
                                # Check if profile links increased
                                current_profiles = await page.query_selector_all('a.MMAFightCenter__ProfileLink')
                                print(f"  Profile links now: {len(current_profiles)}")
                            else:
                                print(f"  Caret {i} already expanded (up arrow), skipping to avoid collapsing")
                            
                        except Exception as e:
                            print(f"  Error with caret {i}: {e}")
                            continue
                            
                except Exception as e:
                    print(f"Error in caret expansion: {e}")
                
                print(f"=== EXPANSION COMPLETE - {expanded_count} attempts ===")
                
                # Final state check
                try:
                    final_open_cards = await page.query_selector_all('.MMAFightCard__Gamestrip--open')
                    final_profile_links = await page.query_selector_all('a.MMAFightCenter__ProfileLink')
                    final_down_arrows = await page.query_selector_all('svg[data-icon="playerControls-downCarot"]')
                    final_up_arrows = await page.query_selector_all('svg[data-icon="playerControls-upCarot"]')
                    
                    print(f"Final state:")
                    print(f"  Open cards: {len(final_open_cards)}")
                    print(f"  Profile links: {len(final_profile_links)}")  
                    print(f"  Down arrows remaining: {len(final_down_arrows)}")
                    print(f"  Up arrows present: {len(final_up_arrows)}")
                    
                except Exception as e:
                    print(f"Error in final state check: {e}")
                
                # Wait for any final animations
                await page.wait_for_timeout(2000)
                
                # Get the page content
                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Now extract fighter data from the fully expanded page
                event_data = self._extract_event_data_from_soup(soup, event_url)
                
                return event_data
                
            except Exception as e:
                print(f"Error in browser scraping: {e}")
                return {}
            finally:
                await context.close()
                await browser.close()

    def _extract_event_data_from_soup(self, soup: BeautifulSoup, event_url: str) -> Dict:
        """Extract event data from BeautifulSoup object"""
        event_data = {
            'id': self._extract_id_from_url(event_url),
            'url': event_url,
            'fighter_urls': []
        }
        
        # Extract event name from <title>
        title_elem = soup.find('title')
        if title_elem:
            title = title_elem.get_text(strip=True)
            # Remove ESPN suffix and "Fight Results" suffix
            event_name = re.sub(r'\s*-\s*ESPN.*$', '', title)
            event_name = re.sub(r'\s*Fight Results\s*$', '', event_name)
            event_data['name'] = event_name
        
        # NEW: Extract fight card segments and bonuses
        try:
            card_segments = self._extract_fight_card_segments(soup)
            event_data['card_segments'] = card_segments
            print(f"Found fight card segments: {list(card_segments.keys())}")
        except Exception as e:
            print(f"Error extracting card segments: {e}")
            event_data['card_segments'] = {}
        
        try:
            fight_bonuses = self._extract_fight_bonuses(soup)
            event_data['fight_bonuses'] = fight_bonuses
            if fight_bonuses:
                print(f"Found fight bonuses: {list(fight_bonuses.keys())}")
        except Exception as e:
            print(f"Error extracting fight bonuses: {e}")
            event_data['fight_bonuses'] = {}
        
        # Collect fighter profile links - normalize to name-slug format
        fighter_urls_raw = set()
        
        # 1) Primary: Get ALL MMA fighter links on the page (expanded and default-open)
        all_fighter_links = soup.select('a[href*="/mma/fighter/_/id/"]')
        print(f"Found {len(all_fighter_links)} total fighter links")
        
        for link in all_fighter_links:
            href = link.get('href', '')
            if '/mma/fighter/_/id/' in href:
                full_url = urljoin(self.base_url, href)
                fighter_urls_raw.add(full_url)
        
        # 2) Also extract from data-player-uid attributes as backup
        uid_elements = soup.find_all(attrs={"data-player-uid": True})
        print(f"Found {len(uid_elements)} elements with data-player-uid")
        
        for elem in uid_elements:
            uid = elem.get('data-player-uid', '')
            id_match = re.search(r'~a:(\d+)', uid)
            if id_match:
                fighter_id = id_match.group(1)
                # If this element is a link, use its href
                if elem.name == 'a' and elem.get('href'):
                    href = elem.get('href', '')
                    if '/mma/fighter/_/id/' in href and fighter_id in href:
                        full_url = urljoin(self.base_url, href)
                        fighter_urls_raw.add(full_url)
                else:
                    # Fallback to ID-only URL 
                    fighter_url = f"{self.base_url}/mma/fighter/_/id/{fighter_id}/"
                    fighter_urls_raw.add(fighter_url)
        
        # 3) Normalize URLs: prefer name-slug format, deduplicate by fighter ID
        fighter_urls = set()
        id_to_slug_url = {}  # Map fighter IDs to their best URLs
        
        for url in fighter_urls_raw:
            fighter_id = self._extract_id_from_url(url)
            if not fighter_id:
                continue
                
            # Check if URL has name slug (path continues after the ID)
            url_parts = url.rstrip('/').split('/')
            if len(url_parts) >= 6:  # .../mma/fighter/_/id/12345/name-slug
                id_index = None
                for i, part in enumerate(url_parts):
                    if part == 'id' and i + 1 < len(url_parts):
                        id_index = i + 1
                        break
                
                if id_index and id_index + 1 < len(url_parts):
                    # Has name slug after the ID
                    has_name_slug = True
                else:
                    has_name_slug = False
            else:
                has_name_slug = False
            
            # Prefer name-slug URLs over ID-only URLs
            if has_name_slug:
                id_to_slug_url[fighter_id] = url
            elif fighter_id not in id_to_slug_url:
                # Only use ID-only if we don't have name-slug version
                id_to_slug_url[fighter_id] = url
        
        fighter_urls = set(id_to_slug_url.values())
        
        print(f"Collected {len(fighter_urls_raw)} raw URLs, normalized to {len(fighter_urls)} unique fighters")
        
        # Debug: Show a few URLs to verify we're getting both main event and expanded fighters
        sample_urls = sorted(list(fighter_urls))[:5]
        print(f"Sample URLs: {sample_urls}")
        
        # Extract names from card
        fighter_names = []
        name_selectors = [
            '.MMACompetitor__Detail h2',
            '.Competitor__Detail h2', 
            '.Fighter__Name',
            '.player__name',
            '[data-player-uid] h2',
            '[data-player-uid] .name'
        ]
        
        for selector in name_selectors:
            for name_elem in soup.select(selector):
                parts = [self._clean_text(x.get_text()) for x in name_elem.find_all('span')]
                if not parts:
                    parts = [self._clean_text(name_elem.get_text())]
                parts = [p for p in parts if p]
                if parts:
                    fighter_names.append(' '.join(parts))
        
        event_data['fighter_urls'] = sorted(list(fighter_urls))
        event_data['fighter_names_from_card'] = list(set(fighter_names))  # Remove duplicates
        
        print(f"Event {event_data.get('name', 'Unknown')}: Found {len(fighter_urls)} fighter URLs, {len(set(fighter_names))} unique names from card")
        
        # Additional debug info if counts don't match
        if len(fighter_urls) != len(set(fighter_names)):
            print(f"  Warning: URL count ({len(fighter_urls)}) != name count ({len(set(fighter_names))})")
            if len(fighter_urls) < len(set(fighter_names)):
                print(f"  Missing URLs for some fighters. Names found: {list(set(fighter_names))}")
        
        return event_data

    def _scrape_event_requests(self, event_url: str) -> Dict:
        """Original requests-based scraping (your current implementation)"""
        soup = self._get_page(event_url)
        if not soup:
            return {}
        return self._extract_event_data_from_soup(soup, event_url)
    
    def scrape_event(self, event_url: str) -> Dict:
        """Main scrape_event method that chooses browser vs requests approach"""
        if self.use_browser:
            return asyncio.run(self.scrape_event_with_browser(event_url))
        else:
            return self._scrape_event_requests(event_url)
    
    def scrape_fighter_profile(self, fighter_url: str) -> Dict:
        """Scrape fighter profile page for basic info and fighting style"""
        soup = self._get_page(fighter_url)
        if not soup:
            return {}
        
        fighter_data: Dict[str, Any] = {
            'id': self._extract_id_from_url(fighter_url),
            'url': fighter_url
        }
        
        # name slug from URL
        url_parts = fighter_url.rstrip('/').split('/')
        if url_parts:
            fighter_data['name_slug'] = url_parts[-1]
        
        # Name from <title>
        title_elem = soup.find('title')
        if title_elem:
            title = title_elem.get_text(strip=True)
            name_match = re.match(r'^([^(]+)', title)
            if name_match:
                fighter_data['name'] = self._clean_text(name_match.group(1))
        
        # Fighting Style from table (best-effort, classes shift occasionally)
        for table in soup.find_all('table', class_='Table'):
            thead = table.find('thead')
            if not thead:
                continue
            headers = [th.get_text(strip=True) for th in thead.find_all('th')]
            if 'Fighting Style' not in headers:
                continue
            tbody = table.find('tbody')
            if not tbody:
                continue
            for row in tbody.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) < len(headers):
                    continue
                row_map = {headers[i]: self._clean_text(cells[i].get_text()) for i in range(len(headers))}
                maybe_style = row_map.get('Fighting Style', '')
                if maybe_style and maybe_style not in ['Height', 'Weight', 'Fighter', '-', '']:
                    fighter_data['fighting_style'] = maybe_style
                    break
            break
        return fighter_data
    
    def scrape_fighter_bio(self, fighter_url: str) -> Dict:
        """Scrape fighter bio page for structured data"""
        bio_url = fighter_url.replace('/fighter/', '/fighter/bio/')
        soup = self._get_page(bio_url)
        if not soup:
            return {}
        
        bio_data: Dict[str, Any] = {
            'id': self._extract_id_from_url(fighter_url),
            'bio_url': bio_url
        }
        
        # Bio list items (labels vary)
        bio_section = soup.find('section', class_='Card Bio')
        if bio_section:
            for item in bio_section.find_all('div', class_='Bio__Item'):
                label_elem = item.find('span', class_='Bio__Label')
                value_elem = item.find('span', class_=re.compile(r'dib flex-uniform'))
                if not (label_elem and value_elem):
                    continue
                label = self._clean_text(label_elem.get_text()).lower()
                value = self._clean_text(value_elem.get_text())
                if 'country' in label:
                    bio_data['country'] = value
                elif 'wt class' in label or 'weight class' in label:
                    bio_data['weight_class'] = value
                elif 'ht/wt' in label or 'height' in label:
                    m = re.match(r"([^,]+),\s*(.+)", value)
                    if m:
                        bio_data['height'] = self._clean_text(m.group(1))
                        bio_data['weight'] = self._clean_text(m.group(2))
                    else:
                        bio_data['height_weight'] = value
                elif 'birthdate' in label:
                    date_match = re.match(r'(\d{1,2}/\d{1,2}/\d{4})', value)
                    if date_match:
                        bio_data['birthdate'] = date_match.group(1)
                    age_match = re.search(r'\((\d+)\)', value)
                    if age_match:
                        bio_data['age'] = int(age_match.group(1))
                elif 'team' in label:
                    bio_data['team'] = value
                elif 'nickname' in label:
                    bio_data['nickname'] = value
                elif 'stance' in label:
                    bio_data['stance'] = value
                elif 'reach' in label:
                    bio_data['reach'] = value.replace('"', '').strip()
        
        # Record block (labels vary a bit)
        stat_block = soup.find('aside', class_='StatBlock')
        if stat_block:
            for item in stat_block.find_all('div', class_='StatBlockInner'):
                label_elem = item.find('div', class_='StatBlockInner__Label')
                value_elem = item.find('div', class_='StatBlockInner__Value')
                if not (label_elem and value_elem):
                    continue
                label = self._clean_text(label_elem.get_text()).lower()
                value = self._clean_text(value_elem.get_text())
                if 'w-l-d' in label or 'wins-losses-draws' in label:
                    bio_data['record'] = value
                elif '(t)ko' in label or 'knockout' in label:
                    bio_data['ko_record'] = value
                elif 'sub' in label or 'submission' in label:
                    bio_data['sub_record'] = value
        
        return bio_data
    
    def scrape_fighter_stats(self, fighter_url: str) -> Dict:
        """
        Scrape fighter stats page; parse the three titled tables
        (Striking / Clinch / Ground) into dicts keyed by event_id (fallback: date|opponent).
        """
        stats_url = fighter_url.replace('/fighter/', '/fighter/stats/')
        soup = self._get_page(stats_url)
        if not soup:
            return {}
        
        # Parse each section
        stats_sections = {}
        for section in ("striking", "clinch", "ground"):
            tbl = self._pick_stats_table_by_title(soup, section)
            stats_sections[section] = self._parse_stats_table(tbl) if tbl else {}

        # (Optional) Preserve older keys for compatibility – not used for merging
        def flatten_for_compat(section_map):
            # turn into a list of {**meta, **metrics}
            out = []
            for payload in section_map.values():
                row = {}
                row.update(payload.get("meta", {}))
                row.update(payload.get("metrics", {}))
                out.append(row)
            return out

        stats_data: Dict[str, Any] = {
            'id': self._extract_id_from_url(fighter_url),
            'stats_url': stats_url,
            'stats_sections': stats_sections,
            # compat lists:
            'striking_fights': flatten_for_compat(stats_sections.get('striking', {})),
            'clinch_fights': flatten_for_compat(stats_sections.get('clinch', {})),
            'ground_fights': flatten_for_compat(stats_sections.get('ground', {})),
        }
        return stats_data
    
    def scrape_fighter_history(self, fighter_url: str) -> Dict:
        """Scrape fighter fight history page"""
        history_url = fighter_url.replace('/fighter/', '/fighter/history/')
        soup = self._get_page(history_url)
        if not soup:
            return {}
        
        history_data: Dict[str, Any] = {
            'id': self._extract_id_from_url(fighter_url),
            'history_url': history_url,
            'fights': []
        }
        
        for table in soup.find_all('table'):
            thead = table.find('thead')
            if not thead:
                continue
            header_text = thead.get_text().lower()
            if any(k in header_text for k in ['date', 'opponent', 'result', 'event']):
                history_data['fights'].extend(self._parse_fight_history_table(table))
        
        return history_data
    
    def _parse_fight_stats_table(self, table, table_type: str) -> List[Dict]:
        """(Legacy) Simple fight-by-fight stats table parser – kept for compatibility."""
        fights: List[Dict[str, Any]] = []
        tbody = table.find('tbody')
        if not tbody:
            return fights
        
        for row in tbody.find_all('tr'):
            cells = row.find_all(['td', 'th'])
            if len(cells) < 3:
                continue
            
            fight: Dict[str, Any] = {'table_type': table_type}
            for i, cell in enumerate(cells):
                text = self._clean_text(cell.get_text())
                fight[f'col_{i}'] = text
                if i == 0 and re.search(r'\d{1,2}/\d{1,2}/\d{4}', text):
                    fight['date'] = text
                elif re.search(r'^\d+/\d+$', text):  # "5/10" style stats
                    fight[f'stat_{i}'] = text
                elif text in ['W', 'L', 'D', 'NC']:
                    fight['result'] = text
            fights.append(fight)
        return fights
    
    def _parse_fight_history_table(self, table) -> List[Dict]:
        """Parse fight history table using the header row for column mapping."""
        fights: List[Dict] = []

        thead = table.find('thead')
        tbody = table.find('tbody')
        if not (thead and tbody):
            return fights

        # Build header map
        ths = thead.find_all('th')
        headers = [self._normalize_header(th.get_text()) for th in ths]

        # If headers look wrong or missing, fall back to the known 7-column layout
        # Date | Opponent | Res. | Decision | Rnd | Time | Event
        if not headers or len(headers) < 3:
            headers = ['date', 'opponent', 'result', 'method', 'round', 'time', 'event']

        for tr in tbody.find_all('tr'):
            tds = tr.find_all('td')
            if not tds:
                continue

            entry: Dict[str, str] = {}
            for i, td in enumerate(tds):
                key = headers[i] if i < len(headers) else None
                value = self._clean_text(td.get_text())

                # Only store recognized fields; avoid emitting generic col_i duplicates
                if key in ('date', 'opponent', 'result', 'method', 'round', 'time', 'event'):
                    # Prefer anchor text for linked fields and capture URLs/IDs
                    if key in ('opponent', 'event'):
                        a = td.find('a', href=True)
                        if a:
                            link_text = self._clean_text(a.get_text()) or value
                            href = urljoin(self.base_url, a['href'])
                            value = link_text
                            if key == 'opponent':
                                entry['opponent_url'] = href
                                entry['opponent_id'] = self._extract_id_from_url(href)
                            else:
                                entry['event_url'] = href
                                entry['event_id'] = self._extract_id_from_url(href)
                    entry[key] = value

            # Some pages label the method column as 'Decision'—already normalized to 'method' above.
            # Basic cleanup: uppercase single-letter results, keep 'NC' as-is.
            if 'result' in entry and entry['result']:
                r = entry['result'].strip().upper()
                if r in ('W', 'L', 'D', 'NC'):
                    entry['result'] = r

            fights.append(entry)

        return fights

    def scrape_complete_fighter(self, fighter_url: str) -> Dict:
        """Scrape all available data for a fighter"""
        print(f"Scraping complete data for fighter: {fighter_url}")
        fighter_data = self.scrape_fighter_profile(fighter_url)
        
        # Bio
        bio_data = self.scrape_fighter_bio(fighter_url)
        for k, v in bio_data.items():
            if k not in fighter_data:
                fighter_data[k] = v
        
        # Stats
        stats_data = self.scrape_fighter_stats(fighter_url)
        for k, v in stats_data.items():
            if k not in fighter_data:
                fighter_data[k] = v
        
        # History
        history_data = self.scrape_fighter_history(fighter_url)

        # ---- NEW: attach Striking/Clinch/Ground metrics into each fight ----
        fights_list = history_data.get('fights', [])
        stats_sections = stats_data.get('stats_sections', {})
        self._attach_stats_to_fights(fights_list, stats_sections)
        history_data['fights'] = fights_list
        # --------------------------------------------------------------------

        for k, v in history_data.items():
            if k not in fighter_data:
                fighter_data[k] = v
        
        return fighter_data
    
    def crawl_all(self, start_year=2025, end_year=1999, out_dir="espn_out", limit_events=None):
        """
        Crawl ESPN MMA data from start_year down to end_year (inclusive)
        """
        self.out_dir = out_dir  # Update if different from init
        os.makedirs(out_dir, exist_ok=True)
        
        events_path = os.path.join(out_dir, "events.jsonl")
        fighters_path = os.path.join(out_dir, "fighters.jsonl")
        
        total_events_processed = 0
        total_fighters_processed = 0
        
        self.logger.info(f"Starting crawl from {start_year} to {end_year}")
        if limit_events:
            self.logger.info(f"Limited to {limit_events} events")
        
        try:
            for year in range(start_year, end_year - 1, -1):
                self.logger.info(f"=== Scraping year {year} ===")
                
                try:
                    events = self.scrape_schedule_year(year)
                    self.logger.info(f"Found {len(events)} events for year {year}")
                except Exception as e:
                    self.logger.error(f"Failed to get schedule for year {year}: {e}")
                    continue
                
                for i, event_info in enumerate(events):
                    if limit_events and total_events_processed >= limit_events:
                        self.logger.info(f"Reached event limit of {limit_events}")
                        return
                    league_val = (event_info.get('league') or "").lower()
                    if self.allowed_leagues and (league_val not in self.allowed_leagues):
                        self.logger.info(f"Skipping non-allowed league event: {event_info.get('name')} [{league_val}]")
                        continue
                    
                    event_url = event_info['url']
                    
                    # Skip if already completed
                    if event_url in self.completed_events:
                        self.logger.info(f"Skipping already completed event: {event_info.get('name', event_url)}")
                        continue
                    
                    # Skip if failed too many times
                    failed_attempts = sum(1 for f in self.failed_events if f.get('url') == event_url and f.get('attempts', 0) >= 3)
                    if failed_attempts > 0:
                        self.logger.warning(f"Skipping event with 3+ failed attempts: {event_url}")
                        continue
                    
                    self.logger.info(f"Processing event {i+1}/{len(events)} for {year}: {event_info.get('name', 'Unknown')}")
                    
                    try:
                        event_data = self.scrape_event(event_url)
                        if not event_data:
                            raise Exception("No event data returned")
                        
                        # Merge schedule info
                        for key, value in event_info.items():
                            if key not in event_data or not event_data[key]:
                                event_data[key] = value

                        fotn_txt = event_data.get('fight_of_the_night')
                        if fotn_txt and event_data.get('card_segments'):
                            for seg, fights in event_data['card_segments'].items():
                                for f in fights:
                                    names = f.get('fighter_names') or []
                                    if self._names_match_fotn(names, fotn_txt):
                                        f['is_fotn'] = True
                        
                        # Save event
                        with open(events_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps(event_data, ensure_ascii=False) + "\n")
                        
                        self.completed_events.add(event_url)
                        total_events_processed += 1
                        
                        self.logger.info(f"✓ Saved event: {event_data.get('name', 'Unknown')} [{event_data.get('date', '')}] - {len(event_data.get('fighter_urls', []))} fighters")
                        
                        # Process fighters
                        fighter_urls = event_data.get('fighter_urls', [])
                        self.logger.info(f"Processing {len(fighter_urls)} fighters from this event")
                        
                        for j, fighter_url in enumerate(fighter_urls):
                            if fighter_url in self.completed_fighters:
                                continue
                            
                            # Skip if failed too many times
                            failed_fighter_attempts = sum(1 for f in self.failed_fighters if f.get('url') == fighter_url and f.get('attempts', 0) >= 3)
                            if failed_fighter_attempts > 0:
                                continue
                            
                            try:
                                fighter_data = self.scrape_complete_fighter(fighter_url)
                                if not fighter_data:
                                    raise Exception("No fighter data returned")
                                
                                with open(fighters_path, "a", encoding="utf-8") as f:
                                    f.write(json.dumps(fighter_data, ensure_ascii=False) + "\n")
                                
                                self.completed_fighters.add(fighter_url)
                                total_fighters_processed += 1
                                
                                if j % 5 == 0 or j == len(fighter_urls) - 1:  # Progress update every 5 fighters
                                    self.logger.info(f"  ✓ Fighter progress: {j+1}/{len(fighter_urls)} - Latest: {fighter_data.get('name', 'Unknown')}")
                                
                            except Exception as e:
                                self._add_failed_fighter(fighter_url, e)
                                continue
                        
                        # Save progress after each event
                        self._save_progress()
                        
                    except Exception as e:
                        self._add_failed_event(event_url, e)
                        continue
                
                self.logger.info(f"Completed year {year}")
                
        except KeyboardInterrupt:
            self.logger.info("Crawl interrupted by user")
        except Exception as e:
            self.logger.error(f"Unexpected error in crawl_all: {e}")
        finally:
            # Final progress save
            self._save_progress()
            
            self.logger.info("=== CRAWL SUMMARY ===")
            self.logger.info(f"Total events processed: {total_events_processed}")
            self.logger.info(f"Total fighters processed: {total_fighters_processed}")
            self.logger.info(f"Failed events: {len(self.failed_events)}")
            self.logger.info(f"Failed fighters: {len(self.failed_fighters)}")
            self.logger.info(f"Completed events: {len(self.completed_events)}")
            self.logger.info(f"Completed fighters: {len(self.completed_fighters)}")
    
    def retry_failed_items(self):
        """Retry previously failed events and fighters"""
        self.logger.info("=== RETRYING FAILED ITEMS ===")
        
        events_path = os.path.join(self.out_dir, "events.jsonl")
        fighters_path = os.path.join(self.out_dir, "fighters.jsonl")
        
        # Retry failed events (with less than 3 attempts)
        events_to_retry = [e for e in self.failed_events if e.get('attempts', 0) < 3]
        self.logger.info(f"Retrying {len(events_to_retry)} failed events")
        
        for event_info in events_to_retry:
            event_url = event_info['url']
            try:
                self.logger.info(f"Retrying event: {event_url}")
                event_data = self.scrape_event(event_url)
                if event_data:
                    with open(events_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(event_data, ensure_ascii=False) + "\n")
                    
                    self.completed_events.add(event_url)
                    # Remove from failed list
                    self.failed_events = [e for e in self.failed_events if e.get('url') != event_url]
                    self.logger.info(f"✓ Retry successful: {event_url}")
                else:
                    raise Exception("No event data returned on retry")
            except Exception as e:
                self._add_failed_event(event_url, e)
        
        # Retry failed fighters (with less than 3 attempts)  
        fighters_to_retry = [f for f in self.failed_fighters if f.get('attempts', 0) < 3]
        self.logger.info(f"Retrying {len(fighters_to_retry)} failed fighters")
        
        for fighter_info in fighters_to_retry:
            fighter_url = fighter_info['url']
            try:
                self.logger.info(f"Retrying fighter: {fighter_url}")
                fighter_data = self.scrape_complete_fighter(fighter_url)
                if fighter_data:
                    with open(fighters_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(fighter_data, ensure_ascii=False) + "\n")
                    
                    self.completed_fighters.add(fighter_url)
                    # Remove from failed list
                    self.failed_fighters = [f for f in self.failed_fighters if f.get('url') != fighter_url]
                    self.logger.info(f"✓ Retry successful: {fighter_url}")
                else:
                    raise Exception("No fighter data returned on retry")
            except Exception as e:
                self._add_failed_fighter(fighter_url, e)
        
        self._save_progress()
        self.logger.info("=== RETRY COMPLETE ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ESPN MMA Scraper")
    parser.add_argument("--start-year", type=int, default=2025, help="Start year (default: 2025)")
    parser.add_argument("--end-year", type=int, default=1999, help="End year (default: 1999)")
    parser.add_argument("--out-dir", default="espn_out", help="Output directory (default: espn_out)")
    parser.add_argument("--limit-events", type=int, help="Limit number of events to scrape (for testing)")
    parser.add_argument("--min-delay", type=float, default=1.0, help="Min delay between requests (seconds)")
    parser.add_argument("--max-delay", type=float, default=3.0, help="Max delay between requests (seconds)")
    parser.add_argument("--use-browser", action="store_true", help="Use browser automation to expand collapsed sections")
    parser.add_argument("--retry-failed", action="store_true", help="Retry previously failed events and fighters")
    parser.add_argument("--leagues", default="ufc", help="Comma-separated leagues to include (default: ufc). Example: ufc,pfl")
    args = parser.parse_args()
    allowed = [s.strip().lower() for s in args.leagues.split(",") if s.strip()]

    scraper = ESPNMMAScraper(
        delay_range=(args.min_delay, args.max_delay),
        use_browser=args.use_browser,
        out_dir=args.out_dir,
        allowed_leagues=allowed
    )
    
    if args.retry_failed:
        scraper.retry_failed_items()
    else:
        scraper.crawl_all(
            start_year=args.start_year,
            end_year=args.end_year,
            out_dir=args.out_dir,
            limit_events=args.limit_events
        )