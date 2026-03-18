"""Claude Computer Use API wrapper and agent loop."""

import asyncio
import logging
import subprocess
from dataclasses import dataclass, field

import anthropic

from core.screenshots import capture_and_encode

logger = logging.getLogger(__name__)

# Computer Use API constants
TOOL_VERSION = "computer_20251124"
BETA_FLAG = "computer-use-2025-11-24"
COMPUTER_TOOL_NAME = "computer"


@dataclass
class ToolResult:
    """Result of executing a computer use action."""
    output: str | None = None
    error: str | None = None
    base64_image: str | None = None


@dataclass
class AgentLoopResult:
    """Result of a complete agent loop execution."""
    messages: list[dict] = field(default_factory=list)
    iterations: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    success: bool = False
    final_text: str = ""


class ActionExecutor:
    """Executes computer use actions via xdotool and scrot."""

    def __init__(self, display: str = ":1", dry_run: bool = False):
        self.display = display
        self.dry_run = dry_run

    async def execute(self, action_input: dict) -> ToolResult:
        """Dispatch and execute a computer use action."""
        action = action_input.get("action", "")
        try:
            if action == "screenshot":
                return await self._screenshot()
            elif action == "left_click":
                return await self._click(action_input, button=1)
            elif action == "right_click":
                return await self._click(action_input, button=3)
            elif action == "middle_click":
                return await self._click(action_input, button=2)
            elif action == "double_click":
                return await self._click(action_input, button=1, clicks=2)
            elif action == "triple_click":
                return await self._click(action_input, button=1, clicks=3)
            elif action == "type":
                return await self._type_text(action_input)
            elif action == "key":
                return await self._key_press(action_input)
            elif action == "mouse_move":
                return await self._mouse_move(action_input)
            elif action == "scroll":
                return await self._scroll(action_input)
            elif action == "left_click_drag":
                return await self._drag(action_input)
            elif action == "left_mouse_down":
                return await self._mouse_button(action_input, "mousedown", 1)
            elif action == "left_mouse_up":
                return await self._mouse_button(action_input, "mouseup", 1)
            elif action == "hold_key":
                return await self._hold_key(action_input)
            elif action == "wait":
                return await self._wait(action_input)
            else:
                return ToolResult(error=f"Unknown action: {action}")
        except Exception as e:
            logger.error("Action %s failed: %s", action, e)
            return ToolResult(error=str(e))

    async def _screenshot(self) -> ToolResult:
        """Capture current screen."""
        b64 = capture_and_encode(self.display)
        return ToolResult(base64_image=b64)

    async def _click(self, inp: dict, button: int, clicks: int = 1) -> ToolResult:
        """Click at coordinates."""
        coord = inp.get("coordinate", [0, 0])
        x, y = coord[0], coord[1]
        modifier = inp.get("text", "")

        cmds = [f"xdotool mousemove --sync {x} {y}"]
        if modifier:
            cmds.append(f"xdotool keydown {modifier}")
        cmds.append(f"xdotool click --repeat {clicks} {button}")
        if modifier:
            cmds.append(f"xdotool keyup {modifier}")

        await self._run_shell(" && ".join(cmds))
        await asyncio.sleep(0.3)
        b64 = capture_and_encode(self.display)
        return ToolResult(output=f"Clicked at ({x}, {y})", base64_image=b64)

    async def _type_text(self, inp: dict) -> ToolResult:
        """Type text string, chunked for reliability."""
        text = inp.get("text", "")
        # Type in chunks to avoid xdotool buffer issues
        chunk_size = 50
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            # Use xdotool type with --clearmodifiers to avoid stuck keys
            await self._run_shell(
                f"xdotool type --delay 12 --clearmodifiers -- {self._shell_escape(chunk)}"
            )
        await asyncio.sleep(0.2)
        b64 = capture_and_encode(self.display)
        return ToolResult(output=f"Typed {len(text)} characters", base64_image=b64)

    async def _key_press(self, inp: dict) -> ToolResult:
        """Press a key or key combination."""
        key = inp.get("key", "")
        # Map common Claude key names to xdotool names
        key_map = {
            "Return": "Return", "Enter": "Return",
            "Tab": "Tab", "Escape": "Escape",
            "Backspace": "BackSpace", "Delete": "Delete",
            "space": "space", "Up": "Up", "Down": "Down",
            "Left": "Left", "Right": "Right",
            "Home": "Home", "End": "End",
            "Page_Up": "Prior", "Page_Down": "Next",
        }
        # Handle modifier combos like "ctrl+a"
        parts = key.split("+")
        mapped = []
        for part in parts:
            stripped = part.strip()
            mapped.append(key_map.get(stripped, stripped))
        xdo_key = "+".join(mapped)

        await self._run_shell(f"xdotool key -- {xdo_key}")
        await asyncio.sleep(0.3)
        b64 = capture_and_encode(self.display)
        return ToolResult(output=f"Pressed {key}", base64_image=b64)

    async def _mouse_move(self, inp: dict) -> ToolResult:
        """Move cursor to coordinates."""
        coord = inp.get("coordinate", [0, 0])
        x, y = coord[0], coord[1]
        await self._run_shell(f"xdotool mousemove --sync {x} {y}")
        return ToolResult(output=f"Moved mouse to ({x}, {y})")

    async def _scroll(self, inp: dict) -> ToolResult:
        """Scroll at coordinates."""
        coord = inp.get("coordinate", [0, 0])
        x, y = coord[0], coord[1]
        direction = inp.get("scroll_direction", "down")
        amount = inp.get("scroll_amount", 3)
        modifier = inp.get("text", "")

        # Button 4=up, 5=down, 6=left, 7=right
        button_map = {"up": 4, "down": 5, "left": 6, "right": 7}
        button = button_map.get(direction, 5)

        cmds = [f"xdotool mousemove --sync {x} {y}"]
        if modifier:
            cmds.append(f"xdotool keydown {modifier}")
        cmds.append(f"xdotool click --repeat {amount} {button}")
        if modifier:
            cmds.append(f"xdotool keyup {modifier}")

        await self._run_shell(" && ".join(cmds))
        await asyncio.sleep(0.3)
        b64 = capture_and_encode(self.display)
        return ToolResult(output=f"Scrolled {direction} {amount} at ({x}, {y})", base64_image=b64)

    async def _drag(self, inp: dict) -> ToolResult:
        """Click and drag from start_coordinate to coordinate."""
        start = inp.get("start_coordinate", [0, 0])
        end = inp.get("coordinate", [0, 0])
        await self._run_shell(
            f"xdotool mousemove --sync {start[0]} {start[1]} "
            f"mousedown 1 "
            f"mousemove --sync {end[0]} {end[1]} "
            f"mouseup 1"
        )
        await asyncio.sleep(0.3)
        b64 = capture_and_encode(self.display)
        return ToolResult(output=f"Dragged from {start} to {end}", base64_image=b64)

    async def _mouse_button(self, inp: dict, action: str, button: int) -> ToolResult:
        """Mouse button down/up."""
        coord = inp.get("coordinate", [0, 0])
        x, y = coord[0], coord[1]
        await self._run_shell(f"xdotool mousemove --sync {x} {y} {action} {button}")
        return ToolResult(output=f"{action} button {button} at ({x}, {y})")

    async def _hold_key(self, inp: dict) -> ToolResult:
        """Hold a key for a duration."""
        key = inp.get("key", "")
        duration = inp.get("duration", 1)
        await self._run_shell(f"xdotool keydown {key}")
        await asyncio.sleep(min(duration, 5))  # Cap at 5 seconds
        await self._run_shell(f"xdotool keyup {key}")
        return ToolResult(output=f"Held {key} for {duration}s")

    async def _wait(self, inp: dict) -> ToolResult:
        """Pause execution."""
        duration = min(inp.get("duration", 1), 10)  # Cap at 10 seconds
        await asyncio.sleep(duration)
        b64 = capture_and_encode(self.display)
        return ToolResult(output=f"Waited {duration}s", base64_image=b64)

    async def _run_shell(self, cmd: str):
        """Run a shell command, or log it if in dry-run mode."""
        if self.dry_run:
            logger.info("[DRY RUN] Would execute: %s", cmd)
            return
        env_prefix = f"DISPLAY={self.display}"
        full_cmd = f"{env_prefix} {cmd}"
        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode != 0:
            error_msg = stderr.decode().strip() if stderr else f"Exit code {proc.returncode}"
            raise RuntimeError(f"Command failed: {cmd}\n{error_msg}")

    @staticmethod
    def _shell_escape(text: str) -> str:
        """Escape text for safe shell usage."""
        return "'" + text.replace("'", "'\\''") + "'"


class AgentLoop:
    """Runs the Computer Use agent loop: screenshot → Claude → action → repeat."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-opus-4-6",
        display_width: int = 1024,
        display_height: int = 768,
        dry_run: bool = False,
    ):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.display_width = display_width
        self.display_height = display_height
        self.executor = ActionExecutor(dry_run=dry_run)
        self.tools = [
            {
                "type": TOOL_VERSION,
                "name": COMPUTER_TOOL_NAME,
                "display_width_px": display_width,
                "display_height_px": display_height,
                "display_number": 1,
            }
        ]

    async def run(
        self,
        task: str,
        system_prompt: str,
        max_iterations: int = 30,
    ) -> AgentLoopResult:
        """Execute a task via the Computer Use agent loop.

        Returns AgentLoopResult with messages, token usage, and final text.
        """
        messages = [{"role": "user", "content": task}]
        result = AgentLoopResult()

        for iteration in range(max_iterations):
            result.iterations = iteration + 1

            # Truncate old screenshots to manage context size
            self._truncate_old_screenshots(messages, keep_last=5)

            logger.info("Agent loop iteration %d/%d", iteration + 1, max_iterations)

            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
                tools=self.tools,
                betas=[BETA_FLAG],
            )

            # Track token usage
            result.total_input_tokens += response.usage.input_tokens
            result.total_output_tokens += response.usage.output_tokens

            # Append assistant response to history
            messages.append({"role": "assistant", "content": response.content})

            # Process tool use blocks
            tool_results = []
            for block in response.content:
                if block.type == "text":
                    result.final_text = block.text
                    logger.debug("Claude says: %s", block.text[:200])
                elif block.type == "tool_use":
                    logger.info(
                        "Executing action: %s(%s)",
                        block.name,
                        block.input.get("action", "unknown"),
                    )
                    action_result = await self.executor.execute(block.input)
                    tool_result = {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": self._format_tool_result(action_result),
                    }
                    if action_result.error:
                        tool_result["is_error"] = True
                    tool_results.append(tool_result)

            # If no tools were used, Claude is done
            if not tool_results:
                result.success = True
                result.messages = messages
                logger.info(
                    "Agent loop completed in %d iterations (%d input tokens, %d output tokens)",
                    result.iterations,
                    result.total_input_tokens,
                    result.total_output_tokens,
                )
                return result

            # Feed tool results back
            messages.append({"role": "user", "content": tool_results})

        # Exceeded max iterations
        result.messages = messages
        logger.warning("Agent loop exceeded %d iterations", max_iterations)
        return result

    @staticmethod
    def _format_tool_result(result: ToolResult) -> list[dict]:
        """Format a ToolResult into content blocks for the API."""
        content = []
        if result.error:
            content.append({"type": "text", "text": result.error})
        elif result.output:
            content.append({"type": "text", "text": result.output})
        if result.base64_image:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": result.base64_image,
                    },
                }
            )
        return content if content else [{"type": "text", "text": "Action completed."}]

    @staticmethod
    def _truncate_old_screenshots(messages: list[dict], keep_last: int = 5):
        """Remove images from older tool results to prevent token bloat.

        Keeps only the last `keep_last` screenshots in the conversation.
        Older images are replaced with a text placeholder.
        """
        image_indices = []
        for i, msg in enumerate(messages):
            if msg.get("role") != "user":
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for j, block in enumerate(content):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    inner_content = block.get("content")
                    if isinstance(inner_content, list):
                        for k, inner_block in enumerate(inner_content):
                            if isinstance(inner_block, dict) and inner_block.get("type") == "image":
                                image_indices.append((i, j, k))

        # Remove all but the last `keep_last` images
        to_remove = image_indices[:-keep_last] if len(image_indices) > keep_last else []
        for i, j, k in to_remove:
            messages[i]["content"][j]["content"][k] = {
                "type": "text",
                "text": "[Screenshot removed to save context]",
            }
