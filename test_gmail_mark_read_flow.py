import asyncio
import unittest
from unittest.mock import AsyncMock, patch


class TestGmailMarkReadFlow(unittest.TestCase):
    def test_mark_read_confirm_then_execute(self):
        async def run():
            from src.core.gmail_mark_read_flow import handle_gmail_mark_read_turn

            # First turn: dry-run lists one page with 2 ids
            page1 = {
                "success": True,
                "data": {
                    "message_ids": ["m1", "m2"],
                    "next_page_token": None,
                    "result_size_estimate": 2,
                },
            }

            list_mock = AsyncMock(return_value=page1)
            headers_mock = AsyncMock(
                return_value={
                    "success": True,
                    "data": {"Subject": "S", "From": "F", "Date": "D"},
                }
            )

            batch_modify_mock = AsyncMock(return_value={"success": True, "data": {"modified": 2}})

            with patch("src.core.gmail_mark_read_flow.gmail_list_message_ids_page", list_mock), patch(
                "src.core.gmail_mark_read_flow.gmail_get_message_headers", headers_mock
            ), patch("src.core.gmail_mark_read_flow.gmail_batch_modify_labels", batch_modify_mock):
                # Turn 1
                reply1 = await handle_gmail_mark_read_turn(
                    999,
                    "Mark all messages from sender@example.com as read",
                )
                self.assertIn("Please confirm", reply1)
                self.assertIn("sender@example.com", reply1)

                # Turn 2 (YES)
                reply2 = await handle_gmail_mark_read_turn(999, "yes")
                self.assertIn("Marked", reply2)

                # Ensure tool calls had required args
                self.assertGreaterEqual(list_mock.await_count, 1)
                self.assertGreaterEqual(batch_modify_mock.await_count, 1)

                bm_kwargs = batch_modify_mock.await_args_list[0].kwargs
                self.assertEqual(bm_kwargs.get("remove_label_ids"), ["UNREAD"])
                self.assertEqual(bm_kwargs.get("message_ids"), ["m1", "m2"])

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
