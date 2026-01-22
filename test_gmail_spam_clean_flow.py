import asyncio
import unittest
from unittest.mock import AsyncMock, patch


class TestGmailSpamCleanFlow(unittest.TestCase):
    def test_spam_clean_confirm_then_move_to_trash(self):
        async def run():
            from src.core.gmail_spam_clean_flow import handle_gmail_spam_clean_turn

            # Dry-run: first page (2 ids) with next token; execute will fetch second page
            page1 = {
                "success": True,
                "data": {"message_ids": ["s1", "s2"], "next_page_token": "t1", "result_size_estimate": 3},
            }
            page2 = {
                "success": True,
                "data": {"message_ids": ["s3"], "next_page_token": None, "result_size_estimate": 3},
            }

            list_mock = AsyncMock(side_effect=[page1, page2])
            modify_mock = AsyncMock(return_value={"success": True, "data": {"modified": 2}})

            with patch("src.core.gmail_spam_clean_flow.gmail_list_message_ids_page", list_mock), patch(
                "src.core.gmail_spam_clean_flow.gmail_batch_modify_labels", modify_mock
            ):
                # Turn 1: prompt
                reply1 = await handle_gmail_spam_clean_turn(111, "empty spam folder")
                self.assertIn("I found", reply1)
                self.assertIn("in:spam", reply1)
                self.assertIn("Reply YES", reply1)

                # Ensure pagination used max_results=500 and q=in:spam
                first_call = list_mock.await_args_list[0]
                self.assertEqual(first_call.kwargs.get("query"), "in:spam")
                self.assertEqual(first_call.kwargs.get("max_results"), 500)

                # Turn 2: yes executes
                reply2 = await handle_gmail_spam_clean_turn(111, "yes")
                self.assertIsInstance(reply2, dict)
                self.assertEqual(reply2.get("status"), "completed")
                self.assertEqual(reply2.get("movedCount"), 3)

                # batchModify invoked with collected message ids
                self.assertGreaterEqual(modify_mock.await_count, 2)
                m0 = modify_mock.await_args_list[0].kwargs
                self.assertEqual(m0.get("remove_label_ids"), ["SPAM"])
                self.assertEqual(m0.get("add_label_ids"), ["TRASH"])
                self.assertEqual(m0.get("message_ids"), ["s1", "s2"])
                m1 = modify_mock.await_args_list[1].kwargs
                self.assertEqual(m1.get("message_ids"), ["s3"])

        asyncio.run(run())

    def test_spam_clean_empty_returns_and_clears(self):
        async def run():
            from src.core.gmail_spam_clean_flow import handle_gmail_spam_clean_turn

            empty_page = {
                "success": True,
                "data": {"message_ids": [], "next_page_token": None, "result_size_estimate": 0},
            }

            list_mock = AsyncMock(return_value=empty_page)
            modify_mock = AsyncMock(return_value={"success": True, "data": {"modified": 0}})

            with patch("src.core.gmail_spam_clean_flow.gmail_list_message_ids_page", list_mock), patch(
                "src.core.gmail_spam_clean_flow.gmail_batch_modify_labels", modify_mock
            ):
                reply1 = await handle_gmail_spam_clean_turn(222, "clean spam")
                self.assertEqual(reply1, "Your spam folder is already empty.")

                # Follow-up YES should not execute anything because no pending state should exist.
                reply2 = await handle_gmail_spam_clean_turn(222, "yes")
                self.assertEqual(reply2, "")
                self.assertEqual(modify_mock.await_count, 0)

        asyncio.run(run())

    def test_spam_permanent_delete_uses_trash_query_and_batch_delete(self):
        async def run():
            from src.core.gmail_spam_clean_flow import handle_gmail_spam_clean_turn

            page1 = {
                "success": True,
                "data": {"message_ids": ["t1"], "next_page_token": None, "result_size_estimate": 1},
            }

            list_mock = AsyncMock(return_value=page1)
            delete_mock = AsyncMock(return_value={"success": True, "data": {"deleted": 1}})

            with patch("src.core.gmail_spam_clean_flow.gmail_list_message_ids_page", list_mock), patch(
                "src.core.gmail_spam_clean_flow.gmail_batch_delete_messages", delete_mock
            ):
                reply1 = await handle_gmail_spam_clean_turn(333, "permanently delete spam")
                self.assertIn("in:trash", reply1)
                reply2 = await handle_gmail_spam_clean_turn(333, "yes")
                self.assertIsInstance(reply2, dict)
                self.assertEqual(reply2.get("status"), "completed")
                self.assertEqual(reply2.get("deletedCount"), 1)
                self.assertEqual(delete_mock.await_count, 1)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
