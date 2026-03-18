"""Content strategy — decides what to post and generates prompts for Claude."""

import logging

from strategies.weight_manager import WeightManager

logger = logging.getLogger(__name__)

# Prompt templates per content style
STYLE_PROMPTS = {
    "hot_take": (
        "Write a provocative but thoughtful hot take about {topic}. "
        "It should be contrarian enough to spark discussion, but grounded in reality. "
        "Keep it to 1-2 sentences, under 280 characters. No hashtags."
    ),
    "thread": (
        "Write the first tweet of a 3-4 tweet thread about {topic}. "
        "Start with a hook that makes people want to read more. "
        "End with '🧵' to indicate it's a thread. Under 280 characters."
    ),
    "question": (
        "Write a thought-provoking question about {topic} that invites discussion. "
        "It should be open-ended and relevant to current trends. "
        "Keep it under 280 characters. No hashtags."
    ),
    "insight": (
        "Share a unique insight, observation, or lesson learned about {topic}. "
        "It should be something most people haven't considered. "
        "Keep it under 280 characters. No hashtags."
    ),
    "meme_caption": (
        "Write a witty, humorous observation about {topic}. "
        "Think viral tweet energy — relatable, funny, shareable. "
        "Keep it under 280 characters. No hashtags."
    ),
}

# Topic descriptions for context
TOPIC_DESCRIPTIONS = {
    "ai": "artificial intelligence, machine learning, LLMs, AI agents, AI safety",
    "tech": "technology industry, startups, product development, software engineering",
    "startups": "entrepreneurship, venture capital, startup culture, building companies",
    "culture": "internet culture, social media trends, digital life, memes",
    "science": "scientific discoveries, research breakthroughs, space, climate, biology",
}


class ContentStrategy:
    """Selects content style and topic, generates the content prompt."""

    def __init__(self, weight_manager: WeightManager):
        self.weight_manager = weight_manager

    async def generate_post_prompt(self) -> tuple[str, str, str]:
        """Generate a content creation prompt.

        Uses weighted random selection for both style and topic.

        Returns:
            Tuple of (content_prompt, selected_style, selected_topic)
        """
        style = await self.weight_manager.select("content_style")
        topic = await self.weight_manager.select("topic")

        template = STYLE_PROMPTS.get(style, STYLE_PROMPTS["insight"])
        topic_desc = TOPIC_DESCRIPTIONS.get(topic, topic)
        prompt = template.replace("{topic}", topic_desc)

        logger.info("Generated post prompt: style=%s, topic=%s", style, topic)
        return prompt, style, topic

    async def generate_content_text(self, style: str, topic: str) -> str:
        """Generate the actual content text via Claude.

        This is a separate API call (not Computer Use) to generate the tweet text,
        which is then passed to the X agent for posting.
        """
        import anthropic
        from config import get_settings

        settings = get_settings()
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        template = STYLE_PROMPTS.get(style, STYLE_PROMPTS["insight"])
        topic_desc = TOPIC_DESCRIPTIONS.get(topic, topic)
        prompt = template.replace("{topic}", topic_desc)

        response = client.messages.create(
            model=settings.MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        text = ""
        for block in response.content:
            if block.type == "text":
                text = block.text.strip()
                break

        # Ensure it fits in a tweet
        if len(text) > 280:
            text = text[:277] + "..."

        logger.info("Generated content (%d chars): %s", len(text), text[:100])
        return text
