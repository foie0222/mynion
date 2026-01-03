"""
Unit tests for Slack receiver response logic.

Tests the is_bot_in_thread() and should_respond() functions
to ensure correct bot response behavior.
"""

# Import functions from receiver module
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from interfaces.slack.receiver import is_bot_in_thread, should_respond


class TestIsBotInThread:
    """Tests for is_bot_in_thread() function."""

    def test_bot_has_message_in_thread(self):
        """Bot should be detected when it has a message in the thread."""
        mock_client = MagicMock()
        mock_client.get_thread_replies.return_value = {
            "messages": [
                {"user": "U_USER_1", "text": "original message", "ts": "1234567890.000000"},
                {"user": "U_BOT_ID", "text": "bot response", "ts": "1234567890.000001"},
            ]
        }

        result = is_bot_in_thread(mock_client, "C_CHANNEL", "1234567890.000000", "U_BOT_ID")

        assert result is True
        mock_client.get_thread_replies.assert_called_once_with("C_CHANNEL", "1234567890.000000")

    def test_bot_has_no_message_in_thread(self):
        """Bot should not be detected when it has no message in the thread."""
        mock_client = MagicMock()
        mock_client.get_thread_replies.return_value = {
            "messages": [
                {"user": "U_USER_1", "text": "original message", "ts": "1234567890.000000"},
                {"user": "U_USER_2", "text": "user reply", "ts": "1234567890.000001"},
            ]
        }

        result = is_bot_in_thread(mock_client, "C_CHANNEL", "1234567890.000000", "U_BOT_ID")

        assert result is False

    def test_empty_thread(self):
        """Should return False for empty thread."""
        mock_client = MagicMock()
        mock_client.get_thread_replies.return_value = {"messages": []}

        result = is_bot_in_thread(mock_client, "C_CHANNEL", "1234567890.000000", "U_BOT_ID")

        assert result is False

    def test_api_error_returns_false(self):
        """Should return False when API call fails."""
        mock_client = MagicMock()
        mock_client.get_thread_replies.side_effect = Exception("API Error")

        result = is_bot_in_thread(mock_client, "C_CHANNEL", "1234567890.000000", "U_BOT_ID")

        assert result is False


class TestShouldRespond:
    """Tests for should_respond() function."""

    def test_respond_to_mention(self):
        """Bot should respond when mentioned."""
        mock_client = MagicMock()
        event = {
            "user": "U_USER_1",
            "text": "<@U_BOT_ID> hello!",
            "channel": "C_CHANNEL",
            "ts": "1234567890.000000",
        }

        result = should_respond(mock_client, event, "U_BOT_ID")

        assert result is True

    def test_respond_to_thread_reply_when_bot_participated(self):
        """Bot should respond to thread reply when it has participated."""
        mock_client = MagicMock()
        mock_client.get_thread_replies.return_value = {
            "messages": [
                {"user": "U_USER_1", "text": "original", "ts": "1234567890.000000"},
                {"user": "U_BOT_ID", "text": "bot reply", "ts": "1234567890.000001"},
            ]
        }
        event = {
            "user": "U_USER_1",
            "text": "follow up question",  # No mention
            "channel": "C_CHANNEL",
            "ts": "1234567890.000002",
            "thread_ts": "1234567890.000000",
        }

        result = should_respond(mock_client, event, "U_BOT_ID")

        assert result is True

    def test_no_respond_to_thread_reply_when_bot_not_participated(self):
        """Bot should NOT respond to thread reply when it has NOT participated."""
        mock_client = MagicMock()
        mock_client.get_thread_replies.return_value = {
            "messages": [
                {"user": "U_USER_1", "text": "original", "ts": "1234567890.000000"},
                {"user": "U_USER_2", "text": "other user reply", "ts": "1234567890.000001"},
            ]
        }
        event = {
            "user": "U_USER_1",
            "text": "another message",  # No mention
            "channel": "C_CHANNEL",
            "ts": "1234567890.000002",
            "thread_ts": "1234567890.000000",
        }

        result = should_respond(mock_client, event, "U_BOT_ID")

        assert result is False

    def test_no_respond_to_regular_message_without_mention(self):
        """Bot should NOT respond to regular message without mention."""
        mock_client = MagicMock()
        event = {
            "user": "U_USER_1",
            "text": "hello everyone",  # No mention, no thread
            "channel": "C_CHANNEL",
            "ts": "1234567890.000000",
        }

        result = should_respond(mock_client, event, "U_BOT_ID")

        assert result is False

    def test_ignore_bot_own_message(self):
        """Bot should NOT respond to its own messages."""
        mock_client = MagicMock()
        event = {
            "user": "U_BOT_ID",  # Bot's own message
            "text": "<@U_BOT_ID> test",
            "channel": "C_CHANNEL",
            "ts": "1234567890.000000",
        }

        result = should_respond(mock_client, event, "U_BOT_ID")

        assert result is False

    def test_ignore_other_bot_message(self):
        """Bot should NOT respond to other bot messages."""
        mock_client = MagicMock()
        event = {
            "user": "U_OTHER_BOT",
            "bot_id": "B_OTHER_BOT",  # Has bot_id
            "text": "<@U_BOT_ID> hello",
            "channel": "C_CHANNEL",
            "ts": "1234567890.000000",
        }

        result = should_respond(mock_client, event, "U_BOT_ID")

        assert result is False

    def test_respond_to_mention_in_thread(self):
        """Bot should respond to mention even in thread where it hasn't participated."""
        mock_client = MagicMock()
        mock_client.get_thread_replies.return_value = {
            "messages": [
                {"user": "U_USER_1", "text": "original", "ts": "1234567890.000000"},
            ]
        }
        event = {
            "user": "U_USER_1",
            "text": "<@U_BOT_ID> help me",  # Has mention
            "channel": "C_CHANNEL",
            "ts": "1234567890.000001",
            "thread_ts": "1234567890.000000",
        }

        result = should_respond(mock_client, event, "U_BOT_ID")

        assert result is True
        # Should not call get_thread_replies since mention check comes first
