"""Test voice response system."""

import asyncio
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, 'src')

from services.tts import synthesize_speech

async def test_voice_system():
    print("=" * 60)
    print("VOICE RESPONSE SYSTEM TEST")
    print("=" * 60)
    
    # Test 1: TTS synthesis
    print("\n1. Testing TTS synthesis:")
    test_text = "Hello, this is Jarvis. The current time is 3:45 PM."
    result = await synthesize_speech(test_text)
    
    print(f"   Success: {result.get('success')}")
    print(f"   File path: {result.get('file_path')}")
    print(f"   Error: {result.get('error')}")
    
    if result.get('success'):
        print(f"   ✓ Voice file created successfully")
        print(f"   ✓ File size: {len(result.get('audio_base64', ''))} bytes (base64)")
    else:
        print(f"   ✗ TTS synthesis failed: {result.get('error')}")
    
    print("\n" + "=" * 60)
    print("VOICE SYSTEM TEST COMPLETE")
    print("=" * 60)
    
    print("\n📝 INSTRUCTIONS FOR TESTING:")
    print("1. Send a VOICE MESSAGE to Jarvis via Telegram")
    print("2. Say something like: 'What time is it?'")
    print("3. Jarvis should:")
    print("   - Transcribe your voice message")
    print("   - Process the request")
    print("   - Respond with a VOICE MESSAGE")
    print("\n✅ If you receive a voice reply, the system is working!")

if __name__ == "__main__":
    asyncio.run(test_voice_system())
