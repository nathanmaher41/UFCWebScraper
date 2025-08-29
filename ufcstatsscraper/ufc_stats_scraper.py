from bs4 import BeautifulSoup
import re
import requests
import time
import random
from urllib.parse import urljoin
from typing import Dict, List, Optional, Tuple
import json
from typing import Iterable, Dict, Set, Tuple
import time
import json
import re
import random
import os
import argparse

ALPHABET = "abcdefghijklmnopqrstuvwxyz"

class UFCStatsScraper:
    def __init__(self, delay_range=(1, 3)):
        """
        UFC Stats scraper with polite crawling delays
        """
        self.base_url = "http://ufcstats.com"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.delay_range = delay_range
    
    def _polite_delay(self):
        """Add random delay between requests"""
        time.sleep(random.uniform(*self.delay_range))
    
    def _get_page(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch and parse a page with error handling"""
        try:
            self._polite_delay()
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def _get_soup(self, url: str) -> Optional[BeautifulSoup]:
        """Compatibility wrapper for older helpers that expect _get_soup."""
        return self._get_page(url)
    
    def _extract_id_from_url(self, url: str) -> str:
        """Extract ID from UFC stats URLs"""
        return url.split('/')[-1] if url else ""
    
    def _parse_stat_fraction(self, text: str) -> Tuple[int, int]:
        """Parse 'X of Y' format stats"""
        if not text or text.strip() == "---":
            return 0, 0
        
        # Handle formats like "96 of 119" or just "96"
        match = re.search(r'(\d+)(?:\s+of\s+(\d+))?', text.strip())
        if match:
            landed = int(match.group(1))
            attempted = int(match.group(2)) if match.group(2) else landed
            return landed, attempted
        return 0, 0
    
    def _parse_percentage(self, text: str) -> int:
        """Parse percentage strings"""
        if not text or text.strip() in ["---", ""]:
            return 0
        match = re.search(r'(\d+)%', text.strip())
        return int(match.group(1)) if match else 0
    
    def _parse_time_control(self, text: str) -> int:
        """Convert time control to seconds (MM:SS format)"""
        if not text or text.strip() in ["---", "0:00"]:
            return 0
        
        match = re.search(r'(\d+):(\d+)', text.strip())
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            return minutes * 60 + seconds
        return 0

    def scrape_fighter(self, fighter_url: str) -> Dict:
        """Scrape fighter details page"""
        soup = self._get_page(fighter_url)
        if not soup:
            return {}
        
        fighter_data = {
            'id': self._extract_id_from_url(fighter_url),
            'url': fighter_url
        }
        
        # Name and record from title
        title_elem = soup.find('h2', class_='b-content__title')
        if title_elem:
            name_elem = title_elem.find('span', class_='b-content__title-highlight')
            record_elem = title_elem.find('span', class_='b-content__title-record')
            
            if name_elem:
                fighter_data['name'] = name_elem.get_text(strip=True)
            
            if record_elem:
                # Parse "Record: 28-1-0 (1 NC)"
                record_text = record_elem.get_text(strip=True)
                record_match = re.search(r'Record:\s*(\d+)-(\d+)-(\d+)(?:\s*\((\d+)\s*NC\))?', record_text)
                if record_match:
                    fighter_data.update({
                        'wins': int(record_match.group(1)),
                        'losses': int(record_match.group(2)),
                        'draws': int(record_match.group(3)),
                        'no_contests': int(record_match.group(4)) if record_match.group(4) else 0
                    })
        
        # Nickname
        nickname_elem = soup.find('p', class_='b-content__Nickname')
        if nickname_elem:
            fighter_data['nickname'] = nickname_elem.get_text(strip=True)
        
        # Physical stats from first info box
        info_items = soup.find_all('li', class_='b-list__box-list-item')
        for item in info_items:
            title_elem = item.find('i', class_='b-list__box-item-title')
            if not title_elem:
                continue
                
            title = title_elem.get_text(strip=True).lower()
            value = item.get_text(strip=True).replace(title_elem.get_text(strip=True), '').strip()
            
            if 'height:' in title:
                fighter_data['height'] = value
            elif 'weight:' in title:
                fighter_data['weight'] = value
            elif 'reach:' in title:
                fighter_data['reach'] = value.replace('"', '').strip()
            elif 'stance:' in title:
                fighter_data['stance'] = value
            elif 'dob:' in title:
                fighter_data['dob'] = value
        
        # Career statistics
        stat_items = soup.find_all('li', class_='b-list__box-list-item')
        for item in stat_items:
            title_elem = item.find('i', class_='b-list__box-item-title')
            if not title_elem:
                continue
                
            title = title_elem.get_text(strip=True).lower()
            value = item.get_text(strip=True).replace(title_elem.get_text(strip=True), '').strip()
            
            if 'slpm:' in title:
                fighter_data['slpm'] = float(value) if value else 0
            elif 'str. acc.:' in title:
                fighter_data['str_acc'] = self._parse_percentage(value)
            elif 'sapm:' in title:
                fighter_data['sapm'] = float(value) if value else 0
            elif 'str. def:' in title:
                fighter_data['str_def'] = self._parse_percentage(value)
            elif 'td avg.:' in title:
                fighter_data['td_avg'] = float(value) if value else 0
            elif 'td acc.:' in title:
                fighter_data['td_acc'] = self._parse_percentage(value)
            elif 'td def.:' in title:
                fighter_data['td_def'] = self._parse_percentage(value)
            elif 'sub. avg.:' in title:
                fighter_data['sub_avg'] = float(value) if value else 0
        
        # Fight history
        fight_rows = soup.find_all('tr', class_='b-fight-details__table-row')
        fights = []
        
        for row in fight_rows:
            if not row.get('onclick'):  # Skip header rows
                continue
                
            fight_data = {}
            
            # Extract fight URL from onclick
            onclick = row.get('onclick', '')
            url_match = re.search(r"doNav\('([^']+)'\)", onclick)
            if url_match:
                fight_data['fight_url'] = url_match.group(1)
                fight_data['fight_id'] = self._extract_id_from_url(url_match.group(1))
            
            cols = row.find_all('td')
            if len(cols) >= 10:
                # W/L result
                result_elem = cols[0].find('a', class_='b-flag')
                if result_elem:
                    result_text = result_elem.find('i', class_='b-flag__text')
                    fight_data['result'] = result_text.get_text(strip=True) if result_text else ''
                
                # Opponent info
                fighter_links = cols[1].find_all('a', class_='b-link')
                if len(fighter_links) >= 2:
                    # Determine which is the current fighter vs opponent
                    for link in fighter_links:
                        link_url = link.get('href', '')
                        fighter_name = link.get_text(strip=True)
                        if fighter_url in link_url:
                            continue  # Skip current fighter
                        else:
                            fight_data['opponent_name'] = fighter_name
                            fight_data['opponent_id'] = self._extract_id_from_url(link_url)
                            break
                
                # Stats (KD, Str, Td, Sub) - extract current fighter's stats
                stats_cols = cols[2:6]  # KD, Str, Td, Sub columns
                stat_values = []
                for col in stats_cols:
                    texts = col.find_all('p', class_='b-fight-details__table-text')
                    if len(texts) >= 2:
                        # First p is current fighter, second is opponent
                        stat_values.append(texts[0].get_text(strip=True))
                
                if len(stat_values) >= 4:
                    fight_data.update({
                        'kd': int(stat_values[0]) if stat_values[0].isdigit() else 0,
                        'str': int(stat_values[1]) if stat_values[1].isdigit() else 0,
                        'td': int(stat_values[2]) if stat_values[2].isdigit() else 0,
                        'sub': int(stat_values[3]) if stat_values[3].isdigit() else 0
                    })
                
                # Event info
                event_link = cols[6].find('a', class_='b-link')
                if event_link:
                    fight_data['event_name'] = event_link.get_text(strip=True)
                    fight_data['event_url'] = event_link.get('href')
                    fight_data['event_id'] = self._extract_id_from_url(event_link.get('href', ''))
                
                # Date
                date_text = cols[6].find_all('p', class_='b-fight-details__table-text')
                if len(date_text) >= 2:
                    fight_data['date'] = date_text[1].get_text(strip=True)
                
                # Method
                method_texts = cols[7].find_all('p', class_='b-fight-details__table-text')
                if method_texts:
                    fight_data['method'] = method_texts[0].get_text(strip=True)
                    if len(method_texts) > 1:
                        fight_data['details'] = method_texts[1].get_text(strip=True)
                
                # Round and Time
                if len(cols) >= 10:
                    fight_data['round'] = cols[8].get_text(strip=True)
                    fight_data['time'] = cols[9].get_text(strip=True)
            
            fights.append(fight_data)
        
        fighter_data['fights'] = fights
        return fighter_data

    def scrape_event(self, event_url: str) -> Dict:
        """Scrape event details page"""
        soup = self._get_page(event_url)
        if not soup:
            return {}
        
        event_data = {
            'id': self._extract_id_from_url(event_url),
            'url': event_url
        }
        
        # Event name
        title_elem = soup.find('span', class_='b-content__title-highlight')
        if title_elem:
            event_data['name'] = title_elem.get_text(strip=True)
        
        # Date and Location
        info_items = soup.find_all('li', class_='b-list__box-list-item')
        for item in info_items:
            title_elem = item.find('i', class_='b-list__box-item-title')
            if not title_elem:
                continue
                
            title = title_elem.get_text(strip=True).lower()
            value = item.get_text(strip=True).replace(title_elem.get_text(strip=True), '').strip()
            
            if 'date:' in title:
                event_data['date'] = value
            elif 'location:' in title:
                event_data['location'] = value
        
        # Fight list with links
        fight_rows = soup.find_all('tr', class_='b-fight-details__table-row')
        fights = []
        
        for row in fight_rows:
            if not row.get('onclick'):
                continue
                
            fight_data = {}
            
            # Extract fight URL from onclick
            onclick = row.get('onclick', '')
            url_match = re.search(r"doNav\('([^']+)'\)", onclick)
            if url_match:
                fight_data['fight_url'] = url_match.group(1)
                fight_data['fight_id'] = self._extract_id_from_url(url_match.group(1))
            
            fights.append(fight_data)
        
        event_data['fights'] = fights
        return event_data

    def scrape_fight(self, fight_url: str) -> Dict:
        """Scrape detailed fight statistics"""
        soup = self._get_page(fight_url)
        if not soup:
            return {}
        
        fight_data = {
            'id': self._extract_id_from_url(fight_url),
            'url': fight_url
        }
        
        # Event info
        event_link = soup.find('h2', class_='b-content__title').find('a') if soup.find('h2', class_='b-content__title') else None
        if event_link:
            fight_data['event_url'] = event_link.get('href')
            fight_data['event_id'] = self._extract_id_from_url(event_link.get('href', ''))
            fight_data['event_name'] = event_link.get_text(strip=True)
        
        # Fighter info
        fighter_divs = soup.find_all('div', class_='b-fight-details__person')
        fighters = []
        
        for div in fighter_divs:
            fighter = {}
            
            # W/L status
            status_elem = div.find('i', class_='b-fight-details__person-status')
            if status_elem:
                fighter['result'] = status_elem.get_text(strip=True)
            
            # Fighter link
            link_elem = div.find('a', class_='b-fight-details__person-link')
            if link_elem:
                fighter['name'] = link_elem.get_text(strip=True)
                fighter['url'] = link_elem.get('href')
                fighter['id'] = self._extract_id_from_url(link_elem.get('href', ''))
            
            # Nickname
            nickname_elem = div.find('p', class_='b-fight-details__person-title')
            if nickname_elem:
                fighter['nickname'] = nickname_elem.get_text(strip=True)
            
            fighters.append(fighter)
        
        fight_data['fighters'] = fighters
        
        # Fight details
        details = soup.find('div', class_='b-fight-details__content')
        if details:
            text_items = details.find_all('i', class_='b-fight-details__text-item')
            text_items.extend(details.find_all('i', class_='b-fight-details__text-item_first'))

            for item in text_items:
                label_elem = item.find('i', class_='b-fight-details__label')
                if not label_elem:
                    continue

                label = label_elem.get_text(strip=True).lower()
                value = item.get_text(strip=True).replace(label_elem.get_text(strip=True), '').strip()

                if 'method:' in label:
                    fight_data['method'] = value
                elif 'round:' in label:
                    fight_data['round'] = int(value) if value.isdigit() else 0
                elif 'time:' in label and 'time format' not in label:
                    fight_data['time'] = value
                elif 'time format:' in label:
                    fight_data['time_format'] = value
                elif 'referee:' in label:
                    fight_data['referee'] = value
                elif 'details:' in label:
                    # Sometimes "Details:" is a labeled row just like Method/Referee
                    fight_data['details'] = value

            # Fallback: on many pages "Details:" is a paragraph right after the labels
            if 'details' not in fight_data:
                for p in details.find_all('p', class_='b-fight-details__text'):
                    txt = p.get_text(" ", strip=True)
                    m = re.search(r'Details:\s*(.+)', txt)
                    if m:
                        fight_data['details'] = m.group(1).strip()
                        break

        fight_title = soup.find('i', class_='b-fight-details__fight-title')
        if fight_title:
            title_text = fight_title.get_text(strip=True)
            fight_data['is_title_fight'] = 'Title' in title_text
            
            # Extract weight class (remove "Title" and "Bout" words)
            weight_class = re.sub(r'\b(Title|Bout)\b', '', title_text).strip()
            fight_data['weight_class'] = weight_class
        
        # Method, Round, Time, etc.
        details = soup.find('div', class_='b-fight-details__content')
        if details:
            text_items = details.find_all('i', class_='b-fight-details__text-item')
            text_items.extend(details.find_all('i', class_='b-fight-details__text-item_first'))

            for item in text_items:
                label_elem = item.find('i', class_='b-fight-details__label')
                if not label_elem:
                    continue

                label = label_elem.get_text(strip=True).lower()
                # preserve spaces so multi-word details don’t collapse
                value = item.get_text(" ", strip=True).replace(label_elem.get_text(strip=True), '').strip()

                if 'method:' in label:
                    fight_data['method'] = value
                elif 'round:' in label:
                    fight_data['round'] = int(value) if value.isdigit() else 0
                elif 'time:' in label and 'time format' not in label:
                    fight_data['time'] = value
                elif 'time format:' in label:
                    fight_data['time_format'] = value
                elif 'referee:' in label:
                    fight_data['referee'] = value
                elif 'details:' in label:
                    # only set when non-empty; don't block the fallback with ""
                    if value:
                        fight_data['details'] = value

            # Fallback: paragraph form like "Details: Spinning Back Kick Body"
            # Use truthiness, not key existence, so we recover from an empty labeled row
            if not fight_data.get('details'):
                for p in details.find_all('p', class_='b-fight-details__text'):
                    txt = p.get_text(" ", strip=True)
                    m = re.search(r'\bDetails:\s*(.+)', txt, flags=re.I)
                    if m:
                        val = m.group(1).strip()
                        if val:
                            fight_data['details'] = val
                            break
        
        # Extract fight totals and round data
        fight_data['totals'] = self._extract_fight_stats(soup, is_totals=True)
        fight_data['rounds'] = self._extract_round_stats(soup)

        fight_data['rounds'] = self._extract_sig_strikes_rounds(soup, fight_data['rounds'])
        
        return fight_data

    def _extract_fight_stats(self, soup: BeautifulSoup, is_totals=True) -> List[Dict]:
        """Extract fighter statistics from totals table"""
        fighters_stats = []
        
        # Find the totals table - look for the first table after "Totals" section
        sections = soup.find_all('section', class_='b-fight-details__section')
        stats_table = None
        
        for section in sections:
            # Look for section containing "Totals" text
            if section.get_text() and 'Totals' in section.get_text():
                # Find the next table element
                stats_table = section.find_next('table')
                break
        
        # If we didn't find it via sections, try a more direct approach
        if not stats_table:
            # Look for any table with the right structure
            tables = soup.find_all('table')
            for table in tables:
                thead = table.find('thead')
                if thead and 'Fighter' in thead.get_text() and 'Sig. str.' in thead.get_text():
                    stats_table = table
                    break
        
        if not stats_table:
            return []
        
        # Get the data row (skip header)
        tbody = stats_table.find('tbody')
        if not tbody:
            return []
            
        data_row = tbody.find('tr')
        if not data_row:
            return []
        
        # Extract fighter names and stats
        cols = data_row.find_all('td')
        if len(cols) < 10:
            return []
        
        # Fighter names (first column has both fighters)
        fighter_names = []
        name_links = cols[0].find_all('a')
        for link in name_links:
            fighter_names.append({
                'name': link.get_text(strip=True),
                'id': self._extract_id_from_url(link.get('href', ''))
            })
        
        # Extract stats for each fighter
        for i in range(min(2, len(fighter_names))):  # Max 2 fighters
            fighter_stats = fighter_names[i].copy()
            
            # Get stats from each column (each column has 2 p tags for 2 fighters)
            stat_cols = cols[1:]  # Skip fighter names column
            stat_names = ['kd', 'sig_str', 'sig_str_pct', 'total_str', 'td', 'td_pct', 'sub_att', 'rev', 'ctrl']
            
            for j, col in enumerate(stat_cols):
                if j >= len(stat_names):
                    break
                    
                stat_texts = col.find_all('p', class_='b-fight-details__table-text')
                if len(stat_texts) > i:
                    stat_value = stat_texts[i].get_text(strip=True)
                    
                    if stat_names[j] in ['sig_str', 'total_str', 'td']:
                        # Parse "X of Y" format
                        landed, attempted = self._parse_stat_fraction(stat_value)
                        fighter_stats[f"{stat_names[j]}_landed"] = landed
                        fighter_stats[f"{stat_names[j]}_attempted"] = attempted
                    elif stat_names[j] in ['sig_str_pct', 'td_pct']:
                        fighter_stats[stat_names[j]] = self._parse_percentage(stat_value)
                    elif stat_names[j] == 'ctrl':
                        fighter_stats['control_time'] = self._parse_time_control(stat_value)
                    else:
                        # Simple integer stats
                        fighter_stats[stat_names[j]] = int(stat_value) if stat_value.isdigit() else 0
            
            fighters_stats.append(fighter_stats)
        
        # Add significant strikes breakdown
        sig_strikes_table = self._find_sig_strikes_table(soup)
        if sig_strikes_table:
            sig_stats = self._extract_sig_strikes_stats(sig_strikes_table)
            for i, fighter_stat in enumerate(fighters_stats):
                if i < len(sig_stats):
                    fighter_stat.update(sig_stats[i])
        
        return fighters_stats

    def _find_sig_strikes_table(self, soup: BeautifulSoup):
        """Find the significant strikes breakdown table"""
        # Look for table after "Significant Strikes" text or section
        # First try to find by section text
        sections = soup.find_all('section', class_='b-fight-details__section')
        for section in sections:
            if 'Significant Strikes' in section.get_text():
                table = section.find_next('table')
                if table:
                    return table
        
        # If that doesn't work, look for any table with Head/Body/Leg columns
        tables = soup.find_all('table')
        for table in tables:
            thead = table.find('thead')
            if thead:
                header_text = thead.get_text()
                if 'Head' in header_text and 'Body' in header_text and 'Leg' in header_text:
                    return table
        
        return None

    def _extract_sig_strikes_stats(self, table) -> List[Dict]:
        """Extract significant strikes breakdown (Head/Body/Leg, Distance/Clinch/Ground)"""
        fighters_stats = []
        
        data_row = table.find('tbody').find('tr') if table.find('tbody') else None
        if not data_row:
            return []
        
        cols = data_row.find_all('td')
        if len(cols) < 9:
            return []
        
        # Get fighter names
        fighter_names = []
        name_links = cols[0].find_all('a')
        for link in name_links:
            fighter_names.append(link.get_text(strip=True))
        
        # Extract stats for each fighter
        for i in range(min(2, len(fighter_names))):
            fighter_stats = {}
            
            # Columns: Sig str, Sig str %, Head, Body, Leg, Distance, Clinch, Ground
            stat_cols = cols[1:]
            stat_names = ['sig_str_total', 'sig_str_pct', 'head', 'body', 'leg', 'distance', 'clinch', 'ground']
            
            for j, col in enumerate(stat_cols):
                if j >= len(stat_names):
                    break
                    
                stat_texts = col.find_all('p', class_='b-fight-details__table-text')
                if len(stat_texts) > i:
                    stat_value = stat_texts[i].get_text(strip=True)
                    
                    if stat_names[j] in ['sig_str_total', 'head', 'body', 'leg', 'distance', 'clinch', 'ground']:
                        # Parse "X of Y" format
                        landed, attempted = self._parse_stat_fraction(stat_value)
                        fighter_stats[f"{stat_names[j]}_landed"] = landed
                        fighter_stats[f"{stat_names[j]}_attempted"] = attempted
                    elif stat_names[j] == 'sig_str_pct':
                        fighter_stats[stat_names[j]] = self._parse_percentage(stat_value)
            
            fighters_stats.append(fighter_stats)
        
        return fighters_stats
    
    def _extract_round_stats_from_row(self, round_number: int, data_row) -> Dict:
        """Extract stats for a single round from a tr element"""
        cols = data_row.find_all('td')
        print(f"DEBUG: Round {round_number} has {len(cols)} columns")
        
        if len(cols) < 9:
            print(f"DEBUG: Round {round_number} data row has insufficient columns: {len(cols)}")
            return None
        
        round_stats = {
            'round_number': round_number,
            'fighters': []
        }
        
        # Get fighter names from first column
        fighter_links = cols[0].find_all('a', class_='b-link')
        if len(fighter_links) < 2:
            print(f"DEBUG: Round {round_number} has insufficient fighter links: {len(fighter_links)}")
            return None
        
        # Extract stats for each fighter
        for i in range(2):  # Always 2 fighters
            fighter_name = fighter_links[i].get_text(strip=True)
            
            fighter_stats = {
                'name': fighter_name,
                'id': self._extract_id_from_url(fighter_links[i].get('href', ''))
            }
            
            # This appears to be significant strikes breakdown data (9 columns)
            # Column mapping: Fighter, Sig str, Sig str %, Head, Body, Leg, Distance, Clinch, Ground
            stat_names = ['sig_str', 'sig_str_pct', 'head', 'body', 'leg', 'distance', 'clinch', 'ground']
            
            # Process each stat column
            for j, stat_name in enumerate(stat_names):
                col_index = j + 1  # Skip fighter name column
                if col_index >= len(cols):
                    break
                    
                col = cols[col_index]
                stat_texts = col.find_all('p', class_='b-fight-details__table-text')
                
                if len(stat_texts) > i:
                    stat_value = stat_texts[i].get_text(strip=True)
                    
                    if stat_name in ['sig_str', 'head', 'body', 'leg', 'distance', 'clinch', 'ground']:
                        landed, attempted = self._parse_stat_fraction(stat_value)
                        fighter_stats[f"{stat_name}_landed"] = landed
                        fighter_stats[f"{stat_name}_attempted"] = attempted
                    elif stat_name == 'sig_str_pct':
                        fighter_stats[stat_name] = self._parse_percentage(stat_value)
            
            round_stats['fighters'].append(fighter_stats)
        
        return round_stats

    def _extract_general_round_stats_from_row(self, round_number: int, data_row) -> Dict:
        """Extract general round stats (10 columns: Fighter, KD, Sig str, %, Total str, TD, TD%, Sub, Rev, Ctrl)"""
        cols = data_row.find_all('td')
        
        round_stats = {
            'round_number': round_number,
            'fighters': []
        }
        
        # Get fighter names from first column
        fighter_links = cols[0].find_all('a', class_='b-link')
        if len(fighter_links) < 2:
            return None
        
        # Extract stats for each fighter
        for i in range(2):  # Always 2 fighters
            fighter_name = fighter_links[i].get_text(strip=True)
            
            fighter_stats = {
                'name': fighter_name,
                'id': self._extract_id_from_url(fighter_links[i].get('href', ''))
            }
            
            # Column mapping for general stats: Fighter, KD, Sig str, Sig str %, Total str, TD, TD %, Sub att, Rev, Ctrl
            stat_names = ['kd', 'sig_str', 'sig_str_pct', 'total_str', 'td', 'td_pct', 'sub_att', 'rev', 'ctrl']
            
            for j, stat_name in enumerate(stat_names):
                col_index = j + 1  # Skip fighter name column
                if col_index >= len(cols):
                    break
                    
                col = cols[col_index]
                stat_texts = col.find_all('p', class_='b-fight-details__table-text')
                
                if len(stat_texts) > i:
                    stat_value = stat_texts[i].get_text(strip=True)
                    
                    if stat_name in ['sig_str', 'total_str', 'td']:
                        landed, attempted = self._parse_stat_fraction(stat_value)
                        fighter_stats[f"{stat_name}_landed"] = landed
                        fighter_stats[f"{stat_name}_attempted"] = attempted
                    elif stat_name in ['sig_str_pct', 'td_pct']:
                        fighter_stats[stat_name] = self._parse_percentage(stat_value)
                    elif stat_name == 'ctrl':
                        fighter_stats['control_time'] = self._parse_time_control(stat_value)
                    else:
                        fighter_stats[stat_name] = int(stat_value) if stat_value.isdigit() else 0
            
            round_stats['fighters'].append(fighter_stats)
        
        return round_stats

    def _extract_round_stats(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract per-round statistics — robust tbody lookup after each Round header"""
        rounds = []

        print("DEBUG: Starting round extraction")

        # Find ALL sections with "Per round" collapse links
        sections = soup.find_all('section', class_='b-fight-details__section')
        per_round_sections = []
        for section in sections:
            collapse_link = section.find('a', class_='b-fight-details__collapse-link_rnd')
            if collapse_link and 'Per round' in collapse_link.get_text():
                per_round_sections.append(section)

        print(f"DEBUG: Found {len(per_round_sections)} per-round sections")
        if not per_round_sections:
            return rounds

        # Use the first per-round section = general stats
        per_round_section = per_round_sections[0]
        print("DEBUG: Using first per-round section (general stats)")

        table = per_round_section.find('table', class_='b-fight-details__table')
        if not table:
            print("DEBUG: Could not find per-round table")
            return rounds

        print("DEBUG: Found per-round table")

        # Verify this is the general stats table (has KD, Sig. Str., etc.)
        header_row = table.find('thead', class_='b-fight-details__table-head_rnd')
        if header_row:
            columns = header_row.find_all('th')
            column_texts = [col.get_text(strip=True) for col in columns]
            print(f"DEBUG: Table columns: {column_texts}")
            if 'KD' not in ' '.join(column_texts):
                print("DEBUG: This doesn't appear to be the general stats table")
                return rounds

        # Each "Round N" is a <thead class="b-fight-details__table-row_type_head">
        round_headers = table.find_all('thead', class_='b-fight-details__table-row_type_head')
        print(f"DEBUG: Found {len(round_headers)} round headers")

        for header in round_headers:
            th = header.find('th')
            if not th:
                continue

            text = th.get_text()
            if 'Round' not in text:
                continue

            m = re.search(r'Round\s+(\d+)', text)
            if not m:
                continue

            round_number = int(m.group(1))
            print(f"DEBUG: Processing Round {round_number}")

            # Robust approach: the round's <tbody> is the NEXT sibling of this header
            tbody = header.find_next_sibling('tbody')

            # Fallback: if parser quirks, climb to the nearest <thead> then hop to next <tbody>
            if not tbody:
                parent_thead = header if header.name == 'thead' else header.find_parent('thead')
                if parent_thead:
                    tbody = parent_thead.find_next_sibling('tbody')

            if not tbody:
                print(f"DEBUG: No tbody sibling found for Round {round_number}")
                continue

            # Safety: ensure this tbody still belongs to the same table
            if tbody.find_parent('table') is not table:
                print(f"DEBUG: Skipping Round {round_number} — tbody not in the same table")
                continue

            rows = tbody.find_all('tr')
            print(f"DEBUG: Tbody for Round {round_number} has {len(rows)} rows")

            if not rows:
                print(f"DEBUG: No data rows for Round {round_number}")
                continue

            data_row = rows[0]  # One combined row per round
            cols = data_row.find_all('td')
            print(f"DEBUG: Round {round_number} first row has {len(cols)} columns")

            # General per-round table usually has >= 10 columns
            if len(cols) >= 10:
                print(f"DEBUG: Extracting Round {round_number}")
                round_stats = self._extract_general_round_stats_from_row(round_number, data_row)
                if round_stats:
                    rounds.append(round_stats)
                    print(f"DEBUG: Successfully extracted Round {round_number}")
                else:
                    print(f"DEBUG: Failed to extract stats from Round {round_number}")
            else:
                print(f"DEBUG: Row has insufficient columns for Round {round_number}: {len(cols)}")

        print(f"DEBUG: Total rounds extracted: {len(rounds)}")
        return rounds
    
    def _extract_round_stats(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract per-round statistics — resilient to tbody-less layouts (thead -> tr)"""
        rounds: List[Dict] = []

        print("DEBUG: Starting round extraction")

        # Find ALL sections with "Per round" collapse links
        sections = soup.find_all('section', class_='b-fight-details__section')
        per_round_sections = []
        for section in sections:
            collapse_link = section.find('a', class_='b-fight-details__collapse-link_rnd')
            if collapse_link and 'Per round' in collapse_link.get_text():
                per_round_sections.append(section)

        print(f"DEBUG: Found {len(per_round_sections)} per-round sections")
        if not per_round_sections:
            return rounds

        # Use the first per-round section = general stats ("KD, Sig. str., Total str., Td, ...")
        per_round_section = per_round_sections[0]
        print("DEBUG: Using first per-round section (general stats)")

        table = per_round_section.find('table', class_='b-fight-details__table')
        if not table:
            print("DEBUG: Could not find per-round table")
            return rounds

        print("DEBUG: Found per-round table")

        # Verify we’re on the general stats per-round table (not the sig-strikes breakdown one)
        header_row = table.find('thead', class_='b-fight-details__table-head_rnd')
        if header_row:
            columns = header_row.find_all('th')
            column_texts = [col.get_text(strip=True) for col in columns]
            print(f"DEBUG: Table columns: {column_texts}")
            if 'KD' not in ' '.join(column_texts):
                print("DEBUG: This doesn't appear to be the general stats table")
                return rounds

        # "Round N" headers
        round_headers = table.find_all('thead', class_='b-fight-details__table-row_type_head')
        print(f"DEBUG: Found {len(round_headers)} round headers")

        for header in round_headers:
            th = header.find('th')
            if not th:
                continue
            text = th.get_text(strip=True)
            m = re.search(r'Round\s+(\d+)', text)
            if not m:
                continue

            round_number = int(m.group(1))
            print(f"DEBUG: Processing Round {round_number}")

            # Walk through *siblings* only, stopping at the next round header
            data_row = None
            for sib in header.next_siblings:
                # Skip whitespace/text
                if not hasattr(sib, "name"):
                    continue

                # Stop if we hit the next round header
                if sib.name == "thead" and "b-fight-details__table-row_type_head" in (sib.get("class") or []):
                    print(f"DEBUG: Hit next round header before finding a row for Round {round_number}")
                    break

                # Case 1: tbody -> take its first tr
                if sib.name == "tbody":
                    # Ensure this tbody belongs to the same table
                    if sib.find_parent('table') is table:
                        rows = sib.find_all('tr')
                        print(f"DEBUG: Found tbody with {len(rows)} rows for Round {round_number}")
                        if rows:
                            data_row = rows[0]
                            break

                # Case 2: some parsers flatten to thead -> tr (no tbody)
                if sib.name == "tr":
                    # Ensure this tr is still in this table (either direct child or inside implicit tbody)
                    if sib.find_parent('table') is table:
                        print(f"DEBUG: Found tr directly after header for Round {round_number}")
                        data_row = sib
                        break

            if not data_row:
                print(f"DEBUG: No data row found for Round {round_number}")
                continue

            cols = data_row.find_all('td')
            print(f"DEBUG: Round {round_number} first row has {len(cols)} columns")

            # General per-round table has 10 columns (Fighter, KD, Sig/%, Total, Td/Td%, Sub, Rev, Ctrl)
            if len(cols) >= 10:
                print(f"DEBUG: Extracting Round {round_number}")
                round_stats = self._extract_general_round_stats_from_row(round_number, data_row)
                if round_stats:
                    rounds.append(round_stats)
                    print(f"DEBUG: Successfully extracted Round {round_number}")
                else:
                    print(f"DEBUG: Failed to extract stats from Round {round_number}")
            else:
                print(f"DEBUG: Row has insufficient columns for Round {round_number}: {len(cols)}")

        print(f"DEBUG: Total rounds extracted: {len(rounds)}")
        return rounds


    def _extract_sig_strikes_rounds(self, soup: BeautifulSoup, existing_rounds: List[Dict]) -> List[Dict]:
        """Extract Significant Strikes per-round breakdown and merge into existing round data."""
        if not existing_rounds:
            return existing_rounds

        print("DEBUG: Starting significant strikes per-round extraction")

        # Find all "Per round" sections on the page
        sections = soup.find_all('section', class_='b-fight-details__section')
        per_round_sections = []
        for section in sections:
            link = section.find('a', class_='b-fight-details__collapse-link_rnd')
            if link and 'Per round' in link.get_text():
                per_round_sections.append(section)

        if not per_round_sections:
            print("DEBUG: No per-round sections found for sig strikes")
            return existing_rounds

        # Identify the sig-strikes per-round table by its header (has Head/Body/Leg/Distance)
        sig_table = None
        for sec in per_round_sections:
            table = sec.find('table', class_='b-fight-details__table')
            if not table:
                continue
            thead = table.find('thead', class_='b-fight-details__table-head_rnd')
            header_txt = thead.get_text(" ", strip=True) if thead else ""
            if all(k in header_txt for k in ["Head", "Body", "Leg", "Distance"]):
                sig_table = table
                break

        if not sig_table:
            print("DEBUG: Could not locate significant strikes per-round table")
            return existing_rounds

        # Gather all "Round N" headers inside this table
        round_headers = sig_table.find_all('thead', class_='b-fight-details__table-row_type_head')
        print(f"DEBUG: Sig-strikes per-round: found {len(round_headers)} round headers")

        # Helper: walk siblings after a given header until next header; return first row we see
        def _row_after_header(table, header):
            for sib in header.next_siblings:
                if not hasattr(sib, "name"):
                    continue
                # stop at next round header
                if sib.name == "thead" and "b-fight-details__table-row_type_head" in (sib.get("class") or []):
                    return None
                # tbody → take its first tr
                if sib.name == "tbody" and (sib.find_parent('table') is table):
                    tr = sib.find('tr')
                    if tr:
                        return tr
                # parser may flatten to thead → tr (no tbody)
                if sib.name == "tr" and (sib.find_parent('table') is table):
                    return sib
            return None

        # Parse a sig-strikes per-round <tr> into two fighter dicts (with IDs)
        def _parse_sig_row(row):
            cols = row.find_all('td')
            if len(cols) < 9:
                return []

            # Fighter IDs & names
            links = cols[0].find_all('a', class_='b-link')
            fighter_ids = [self._extract_id_from_url(a.get('href', '')) for a in links]
            fighter_names = [a.get_text(strip=True) for a in links]

            # Columns (skip fighter names col)
            stat_cols = cols[1:]
            labels = ['sig_str_total', 'sig_str_pct', 'head', 'body', 'leg', 'distance', 'clinch', 'ground']

            out = []
            for i in range(min(2, len(fighter_ids))):
                d = {'id': fighter_ids[i], 'name': fighter_names[i]}
                for j, label in enumerate(labels):
                    col = stat_cols[j]
                    texts = col.find_all('p', class_='b-fight-details__table-text')
                    if len(texts) <= i:
                        continue
                    val = texts[i].get_text(strip=True)
                    if label == 'sig_str_pct':
                        d['sig_str_pct_detailed'] = self._parse_percentage(val)
                    else:
                        landed, attempted = self._parse_stat_fraction(val)
                        d[f"{label}_landed"] = landed
                        d[f"{label}_attempted"] = attempted
                out.append(d)
            return out

        # Round → list[fighter stats]
        sig_by_round: Dict[int, List[Dict]] = {}

        for hdr in round_headers:
            th = hdr.find('th')
            if not th:
                continue
            m = re.search(r'Round\s+(\d+)', th.get_text(strip=True))
            if not m:
                continue

            rnd = int(m.group(1))
            row = _row_after_header(sig_table, hdr)
            if not row:
                print(f"DEBUG: Sig-strikes: no row found for Round {rnd}")
                continue

            fighters_stats = _parse_sig_row(row)
            if fighters_stats:
                sig_by_round[rnd] = fighters_stats
                print(f"DEBUG: Sig-strikes: parsed Round {rnd}")

        # Merge into existing rounds by round_number + fighter id
        for rnd_obj in existing_rounds:
            rn = rnd_obj.get('round_number')
            if rn not in sig_by_round:
                continue
            adders = {f['id']: f for f in sig_by_round[rn]}
            for f in rnd_obj.get('fighters', []):
                fid = f.get('id')
                if fid in adders:
                    # Add only the detailed breakdown fields to avoid colliding with general stats
                    extra = adders[fid]
                    for k, v in extra.items():
                        if k in ('id', 'name'):
                            continue
                        f[k] = v

        print("DEBUG: Significant strikes per-round merged")
        return existing_rounds

    def _extract_single_round_sig_strikes(self, round_number: int, tbody) -> List[Dict]:
        """Extract significant strikes breakdown for a single round"""
        data_row = tbody.find('tr')
        if not data_row:
            return []
        
        cols = data_row.find_all('td')
        if len(cols) < 9:  # Need 9 columns for sig strikes breakdown
            return []
        
        fighters_sig_stats = []
        
        # Get fighter names
        fighter_links = cols[0].find_all('a', class_='b-link')
        
        # Extract sig strikes stats for each fighter
        for i in range(min(2, len(fighter_links))):
            sig_stats = {}
            
            # Column mapping for sig strikes:
            # 0: Fighter, 1: Sig str, 2: Sig str %, 3: Head, 4: Body, 5: Leg, 6: Distance, 7: Clinch, 8: Ground
            stat_names = ['sig_str_total', 'sig_str_pct_detailed', 'head', 'body', 'leg', 'distance', 'clinch', 'ground']
            
            for j, stat_name in enumerate(stat_names):
                col_index = j + 1
                if col_index >= len(cols):
                    break
                    
                col = cols[col_index]
                stat_texts = col.find_all('p', class_='b-fight-details__table-text')
                
                if len(stat_texts) > i:
                    stat_value = stat_texts[i].get_text(strip=True)
                    
                    if stat_name in ['sig_str_total', 'head', 'body', 'leg', 'distance', 'clinch', 'ground']:
                        landed, attempted = self._parse_stat_fraction(stat_value)
                        sig_stats[f"{stat_name}_landed"] = landed
                        sig_stats[f"{stat_name}_attempted"] = attempted
                    elif stat_name == 'sig_str_pct_detailed':
                        sig_stats['sig_str_pct_detailed'] = self._parse_percentage(stat_value)
            
            fighters_sig_stats.append(sig_stats)
        
        return fighters_sig_stats
    
    def iter_fighter_urls(self, letter: str) -> Iterable[str]:
        """
        Yield fighter-details URLs for a given letter (last name index).
        Uses the 'page=all' variant to avoid pagination.
        Example: http://ufcstats.com/statistics/fighters?char=a&page=all
        """
        url = f"{self.base_url}/statistics/fighters?char={letter}&page=all"
        soup = self._get_soup(url)
        if not soup:
            return

        # Be flexible about table structure: grab any anchors that look like fighter links
        seen = set()
        for a in soup.select('a[href*="/fighter-details/"]'):
            href = (a.get("href") or "").strip()
            if href and "/fighter-details/" in href and href not in seen:
                seen.add(href)
                yield href

    def iter_all_fighter_urls(self, letters: str = ALPHABET) -> Iterable[Tuple[str, str]]:
        """Yield (letter, fighter_url) for all letters requested."""
        for ch in letters:
            for f_url in self.iter_fighter_urls(ch):
                yield ch, f_url

    # ---------- Fighter -> fights ----------
    def iter_fight_urls_for_fighter(self, fighter_url: str) -> Iterable[str]:
        """
        On a fighter-details page, pull fight-details links from the 'FIGHT HISTORY - PRO' table.
        Your fighter scraper already visits this page, but this method is lightweight and robust.
        """
        soup = self._get_soup(fighter_url)
        if not soup:
            return
        # Any link that looks like a fight-details page
        seen = set()
        for a in soup.select('a[href*="/fight-details/"]'):
            href = (a.get("href") or "").strip()
            if href and "/fight-details/" in href and href not in seen:
                seen.add(href)
                yield href

    # ---------- Orchestrator ----------
    def crawl_all(
        self,
        letters: str = ALPHABET,
        out_dir: str = "out",
        throttle_range: Tuple[float, float] = (0.6, 1.2),
        checkpoint_path: str = "out/checkpoint.jsonl",
        write_jsonl: bool = True,
    ):
        """
        Crawl all fighters (A–Z), then all their fights, then events for those fights.
        Saves fighters.jsonl, fights.jsonl, events.jsonl in `out_dir` (append-only, de-duplicated in-memory).
        """
        os.makedirs(out_dir, exist_ok=True)

        fighters_path = os.path.join(out_dir, "fighters.jsonl")
        fights_path   = os.path.join(out_dir, "fights.jsonl")
        events_path   = os.path.join(out_dir, "events.jsonl")

        # In-memory dedupe (optionally hydrate from disk if resuming)
        seen_fighters: Set[str] = set()
        seen_fights:   Set[str] = set()
        seen_events:   Set[str] = set()

        def _sleep():
            lo, hi = throttle_range
            time.sleep(random.uniform(lo, hi))

        # --- Crawl fighters by letter ---
        for letter, fighter_url in self.iter_all_fighter_urls(letters):
            # fighter_id = self._extract_id(fighter_url)  # you already have _extract_id(...)
            fighter_id = self._extract_id_from_url(fighter_url)
            if fighter_id in seen_fighters:
                continue

            try:
                fighter_data = self.scrape_fighter(fighter_url)  # your existing method
                seen_fighters.add(fighter_id)
                if write_jsonl and fighter_data:
                    with open(fighters_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(fighter_data, ensure_ascii=False) + "\n")
                print(f"[fighters] {letter.upper()} :: {fighter_data.get('name','?')} ({fighter_id})")
            except Exception as e:
                print(f"[fighters][ERR] {fighter_url} :: {e}")
            _sleep()

            # --- For each fighter, crawl their fights ---
            for fight_url in self.iter_fight_urls_for_fighter(fighter_url):
                # fight_id = self._extract_id(fight_url)
                fight_id   = self._extract_id_from_url(fight_url)
                if fight_id in seen_fights:
                    continue
                try:
                    fight_data = self.scrape_fight(fight_url)  # your existing method (now with per-rounds fixed)
                    if fight_data:
                        seen_fights.add(fight_id)
                        if write_jsonl:
                            with open(fights_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps(fight_data, ensure_ascii=False) + "\n")
                        print(f"[fights] {fight_id} :: {fight_data.get('event_name','?')}")
                        _sleep()

                        # --- Crawl the event for this fight ---
                        event_url = fight_data.get("event_url")
                        if event_url:
                            # event_id = self._extract_id(event_url)
                            event_id   = self._extract_id_from_url(event_url)
                            if event_id not in seen_events:
                                try:
                                    event_data = self.scrape_event(event_url)  # your existing method
                                    if event_data:
                                        seen_events.add(event_id)
                                        if write_jsonl:
                                            with open(events_path, "a", encoding="utf-8") as f:
                                                f.write(json.dumps(event_data, ensure_ascii=False) + "\n")
                                        print(f"[events] {event_id} :: {event_data.get('name','?')}")
                                except Exception as ee:
                                    print(f"[events][ERR] {event_url} :: {ee}")
                                _sleep()
                except Exception as e:
                    print(f"[fights][ERR] {fight_url} :: {e}")
                _sleep()

# Example usage
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--letters", default="q", help="Letters of last-name index to crawl (e.g. 'q' or 'abc')")
    ap.add_argument("--out", default="out_q", help="Output directory")
    ap.add_argument("--min-delay", type=float, default=0.6, help="Min polite delay between requests (seconds)")
    ap.add_argument("--max-delay", type=float, default=1.2, help="Max polite delay between requests (seconds)")
    args = ap.parse_args()

    scraper = UFCStatsScraper(delay_range=(args.min_delay, args.max_delay))
    scraper.crawl_all(letters=args.letters, out_dir=args.out)