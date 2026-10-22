"""Reddit content strategy — value-first, karma-building approach for r/tiktokshop etc."""

import logging
import random

from strategies.weight_manager import WeightManager

logger = logging.getLogger(__name__)

REDDIT_PERSONA = (
    "You are posting on Reddit as Ali Attaran, a founder and AI engineer "
    "building multiple products. Your main project is MCRO (mcro.ai), a TikTok Shop "
    "analytics and automation platform with a Chrome extension.\n\n"
    "Your other projects: Jarvis (multi-channel AI gateway), Fleet Commander "
    "(Claude Code plugin for agent teams), Video Ad Pipeline (AI video ads), Moderator "
    "(autonomous social media agent).\n\n"
    "CRITICAL REDDIT RULES:\n"
    "- Reddit HATES self-promotion. Value first, always.\n"
    "- Write in a conversational, helpful tone. Not salesy. Not corporate.\n"
    "- Share genuine experience and knowledge. Be the helpful expert.\n"
    "- When mentioning your own tools, frame as 'I built X because I had problem Y' "
    "NOT 'Check out X, it does Y'.\n"
    "- Include specific details, numbers, and real experiences.\n"
    "- Match the subreddit's culture and norms.\n"
    "- Never use hashtags. Never use emojis excessively.\n"
    "- Longer is fine on Reddit — 2-5 paragraphs for posts, 1-3 paragraphs for comments.\n"
    "- Never start with 'Great question!' or similar filler.\n"
)

# ── MCRO Product Facts (for organic weaving into content) ─────

MCRO_FACTS = {
    "what": "MCRO is a TikTok Shop analytics and automation platform at mcro.ai with a Chrome extension",
    "chrome_extension": "Chrome extension for quick promotion setup, one-click scheduling, recurrence management, seamless sync with dashboard",
    "dashboard": "Web dashboard: real-time revenue/profit/cost tracking, inventory optimizer, fulfillment tracking across CLT2/LGB8/AVP1/JFK8 centers",
    "repricing": "Dynamic repricing engine with 4 strategies: Velocity Surge (match Buy Box when sales drop), Liquidation Protocol (auto price reduction), Profit Maximizer (raise prices when competitors low), Night Owl (increase margins during low-competition hours)",
    "ai": "AI-powered product title and description optimization via Gemini API, plus TikTok's Diagnose API for performance analysis",
    "promotions": "Flash sales, coupon campaigns, promotion templates (Summer, Black Friday, Cyber Monday), automatic affiliate notifications",
    "publishing": "Direct video upload and publishing to TikTok via Creator API (Hyperdrive tier)",
    "pain_point": "TikTok Shop's built-in analytics are basic — no competitor tracking, no dynamic repricing, no AI optimization",
    "target": "TikTok Shop sellers, dropshippers, and e-commerce brands",
    "pricing": "Spark (free, 50 products) → Velocity ($39/mo, 500 products) → Hyperdrive ($79/mo, 5000 products, Creator API access)",
    "tech": "Next.js 14, React 19, MongoDB, Redis, Stripe, Chrome Extension APIs",
}

# ── Content Types ─────────────────────────────────────────────

CONTENT_TYPES = {
    "helpful_comment": {
        "description": "Answer a question about TikTok Shop with genuine, detailed help",
        "promotional": False,
        "prompt": (
            "Write a helpful Reddit comment answering this question/discussion. "
            "Share genuine experience and actionable advice. Be detailed (2-4 paragraphs). "
            "Do NOT mention mcro.ai or any of your products. Pure value only.\n\n"
            "Post title: {title}\n"
            "Post body: {body}\n"
            "Subreddit: r/{subreddit}"
        ),
    },
    "experience_share": {
        "description": "Share personal experience with TikTok Shop",
        "promotional": False,
        "prompt": (
            "Write a Reddit comment sharing your personal experience relevant to this post. "
            "Include specific numbers, timelines, or lessons learned. Be authentic. "
            "Do NOT mention mcro.ai or any products.\n\n"
            "Post title: {title}\n"
            "Post body: {body}\n"
            "Subreddit: r/{subreddit}"
        ),
    },
    "guide_post": {
        "description": "Tutorial/guide post about TikTok Shop with soft mcro.ai mention",
        "promotional": True,
        "prompt": (
            "Write a Reddit post that's a practical guide about {topic}. "
            "Provide real, actionable steps (5-8 steps). Include specific details. "
            "The guide should be genuinely useful even without mcro.ai. "
            "At the very end, you can briefly mention 'I've been building mcro.ai to help "
            "with some of this' — but keep it to one sentence max. The guide is the value.\n\n"
            "Subreddit: r/{subreddit}"
        ),
    },
    "discussion_starter": {
        "description": "Start a discussion about TikTok Shop trends or strategies",
        "promotional": False,
        "prompt": (
            "Write a Reddit post starting a discussion about {topic}. "
            "Share your perspective and ask for others' experiences. "
            "Be specific — mention trends, numbers, or observations. "
            "No product mentions.\n\n"
            "Subreddit: r/{subreddit}"
        ),
    },
    "build_in_public": {
        "description": "'I built this' post for r/SideProject or r/Entrepreneur",
        "promotional": True,
        "prompt": (
            "Write an 'I built this' Reddit post about mcro.ai for r/{subreddit}. "
            "Structure: Problem you faced → What you built → Key features → "
            "What's next → Ask for feedback. Be genuine and humble. "
            "This is a subreddit that welcomes self-promotion, so be direct about "
            "what mcro.ai does. Include the URL mcro.ai.\n\n"
            "Key features to mention: {features}"
        ),
    },
    "tool_mention_comment": {
        "description": "Reply where someone asks for TikTok Shop tools",
        "promotional": True,
        "prompt": (
            "Write a Reddit comment where someone is asking for TikTok Shop tools or analytics. "
            "Recommend 2-3 tools/approaches (not just yours), then mention 'I've also been "
            "building mcro.ai which does [specific feature relevant to their question]'. "
            "Be honest about what it does and doesn't do.\n\n"
            "Post title: {title}\n"
            "Post body: {body}\n"
            "Subreddit: r/{subreddit}"
        ),
    },
}

# ── Subreddit Configs ─────────────────────────────────────────

SUBREDDIT_CONFIG = {
    "tiktokshop": {
        "post_types": ["guide_post", "discussion_starter", "experience_share"],
        "comment_types": ["helpful_comment", "experience_share", "tool_mention_comment"],
        "keywords": ["analytics", "sales", "dashboard", "automation", "chrome extension",
                      "product research", "trending", "shop analytics", "conversion",
                      "revenue", "best sellers", "tools"],
        "promotion_allowed": True,
        "min_karma_to_post": 50,
    },
    "tiktok": {
        "post_types": ["discussion_starter", "experience_share"],
        "comment_types": ["helpful_comment", "experience_share"],
        "keywords": ["shop", "selling", "analytics", "creator", "monetization",
                      "e-commerce", "tiktok shop"],
        "promotion_allowed": False,
        "min_karma_to_post": 100,
    },
    "ecommerce": {
        "post_types": ["guide_post", "experience_share", "discussion_starter"],
        "comment_types": ["helpful_comment", "experience_share"],
        "keywords": ["tiktok", "social commerce", "analytics", "automation",
                      "platform comparison", "selling"],
        "promotion_allowed": True,
        "min_karma_to_post": 100,
    },
    "dropshipping": {
        "post_types": ["guide_post", "experience_share"],
        "comment_types": ["helpful_comment", "experience_share"],
        "keywords": ["tiktok shop", "product research", "trending", "analytics",
                      "supplier", "automation"],
        "promotion_allowed": True,
        "min_karma_to_post": 100,
    },
    "smallbusiness": {
        "post_types": ["experience_share", "discussion_starter"],
        "comment_types": ["helpful_comment", "experience_share"],
        "keywords": ["tiktok", "social media", "e-commerce", "online sales",
                      "marketing", "analytics"],
        "promotion_allowed": False,
        "min_karma_to_post": 200,
    },
    "Entrepreneur": {
        "post_types": ["experience_share", "build_in_public"],
        "comment_types": ["helpful_comment", "experience_share"],
        "keywords": ["saas", "chrome extension", "side project", "tiktok",
                      "e-commerce", "startup"],
        "promotion_allowed": True,
        "min_karma_to_post": 100,
    },
    "SideProject": {
        "post_types": ["build_in_public"],
        "comment_types": ["helpful_comment"],
        "keywords": ["chrome extension", "saas", "analytics", "automation",
                      "tiktok", "e-commerce"],
        "promotion_allowed": True,
        "min_karma_to_post": 10,
    },
    "socialmediamarketing": {
        "post_types": ["guide_post", "discussion_starter"],
        "comment_types": ["helpful_comment", "experience_share"],
        "keywords": ["tiktok", "social commerce", "analytics", "content strategy",
                      "engagement", "algorithm"],
        "promotion_allowed": False,
        "min_karma_to_post": 100,
    },
}

# ── Topics for posts ──────────────────────────────────────────

REDDIT_TOPICS = {
    "tiktok_analytics": "TikTok Shop analytics — what metrics matter, how to track performance, tools and techniques",
    "product_research": "Finding winning products on TikTok Shop — research methods, trend spotting, competitor analysis",
    "tiktok_algorithm": "How the TikTok Shop algorithm works — content velocity, conversion signals, ranking factors",
    "seller_tips": "Practical TikTok Shop seller tips — listing optimization, pricing strategy, inventory management",
    "social_commerce": "Social commerce trends — TikTok vs Amazon vs Shopify, where the market is going",
    "automation_tools": "E-commerce automation — tools, workflows, and time-saving strategies for online sellers",
    "build_in_public": "Building MCRO — progress updates, challenges, technical decisions, lessons learned",
}


def _get_gemini_client():
    from google import genai
    from config import get_settings
    return genai.Client(api_key=get_settings().GEMINI_API_KEY)


class RedditContentStrategy:
    """Generates Reddit-appropriate content via Gemini."""

    def __init__(self, weight_manager: WeightManager, db=None):
        self.weight_manager = weight_manager
        self.db = db

    async def generate_comment(
        self, post_title: str, post_body: str, subreddit: str,
        content_type: str = "helpful_comment",
    ) -> str:
        """Generate a Reddit comment for a specific post."""
        client = _get_gemini_client()

        ct = CONTENT_TYPES.get(content_type, CONTENT_TYPES["helpful_comment"])
        prompt = ct["prompt"].format(
            title=post_title, body=post_body[:500], subreddit=subreddit,
            topic="", features="",
        )

        guidelines = ""
        if self.db:
            try:
                guideline = await self.db.get_active_guideline("reddit")
                if guideline:
                    guidelines = guideline.guidelines_text
            except Exception:
                pass

        full_prompt = REDDIT_PERSONA
        if guidelines:
            full_prompt += f"\n\n{guidelines}"
        full_prompt += f"\n\n{prompt}"

        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=full_prompt,
        )

        text = ""
        if not response.candidates or not response.candidates[0].content.parts:
            raise ValueError("Gemini returned empty response (safety filter or quota?)")
        for part in response.candidates[0].content.parts:
            if part.text:
                text = part.text.strip()
                break

        # Reddit comments can be longer — cap at 2000 chars
        if len(text) > 2000:
            text = text[:1997] + "..."

        return text

    async def generate_post(self, subreddit: str, content_type: str = "guide_post") -> tuple[str, str]:
        """Generate a Reddit post (title + body). Returns (title, body)."""
        client = _get_gemini_client()

        topic_key = random.choice(list(REDDIT_TOPICS.keys()))
        topic_desc = REDDIT_TOPICS[topic_key]

        ct = CONTENT_TYPES.get(content_type, CONTENT_TYPES["guide_post"])
        features = ", ".join([MCRO_FACTS["chrome_extension"], MCRO_FACTS["dashboard"]])
        prompt = ct["prompt"].format(
            topic=topic_desc, subreddit=subreddit, title="", body="",
            features=features,
        )

        guidelines = ""
        if self.db:
            try:
                guideline = await self.db.get_active_guideline("reddit")
                if guideline:
                    guidelines = guideline.guidelines_text
            except Exception:
                pass

        full_prompt = REDDIT_PERSONA
        if guidelines:
            full_prompt += f"\n\n{guidelines}"
        full_prompt += (
            f"\n\n{prompt}\n\n"
            f"Format your response as:\n"
            f"TITLE: [post title here]\n"
            f"---\n"
            f"[post body here]"
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=full_prompt,
        )

        text = ""
        if not response.candidates or not response.candidates[0].content.parts:
            raise ValueError("Gemini returned empty response (safety filter or quota?)")
        for part in response.candidates[0].content.parts:
            if part.text:
                text = part.text.strip()
                break

        # Parse title and body
        if "TITLE:" in text and "---" in text:
            parts = text.split("---", 1)
            title = parts[0].replace("TITLE:", "").strip()
            body = parts[1].strip()
        else:
            lines = text.split("\n", 1)
            title = lines[0].strip()
            body = lines[1].strip() if len(lines) > 1 else ""

        # Cap title at 300 chars (Reddit limit)
        if len(title) > 300:
            title = title[:297] + "..."

        logger.info("Reddit content: type=%s, subreddit=r/%s, topic=%s", content_type, subreddit, topic_key)
        return title, body

    def select_subreddit_for_comment(self) -> str:
        """Pick a subreddit to comment in (weighted toward high-value targets)."""
        # Prioritize TikTok Shop related subs
        weighted = (
            ["tiktokshop"] * 4 +
            ["ecommerce"] * 2 +
            ["dropshipping"] * 2 +
            ["smallbusiness"] * 1 +
            ["Entrepreneur"] * 1 +
            ["socialmediamarketing"] * 1 +
            ["tiktok"] * 1
        )
        return random.choice(weighted)

    def select_subreddit_for_post(self, karma: int) -> tuple[str, str] | None:
        """Pick a subreddit and content type for posting based on karma phase.
        Returns (subreddit, content_type) or None if posting not allowed yet."""
        if karma < 50:
            return None  # Phase 1: comment only

        eligible = []
        for sub, config in SUBREDDIT_CONFIG.items():
            if karma >= config["min_karma_to_post"] and config["post_types"]:
                for pt in config["post_types"]:
                    eligible.append((sub, pt))

        if not eligible:
            return None

        return random.choice(eligible)

    def is_post_relevant(self, post: dict, subreddit: str) -> bool:
        """Check if a post is worth commenting on based on keywords. Skips political content."""
        from strategies.targeting_strategy import is_political

        text = f"{post.get('title', '')} {post.get('body', '')}".lower()

        # Never engage with political content
        if is_political(text):
            return False

        config = SUBREDDIT_CONFIG.get(subreddit, {})
        keywords = config.get("keywords", [])
        return any(kw.lower() in text for kw in keywords)
