# Gmail Improvements - Testing Guide

## 🎯 What Was Improved

### **1. `gmail_search()` - Now Returns Enriched Metadata**

**Before**:
```python
# Returned only IDs (useless for LLM)
{"success": True, "data": [{"id": "abc123", "threadId": "xyz"}]}
```

**After**:
```python
# Returns full metadata (useful for LLM reasoning)
{
    "success": True,
    "data": [{
        "id": "abc123",
        "subject": "Meeting Tomorrow",
        "from": "john@company.com",
        "date": "Tue, 10 Dec 2025 14:30:00",
        "snippet": "Hi, let's meet at 3pm...",
        "labels": ["INBOX", "IMPORTANT"]
    }]
}
```

### **2. `gmail_label()` - Now Supports Removing Labels**

**Before**:
```python
# Could only ADD labels
await gmail_label(message_id, labels=["IMPORTANT"])
```

**After**:
```python
# Can ADD and REMOVE labels in one call
await gmail_label(
    message_id,
    labels=["IMPORTANT"],           # Add these
    remove_labels=["INBOX", "SPAM"] # Remove these
)
```

---

## 🧪 Testing Options

### **Option 1: Quick Test (30 seconds)**

Run the quick test to verify both improvements work:

```bash
python quick_gmail_test.py
```

**Expected Output**:
```
🧪 Quick Gmail Test

1️⃣  Testing gmail_search()...
   ✅ Found 3 emails
   📧 First email:
      Subject: Meeting Tomorrow
      From: john@company.com
   ✅ Returns enriched metadata (NOT just IDs)

2️⃣  Testing gmail_label() with remove_labels...
   ✅ gmail_label() accepts remove_labels parameter

✅ Quick test complete!
```

---

### **Option 2: Comprehensive Test Suite (2 minutes)**

Run the full test suite with detailed checks:

```bash
python test_gmail_improvements.py
```

**Tests Included**:
1. ✅ `gmail_search()` returns enriched metadata
2. ✅ `gmail_label()` backward compatible (old code still works)
3. ✅ `gmail_label()` can remove labels (new feature)
4. ✅ `gmail_search()` works with search queries

**Expected Output**:
```
🧪 GMAIL IMPROVEMENTS TEST SUITE
✅ Gmail credentials found

TEST 1: gmail_search() - Enriched Metadata
📧 Searching for recent emails (limit=5)...
✅ SUCCESS: Found 5 emails
📋 First email metadata:
   ID: 18c5d2a3b4f1e890
   Subject: Q4 Budget Meeting
   From: john@company.com
   Date: Tue, 10 Dec 2025 14:30:00 +0000
   Snippet: Hi team, let's discuss the Q4 budget...
   Labels: ['INBOX', 'IMPORTANT']
✅ PASSED: gmail_search() returns enriched metadata!

[... more tests ...]

📊 TEST SUMMARY
✅ PASSED: gmail_search() enriched metadata
✅ PASSED: gmail_label() backward compatible
✅ PASSED: gmail_label() remove labels
✅ PASSED: gmail_search() with query

🎯 Results: 4/4 tests passed
🎉 ALL TESTS PASSED! Gmail improvements are working correctly!
```

---

### **Option 3: Test via Telegram (Real-World)**

Test through Jarvis in Telegram:

#### **Test gmail_search():**

Send to Jarvis:
```
Search my emails for "meeting"
```

**Expected**: Jarvis shows you email subjects, senders, and snippets (not just IDs)

#### **Test gmail_label():**

Send to Jarvis:
```
Add the Important label to my latest email
```

**Expected**: Jarvis successfully labels the email

---

## 🔧 Prerequisites

Before testing, ensure you have:

1. **Gmail API Credentials** in `.env`:
   ```
   GMAIL_API_TOKEN=your_token_here
   # OR
   GOOGLE_CLIENT_ID=your_client_id
   GOOGLE_CLIENT_SECRET=your_client_secret
   GOOGLE_REFRESH_TOKEN=your_refresh_token
   ```

2. **At least a few emails** in your Gmail inbox

3. **Python dependencies** installed:
   ```bash
   pip install -r requirements.txt
   ```

---

## ✅ Success Criteria

### **gmail_search() is working if:**
- ✅ Returns `subject`, `from`, `date`, `snippet`, `labels` for each email
- ✅ NOT just returning `{"id": "...", "threadId": "..."}`
- ✅ LLM can reason about email content without additional API calls

### **gmail_label() is working if:**
- ✅ Old code without `remove_labels` still works (backward compatible)
- ✅ New code with `remove_labels` parameter works
- ✅ Can add and remove labels in a single call

---

## 🐛 Troubleshooting

### **Error: "MISSING_GMAIL_API_TOKEN"**
- Check your `.env` file has Gmail credentials
- Restart the server after adding credentials

### **Error: "HTTP_ERROR" or "API_ERROR"**
- Check your internet connection
- Verify Gmail API is enabled in Google Cloud Console
- Check if your OAuth token is expired (refresh it)

### **No emails found**
- Your inbox might be empty
- Try a different search query: `is:unread` or `from:someone@example.com`

### **Test fails but no error**
- Check the detailed output for which assertion failed
- Verify you have at least 1 email in your inbox

---

## 📊 What to Look For

### **In Test Output:**

✅ **Good Signs**:
- "Returns enriched metadata (NOT just IDs)"
- "PASSED: gmail_search() returns enriched metadata"
- "PASSED: gmail_label() backward compatible"
- "PASSED: New signature with remove_labels works"

❌ **Bad Signs**:
- "Still returning IDs only"
- "Missing fields: ['subject', 'from']"
- "FAILED: Cannot get test email"

### **In Jarvis Responses:**

✅ **Good**: 
```
I found 3 emails about "meeting":

1. "Q4 Budget Meeting" from john@company.com
   Snippet: Let's discuss the Q4 budget...

2. "Team Meeting Notes" from sarah@company.com
   Snippet: Here are the notes from today...
```

❌ **Bad**:
```
I found 3 emails: abc123, def456, ghi789
```

---

## 🎯 Next Steps After Testing

### **If All Tests Pass** ✅
1. The improvements are working correctly
2. Jarvis can now reason about emails without extra API calls
3. You can use the new `remove_labels` feature in tools

### **If Tests Fail** ❌
1. Check the error messages in test output
2. Verify Gmail credentials in `.env`
3. Check server logs for detailed errors
4. Try the quick test first before the full suite

---

## 📝 Manual Testing Commands

If you want to test manually in Python:

```python
import asyncio
from dotenv import load_dotenv
load_dotenv()

from src.services.gmail import gmail_search, gmail_label

async def manual_test():
    # Test search
    result = await gmail_search("", limit=3)
    print(result)
    
    # Test label
    if result["success"] and result["data"]:
        msg_id = result["data"][0]["id"]
        label_result = await gmail_label(
            msg_id,
            labels=["INBOX"],
            remove_labels=["UNREAD"]
        )
        print(label_result)

asyncio.run(manual_test())
```

---

## 🚀 Summary

**Two simple ways to verify:**

1. **Quick** (30 sec): `python quick_gmail_test.py`
2. **Thorough** (2 min): `python test_gmail_improvements.py`

**Both improvements are backward compatible** - existing code continues to work!

---

**Status**: ✅ Ready to test
**Files**: `quick_gmail_test.py`, `test_gmail_improvements.py`
**Time**: 30 seconds - 2 minutes
