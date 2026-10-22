"""Engagement strategy — decides how and where to comment, using Gemini for text generation."""

import logging

from strategies.weight_manager import WeightManager

logger = logging.getLogger(__name__)

COMMENT_STYLE_PROMPTS = {
    "agree_and_extend": (
        "Write a reply that agrees with the post's main point and extends it "
        "with an additional insight or example about {topic}. "
        "Be genuine, not sycophantic. 1-2 sentences, under 280 characters."
    ),
    "question": (
        "Write a thoughtful follow-up question about {topic} that shows you "
        "engaged with the post's content. It should invite further discussion. "
        "Under 280 characters."
    ),
    "humor": (
        "Write a witty, relevant reply about {topic} that adds levity while "
        "still being on-topic. Not mean-spirited — clever and friendly. "
        "Under 280 characters."
    ),
    "counterpoint": (
        "Write a respectful counterpoint or alternative perspective on {topic}. "
        "Challenge the idea thoughtfully without being combative. "
        "Under 280 characters."
    ),
    "resource_share": (
        "Write a reply that shares a relevant fact, framework, or perspective "
        "about {topic} that adds value to the conversation. "
        "Under 280 characters."
    ),
}


def _get_gemini_client():
    from google import genai
    from config import get_settings
    settings = get_settings()
    return genai.Client(api_key=settings.GEMINI_API_KEY)


class EngagementStrategy:
    """Selects comment style and generates engagement text via Gemini."""

    def __init__(self, weight_manager: WeightManager):
        self.weight_manager = weight_manager

    async def generate_comment_prompt(self) -> tuple[str, str, str]:
        """Generate a comment creation prompt."""
        style = await self.weight_manager.select("comment_style")
        topic = await self.weight_manager.select("topic")

        template = COMMENT_STYLE_PROMPTS.get(style, COMMENT_STYLE_PROMPTS["agree_and_extend"])
        prompt = template.replace("{topic}", topic)

        logger.info("Generated comment prompt: style=%s, topic=%s", style, topic)
        return prompt, style, topic

    async def generate_comment_text(self, style: str, topic: str, post_context: str = "") -> str:
        """Generate comment text via Gemini. Skips political content."""
        from strategies.targeting_strategy import is_political

        # Skip political posts entirely
        if post_context and is_political(post_context):
            logger.info("Skipping political post — not engaging")
            return ""

        client = _get_gemini_client()

        template = COMMENT_STYLE_PROMPTS.get(style, COMMENT_STYLE_PROMPTS["agree_and_extend"])
        prompt = template.replace("{topic}", topic)

        if post_context:
            prompt = f"Context — you are replying to this post: \"{post_context}\"\n\n{prompt}"

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        text = ""
        if not response.candidates or not response.candidates[0].content.parts:
            raise ValueError("Gemini returned empty response (safety filter or quota?)")
        for part in response.candidates[0].content.parts:
            if part.text:
                text = part.text.strip()
                break

        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]

        if len(text) > 280:
            text = text[:277] + "..."

        logger.info("Generated comment (%d chars): %s", len(text), text[:100])
        return text

    async def generate_mention_reply(self, mention_text: str) -> str:
        """Generate a reply to a mention using Gemini. Skips political mentions."""
        from strategies.targeting_strategy import is_political

        if is_political(mention_text):
            logger.info("Skipping political mention — not replying")
            return ""

        client = _get_gemini_client()

        prompt = (
            f"Someone mentioned you on X (Twitter) with this message:\n"
            f"\"{mention_text}\"\n\n"
            f"Write a friendly, authentic reply. Be conversational, not robotic. "
            f"Under 280 characters. No hashtags."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        text = ""
        if not response.candidates or not response.candidates[0].content.parts:
            raise ValueError("Gemini returned empty response (safety filter or quota?)")
        for part in response.candidates[0].content.parts:
            if part.text:
                text = part.text.strip()
                break

        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]

        if len(text) > 280:
            text = text[:277] + "..."

        return text
