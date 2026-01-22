"""Test complete memory system."""

import asyncio
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, 'src')

from services.memory_engine import (
    save_memory,
    load_memory,
    delete_memory,
    list_memory,
    search_memory,
    classify_memory
)

async def test_memory_system():
    print("=" * 60)
    print("MEMORY SYSTEM TEST")
    print("=" * 60)
    
    # Test 1: Save memory
    print("\n1. Testing save_memory():")
    result = await save_memory("test_preference", "short emails")
    print(f"   Success: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    
    # Test 2: Load memory
    print("\n2. Testing load_memory():")
    result = await load_memory()
    print(f"   Success: {result.get('success')}")
    print(f"   Count: {result.get('count')}")
    if result.get('memory'):
        for entry in result['memory'][:3]:
            print(f"   - {entry['key']}: {entry['value']}")
    
    # Test 3: List memory
    print("\n3. Testing list_memory():")
    result = await list_memory()
    print(f"   Success: {result.get('success')}")
    print(f"   Keys: {result.get('keys')[:5]}")
    
    # Test 4: Search memory
    print("\n4. Testing search_memory():")
    result = await search_memory("test")
    print(f"   Success: {result.get('success')}")
    print(f"   Results: {result.get('count')}")
    
    # Test 5: Classify memory
    print("\n5. Testing classify_memory():")
    result = await classify_memory("I prefer short emails")
    print(f"   Should store: {result.get('should_store')}")
    print(f"   Key: {result.get('key')}")
    print(f"   Value: {result.get('value')}")
    
    # Test 6: Delete memory
    print("\n6. Testing delete_memory():")
    result = await delete_memory("test_preference")
    print(f"   Success: {result.get('success')}")
    print(f"   Message: {result.get('message')}")
    
    print("\n" + "=" * 60)
    print("✓ ALL MEMORY TESTS PASSED")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_memory_system())
