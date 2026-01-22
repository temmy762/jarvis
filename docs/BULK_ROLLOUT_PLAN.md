# Bulk Operations Rollout Plan

## Purpose

This document defines the **phased rollout order** for bulk operation adapters.

The order matters. Each wave builds confidence and catches issues before moving to higher-risk operations.

---

## Wave 1: Gmail (Low Risk, High Value) ✅

### Why First?

- **Same API**: All operations use Gmail REST API with consistent error handling
- **Same failure modes**: Network errors, rate limits, invalid IDs
- **Easy to test**: Can test with real emails in a safe environment
- **High value**: Users frequently need to bulk-label or archive emails
- **Reversible**: Most operations can be undone (e.g., remove label, unarchive)

### Supported Actions

1. **`label`**: Apply labels to emails
   - Risk: Low (additive operation, doesn't remove data)
   - Reversibility: High (can remove label later)
   - Use case: "Label all emails from Hostinger as 'Work'"

2. **`archive`**: Archive emails (remove INBOX label)
   - Risk: Low (doesn't delete, just moves out of inbox)
   - Reversibility: High (can move back to inbox)
   - Use case: "Archive all promotional emails from last month"

3. **`move_to_label`**: Apply label and remove INBOX (combined operation)
   - Risk: Low (same as archive + label)
   - Reversibility: High (can reverse both operations)
   - Use case: "Move all receipts to 'Receipts' label"

### Implementation Status

- [x] `GmailBulkAdapter` implemented
- [x] Registered in adapter registry
- [ ] Integration tested with real Gmail data
- [ ] User acceptance testing

### Testing Checklist

- [ ] Test with 5 emails (small batch)
- [ ] Test with 50 emails (medium batch)
- [ ] Test with 150 emails (large batch, multiple batches)
- [ ] Test with invalid label name (error handling)
- [ ] Test with no matching emails (empty result)
- [ ] Test cancellation mid-operation
- [ ] Test continuation after pause
- [ ] Test with API rate limit (if possible)

---

## Wave 2: Calendar (Medium Risk) ⚠️

### Why Second?

- **Different API**: Google Calendar API has different patterns
- **Higher stakes**: Deleting events is more destructive than labeling emails
- **Requires explicit confirmation**: Users must see exactly what will be affected
- **Smaller batch sizes**: Recommended to process fewer items per batch (e.g., 5-10)

### Supported Actions

1. **`delete_events`**: Permanently delete calendar events
   - Risk: Medium (destructive, cannot be undone)
   - Reversibility: None (permanent deletion)
   - Use case: "Delete all 'Daily Standup' events from last month"
   - **Extra rule**: Requires explicit confirmation text showing event count

2. **`reschedule_events`**: Change start/end times for events
   - Risk: Medium (modifies important data)
   - Reversibility: Low (original times are lost)
   - Use case: "Move all meetings on Friday to next Monday"
   - **Extra rule**: Show before/after times in confirmation

### Implementation Requirements

- [ ] `CalendarBulkAdapter` class
- [ ] Explicit confirmation text generator
- [ ] Smaller default batch size (5-10 instead of 20)
- [ ] Enhanced error messages for calendar-specific failures
- [ ] Dry-run mode (show what would be affected without executing)

### Extra Safety Rules

1. **Explicit confirmation text**:
   ```
   This will DELETE 15 calendar events:
   - Daily Standup (Dec 1-15)
   - Team Sync (Dec 3, 10)
   
   This action CANNOT be undone.
   
   Say 'continue' to proceed, or 'cancel' to stop.
   ```

2. **Smaller batch size**:
   - Default: 5 events per batch (instead of 20)
   - Max: 10 events per batch
   - Rationale: Gives user more control, easier to spot mistakes

3. **Dry-run first**:
   - Before starting bulk operation, show preview of affected events
   - User must explicitly confirm after seeing preview

### Testing Checklist

- [ ] Test delete with test calendar events only
- [ ] Test reschedule with non-critical events
- [ ] Verify confirmation text shows all affected events
- [ ] Test cancellation before any deletions
- [ ] Test error handling for recurring events
- [ ] Test with events that have attendees (should warn)

---

## Wave 3: Trello & External APIs (High Risk) ⚠️⚠️

### Why Last?

- **External APIs**: Not Google, different error patterns
- **Idempotency concerns**: Must handle duplicate operations gracefully
- **Retry discipline**: Network failures require careful retry logic
- **Strong error summaries**: Users need detailed feedback on what succeeded/failed

### Supported Actions

1. **`move_cards`**: Move Trello cards between lists
   - Risk: High (affects project management workflows)
   - Reversibility: Medium (can move back, but history is affected)
   - Use case: "Move all cards in 'To Do' to 'In Progress'"

2. **`archive_cards`**: Archive Trello cards
   - Risk: High (removes from active view)
   - Reversibility: Medium (can unarchive, but disrupts workflow)
   - Use case: "Archive all completed cards from last quarter"

3. **`update_crm_records`**: Bulk update CRM entries (future)
   - Risk: Very High (business-critical data)
   - Reversibility: Low (depends on CRM system)
   - Use case: "Update all leads from 'Cold' to 'Warm'"

### Implementation Requirements

- [ ] `TrelloBulkAdapter` class
- [ ] Idempotency checks (detect and skip duplicate operations)
- [ ] Retry logic with exponential backoff
- [ ] Detailed error summaries (per-item success/failure)
- [ ] Webhook/callback support for async operations
- [ ] Rate limit handling specific to Trello API

### Extra Safety Rules

1. **Idempotency awareness**:
   - Check if card is already in target list before moving
   - Skip already-archived cards
   - Return success for no-op operations (don't treat as error)

2. **Retry discipline**:
   - Max 2 retries per item (not per batch)
   - Exponential backoff: 1s, 2s, 4s
   - Only retry on network errors, not on validation errors

3. **Strong error summaries**:
   ```
   Processed 20/50 cards. 3 errors:
   - Card "Fix bug #123": Already archived (skipped)
   - Card "Design mockup": Not found (may have been deleted)
   - Card "Write docs": API timeout (will retry on next batch)
   ```

### Testing Checklist

- [ ] Test with test Trello board only
- [ ] Test idempotency (run same operation twice)
- [ ] Test retry logic with simulated network failures
- [ ] Test rate limit handling
- [ ] Verify error summaries are clear and actionable
- [ ] Test cancellation mid-operation
- [ ] Test with cards that have attachments/comments

---

## Rollout Timeline (Recommended)

### Week 1: Wave 1 (Gmail)
- Day 1-2: Implement `GmailBulkAdapter`
- Day 3-4: Integration testing with real data
- Day 5: User acceptance testing
- Day 6-7: Bug fixes and refinements

### Week 2: Wave 1 Stabilization
- Monitor production usage
- Collect user feedback
- Fix any issues that arise
- Optimize batch sizes based on real usage

### Week 3: Wave 2 (Calendar)
- Day 1-2: Implement `CalendarBulkAdapter`
- Day 3-4: Implement explicit confirmation and dry-run
- Day 5: Integration testing
- Day 6-7: User acceptance testing

### Week 4: Wave 2 Stabilization
- Monitor production usage
- Ensure safety rules are working
- Collect feedback on confirmation flow

### Week 5+: Wave 3 (Trello)
- Implement `TrelloBulkAdapter` with idempotency
- Implement retry logic
- Extensive testing with test boards
- Gradual rollout to users

---

## Success Criteria

### Wave 1 (Gmail)
- [ ] 100+ bulk operations completed without critical errors
- [ ] Average batch processing time < 30 seconds
- [ ] User satisfaction score > 4/5
- [ ] Zero data loss incidents

### Wave 2 (Calendar)
- [ ] 50+ bulk operations completed without critical errors
- [ ] Zero accidental deletions (all deletions were intended)
- [ ] Confirmation flow is clear (user feedback)
- [ ] Dry-run feature is used in 80%+ of delete operations

### Wave 3 (Trello)
- [ ] 25+ bulk operations completed without critical errors
- [ ] Idempotency checks prevent duplicate operations
- [ ] Retry logic successfully recovers from transient failures
- [ ] Error summaries are actionable and clear

---

## Rollback Plan

If critical issues arise in any wave:

1. **Immediate**: Disable the adapter in `registry.py`
   ```python
   # BULK_ADAPTERS["gmail"] = GmailBulkAdapter()  # DISABLED
   ```

2. **Communication**: Notify users that bulk operations for that tool are temporarily unavailable

3. **Investigation**: Analyze logs and error reports

4. **Fix**: Address root cause

5. **Re-enable**: After thorough testing, re-enable the adapter

---

## Monitoring & Alerts

### Metrics to Track

- **Success rate**: % of bulk operations that complete successfully
- **Error rate**: % of individual items that fail
- **Average batch time**: Time to process one batch
- **Cancellation rate**: % of operations cancelled by users
- **Retry rate**: % of items that required retries

### Alerts to Set Up

- Alert if success rate drops below 90%
- Alert if average batch time exceeds 60 seconds
- Alert if error rate exceeds 10%
- Alert if any operation causes API rate limiting

---

## Summary

**Wave 1 (Gmail)**: Low risk, high value. Start here.  
**Wave 2 (Calendar)**: Medium risk. Requires extra safety rules.  
**Wave 3 (Trello)**: High risk. Requires idempotency and retry discipline.

**This order matters.** Each wave builds confidence and catches issues before moving to higher-risk operations.
