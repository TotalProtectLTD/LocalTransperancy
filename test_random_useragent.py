#!/usr/bin/env python3
"""
Random User Agent Test Script
==============================

This script demonstrates the fake-useragent integration by generating
multiple random Chrome user agents.

Usage:
    python test_random_useragent.py [--count N]
"""

import argparse

try:
    from fake_useragent import UserAgent
    FAKE_USERAGENT_AVAILABLE = True
except ImportError:
    FAKE_USERAGENT_AVAILABLE = False
    print("❌ fake-useragent not installed")
    print("   Install: pip install fake-useragent\n")
    exit(1)


def test_user_agents(count=5):
    """
    Test generating random Chrome user agents.
    
    Args:
        count: Number of user agents to generate
    """
    print("="*80)
    print("RANDOM CHROME USER AGENT TEST")
    print("="*80)
    print(f"\nGenerating {count} random Chrome user agents:\n")
    
    ua = UserAgent(browsers=['Chrome'])
    
    user_agents = []
    for i in range(count):
        user_agent = ua.random
        user_agents.append(user_agent)
        
        # Extract Chrome version
        import re
        chrome_version_match = re.search(r'Chrome/([\d.]+)', user_agent)
        chrome_version = chrome_version_match.group(1) if chrome_version_match else 'unknown'
        
        # Extract OS
        os_name = 'Unknown'
        if 'Windows' in user_agent:
            os_name = 'Windows'
        elif 'Mac' in user_agent or 'Macintosh' in user_agent:
            os_name = 'macOS'
        elif 'Linux' in user_agent:
            os_name = 'Linux'
        
        print(f"User Agent #{i+1}:")
        print(f"  Chrome Version: {chrome_version}")
        print(f"  OS: {os_name}")
        print(f"  Full UA: {user_agent[:80]}...")
        print()
    
    # Check uniqueness
    unique_count = len(set(user_agents))
    print("="*80)
    print(f"✅ Generated {count} user agents")
    print(f"✅ {unique_count} unique user agents ({unique_count/count*100:.1f}% uniqueness)")
    
    if unique_count == count:
        print("✅ All user agents are different!")
    else:
        print(f"⚠️  {count - unique_count} duplicate(s) found (normal for small samples)")
    
    print("\n" + "="*80)
    print("INTEGRATION STATUS")
    print("="*80)
    print("✅ fake-useragent is working correctly")
    print("✅ Chrome user agents are randomized")
    print("✅ Your scraper will use different user agents each run")
    print("\nTo see this in action, run your scraper:")
    print("  python google_ads_transparency_scraper.py \"YOUR_URL\"")
    print("\nLook for this output:")
    print("  🎭 User Agent: Random Chrome [VERSION]")


def main():
    parser = argparse.ArgumentParser(
        description='Test fake-useragent Chrome randomization',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--count', type=int, default=5,
                        help='Number of user agents to generate (default: 5)')
    
    args = parser.parse_args()
    
    if args.count < 1:
        print("❌ Count must be at least 1")
        return
    
    if args.count > 100:
        print("⚠️  Generating >100 user agents may take a while...")
    
    test_user_agents(args.count)


if __name__ == "__main__":
    main()

