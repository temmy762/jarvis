# Jarvis AI Agent - Complete Test Sentences

This document contains comprehensive test sentences to validate all Jarvis features and subsystems.

---

## 🕐 TIME-AWARENESS TESTS

### **Basic Time Queries**
1. "What time is it now?"
2. "What's today's date?"
3. "What day is it today?"
4. "Tell me the current time"

### **Relative Time Expressions**
5. "Schedule a meeting in 2 hours"
6. "Create a task due tomorrow"
7. "Set a reminder for next Monday"
8. "Book a meeting for tomorrow at 3pm"
9. "Schedule something for next week"
10. "Create an event in 30 minutes"
11. "Set a task due end of day"
12. "Schedule a call for Friday at 10am"
13. "Create a reminder for this afternoon"
14. "Book a meeting for tomorrow morning"

### **Ambiguous Time (Should Ask for Clarification)**
15. "Schedule a meeting sometime"
16. "Create a task due later"
17. "Set a reminder soon"

---

## 🧠 LONG-TERM MEMORY TESTS

### **Saving Preferences**
18. "I prefer short emails"
19. "My assistant is David"
20. "I like morning meetings"
21. "Remember that I prefer formal tone"
22. "Please remember my manager is Sarah"
23. "I always want meeting links included"
24. "From now on, use bullet points in emails"
25. "My team lead is John"
26. "I prefer 30-minute meetings"
27. "Remember that I work from 9am to 5pm"

### **Loading Memory**
28. "What do you remember about me?"
29. "What are my preferences?"
30. "Tell me what you know about my assistant"
31. "What do you remember about emails?"
32. "Show me my stored preferences"

### **Searching Memory**
33. "Search for anything about meetings"
34. "Find what you remember about David"
35. "Look up my email preferences"

### **Deleting Memory**
36. "Forget my email preference"
37. "Delete what you know about my assistant"
38. "Remove my meeting preferences"

### **Temporary Instructions (Should NOT Store)**
39. "Send an email to John right now"
40. "What's the weather today?"
41. "Can you help me with this task?"
42. "Schedule a meeting for today at 3pm"

---

## 📧 GMAIL TESTS

### **Reading Emails**
43. "Show me my latest emails"
44. "Read my unread emails"
45. "Show me emails from David"
46. "Find emails about the project"
47. "Show me important emails"
48. "Read emails from last week"

### **Sending Emails**
49. "Send an email to david@example.com with subject 'Meeting Follow-up' and message 'Thanks for the meeting today'"
50. "Email my assistant about tomorrow's schedule"
51. "Send a short email to Sarah about the project update"
52. "Compose an email to the team about the deadline"

### **Email Management**
53. "Mark all emails from John as read"
54. "Archive emails from last month"
55. "Create a label called 'Important Projects'"
56. "Move emails from Sarah to the 'Team' label"
57. "Forward the latest email from David to sarah@example.com"

### **Email Search**
58. "Search for emails containing 'budget'"
59. "Find emails with attachments from last week"
60. "Show me starred emails"

---

## 📅 CALENDAR TESTS

### **Listing Events**
61. "What's on my calendar today?"
62. "Show me my meetings this week"
63. "What events do I have tomorrow?"
64. "List my upcoming appointments"

### **Creating Events**
65. "Schedule a meeting with David tomorrow at 2pm for 1 hour"
66. "Create a team meeting on Friday at 10am"
67. "Book a 30-minute call with Sarah next Monday at 3pm"
68. "Schedule a project review meeting for next week"

### **Creating Google Meet Events**
69. "Create a Google Meet with David tomorrow at 3pm"
70. "Schedule a video call with the team on Friday at 2pm"
71. "Set up a Meet link for tomorrow's standup at 9am"

### **Checking Availability**
72. "Am I free tomorrow at 3pm?"
73. "Check if I'm available on Friday at 10am"
74. "Do I have any conflicts on Monday afternoon?"
75. "Find my next available slot"

### **Finding Available Slots**
76. "When am I free tomorrow?"
77. "Find me 3 available time slots this week"
78. "Show me when I'm available for a 1-hour meeting"

### **Rescheduling Events**
79. "Reschedule my 3pm meeting to 4pm"
80. "Move tomorrow's team meeting to Friday"
81. "Change my meeting with David to next week"

### **Canceling Events**
82. "Cancel my 2pm meeting today"
83. "Delete tomorrow's standup meeting"
84. "Remove the project review from my calendar"

---

## 📋 TRELLO TESTS

### **Listing Boards and Cards**
85. "Show me my Trello boards"
86. "List all cards in my 'Work' board"
87. "What tasks do I have in the 'To Do' list?"
88. "Show me all my Trello tasks"

### **Creating Cards**
89. "Create a Trello card called 'Review budget' in my Work board"
90. "Add a task 'Call David' to my To Do list"
91. "Create a card 'Finish report' due tomorrow"
92. "Add 'Team meeting prep' to my tasks"

### **Creating Cards with Due Dates**
93. "Create a task 'Submit proposal' due next Friday"
94. "Add a card 'Review code' due end of day"
95. "Create 'Client presentation' due next Monday at 2pm"

### **Updating Cards**
96. "Move 'Review budget' to 'In Progress'"
97. "Mark 'Call David' as complete"
98. "Update the due date of 'Finish report' to next week"
99. "Add a comment to 'Team meeting prep' saying 'Agenda ready'"

### **Searching Cards**
100. "Find all Trello cards about the project"
101. "Search for tasks assigned to me"
102. "Show me overdue tasks"

### **Deleting Cards**
103. "Delete the card 'Old task'"
104. "Remove 'Completed project' from Trello"

---

## 🔄 COMBINED WORKFLOW TESTS

### **Time + Calendar**
105. "What time is my next meeting?"
106. "Schedule a meeting in 2 hours and send me the details"
107. "Am I free tomorrow afternoon? If yes, schedule a team sync"

### **Time + Trello**
108. "Create a task due in 3 days"
109. "Show me tasks due this week"
110. "Add a card due tomorrow morning"

### **Memory + Gmail**
111. "Send an email to my assistant" (should use stored assistant name)
112. "Email David using my preferred style" (should use stored email preference)
113. "Compose a message to my manager" (should use stored manager name)

### **Memory + Calendar**
114. "Schedule a meeting with my assistant" (should use stored name)
115. "Book a call with my manager tomorrow" (should use stored name)
116. "Create a meeting at my preferred time" (should use stored preference)

### **Memory + Trello**
117. "Create a task for my assistant"
118. "Add a card about the project my manager mentioned"

### **Time + Memory + Calendar**
119. "Schedule a meeting with my assistant in 2 hours"
120. "Book a call with my manager tomorrow at my preferred time"

---

## 🎯 INTENT ROUTING TESTS

### **Gmail Intent**
121. "Check my inbox"
122. "Reply to the latest email"
123. "Draft an email about the meeting"
124. "Organize my emails by sender"

### **Calendar Intent**
125. "What's my schedule like?"
126. "Block time for focused work tomorrow"
127. "Find time for a meeting with David"
128. "Clear my calendar for Friday afternoon"

### **Trello Intent**
129. "What tasks are pending?"
130. "Organize my Trello board"
131. "Prioritize my tasks"
132. "Show me what's due soon"

---

## 🧪 EDGE CASES & ERROR HANDLING

### **Invalid Inputs**
133. "Schedule a meeting" (missing time)
134. "Send an email" (missing recipient)
135. "Create a task" (missing details)
136. "Delete" (missing what to delete)

### **Conflicting Times**
137. "Schedule a meeting tomorrow at 2pm" (when already busy)
138. "Book two meetings at the same time"

### **Missing Information**
139. "Email my assistant" (when assistant name not stored)
140. "Schedule with my manager" (when manager not stored)

### **Ambiguous Requests**
141. "Do that thing I mentioned"
142. "Send it to them"
143. "Schedule it for later"

---

## 🗣️ CONVERSATIONAL TESTS

### **Natural Language**
144. "Hey Jarvis, what's on my plate today?"
145. "Can you help me organize my day?"
146. "I need to catch up on emails"
147. "What should I focus on right now?"

### **Follow-up Questions**
148. "What time is it?" → "Schedule a meeting in 1 hour"
149. "Show my calendar" → "Am I free at 3pm?"
150. "List my tasks" → "Mark the first one as done"

### **Multi-step Requests**
151. "Check if I'm free tomorrow at 2pm, and if yes, schedule a meeting with David"
152. "Find my next available slot and create a Google Meet"
153. "Show me emails from Sarah and create a task to follow up"

---

## 🎨 OUTPUT FORMATTING TESTS

### **Plain Text Verification**
154. "Send me a summary of my day" (should be plain text, no Markdown)
155. "List my top 5 tasks" (should use plain text, no bullets/asterisks)
156. "Describe my schedule" (should be clean, no formatting symbols)

### **Email Signature**
157. "Send an email to david@example.com" (should include "Warm regards, Saara")
158. "Draft a message to the team" (should have proper signature)

### **Voice Mode**
159. (Send voice message: "What time is it?")
160. (Send voice message: "Schedule a meeting tomorrow")

---

## 🔍 MEMORY CLASSIFICATION TESTS

### **Should Store**
161. "I prefer concise responses"
162. "My work hours are 9 to 5"
163. "I always want calendar invites sent to my team"
164. "Remember that I'm in the Berlin timezone"
165. "My direct reports are Alice and Bob"

### **Should NOT Store**
166. "I'm feeling tired today"
167. "Can you help me right now?"
168. "This is urgent"
169. "I think we should meet soon"
170. "Maybe we can discuss this later"

---

## 📊 COMPREHENSIVE WORKFLOW TEST

### **Complete User Journey**
171. "What time is it?" 
172. "I prefer short emails" (store preference)
173. "My assistant is David" (store detail)
174. "Show me my calendar for today"
175. "Am I free at 3pm tomorrow?"
176. "Schedule a meeting with my assistant tomorrow at 3pm" (use stored name)
177. "Send an email to my assistant about tomorrow's meeting" (use stored name and preference)
178. "Create a Trello card to prepare for the meeting, due tomorrow at 2pm"
179. "What do you remember about me?" (should show stored preferences)
180. "Show me all my tasks due this week"

---

## 🚀 STRESS TESTS

### **Rapid Fire**
181. "What time is it?"
182. "Schedule a meeting in 1 hour"
183. "Send an email to david@example.com"
184. "Create a task due tomorrow"
185. "Show my calendar"
186. "What's my next meeting?"
187. "Am I free at 4pm?"
188. "List my Trello boards"
189. "Search emails from Sarah"
190. "What do you remember about me?"

### **Complex Queries**
191. "Check if I'm free tomorrow between 2pm and 4pm, and if yes, schedule a 1-hour Google Meet with David and Sarah, then send them both an email with the meeting link, and create a Trello card to prepare the agenda due 1 hour before the meeting"

192. "Find all emails from my assistant about the project, create a summary, schedule a follow-up meeting for next week, and add a task to review the materials"

193. "Show me my schedule for this week, identify any conflicts, suggest alternative times, and update my calendar accordingly"

---

## ✅ EXPECTED BEHAVIORS

### **Time Awareness**
- ✅ Always calls `get_current_time()` for time queries
- ✅ Never guesses or assumes dates/times
- ✅ Parses natural language accurately
- ✅ Rejects ambiguous time expressions politely

### **Memory**
- ✅ Stores preferences, habits, personal details
- ✅ Does NOT store temporary tasks or emotional statements
- ✅ Loads memory automatically in conversations
- ✅ References stored information naturally

### **Output**
- ✅ Always plain text (no Markdown, no emojis)
- ✅ Includes "Warm regards, Saara" in emails
- ✅ Clean, professional, concise responses
- ✅ No system commentary or meta-information

### **Error Handling**
- ✅ Polite clarification requests for missing info
- ✅ Clear error messages for failures
- ✅ Suggestions for conflicts or issues
- ✅ Never crashes or returns technical errors to user

---

## 📝 TESTING CHECKLIST

Use this checklist to track your testing progress:

- [ ] Time-Awareness Tests (1-17)
- [ ] Long-Term Memory Tests (18-42)
- [ ] Gmail Tests (43-60)
- [ ] Calendar Tests (61-84)
- [ ] Trello Tests (85-104)
- [ ] Combined Workflow Tests (105-120)
- [ ] Intent Routing Tests (121-132)
- [ ] Edge Cases & Error Handling (133-143)
- [ ] Conversational Tests (144-153)
- [ ] Output Formatting Tests (154-160)
- [ ] Memory Classification Tests (161-170)
- [ ] Comprehensive Workflow Test (171-180)
- [ ] Stress Tests (181-193)

---

## 🎯 SUCCESS CRITERIA

**Jarvis passes if**:
- ✅ All time queries return accurate real-time data
- ✅ Memory is stored and retrieved correctly
- ✅ All Gmail/Calendar/Trello operations work
- ✅ Output is always clean plain text
- ✅ Errors are handled gracefully
- ✅ User experience is smooth and natural

---

## 🚦 PRIORITY TESTING SEQUENCE

### **Phase 1: Core Functions (Quick Validation - 15 min)**
1. Test #1: "What time is it now?"
2. Test #18: "I prefer short emails"
3. Test #28: "What do you remember about me?"
4. Test #43: "Show me my latest emails"
5. Test #61: "What's on my calendar today?"
6. Test #85: "Show me my Trello boards"

### **Phase 2: Integration Tests (30 min)**
7. Test #105-120: Combined workflow tests
8. Test #171-180: Comprehensive user journey

### **Phase 3: Full Validation (2-3 hours)**
9. All 193 tests in sequence

---

**Total Test Sentences: 193**

**Estimated Testing Time: 2-3 hours for complete validation**

**Quick Validation: Tests 1, 18, 28, 43, 61, 85 (15 minutes)**
