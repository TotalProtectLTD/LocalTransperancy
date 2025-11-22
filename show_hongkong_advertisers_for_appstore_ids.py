#!/usr/bin/env python3
"""
Show Hong Kong Advertiser Names for Specific App Store IDs

This script queries the database to show all Hong Kong advertiser names
that have creatives with the specified App Store IDs.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import sys

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'database': 'local_transparency',
    'user': 'transparency_user',
    'password': 'transparency_pass_2025',
    'port': 5432
}

# List of App Store IDs to query
APPSTORE_IDS = [
    '1194582243', '1287969142', '1442452990', '1476380919', '1510944943',
    '1541639300', '1561471269', '1572650132', '1579881271', '1583884012',
    '1586294812', '1600084776', '1604046337', '1616826837', '1631353052',
    '1640720714', '1642271990', '1658676883', '1659844441', '1667252943',
    '6443534300', '6444077039', '6445917429', '6448141961', '6448330325',
    '6449011052', '6450455056', '6450886310', '6452720984', '6468660242',
    '6468928497', '6473826568', '6474166061', '6474616701', '6475751257',
    '6476032667', '6479338003', '6479976058', '6498471359', '6498632440',
    '6498886052', '6502380913', '6502456017', '6502861315', '6504657003',
    '6504668266', '6547844314', '6621235370', '6636528078', '6670714770',
    '6720739614', '6736533328', '6736620089', '6736824783', '6737124937',
    '6737131987', '6737263668', '6737305905', '6737345462', '6737458752',
    '6737480763', '6738036033', '6738095501', '6738099357', '6738339678',
    '6738570954', '6738576967', '6739134477', '6739212141', '6739242033',
    '6739285422', '6739763661', '6739783282', '6740404806', '6740665420',
    '6740840209', '6742173488', '6742389064', '6742598747', '6742649462',
    '6742778673', '6743194785', '6743303836', '6743409054', '6743441242',
    '6743617473', '6743688560', '6743744722', '6743837308', '6744012640',
    '6744400296', '6744552277', '6744826748', '6744916574', '6745007288',
    '6745184985', '6745303112', '6745339199', '6745728288', '6745804227',
    '6745936005', '6746176633', '6746331027', '6746356794', '6746396623',
    '6746400528', '6746409891', '6746558759', '6746647977', '6746700645',
    '6746739467', '6746844428', '6747003427', '6747069278', '6747101898',
    '6747390195', '6747411835', '6747802267', '6747917472', '6747959689',
    '6747960549', '6747978964', '6748110124', '6748288729', '6748430553',
    '6748669439', '6748699535', '6748724320', '6748742273', '6748825183',
    '6748912522', '6748972079', '6749096656', '6749212207', '6749252086',
    '6749436592', '6749560333', '6749562189', '6749749353', '6749853438',
    '6749966512', '6750488029', '6751341330', '6751528054', '6751531813',
    '6751535832', '6751579238', '6751620768', '6751622833', '6751704700',
    '6751836390', '6751941424', '6752275913', '6752328713', '6752330944',
    '6752439949', '6752766291', '6752858675', '6752903768', '6753183090',
    '6753289051', '6753887352', '6753973709'
]

def show_hongkong_advertisers():
    """Show Hong Kong advertiser names for the specified App Store IDs."""
    
    # Create placeholders for the IN clause
    placeholders = ','.join(['%s'] * len(APPSTORE_IDS))
    
    query = f"""
    SELECT DISTINCT
        a.advertiser_id,
        a.advertiser_name,
        COUNT(DISTINCT cf.creative_id) as creative_count,
        COUNT(DISTINCT cf.appstore_id) as appstore_id_count,
        STRING_AGG(DISTINCT cf.appstore_id, ', ' ORDER BY cf.appstore_id) as appstore_ids
    FROM creatives_fresh cf
    INNER JOIN advertisers a ON cf.advertiser_id = a.advertiser_id
    WHERE a.country = 'HK'
      AND cf.appstore_id IN ({placeholders})
      AND cf.appstore_id IS NOT NULL
      AND cf.appstore_id != ''
    GROUP BY a.advertiser_id, a.advertiser_name
    ORDER BY creative_count DESC, a.advertiser_name;
    """
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("=" * 100)
        print("Hong Kong Advertisers with Specified App Store IDs")
        print("=" * 100)
        print(f"Total App Store IDs searched: {len(APPSTORE_IDS)}")
        print()
        
        cursor.execute(query, APPSTORE_IDS)
        results = cursor.fetchall()
        
        if not results:
            print("No Hong Kong advertisers found with the specified App Store IDs.")
            return
        
        print(f"Found {len(results)} Hong Kong advertiser(s):\n")
        print(f"{'#':<4} {'Advertiser Name':<60} {'ID':<25} {'Creatives':<12} {'App Store IDs':<12}")
        print("-" * 115)
        
        total_creatives = 0
        total_appstore_ids = 0
        
        for idx, row in enumerate(results, 1):
            advertiser_name = row['advertiser_name'] or 'N/A'
            advertiser_id = row['advertiser_id'] or 'N/A'
            creative_count = row['creative_count'] or 0
            appstore_count = row['appstore_id_count'] or 0
            
            # Truncate long names
            display_name = advertiser_name
            if len(display_name) > 58:
                display_name = display_name[:55] + "..."
            
            print(f"{idx:<4} {display_name:<60} {advertiser_id:<25} {creative_count:<12} {appstore_count:<12}")
            
            total_creatives += creative_count
            total_appstore_ids += appstore_count
        
        print("-" * 115)
        print(f"{'TOTAL':<4} {'':<60} {'':<25} {total_creatives:<12} {total_appstore_ids:<12}")
        print()
        print(f"Summary:")
        print(f"  - Advertisers: {len(results)}")
        print(f"  - Total Creatives: {total_creatives}")
        print(f"  - Unique App Store IDs: {total_appstore_ids}")
        
        # Show full advertiser names list
        print()
        print("=" * 100)
        print("Full Advertiser Names List:")
        print("=" * 100)
        for idx, row in enumerate(results, 1):
            print(f"{idx}. {row['advertiser_name']}")
        
        cursor.close()
        conn.close()
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    show_hongkong_advertisers()


