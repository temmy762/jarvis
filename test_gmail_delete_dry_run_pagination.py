import asyncio
import unittest
from unittest.mock import AsyncMock, patch


class TestGmailDeleteDryRunPagination(unittest.TestCase):
    def test_dry_run_paginates_and_uses_query(self):
        async def run():
            from src.core.gmail_delete_flow import handle_gmail_delete_turn

            # Two pages: 2 ids then 2 ids
            page1 = {
                "success": True,
                "data": {
                    "message_ids": ["id1", "id2"],
                    "next_page_token": "t1",
                    "result_size_estimate": 999,
                },
            }
            page2 = {
                "success": True,
                "data": {
                    "message_ids": ["id3", "id4"],
                    "next_page_token": None,
                    "result_size_estimate": 999,
                },
            }

            list_mock = AsyncMock(side_effect=[page1, page2])

            # Always return headers successfully
            headers_mock = AsyncMock(
                return_value={
                    "success": True,
                    "data": {"Subject": "S", "From": "F", "Date": "D"},
                }
            )

            with patch("src.core.gmail_delete_flow.gmail_list_message_ids_page", list_mock), patch(
                "src.core.gmail_delete_flow.gmail_get_message_headers", headers_mock
            ):
                reply = await handle_gmail_delete_turn(123, "Delete all emails older than 30 days")

            self.assertIsInstance(reply, str)
            self.assertIn("older_than:30d", reply)
            self.assertIn("Say YES to move them to Trash, or CANCEL.", reply)
            self.assertIn("I found", reply)

            # Ensure pagination happened
            self.assertGreaterEqual(list_mock.await_count, 2)

            # Ensure max_results is 500 and query includes older_than
            first_call = list_mock.await_args_list[0]
            kwargs = first_call.kwargs
            self.assertEqual(kwargs.get("max_results"), 500)
            self.assertIn("older_than:30d", kwargs.get("query", ""))

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
