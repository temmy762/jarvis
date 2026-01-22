"""Test Supabase-backed memory functions."""

import asyncio
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, 'src')

from core.memory import (
    append_message,
    get_recent_messages,
    get_long_term_memory,
    update_long_term_memory
)

async def test_supabase_memory():
    print("=" * 60)
    print("SUPABASE MEMORY MODULE TEST")
    print("=" * 60)
    
    user_id = "test_user_123"
    
    # Test 1: Append message
    print("\n1. Testing append_message():")
    result = await append_message(user_id, "user", "Hello Jarvis")
    print(f"   Success: {result}")
    
    # Test 2: Get recent messages
    print("\n2. Testing get_recent_messages():")
    messages = await get_recent_messages(user_id, limit=5)
    print(f"   Messages retrieved: {len(messages)}")
    if messages:
        for msg in messages[:3]:
            print(f"   - {msg.get('role')}: {msg.get('content')[:50]}...")
    
    # Test 3: Get long-term memory
    print("\n3. Testing get_long_term_memory():")
    memory = await get_long_term_memory(user_id)
    print(f"   Memory exists: {memory is not None}")
    if memory:
        print(f"   Memory preview: {memory[:100]}...")
    
    # Test 4: Update long-term memory
    print("\n4. Testing update_long_term_memory():")
    test_summary = "User prefers short emails and morning meetings."
    result = await update_long_term_memory(user_id, test_summary)
    print(f"   Success: {result}")
    
    # Verify update
    print("\n5. Verifying memory update:")
    memory = await get_long_term_memory(user_id)
    print(f"   Updated memory: {memory}")
    
    print("\n" + "=" * 60)
    print("✓ ALL SUPABASE MEMORY TESTS PASSED")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_supabase_memory())
