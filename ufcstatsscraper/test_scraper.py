#!/usr/bin/env python3
"""
Test script for UFC Stats scraper
Tests all three main functions: fighter, event, and fight scraping
"""

from ufc_stats_scraper import UFCStatsScraper
import json
import time

def test_fighter_scraper():
    """Test fighter data extraction"""
    print("=" * 60)
    print("TESTING FIGHTER SCRAPER")
    print("=" * 60)
    
    scraper = UFCStatsScraper(delay_range=(1, 2))
    fighter_url = "http://ufcstats.com/fighter-details/07225ba28ae309b6"  # Jon Jones
    
    print(f"Scraping: {fighter_url}")
    fighter_data = scraper.scrape_fighter(fighter_url)
    
    if not fighter_data:
        print("❌ FAILED: No data returned")
        return False
    
    # Test key fields
    required_fields = ['id', 'name', 'nickname', 'height', 'weight', 'wins', 'losses']
    missing_fields = [field for field in required_fields if field not in fighter_data]
    
    if missing_fields:
        print(f"❌ FAILED: Missing fields: {missing_fields}")
        return False
    
    print("✅ SUCCESS: Fighter data extracted")
    print(f"   Name: {fighter_data.get('name', 'N/A')}")
    print(f"   Nickname: {fighter_data.get('nickname', 'N/A')}")
    print(f"   Record: {fighter_data.get('wins', 0)}-{fighter_data.get('losses', 0)}-{fighter_data.get('draws', 0)} ({fighter_data.get('no_contests', 0)} NC)")
    print(f"   Height: {fighter_data.get('height', 'N/A')}")
    print(f"   Weight: {fighter_data.get('weight', 'N/A')}")
    print(f"   Reach: {fighter_data.get('reach', 'N/A')}")
    print(f"   DOB: {fighter_data.get('dob', 'N/A')}")
    print(f"   SLpM: {fighter_data.get('slpm', 'N/A')}")
    print(f"   Str. Acc.: {fighter_data.get('str_acc', 'N/A')}%")
    print(f"   Fight History: {len(fighter_data.get('fights', []))} fights")
    
    if fighter_data.get('fights'):
        recent_fight = fighter_data['fights'][0]  # Most recent fight
        print(f"   Most Recent: vs {recent_fight.get('opponent_name', 'Unknown')} ({recent_fight.get('result', 'N/A')})")
    
    return True

def test_event_scraper():
    """Test event data extraction"""
    print("\n" + "=" * 60)
    print("TESTING EVENT SCRAPER")
    print("=" * 60)
    
    scraper = UFCStatsScraper(delay_range=(1, 2))
    event_url = "http://ufcstats.com/event-details/daff32bc96d1eabf"  # UFC 309
    
    print(f"Scraping: {event_url}")
    event_data = scraper.scrape_event(event_url)
    
    if not event_data:
        print("❌ FAILED: No data returned")
        return False
    
    required_fields = ['id', 'name', 'date', 'location']
    missing_fields = [field for field in required_fields if field not in event_data]
    
    if missing_fields:
        print(f"❌ FAILED: Missing fields: {missing_fields}")
        return False
    
    print("✅ SUCCESS: Event data extracted")
    print(f"   Name: {event_data.get('name', 'N/A')}")
    print(f"   Date: {event_data.get('date', 'N/A')}")
    print(f"   Location: {event_data.get('location', 'N/A')}")
    print(f"   Fights: {len(event_data.get('fights', []))} fights")
    
    return True

def test_fight_scraper():
    """Test fight data extraction"""
    print("\n" + "=" * 60)
    print("TESTING FIGHT SCRAPER")
    print("=" * 60)
    
    scraper = UFCStatsScraper(delay_range=(1, 2))
    fight_url = "http://ufcstats.com/fight-details/4f4189009a190e35"  # Jones vs Miocic
    
    print(f"Scraping: {fight_url}")
    fight_data = scraper.scrape_fight(fight_url)
    
    if not fight_data:
        print("❌ FAILED: No data returned")
        return False
    
    required_fields = ['id', 'fighters', 'is_title_fight', 'weight_class', 'method', 'round']
    missing_fields = [field for field in required_fields if field not in fight_data]
    
    if missing_fields:
        print(f"❌ FAILED: Missing fields: {missing_fields}")
        return False
    
    print("✅ SUCCESS: Fight data extracted")
    print(f"   Event: {fight_data.get('event_name', 'N/A')}")
    print(f"   Title Fight: {fight_data.get('is_title_fight', False)}")
    print(f"   Weight Class: {fight_data.get('weight_class', 'N/A')}")
    print(f"   Method: {fight_data.get('method', 'N/A')}")
    print(f"   Round: {fight_data.get('round', 'N/A')}")
    print(f"   Time: {fight_data.get('time', 'N/A')}")
    print(f"   Referee: {fight_data.get('referee', 'N/A')}")
    print(f"   Details: {fight_data.get('details', 'N/A')}")
    
    # Test fighters data
    fighters = fight_data.get('fighters', [])
    print(f"   Fighters: {len(fighters)}")
    for i, fighter in enumerate(fighters):
        print(f"     Fighter {i+1}: {fighter.get('name', 'Unknown')} ({fighter.get('result', 'N/A')})")
    
    # Test totals data
    totals = fight_data.get('totals', [])
    print(f"   Fight Totals: {len(totals)} fighters")
    for i, stats in enumerate(totals):
        print(f"     Fighter {i+1}: {stats.get('name', 'Unknown')}")
        print(f"       Sig Strikes: {stats.get('sig_str_landed', 0)}/{stats.get('sig_str_attempted', 0)} ({stats.get('sig_str_pct', 0)}%)")
        print(f"       Takedowns: {stats.get('td_landed', 0)}/{stats.get('td_attempted', 0)}")
        print(f"       Control: {stats.get('control_time', 0)} seconds")
    
    # Test rounds data  
    rounds = fight_data.get('rounds', [])
    print(f"   Round Data: {len(rounds)} rounds")
    for round_data in rounds:
        print(f"     Round {round_data.get('round_number', '?')}: {len(round_data.get('fighters', []))} fighters")
    
    return True

def save_sample_data(fighter_data, event_data, fight_data):
    """Save sample data to JSON files for inspection"""
    print("\n" + "=" * 60)
    print("SAVING SAMPLE DATA")
    print("=" * 60)
    
    try:
        with open('sample_fighter_data.json', 'w', encoding='utf-8') as f:
            json.dump(fighter_data, f, indent=2, ensure_ascii=False)
        print("✅ Saved: sample_fighter_data.json")
        
        with open('sample_event_data.json', 'w', encoding='utf-8') as f:
            json.dump(event_data, f, indent=2, ensure_ascii=False)
        print("✅ Saved: sample_event_data.json")
        
        with open('sample_fight_data.json', 'w', encoding='utf-8') as f:
            json.dump(fight_data, f, indent=2, ensure_ascii=False)
        print("✅ Saved: sample_fight_data.json")
        
        print("\nYou can inspect these JSON files to see the complete data structure")
        
    except Exception as e:
        print(f"❌ Error saving files: {e}")

def main():
    """Run all tests"""
    print("UFC STATS SCRAPER TEST SUITE")
    print("Testing with Jon Jones vs Stipe Miocic (UFC 309) data")
    
    start_time = time.time()
    
    # Run tests
    fighter_success = test_fighter_scraper()
    event_success = test_event_scraper() 
    fight_success = test_fight_scraper()
    
    # Get data for saving
    if fighter_success and event_success and fight_success:
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED - Getting sample data")
        print("=" * 60)
        
        scraper = UFCStatsScraper(delay_range=(1, 2))
        fighter_data = scraper.scrape_fighter("http://ufcstats.com/fighter-details/07225ba28ae309b6")
        event_data = scraper.scrape_event("http://ufcstats.com/event-details/daff32bc96d1eabf")
        fight_data = scraper.scrape_fight("http://ufcstats.com/fight-details/4f4189009a190e35")
        
        save_sample_data(fighter_data, event_data, fight_data)
    
    # Summary
    total_time = time.time() - start_time
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Fighter Scraper: {'✅ PASS' if fighter_success else '❌ FAIL'}")
    print(f"Event Scraper:   {'✅ PASS' if event_success else '❌ FAIL'}")
    print(f"Fight Scraper:   {'✅ PASS' if fight_success else '❌ FAIL'}")
    print(f"Total Time: {total_time:.1f} seconds")
    
    if fighter_success and event_success and fight_success:
        print("\n🎉 ALL TESTS PASSED! The scraper is working correctly.")
        print("\nNext steps:")
        print("1. Review the saved JSON files to verify data completeness")
        print("2. Test with additional fighters/fights if needed")
        print("3. Ready to integrate ESPN data scraping")
    else:
        print("\n⚠️  Some tests failed. Check the error messages above.")

if __name__ == "__main__":
    main()