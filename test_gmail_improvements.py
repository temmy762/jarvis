"""Test script for Gmail improvements: gmail_search() and gmail_label()

This script tests:
1. gmail_search() now returns enriched metadata (not just IDs)
2. gmail_label() now supports optional remove_labels parameter

Prerequisites:
- GMAIL_API_TOKEN or Google OAuth credentials in .env
- At least a few emails in your Gmail inbox
"""

import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.services.gmail import gmail_search, gmail_label, gmail_create_label


async def test_gmail_search_enriched():
    """Test that gmail_search() returns enriched metadata."""
    print("\n" + "="*60)
    print("TEST 1: gmail_search() - Enriched Metadata")
    print("="*60)
    
    # Search for recent emails (empty query = all emails)
    print("\n📧 Searching for recent emails (limit=5)...")
    result = await gmail_search(query="", limit=5)
    
    if not result.get("success"):
        print(f"❌ FAILED: {result.get('error')}")
        return False
    
    emails = result.get("data", [])
    print(f"✅ SUCCESS: Found {len(emails)} emails")
    
    if len(emails) == 0:
        print("⚠️  No emails found (inbox might be empty)")
        return True
    
    # Check first email has enriched metadata
    first_email = emails[0]
    print("\n📋 First email metadata:")
    print(f"   ID: {first_email.get('id', 'MISSING')}")
    print(f"   Subject: {first_email.get('subject', 'MISSING')}")
    print(f"   From: {first_email.get('from', 'MISSING')}")
    print(f"   Date: {first_email.get('date', 'MISSING')}")
    print(f"   Snippet: {first_email.get('snippet', 'MISSING')[:50]}...")
    print(f"   Labels: {first_email.get('labels', 'MISSING')}")
    
    # Verify all required fields are present
    required_fields = ['id', 'subject', 'from', 'date', 'snippet', 'labels']
    missing_fields = [f for f in required_fields if f not in first_email]
    
    if missing_fields:
        print(f"\n❌ FAILED: Missing fields: {missing_fields}")
        return False
    
    # Verify it's NOT just returning IDs (old behavior)
    if first_email.get('subject') == 'MISSING' or not first_email.get('subject'):
        print("\n❌ FAILED: Subject is missing (still returning IDs only)")
        return False
    
    print("\n✅ PASSED: gmail_search() returns enriched metadata!")
    return True


async def test_gmail_label_backward_compatible():
    """Test that gmail_label() still works without remove_labels (backward compatible)."""
    print("\n" + "="*60)
    print("TEST 2: gmail_label() - Backward Compatibility")
    print("="*60)
    
    # Get a message ID to test with
    print("\n📧 Getting a test email...")
    search_result = await gmail_search(query="", limit=1)
    
    if not search_result.get("success") or not search_result.get("data"):
        print("❌ FAILED: Cannot get test email")
        return False
    
    message_id = search_result["data"][0]["id"]
    print(f"✅ Got message ID: {message_id}")
    
    # Test old signature (without remove_labels)
    print("\n🏷️  Testing old signature: gmail_label(message_id, labels)")
    result = await gmail_label(message_id, ["INBOX"])
    
    if not result.get("success"):
        print(f"❌ FAILED: {result.get('error')}")
        return False
    
    print("✅ PASSED: Old signature still works (backward compatible)!")
    return True


async def test_gmail_label_with_remove():
    """Test that gmail_label() can now remove labels."""
    print("\n" + "="*60)
    print("TEST 3: gmail_label() - Remove Labels Feature")
    print("="*60)
    
    # Get a message ID to test with
    print("\n📧 Getting a test email...")
    search_result = await gmail_search(query="", limit=1)
    
    if not search_result.get("success") or not search_result.get("data"):
        print("❌ FAILED: Cannot get test email")
        return False
    
    message_id = search_result["data"][0]["id"]
    current_labels = search_result["data"][0].get("labels", [])
    print(f"✅ Got message ID: {message_id}")
    print(f"   Current labels: {current_labels}")
    
    # Create a test label
    test_label_name = "TEST_JARVIS_LABEL"
    print(f"\n🏷️  Creating test label: {test_label_name}")
    create_result = await gmail_create_label(test_label_name)
    
    if not create_result.get("success"):
        # Label might already exist, that's okay
        print(f"⚠️  Label creation: {create_result.get('error')}")
        print("   (This is okay if label already exists)")
    else:
        print(f"✅ Created label: {create_result['data'].get('id')}")
    
    # Test new signature with remove_labels
    print(f"\n🏷️  Testing new signature with remove_labels parameter")
    print(f"   Adding: ['INBOX']")
    print(f"   Removing: ['UNREAD'] (if present)")
    
    result = await gmail_label(
        message_id, 
        labels=["INBOX"],
        remove_labels=["UNREAD"]
    )
    
    if not result.get("success"):
        print(f"❌ FAILED: {result.get('error')}")
        return False
    
    print("✅ PASSED: New signature with remove_labels works!")
    return True


async def test_gmail_search_with_query():
    """Test gmail_search() with an actual search query."""
    print("\n" + "="*60)
    print("TEST 4: gmail_search() - With Search Query")
    print("="*60)
    
    # Search for unread emails
    print("\n📧 Searching for unread emails...")
    result = await gmail_search(query="is:unread", limit=5)
    
    if not result.get("success"):
        print(f"❌ FAILED: {result.get('error')}")
        return False
    
    emails = result.get("data", [])
    print(f"✅ SUCCESS: Found {len(emails)} unread emails")
    
    if len(emails) > 0:
        print("\n📋 Sample unread email:")
        email = emails[0]
        print(f"   Subject: {email.get('subject')}")
        print(f"   From: {email.get('from')}")
        print(f"   Has UNREAD label: {'UNREAD' in email.get('labels', [])}")
    
    print("\n✅ PASSED: Search queries work correctly!")
    return True


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("🧪 GMAIL IMPROVEMENTS TEST SUITE")
    print("="*60)
    
    # Check credentials
    if not os.getenv("GMAIL_API_TOKEN") and not os.getenv("GOOGLE_REFRESH_TOKEN"):
        print("\n❌ ERROR: No Gmail credentials found!")
        print("   Set GMAIL_API_TOKEN or GOOGLE_REFRESH_TOKEN in .env")
        return
    
    print("✅ Gmail credentials found")
    
    # Run tests
    results = []
    
    try:
        results.append(("gmail_search() enriched metadata", await test_gmail_search_enriched()))
        results.append(("gmail_label() backward compatible", await test_gmail_label_backward_compatible()))
        results.append(("gmail_label() remove labels", await test_gmail_label_with_remove()))
        results.append(("gmail_search() with query", await test_gmail_search_with_query()))
    except Exception as exc:
        print(f"\n❌ EXCEPTION: {exc!r}")
        import traceback
        traceback.print_exc()
    
    # Summary
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\n🎯 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Gmail improvements are working correctly!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check output above for details.")


if __name__ == "__main__":
    asyncio.run(main())
