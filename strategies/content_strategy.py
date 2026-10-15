"""Content strategy — decides what to post and generates prompts via Gemini."""

import logging

from strategies.weight_manager import WeightManager

logger = logging.getLogger(__name__)

# ── Persona ─────────────────────────────────────────────────
# Ali Attaran — builder, founder, AI engineer.
# Building in public across multiple projects.
# Voice: direct, technical but accessible, contrarian, no fluff.

PERSONA = (
    "You are tweeting as Ali Attaran (@AlyAttaran), a founder and AI engineer "
    "building multiple products in public. Your projects include:\n\n"
    "- MCRO (mcro.ai): TikTok Shop analytics & automation SaaS + Chrome extension. "
    "Features: AI-powered product title/description optimization (Gemini), dynamic repricing "
    "engine (Velocity Surge, Liquidation Protocol, Profit Maximizer, Night Owl strategies), "
    "promotions management, inventory optimizer, fulfillment tracking across CLT2/LGB8/AVP1/JFK8, "
    "direct video publishing via TikTok Creator API, affiliate management. "
    "Plans: Spark (free) → Velocity ($39/mo) → Hyperdrive ($79/mo). "
    "Tech: Next.js 14, React 19, MongoDB, Redis, Stripe, Chrome Extension.\n\n"
    "- Jarvis: multi-channel AI gateway with 80+ tools running 24/7 on GCP Cloud Run. "
    "Dual-brain: Claude Opus 4.6 (complex tasks) + Gemini 2.5 Flash (quick queries, auto-routed). "
    "Channels: Slack, Telegram, Email, SMS. Features: 4 concurrent Claude Code agents, "
    "adversarial audit panel (Breaker/Hacker/StressTester), AI news agent with self-improvement "
    "flywheel, pain finder scanning 10+ platforms, skills system with hot-loading, "
    "home machine bridge via Cloudflare Tunnel, remote Claude Code sessions via browser URL, "
    "MCP server integration. MongoDB persistence, 52-pattern command blocklist.\n\n"
    "- Video Ad Pipeline: 8-stage automated cinematic video ads for e-commerce. "
    "Stages: product loading → script generation (Director's Bible with 8 ad archetypes) → "
    "hero renders → keyframe generation → dual-model video gen (Kling 3.0 + Veo 3.1 simultaneously) "
    "→ voiceover (Gemini TTS) → music (KIE Suno) → FFmpeg stitching. "
    "UGC mode: 5 styles × 6 hooks × 5 CTAs = 24,000+ angle variations per actor. "
    "Lip sync: Sync Lipsync 2.0 Pro ($5/min, perfect sync).\n\n"
    "- Fleet Commander: Claude Code plugin for dispatching coordinated AI agent teams. "
    "6 roles (Planner, Coder, Debugger, Reviewer, Researcher, Scout) with model+effort codes "
    "(h1=Haiku low, o3=Opus high). 3-phase execution: discovery → implementation → verification. "
    "Custom roles at runtime. Post-execution calibration reports.\n\n"
    "- Moderator: autonomous multi-platform social media agent (X, Instagram, TikTok, YouTube, Reddit). "
    "Adaptive learning via engagement-weighted content selection. Per-platform content reflection "
    "every 3 days. ELEMNT supplement brand + Ali personal brand.\n\n"
    "- Amazon PPC optimization tools\n"
    "- CoverMax: insurance tech\n\n"
    "Your voice: direct, no-BS, technical but accessible. You share real numbers, "
    "real failures, real wins. You think AI agents are the next platform shift. "
    "You build fast, ship daily, and learn from what breaks. "
    "Never use corporate speak, never hedge with 'I think maybe'. "
    "You're a practitioner sharing from the trenches, not a thought leader pontificating.\n\n"
    "IMPORTANT: Write as Ali in first person. Reference your actual projects when relevant. "
    "Share specific technical decisions, numbers, and lessons — not generic advice.\n\n"
    "GROWTH STRATEGY — follow this posting cadence:\n"
    "- Every 3rd post should be a THREAD (3-5 tweets) about building one of your projects. "
    "Threads get 2-5x more engagement than single tweets.\n"
    "- At least 1 post per day should mention MCRO (mcro.ai) — your TikTok Shop analytics platform. "
    "Frame it as build-in-public updates: what you shipped, what broke, what you learned.\n"
    "- When posting about MCRO, include mcro.ai URL naturally (never forced).\n"
    "- Weave in the freebie campaign: '12 free Claude Code skills at github.com/aattaran/freebies' "
    "— mention it in thread endings or as a PS, not as the main content.\n"
    "- Build narrative arcs: a problem on Monday → progress on Wednesday → result on Friday. "
    "Don't post disconnected random thoughts.\n"
    "- Engage with replies to your own threads to boost algorithm visibility."
)

STYLE_PROMPTS = {
    "build_update": (
        "Share a specific build update or progress report on one of your projects "
        "related to {topic}. Include a concrete detail — a metric, a decision, "
        "a problem you solved, or something you shipped today. "
        "Keep it under 280 characters. No hashtags."
    ),
    "lesson_learned": (
        "Share a specific lesson you learned while building your projects, "
        "related to {topic}. Something that surprised you or that you'd do differently. "
        "Be concrete — name the tool, the number, the mistake. "
        "Keep it under 280 characters. No hashtags."
    ),
    "hot_take": (
        "Write a provocative but grounded hot take about {topic}, "
        "informed by your experience building AI products and automation. "
        "Contrarian but backed by something you've actually seen. "
        "Keep it to 1-2 sentences, under 280 characters. No hashtags."
    ),
    "thread": (
        "Write the first tweet of a 4-5 tweet thread about {topic}. "
        "Structure: Tweet 1 = hook that makes people NEED to read the rest "
        "(a bold claim, surprising number, or contrarian take). "
        "End tweet 1 with 🧵 emoji. Under 280 characters. "
        "Make the hook specific to YOUR project — not generic advice."
    ),
    "question": (
        "Ask a genuine question about {topic} that you're actually wrestling with "
        "in your projects. Make it specific enough that practitioners can give useful answers. "
        "Keep it under 280 characters. No hashtags."
    ),
    "insight": (
        "Share a unique insight about {topic} from your experience shipping AI products. "
        "Something most people haven't considered because they haven't built it themselves. "
        "Keep it under 280 characters. No hashtags."
    ),
    "meme_caption": (
        "Write a witty, relatable observation about {topic} from a builder's perspective. "
        "The kind of thing that makes other developers and founders nod and laugh. "
        "Keep it under 280 characters. No hashtags."
    ),
}

TOPIC_DESCRIPTIONS = {
    "ai_agents": (
        "AI agents, multi-agent systems, autonomous workflows. From your experience: "
        "Jarvis has 80+ tools with dual-brain routing (Claude Opus for complex, Gemini Flash "
        "for simple), adversarial audit panel (3 personas catch bugs after every task), "
        "4 concurrent Claude Code agents, skills system. Fleet Commander dispatches "
        "coordinated agent teams with 6 roles and effort levels. Moderator runs 5 platforms "
        "autonomously with adaptive learning."
    ),
    "build_in_public": (
        "building in public, shipping fast, sharing progress and failures transparently, "
        "indie hacking, solo founder life. You're building MCRO (mcro.ai — TikTok Shop SaaS), "
        "Jarvis (80+ tool AI gateway on GCP), Video Ad Pipeline (8-stage dual-model), "
        "Fleet Commander (Claude Code plugin), and Moderator simultaneously."
    ),
    "ai_video": (
        "AI video generation, automated video ad pipelines. Your Video Ad Pipeline: "
        "8-stage system from product JSON to final cinematic video. Director's Bible with "
        "8 ad archetypes. Dual-model generation (Kling 3.0 + Veo 3.1 simultaneously). "
        "UGC mode: 5 styles × 6 hooks × 5 CTAs = 24,000+ angle variations. "
        "Sync Lipsync 2.0 Pro for perfect lip sync. Gemini TTS voiceover, KIE Suno music."
    ),
    "mcro": (
        "MCRO (mcro.ai) — TikTok Shop analytics, automation, and Chrome extension. "
        "Dynamic repricing engine with 4 strategies (Velocity Surge, Liquidation Protocol, "
        "Profit Maximizer, Night Owl). AI product optimization via Gemini. "
        "Inventory optimizer, promotions management, fulfillment tracking, "
        "direct video publishing via TikTok Creator API. Chrome extension for quick "
        "promotion setup. Plans from free to $79/mo."
    ),
    "ecommerce_tools": (
        "TikTok Shop, e-commerce automation, Amazon PPC, product analytics. "
        "From your MCRO project: dynamic repricing, AI listing optimization, "
        "promotion scheduling, affiliate management, fulfillment tracking. "
        "Chrome extension overlays analytics on TikTok Shop pages."
    ),
    "dev_tools": (
        "developer tools, AI-assisted coding, Claude Code plugins, MCP servers. "
        "Fleet Commander: dispatch coordinated agent teams with custom roles, model+effort "
        "codes (h1=Haiku low, o3=Opus high), 3-phase execution. Jarvis: MCP server "
        "integration, skills system with hot-loading, remote Claude Code sessions via "
        "browser URL, GitHub Actions integration."
    ),
    "tech_stack": (
        "technical architecture decisions, infrastructure, deployment. "
        "Your stack: GCP Cloud Run (Jarvis, always-on, 1 instance), DigitalOcean "
        "(Moderator droplet, MCRO backend), Vercel (MCRO frontend), Next.js 14, "
        "React 19, MongoDB, Redis, Stripe, Docker, Cloudflare Tunnel for home bridge. "
        "Real tradeoffs you've made choosing between providers and frameworks."
    ),
}


def _get_gemini_client():
    """Get a Gemini client."""
    from google import genai
    from config import get_settings
    settings = get_settings()
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _load_active_campaign() -> dict | None:
    """Load the active campaign from data/campaigns.json. Returns None if no active campaign."""
    import json
    from pathlib import Path
    from datetime import date

    path = Path("data/campaigns.json")
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        active_id = data.get("active_campaign")
        if not active_id:
            return None

        campaign = data.get("campaigns", {}).get(active_id)
        if not campaign:
            return None

        # Check date range if set
        today = date.today().isoformat()
        start = campaign.get("start_date")
        end = campaign.get("end_date")
        if start and today < start:
            return None
        if end and today > end:
            return None

        return campaign
    except Exception:
        return None


class ContentStrategy:
    """Selects content style and topic, generates content via Gemini."""

    def __init__(self, weight_manager: WeightManager, db=None):
        self.weight_manager = weight_manager
        self.db = db
        self._cached_guidelines: str | None = None

    async def _get_style_preamble(self) -> str:
        """Load the active X style guideline from the database."""
        if not self.db:
            return ""
        try:
            guideline = await self.db.get_active_guideline("x")
            if guideline:
                return guideline.guidelines_text
        except Exception:
            pass
        return ""

    async def generate_post_prompt(self, trending_topics: list[str] | None = None) -> tuple[str, str, str]:
        """Generate a content creation prompt, influenced by active campaign + trends."""
        import random as _random

        campaign = _load_active_campaign()

        # If active campaign, 70% of posts focus on campaign topic
        if campaign and _random.random() < 0.7:
            style = await self.weight_manager.select("content_style")
            topic = campaign.get("product", await self.weight_manager.select("topic"))

            # Build campaign-aware topic description
            features = campaign.get("focus_features", [])
            talking_points = campaign.get("talking_points", [])
            links = campaign.get("links", {})
            feature = _random.choice(features) if features else ""
            point = _random.choice(talking_points) if talking_points else ""

            topic_desc = TOPIC_DESCRIPTIONS.get(topic, topic)
            topic_desc = (
                f"{topic_desc}\n\n"
                f"ACTIVE CAMPAIGN: {campaign.get('name', '')}\n"
                f"Focus on this feature: {feature}\n"
                f"Talking point: {point}\n"
                f"Links: {', '.join(f'{k}: {v}' for k, v in links.items())}\n"
                f"CTA: {campaign.get('cta', '')}\n"
                f"Tone: {campaign.get('tone', 'build-in-public')}"
            )
        else:
            style = await self.weight_manager.select("content_style")
            topic = await self.weight_manager.select("topic")
            topic_desc = TOPIC_DESCRIPTIONS.get(topic, topic)

        # Trending topics
        if trending_topics and len(trending_topics) > 0:
            if _random.random() < 0.3:
                trend = _random.choice(trending_topics[:5])
                topic_desc = f"{topic_desc}, specifically relating to the current trend: '{trend}'"
                logger.info("Incorporating trend: %s", trend)

        template = STYLE_PROMPTS.get(style, STYLE_PROMPTS["insight"])
        prompt = template.replace("{topic}", topic_desc)

        logger.info("Generated post prompt: style=%s, topic=%s, campaign=%s",
                     style, topic, campaign.get("name", "none") if campaign else "none")
        return prompt, style, topic

    async def generate_content_text(self, style: str, topic: str) -> str:
        """Generate tweet text via Gemini, with learned style guidelines."""
        client = _get_gemini_client()

        template = STYLE_PROMPTS.get(style, STYLE_PROMPTS["insight"])
        topic_desc = TOPIC_DESCRIPTIONS.get(topic, topic)
        prompt = template.replace("{topic}", topic_desc)

        # Prepend persona + learned guidelines
        guidelines = await self._get_style_preamble()
        full_prompt = PERSONA
        if guidelines:
            full_prompt = f"{full_prompt}\n\n{guidelines}"
        prompt = f"{full_prompt}\n\n{prompt}"

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

        # Remove quotes if Gemini wraps the response
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]

        if len(text) > 280:
            text = text[:277] + "..."

        logger.info("Generated content (%d chars): %s", len(text), text[:100])
        return text

    async def generate_thread(self, topic: str, num_tweets: int = 5) -> list[str]:
        """Generate a multi-tweet thread via Gemini, with learned style guidelines."""
        import random as _random
        client = _get_gemini_client()

        topic_desc = TOPIC_DESCRIPTIONS.get(topic, topic)

        # Use campaign thread topic if available
        campaign = _load_active_campaign()
        campaign_context = ""
        if campaign:
            thread_topics = campaign.get("thread_topics", [])
            if thread_topics:
                specific_topic = _random.choice(thread_topics)
                links = campaign.get("links", {})
                campaign_context = (
                    f"\n\nCAMPAIGN THREAD TOPIC: {specific_topic}\n"
                    f"Links to include naturally: {', '.join(f'{k}: {v}' for k, v in links.items())}\n"
                    f"CTA: {campaign.get('cta', '')}\n"
                    f"Focus features: {', '.join(campaign.get('focus_features', [])[:3])}\n"
                    f"Tone: {campaign.get('tone', 'build-in-public')}"
                )

        # Prepend persona + learned guidelines
        guidelines = await self._get_style_preamble()
        preamble = PERSONA
        if guidelines:
            preamble = f"{preamble}\n\n{guidelines}"

        # Build a thread that tells a story, not random tips
        prompt = (
            f"{preamble}\n\n"
            f"Write a {num_tweets}-tweet thread about {topic_desc}.{campaign_context}\n\n"
            f"THREAD STRUCTURE (tell a story, not random tips):\n"
            f"- Tweet 1: HOOK — a bold claim, surprising number, or contrarian take that makes people "
            f"stop scrolling. End with 🧵. Reference YOUR specific project.\n"
            f"- Tweet 2: CONTEXT — the problem you faced or the situation that led to this insight.\n"
            f"- Tweet 3-{num_tweets-1}: THE MEAT — what you did, what happened, specific technical "
            f"details, real numbers, real decisions. Each tweet builds on the previous one.\n"
            f"- Tweet {num_tweets}: TAKEAWAY + CTA — what you learned, what's next. "
        )

        # If topic is MCRO, include mcro.ai link in the thread
        if topic == "mcro":
            prompt += (
                f"Include mcro.ai naturally in the final tweet. "
                f"Example: 'Building this at mcro.ai — if you sell on TikTok Shop, check it out.'\n"
            )

        # Sometimes add freebie mention
        import random
        if random.random() < 0.3:
            prompt += (
                f"PS: Add a final tweet mentioning: 'I also packaged 12 free Claude Code skills "
                f"at github.com/aattaran/freebies — grab them if you use Claude Code.'\n"
            )

        prompt += (
            f"\nRULES:\n"
            f"- Each tweet MUST be under 280 characters\n"
            f"- No hashtags\n"
            f"- The thread must tell ONE coherent story from hook to conclusion\n"
            f"- Reference specific projects, numbers, tools — not generic advice\n"
            f"- Each tweet should make the reader want to read the next one\n"
            f"- Format: output each tweet on its own line, separated by ---"
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

        tweets = [t.strip() for t in text.split("---") if t.strip()]
        tweets = [t[:280] for t in tweets]

        logger.info("Generated thread (%d tweets) on topic=%s", len(tweets), topic)
        return tweets
