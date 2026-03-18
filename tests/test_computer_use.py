"""Tests for the Computer Use agent loop (mocked — no Docker or API calls)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.computer_use import ActionExecutor, AgentLoop, ToolResult


class TestToolResult:
    def test_success_result(self):
        result = ToolResult(output="Clicked", base64_image="abc123")
        assert result.output == "Clicked"
        assert result.error is None
        assert result.base64_image == "abc123"

    def test_error_result(self):
        result = ToolResult(error="Command failed")
        assert result.error == "Command failed"
        assert result.output is None


class TestActionExecutor:
    @pytest.mark.asyncio
    async def test_screenshot_action(self):
        executor = ActionExecutor(dry_run=True)
        with patch("core.computer_use.capture_and_encode", return_value="base64data"):
            result = await executor.execute({"action": "screenshot"})
        assert result.base64_image == "base64data"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        executor = ActionExecutor(dry_run=True)
        result = await executor.execute({"action": "teleport"})
        assert result.error == "Unknown action: teleport"

    @pytest.mark.asyncio
    async def test_wait_action_capped(self):
        executor = ActionExecutor(dry_run=True)
        with patch("core.computer_use.capture_and_encode", return_value="img"):
            result = await executor.execute({"action": "wait", "duration": 100})
        # Duration should be capped at 10
        assert result.output == "Waited 10s"


class TestAgentLoop:
    def _make_mock_response(self, content_blocks, stop_reason="end_turn"):
        """Create a mock API response."""
        response = MagicMock()
        response.content = content_blocks
        response.stop_reason = stop_reason
        response.usage = MagicMock()
        response.usage.input_tokens = 100
        response.usage.output_tokens = 50
        return response

    @pytest.mark.asyncio
    async def test_simple_text_response(self):
        """Agent loop should complete when Claude responds with text only."""
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Task complete!"

        response = self._make_mock_response([text_block])

        with patch("anthropic.Anthropic") as MockClient:
            mock_client = MagicMock()
            mock_client.beta.messages.create.return_value = response
            MockClient.return_value = mock_client

            loop = AgentLoop(api_key="test-key", dry_run=True)
            loop.client = mock_client

            result = await loop.run("Do something", "System prompt")

        assert result.success is True
        assert result.iterations == 1
        assert result.final_text == "Task complete!"

    @pytest.mark.asyncio
    async def test_tool_use_then_completion(self):
        """Agent loop should execute tool, feed result, then complete."""
        # First response: tool_use
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "tool_123"
        tool_block.name = "computer"
        tool_block.input = {"action": "screenshot"}
        response1 = self._make_mock_response([tool_block])

        # Second response: text (done)
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Done!"
        response2 = self._make_mock_response([text_block])

        with patch("anthropic.Anthropic") as MockClient:
            mock_client = MagicMock()
            mock_client.beta.messages.create.side_effect = [response1, response2]
            MockClient.return_value = mock_client

            loop = AgentLoop(api_key="test-key", dry_run=True)
            loop.client = mock_client
            loop.executor = AsyncMock()
            loop.executor.execute.return_value = ToolResult(
                output="Screenshot taken", base64_image="img_data"
            )

            result = await loop.run("Take a screenshot", "System prompt")

        assert result.success is True
        assert result.iterations == 2
        loop.executor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_max_iterations_exceeded(self):
        """Agent loop should stop after max_iterations."""
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "tool_1"
        tool_block.name = "computer"
        tool_block.input = {"action": "screenshot"}
        response = self._make_mock_response([tool_block])

        with patch("anthropic.Anthropic"):
            loop = AgentLoop(api_key="test-key", dry_run=True)
            loop.client = MagicMock()
            loop.client.beta.messages.create.return_value = response
            loop.executor = AsyncMock()
            loop.executor.execute.return_value = ToolResult(base64_image="img")

            result = await loop.run("Loop forever", "System", max_iterations=3)

        assert result.success is False
        assert result.iterations == 3

    def test_format_tool_result_with_image(self):
        result = ToolResult(output="Clicked", base64_image="abc123")
        formatted = AgentLoop._format_tool_result(result)
        assert len(formatted) == 2
        assert formatted[0]["type"] == "text"
        assert formatted[1]["type"] == "image"
        assert formatted[1]["source"]["data"] == "abc123"

    def test_format_tool_result_error(self):
        result = ToolResult(error="Something broke")
        formatted = AgentLoop._format_tool_result(result)
        assert len(formatted) == 1
        assert formatted[0]["text"] == "Something broke"

    def test_truncate_old_screenshots(self):
        """Should keep only the last N screenshots."""
        messages = [
            {"role": "user", "content": "Start"},
        ]
        # Add 8 tool results with screenshots
        for i in range(8):
            messages.append({"role": "assistant", "content": [{"type": "text", "text": f"Step {i}"}]})
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": f"tool_{i}",
                        "content": [
                            {"type": "text", "text": f"Result {i}"},
                            {"type": "image", "source": {"type": "base64", "data": f"img_{i}"}},
                        ],
                    }
                ],
            })

        AgentLoop._truncate_old_screenshots(messages, keep_last=3)

        # Count remaining images
        image_count = 0
        for msg in messages:
            if msg.get("role") != "user" or not isinstance(msg.get("content"), list):
                continue
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    for inner in block.get("content", []):
                        if isinstance(inner, dict) and inner.get("type") == "image":
                            image_count += 1

        assert image_count == 3
