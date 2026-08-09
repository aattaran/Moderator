"""Content reflection — analyzes past posts via Gemini to evolve style guidelines."""

import json
import logging

from config import Settings
from storage.database import Database
from storage.models import Post, StyleGuideline

logger = logging.getLogger(__name__)

REFLECTION_PROMPT = """You are analyzing the performance of tweets posted by an autonomous bot account.
Your job: find patterns in what works and what doesn't, then produce actionable style guidelines.

## Top Performing Posts (highest engagement):
{top_posts}

## Bottom Performing Posts (lowest engagement):
{bottom_posts}

## Current Style Guidelines (previous version):
{current_guidelines}

Based on this data, produce:

1. **PATTERNS**: What do the top posts have in common? Consider: sentence structure, tone,
   specificity vs generality, use of questions, controversy level, length, topic framing.

2. **ANTI_PATTERNS**: What do the bottom posts have in common? What should be avoided?

3. **GUIDELINES**: Write 5-8 concise, actionable guidelines for generating better tweets.
   Each should be a single imperative sentence.
   Example: "Lead with a specific, concrete claim rather than a vague observation."

4. **TOPIC_INSIGHTS**: Which sub-topics or angles performed best? Be specific about
   framings, not just broad categories.

5. **SUMMARY**: One paragraph explaining the key takeaway.

Return ONLY valid JSON with these exact keys:
{{"patterns": ["..."], "anti_patterns": ["..."], "guidelines": ["..."], "topic_insights": ["..."], "summary": "..."}}
"""


def _engagement_score(post: Post) -> float:
    return post.engagement_likes + (post.engagement_reposts * 3) + (post.engagement_replies * 2)


def _format_post(post: Post, score: float) -> str:
    return (
        f"- [{post.content_style}] [{post.topic or 'unknown'}] "
        f"(likes={post.engagement_likes}, reposts={post.engagement_reposts}, "
        f"replies={post.engagement_replies}, score={score:.0f})\n"
        f"  \"{post.content[:280]}\""
    )


class ContentReflector:
    """Periodically reflects on post performance and evolves style guidelines."""

    def __init__(self, db: Database, config: Settings):
        self.db = db
        self.config = config

    async def run_reflection(self, platform: str) -> StyleGuideline | None:
        """Analyze recent posts and produce updated style guidelines."""
        min_posts = getattr(self.config, "REFLECTION_MIN_POSTS", 15)

        posts = await self.db.get_posts_with_engagement(platform, min_age_hours=48, limit=100)
        if len(posts) < min_posts:
            logger.info(
                "Reflection skipped — only %d posts with engagement (need %d)",
                len(posts), min_posts,
            )
            return None

        # Score and rank all posts
        scored = [(p, _engagement_score(p)) for p in posts]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Split into top 25% and bottom 25%
        n = len(scored)
        top_n = max(3, n // 4)
        bottom_n = max(3, n // 4)
        top_posts = scored[:top_n]
        bottom_posts = scored[-bottom_n:]

        avg_score = sum(s for _, s in scored) / n

        # Format for the prompt
        top_text = "\n\n".join(_format_post(p, s) for p, s in top_posts)
        bottom_text = "\n\n".join(_format_post(p, s) for p, s in bottom_posts)

        # Get current guidelines for this platform
        guideline_platform = "elemnt" if platform in ("facebook", "instagram", "tiktok") else platform
        current = await self.db.get_active_guideline(guideline_platform)
        current_text = current.guidelines_text if current else "None yet — this is the first reflection."

        prompt = REFLECTION_PROMPT.format(
            top_posts=top_text,
            bottom_posts=bottom_text,
            current_guidelines=current_text,
        )

        # Call Gemini
        try:
            from google import genai
            client = genai.Client(api_key=self.config.GEMINI_API_KEY)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )

            if not response.candidates or not response.candidates[0].content.parts:
                logger.warning("Reflection: Gemini returned empty response, skipping")
                return None

            raw = ""
            for part in response.candidates[0].content.parts:
                if part.text:
                    raw = part.text.strip()
                    break

            # Parse JSON — handle markdown code blocks
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            analysis = json.loads(raw)

        except (json.JSONDecodeError, Exception) as e:
            logger.error("Reflection failed — could not parse Gemini response: %s", e)
            return None

        # Build the guidelines text that gets prepended to prompts
        guidelines_list = analysis.get("guidelines", [])
        guidelines_text = "Follow these style guidelines based on what has worked best for this account:\n"
        guidelines_text += "\n".join(f"- {g}" for g in guidelines_list)

        # Store
        version = await self.db.get_next_guideline_version(guideline_platform)
        guideline = StyleGuideline(
            version=version,
            platform=guideline_platform,
            guidelines_text=guidelines_text,
            analysis_summary=analysis.get("summary", ""),
            top_patterns=analysis.get("patterns", []),
            anti_patterns=analysis.get("anti_patterns", []),
            posts_analyzed=n,
            avg_engagement_score=avg_score,
        )
        guideline.id = await self.db.insert_style_guideline(guideline)

        logger.info(
            "Reflection v%d complete — analyzed %d posts (avg score: %.1f). Guidelines: %s",
            version, n, avg_score, guidelines_text[:200],
        )

        # Log insights
        for insight in analysis.get("topic_insights", []):
            logger.info("  Topic insight: %s", insight)

        return guideline
