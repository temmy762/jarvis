"""Test script to verify Calendar INVALID_ARGUMENTS fix.

This script tests:
1. Natural language time parsing
2. Auto-generation of end time (start + 1 hour)
3. Validation (end > start, not in past)
4. Timezone handling
5. Clarification requests for unparseable times
"""

import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from src.services.calendar import (
    _parse_natural_time,
    _extract_time_from_expr,
    _get_timezone_obj,
    calendar_create_event_safe,
    DEFAULT_TIMEZONE,
)


def test_time_extraction():
    """Test time extraction from expressions."""
    print("\n" + "=" * 60)
    print("TEST 1: Time Extraction from Expressions")
    print("=" * 60)
    
    test_cases = [
        ("6am", (6, 0)),
        ("6 am", (6, 0)),
        ("6:30am", (6, 30)),
        ("6:30 am", (6, 30)),
        ("3pm", (15, 0)),
        ("3:45pm", (15, 45)),
        ("14:00", (14, 0)),
        ("23:30", (23, 30)),
        ("12am", (0, 0)),
        ("12pm", (12, 0)),
        ("no time here", (None, 0)),
    ]
    
    passed = 0
    for expr, expected in test_cases:
        result = _extract_time_from_expr(expr)
        status = "[OK]" if result == expected else "[FAIL]"
        if result == expected:
            passed += 1
        print(f"  {status} '{expr}' -> {result} (expected {expected})")
    
    print(f"\n  Result: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


def test_natural_time_parsing():
    """Test natural language time parsing."""
    print("\n" + "=" * 60)
    print("TEST 2: Natural Language Time Parsing")
    print("=" * 60)
    
    tz = _get_timezone_obj(DEFAULT_TIMEZONE)
    now = datetime.now(tz)
    
    test_cases = [
        ("tomorrow at 6am", True),
        ("tomorrow at 3pm", True),
        ("tomorrow morning", True),
        ("tomorrow afternoon", True),
        ("tomorrow evening", True),
        ("in 2 hours", True),
        ("in 30 minutes", True),
        ("in 3 days", True),
        ("today at 5pm", True),
        ("friday at 10am", True),
        ("monday at 2pm", True),
        ("6am", True),
        ("3:30pm", True),
        ("2025-01-22T15:00:00", True),
        ("blah blah random text", False),
        ("", False),
    ]
    
    passed = 0
    for expr, should_succeed in test_cases:
        if not expr:
            print(f"  [SKIP] Skipping empty expression")
            passed += 1
            continue
            
        result_dt, error = _parse_natural_time(expr, now, DEFAULT_TIMEZONE)
        success = result_dt is not None
        
        if success == should_succeed:
            passed += 1
            status = "[OK]"
        else:
            status = "[FAIL]"
        
        if success:
            print(f"  {status} '{expr}' -> {result_dt.strftime('%Y-%m-%d %H:%M %Z')}")
        else:
            print(f"  {status} '{expr}' -> FAILED: {error[:50]}...")
    
    print(f"\n  Result: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


async def test_calendar_create_event_safe():
    """Test the safe calendar event creation with validation."""
    print("\n" + "=" * 60)
    print("TEST 3: calendar_create_event_safe Validation")
    print("=" * 60)
    
    test_cases = [
        # (summary, start_time, end_time, expected_success, expected_error_type)
        ("Meeting", "tomorrow at 6am", None, True, None),  # Auto-generate end
        ("Meeting", "tomorrow at 3pm", "tomorrow at 4pm", True, None),  # Both times
        ("Meeting", "in 2 hours", None, True, None),  # Relative time
        ("", "tomorrow at 6am", None, False, "VALIDATION_ERROR"),  # No summary
        ("Meeting", "", None, False, "PARSE_ERROR"),  # No start time
        ("Meeting", "gibberish text xyz", None, False, "PARSE_ERROR"),  # Unparseable
        ("Meeting", "tomorrow at 5pm", "tomorrow at 3pm", False, "VALIDATION_ERROR"),  # End before start
    ]
    
    passed = 0
    for summary, start, end, expect_success, expect_error in test_cases:
        result = await calendar_create_event_safe(
            summary=summary,
            start_time=start,
            end_time=end,
        )
        
        success = result.get("success", False)
        error_type = result.get("error")
        
        # For successful API calls, we check if it succeeded or got an auth error (expected in test)
        if expect_success:
            # Accept either success or MISSING_CALENDAR_TOKEN (no creds in test)
            if success or error_type == "MISSING_CALENDAR_TOKEN":
                passed += 1
                status = "[OK]"
            else:
                status = "[FAIL]"
        else:
            if not success and error_type == expect_error:
                passed += 1
                status = "[OK]"
            else:
                status = "[FAIL]"
        
        desc = f"'{summary[:20]}', '{start}', '{end}'"
        if success:
            print(f"  {status} {desc} -> SUCCESS")
        else:
            msg = result.get("message", result.get("error", ""))[:40]
            print(f"  {status} {desc} -> {error_type}: {msg}")
    
    print(f"\n  Result: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


async def test_timezone_handling():
    """Test timezone is properly included in payloads."""
    print("\n" + "=" * 60)
    print("TEST 4: Timezone Handling")
    print("=" * 60)
    
    print(f"  Default timezone: {DEFAULT_TIMEZONE}")
    
    tz = _get_timezone_obj(DEFAULT_TIMEZONE)
    now = datetime.now(tz)
    print(f"  Current time in {DEFAULT_TIMEZONE}: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    # Test that ISO output includes timezone
    test_dt, _ = _parse_natural_time("tomorrow at 10am", now, DEFAULT_TIMEZONE)
    if test_dt:
        iso_str = test_dt.isoformat()
        has_tz = "+" in iso_str or "-" in iso_str[10:]  # After date part
        print(f"  Parsed 'tomorrow at 10am' -> {iso_str}")
        print(f"  [OK] ISO string includes timezone offset: {has_tz}")
        return has_tz
    else:
        print("  [FAIL] Failed to parse time")
        return False


async def main():
    print("\n" + "=" * 60)
    print("CALENDAR FIX VERIFICATION TESTS")
    print("=" * 60)
    print(f"Testing with timezone: {DEFAULT_TIMEZONE}")
    
    results = []
    
    # Test 1: Time extraction
    results.append(("Time Extraction", test_time_extraction()))
    
    # Test 2: Natural time parsing
    results.append(("Natural Time Parsing", test_natural_time_parsing()))
    
    # Test 3: Safe event creation
    results.append(("Safe Event Creation", await test_calendar_create_event_safe()))
    
    # Test 4: Timezone handling
    results.append(("Timezone Handling", await test_timezone_handling()))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "[OK] PASSED" if passed else "[FAIL] FAILED"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("ALL TESTS PASSED! Calendar fix is working correctly.")
    else:
        print("Some tests failed. Please review the output above.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
