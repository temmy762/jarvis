"""Test voice tag detection."""

# Test different tag formats
test_responses = [
    "It's 3:45 PM on Tuesday. [VOICE_RESPONSE_REQUESTED]",
    "It's 3:45 PM on Tuesday. [VOICERESPONSEREQUESTED]",
    "It's 3:45 PM on Tuesday. [VOICE RESPONSE REQUESTED]",
    "Which task would you like me to write? [VOICERESPONSEREQUESTED]",
]

print("=" * 60)
print("VOICE TAG DETECTION TEST")
print("=" * 60)

for i, response in enumerate(test_responses, 1):
    print(f"\nTest {i}:")
    print(f"Response: {response}")
    
    # Check detection
    wants_voice = (
        response.endswith("[VOICE_RESPONSE_REQUESTED]") or
        response.endswith("[VOICERESPONSEREQUESTED]") or
        response.endswith("[VOICE RESPONSE REQUESTED]")
    )
    
    print(f"Detected as voice: {wants_voice}")
    
    if wants_voice:
        # Clean the response
        cleaned = (
            response
            .replace("[VOICE_RESPONSE_REQUESTED]", "")
            .replace("[VOICERESPONSEREQUESTED]", "")
            .replace("[VOICE RESPONSE REQUESTED]", "")
            .strip()
        )
        print(f"Cleaned text: {cleaned}")
        print("✓ Would trigger TTS")
    else:
        print("✗ Would NOT trigger TTS")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
