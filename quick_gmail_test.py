"""Quick Gmail test - Just verify the improvements work

Run this for a fast check:
    python quick_gmail_test.py
"""

import asyncio
from dotenv import load_dotenv

load_dotenv()

from src.services.gmail import gmail_search, gmail_label


async def quick_test():
    print("\nQuick Gmail Test\n")
    
    # Test 1: gmail_search() returns enriched data
    print("[1] Testing gmail_search()...")
    result = await gmail_search("", limit=3)
    
    if result.get("success"):
        emails = result.get("data", [])
        if emails:
            email = emails[0]
            print(f"   [OK] Found {len(emails)} emails")
            print(f"   First email:")
            print(f"      Subject: {email.get('subject', 'N/A')}")
            print(f"      From: {email.get('from', 'N/A')}")
            
            # Check if it's enriched (not just IDs)
            if email.get('subject') and email.get('from'):
                print("   [PASS] Returns enriched metadata (NOT just IDs)")
            else:
                print("   [FAIL] Still returning IDs only")
        else:
            print("   [WARN] No emails found (inbox empty?)")
    else:
        print(f"   [FAIL] Error: {result.get('error')}")
    
    # Test 2: gmail_label() accepts remove_labels
    print("\n[2] Testing gmail_label() with remove_labels...")
    
    if result.get("success") and result.get("data"):
        msg_id = result["data"][0]["id"]
        
        # Test with remove_labels parameter
        label_result = await gmail_label(
            msg_id,
            labels=["INBOX"],
            remove_labels=[]  # Empty list is fine
        )
        
        if label_result.get("success"):
            print("   [PASS] gmail_label() accepts remove_labels parameter")
        else:
            print(f"   [FAIL] Error: {label_result.get('error')}")
    
    print("\n[DONE] Quick test complete!\n")


if __name__ == "__main__":
    asyncio.run(quick_test())
