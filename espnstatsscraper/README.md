# ESPN MMA Scraper

A Python scraper to extract fighter profiles, stats, bios, and fight history from ESPN's MMA section.

## Setup

### 1. Create Virtual Environment

```bash
# Create virtual environment
python -m venv espn_env

# Activate virtual environment
# On Windows:
espn_env\Scripts\activate

# On macOS/Linux:
source espn_env/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
python espn_stats_scraper.py
```

This will scrape all events from 2025 down to 1999 and save data to `espn_out/` directory.

### Testing with Limited Events

```bash
# Test with just 2 events
python espn_stats_scraper.py --limit-events 2

# Test specific year range
python espn_stats_scraper.py --start-year 2024 --end-year 2024 --limit-events 5
```

### Command Line Options

- `--start-year` (int): Start year (default: 2025)
- `--end-year` (int): End year (default: 1999)  
- `--out-dir` (str): Output directory (default: "espn_out")
- `--limit-events` (int): Limit number of events to scrape (for testing)
- `--min-delay` (float): Min delay between requests in seconds (default: 1.0)
- `--max-delay` (float): Max delay between requests in seconds (default: 3.0)

### Examples

```bash
# Test run with 2 events from 2024
python espn_stats_scraper.py --start-year 2024 --end-year 2024 --limit-events 2 --out-dir test_output

# Full scrape with custom delays
python espn_stats_scraper.py --min-delay 0.5 --max-delay 2.0

# Scrape specific year range
python espn_stats_scraper.py --start-year 2023 --end-year 2020
```

## Output

The scraper creates two JSONL files:

### `events.jsonl`
Each line contains an event with:
- `id`: ESPN event ID
- `url`: ESPN event URL
- `name`: Event name
- `fighter_urls`: List of fighter profile URLs from this event

### `fighters.jsonl`  
Each line contains a fighter with:
- `id`: ESPN fighter ID
- `url`: Fighter profile URL
- `name_slug`: Fighter name from URL
- `fighting_style`: Fighting style (when available)
- `striking_stats`: Fight-by-fight striking data
- `clinch_stats`: Fight-by-fight clinch data  
- `ground_stats`: Fight-by-fight ground data
- `country_candidates`: Potential country identifications
- `weight_class_candidates`: Potential weight class info
- `physical_stats_candidates`: Height/weight data
- `birthdate_candidates`: Date of birth info
- `record_candidates`: Win-loss records
- `fights`: Fight history with opponents, results, methods

## Data Quality Notes

- ESPN fighter profiles vary significantly in completeness
- Some fighters may have minimal data available
- The scraper uses pattern matching to identify data fields
- Review output data to assess quality and adjust parsing as needed

## Rate Limiting

The scraper includes polite delays between requests:
- Default: 1-3 seconds between requests
- Respects ESPN's servers with reasonable request timing
- Can be adjusted with `--min-delay` and `--max-delay` options

## Troubleshooting

### Common Issues

1. **No data extracted**: ESPN's HTML structure may have changed
2. **Missing fighting styles**: Not all fighter profiles include this field
3. **Incomplete stats**: Some fighters have limited ESPN data

### Debugging

Run with limited events first to inspect output:

```bash
python espn_stats_scraper.py --limit-events 1
```

Then examine `espn_out/events.jsonl` and `espn_out/fighters.jsonl` to see what data was captured.

## Development

To modify data extraction logic, focus on these methods in `espn_stats_scraper.py`:

- `scrape_fighter_profile()`: Basic fighter info and fighting style
- `scrape_fighter_stats()`: Fight-by-fight stats tables
- `scrape_fighter_bio()`: Physical stats, records, bio info
- `scrape_fighter_history()`: Fight history table
- `_parse_stats_table()`: Stats table parsing logic
- `_parse_fight_history_table()`: Fight history parsing logic


```bash
pip install -r requirements.txt
```
pip install playwright && playwright install chromium

python espn_stats_scraper.py