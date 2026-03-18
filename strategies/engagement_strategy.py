"""Engagement strategy — decides how and where to comment for maximum engagement."""

import logging

from strategies.weight_manager import WeightManager

logger = logging.getLogger(__name__)

# Comment style templates — these guide Claude in generating the actual comment
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


class EngagementStrategy:
    """Selects comment style and generates engagement prompts."""

    def __init__(self, weight_manager: WeightManager):
        self.weight_manager = weight_manager

    async def generate_comment_prompt(self) -> tuple[str, str, str]:
        """Generate a comment creation prompt.

        Returns:
            Tuple of (comment_prompt, selected_style, selected_topic)
        """
        style = await self.weight_manager.select("comment_style")
        topic = await self.weight_manager.select("topic")

        template = COMMENT_STYLE_PROMPTS.get(style, COMMENT_STYLE_PROMPTS["agree_and_extend"])
        prompt = template.replace("{topic}", topic)

        logger.info("Generated comment prompt: style=%s, topic=%s", style, topic)
        return prompt, style, topic

    async def generate_comment_text(self, style: str, topic: str, post_context: str = "") -> str:
        """Generate the actual comment text via Claude.

        Args:
            style: Comment style to use
            topic: Topic category
            post_context: Optional context about the post being replied to

        Returns:
            The generated comment text
        """
        import anthropic
        from config import get_settings

        settings = get_settings()
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        template = COMMENT_STYLE_PROMPTS.get(style, COMMENT_STYLE_PROMPTS["agree_and_extend"])
        prompt = template.replace("{topic}", topic)

        if post_context:
            prompt = f"Context — you are replying to this post: \"{post_context}\"\n\n{prompt}"

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

        if len(text) > 280:
            text = text[:277] + "..."

        logger.info("Generated comment (%d chars): %s", len(text), text[:100])
        return text
