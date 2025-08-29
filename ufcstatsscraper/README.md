# UFC Fight Data Scraper

A Python scraper for extracting UFC fight data from UFC Stats website for machine learning and analytics purposes.

## Features

- **Fighter Data**: Personal stats, career statistics, complete fight history
- **Event Data**: Event details, location, date, fight listings  
- **Fight Data**: Detailed fight statistics including round-by-round breakdowns
- **Polite Crawling**: Built-in delays and proper headers to respect the website
- **Robust Parsing**: Handles various data formats and edge cases

## Setup

### 1. Clone/Download the project
```bash
git clone <your-repo> # or download the files
cd ufc-scraper
```

### 2. Create Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

## Usage

### Basic Example
```python
from ufc_stats_scraper import UFCStatsScraper

# Initialize scraper
scraper = UFCStatsScraper(delay_range=(1, 3))

# Test URLs
fighter_url = "http://ufcstats.com/fighter-details/07f72a2a7591b409"  # Jon Jones
event_url = "http://ufcstats.com/event-details/daff32bc96d1eabf"     # UFC 309
fight_url = "http://ufcstats.com/fight-details/b35e47f2f58ef026"     # Jones vs Miocic

# Scrape fighter data
fighter_data = scraper.scrape_fighter(fighter_url)
print(f"Fighter: {fighter_data['name']}")
print(f"Record: {fighter_data['wins']}-{fighter_data['losses']}-{fighter_data['draws']}")

# Scrape event data
event_data = scraper.scrape_event(event_url)
print(f"Event: {event_data['name']}")
print(f"Date: {event_data['date']}")

# Scrape fight data  
fight_data = scraper.scrape_fight(fight_url)
print(f"Title Fight: {fight_data['is_title_fight']}")
print(f"Method: {fight_data['method']}")
```

### Running the Test Script
```bash
python ufc_stats_scraper.py
```

This will run the example at the bottom of the scraper file using the Jon Jones vs Stipe Miocic fight data.

## Data Structure

### Fighter Data
```python
{
    'id': 'fighter_id',
    'name': 'Fighter Name', 
    'nickname': 'Nickname',
    'height': '6\' 4"',
    'weight': '248 lbs.',
    'reach': '84',
    'stance': 'Orthodox',
    'dob': 'Jul 19, 1987',
    'wins': 28,
    'losses': 1, 
    'draws': 0,
    'no_contests': 1,
    'slpm': 4.38,           # Significant Strikes Landed per Minute
    'str_acc': 58,          # Striking Accuracy %
    'sapm': 2.24,           # Significant Strikes Absorbed per Minute  
    'str_def': 64,          # Strike Defense %
    'td_avg': 1.89,         # Takedown Average
    'td_acc': 45,           # Takedown Accuracy %
    'td_def': 95,           # Takedown Defense %
    'sub_avg': 0.5,         # Submission Average
    'fights': [...]         # Complete fight history
}
```

### Fight Data  
```python
{
    'id': 'fight_id',
    'event_name': 'UFC 309: Jones vs. Miocic',
    'is_title_fight': True,
    'weight_class': 'UFC Heavyweight',
    'method': 'KO/TKO',
    'round': 3,
    'time': '4:29',
    'referee': 'Herb Dean',
    'details': 'Spinning Back Kick Body',
    'fighters': [...],      # Fighter info and results
    'totals': [...],        # Fight totals for each fighter
    'rounds': [...]         # Round-by-round stats
}
```

### Fight Statistics (Totals & Rounds)
```python
{
    'name': 'Fighter Name',
    'id': 'fighter_id', 
    'kd': 1,                           # Knockdowns
    'sig_str_landed': 96,              # Significant Strikes Landed
    'sig_str_attempted': 119,          # Significant Strikes Attempted  
    'sig_str_pct': 80,                 # Significant Strike %
    'total_str_landed': 104,           # Total Strikes Landed
    'total_str_attempted': 128,        # Total Strikes Attempted
    'td_landed': 1,                    # Takedowns Landed
    'td_attempted': 1,                 # Takedowns Attempted
    'td_pct': 100,                     # Takedown %
    'sub_att': 0,                      # Submission Attempts
    'rev': 0,                          # Reversals
    'control_time': 231,               # Control Time (seconds)
    # Significant Strikes Breakdown:
    'head_landed': 70, 'head_attempted': 91,
    'body_landed': 16, 'body_attempted': 18, 
    'leg_landed': 10, 'leg_attempted': 10,
    'distance_landed': 54, 'distance_attempted': 70,
    'clinch_landed': 2, 'clinch_attempted': 3,
    'ground_landed': 40, 'ground_attempted': 46
}
```

## Rate Limiting

The scraper includes built-in delays between requests (1-3 seconds by default) to be respectful to the UFC Stats website. You can adjust this:

```python
scraper = UFCStatsScraper(delay_range=(2, 5))  # 2-5 second delays
```

## Error Handling

The scraper includes comprehensive error handling:
- Network timeouts and connection errors
- Missing HTML elements 
- Malformed data parsing
- Invalid URLs

Failed requests return empty dictionaries and log errors to console.

## Legal Considerations  

This scraper is designed for research and educational purposes. Please:
- Respect robots.txt guidelines
- Use reasonable delays between requests
- Don't overload the target servers
- Follow the website's terms of service
- Consider reaching out to UFC Stats for official API access for commercial use

## Troubleshooting

### Common Issues

1. **Import Error**: Make sure virtual environment is activated and dependencies are installed
2. **Network Timeouts**: Increase delay range or check internet connection  
3. **Empty Results**: Verify URLs are correct and website structure hasn't changed
4. **Rate Limiting**: Increase delay_range if getting blocked

### Debug Mode
Add print statements in the scraper methods to debug parsing issues:
```python
print(f"Scraping URL: {url}")
print(f"Found {len(fight_rows)} fight rows")
```

## Contributing

This scraper was built for UFC Stats specifically. If you encounter parsing errors or missing data fields, please:
1. Check if the website structure has changed
2. Update the corresponding CSS selectors  
3. Test with multiple examples to ensure robustness

## Next Steps

- Add ESPN data integration for supplementary fighter information
- Implement database storage for scraped data
- Build data validation and cleanup utilities
- Create batch processing for multiple fighters/events

ufc_stats_scraper.py \
  --letters abcdefghijklmnopqrstuvwxyz \
  --out out_all \
  --min-delay 1.0 \
  --max-delay 2.0
