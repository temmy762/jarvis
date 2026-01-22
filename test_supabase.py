"""Test Supabase connection."""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

print("=" * 60)
print("SUPABASE CONNECTION TEST")
print("=" * 60)

# Check environment variables
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

print(f"\n1. Environment Variables:")
print(f"   URL exists: {url is not None}")
print(f"   URL value: {url}")
print(f"   Key exists: {key is not None}")
print(f"   Key format: {key[:30] if key else None}...")
print(f"   Key length: {len(key) if key else 0}")

# Test direct connection
print(f"\n2. Direct Connection Test:")
try:
    from supabase import create_client
    client = create_client(url, key)
    print(f"   ✓ Client created successfully")
    
    # Test query
    result = client.table('conversation_messages').select('*').limit(1).execute()
    print(f"   ✓ Query executed successfully")
    print(f"   ✓ Data returned: {result.data is not None}")
except Exception as exc:
    print(f"   ✗ Error: {exc}")

# Test memory module
print(f"\n3. Memory Module Test:")
sys.path.insert(0, 'src')
try:
    from core.memory import _get_supabase_client
    client = _get_supabase_client()
    print(f"   Client initialized: {client is not None}")
    print(f"   Client type: {type(client).__name__}")
    
    if client:
        print(f"   ✓ Memory module configured correctly")
    else:
        print(f"   ✗ Memory module failed to initialize")
except Exception as exc:
    print(f"   ✗ Error: {exc}")

print("\n" + "=" * 60)
