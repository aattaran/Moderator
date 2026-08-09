"""Seed the database with initial style guidelines based on known high-performing tweet patterns.

This runs once on first startup to give the bot intelligent defaults instead of
waiting 5+ days to learn from scratch. The guidelines evolve from here via reflection.
"""

import json
import logging

from storage.database import Database
from storage.models import StyleGuideline

logger = logging.getLogger(__name__)

# Based on analysis of high-performing tweets across tech/startup/AI accounts
SEED_GUIDELINES = StyleGuideline(
    version=0,
    guidelines_text=(
        "Follow these style guidelines for Ali's build-in-public account:\n"
        "- Always reference a specific project (MCRO, Jarvis, video pipeline, Fleet Commander, Moderator) — never tweet generic advice.\n"
        "- Share real numbers: API costs, token counts, response times, user counts, lines of code, hours spent.\n"
        "- Show the messy reality of building — bugs, wrong decisions, pivots. Not just wins.\n"
        "- Keep sentences punchy. One idea per sentence. Write like you're texting a founder friend, not writing a blog.\n"
        "- When sharing a lesson, name the specific tool or decision that taught it.\n"
        "- Build-update tweets should feel like a changelog entry written by a human: 'Shipped X. It broke Y. Fixed by Z.'\n"
        "- End with something that invites builders to share their experience, not a generic 'What do you think?'\n"
        "- Never sound like a LinkedIn influencer. No 'Excited to announce' or 'Here are 5 lessons I learned.'"
    ),
    analysis_summary=(
        "Seed guidelines for Ali Attaran's build-in-public account. Voice: direct, technical, "
        "practitioner-first. Content should reference specific projects (MCRO, Jarvis, video pipeline, "
        "Fleet Commander, Moderator) with real numbers and concrete details. "
        "The account grows by showing the real process of shipping AI products, not by generic thought leadership."
    ),
    top_patterns=[
        "Naming the specific project and what changed",
        "Including real numbers (costs, metrics, timelines)",
        "Sharing failures and what was learned",
        "Technical details accessible to non-experts",
        "Build-update format: shipped X, broke Y, fixed by Z",
        "First-person, present-tense energy",
    ],
    anti_patterns=[
        "Generic AI takes without grounding in a project",
        "LinkedIn-style 'Excited to announce' language",
        "Advice tweets that could come from anyone",
        "Tweets without any concrete detail or number",
        "Thought-leader pontificating without building",
        "Using hashtags or excessive emojis",
        "Corporate voice or press release tone",
        "Hedging with 'I think maybe' or 'It seems like'",
    ],
    posts_analyzed=0,
    avg_engagement_score=0.0,
)


ELEMNT_SEED_GUIDELINES = StyleGuideline(
    version=0,
    platform="elemnt",
    guidelines_text=(
        "Follow these style guidelines for ELEMNT supplement brand content:\n"
        "- Always reference a specific ingredient with its mechanism (e.g., 'GlucoVantage® delivers 5x absorption vs standard berberine').\n"
        "- Use FDA-compliant language: 'supports', 'may help', 'designed to' — NEVER 'cures', 'treats', 'prevents'.\n"
        "- Lead with the health benefit, not the product name. People care about outcomes, not brands.\n"
        "- Include one scientific detail per post — a dosage, absorption rate, or study reference.\n"
        "- Mix content: 60% educational health tips, 30% product-focused, 10% community questions.\n"
        "- End with a question or call for community experience ('Have you noticed a difference in your energy levels?').\n"
        "- Sound like a knowledgeable friend, not an advertisement. No hype, no urgency tactics.\n"
        "- Reference trust signals naturally: Made in USA, GMP Practice, No Fillers, 3rd Party Tested."
    ),
    analysis_summary=(
        "Seed guidelines for ELEMNT supplement brand. Voice: scientific but accessible, "
        "educational first, product second. FDA-compliant language required. "
        "Content should build community trust through genuine health education, "
        "not hard selling. Reference specific ingredients and mechanisms for credibility."
    ),
    top_patterns=[
        "Specific ingredient + mechanism (GlucoVantage 5x absorption)",
        "Educational content that teaches before it sells",
        "Community questions that invite personal experience sharing",
        "Trust signals woven naturally into content",
        "Comparison format: standard vs advanced ingredient",
        "Scientific details accessible to non-experts",
    ],
    anti_patterns=[
        "Direct medical claims (cures, treats, prevents)",
        "Hard selling or urgency tactics (limited time, act now)",
        "Generic health advice without ingredient specificity",
        "Ignoring FDA compliance language requirements",
        "Sounding like a corporate press release",
        "Posts without any scientific backing or detail",
        "Using first person singular ('I') — brand should use 'we' or third person",
        "Excessive emojis or hashtag spam",
    ],
    posts_analyzed=0,
    avg_engagement_score=0.0,
)


REDDIT_SEED_GUIDELINES = StyleGuideline(
    version=0,
    platform="reddit",
    guidelines_text=(
        "Follow these style guidelines for Ali's Reddit account:\n"
        "- Be the most helpful person in the thread. Answer completely, not partially.\n"
        "- Share specific numbers, tools, and processes from real TikTok Shop experience.\n"
        "- Write 2-5 paragraph comments. Reddit rewards depth, not brevity.\n"
        "- Never start comments with 'Great question!' or similar filler.\n"
        "- When someone asks for tool recommendations, list 3-4 options with honest pros/cons. "
        "Only include mcro.ai if genuinely relevant and only after 10+ non-promotional comments.\n"
        "- Match the subreddit's tone: r/SideProject is casual and supportive, "
        "r/ecommerce is practical and data-driven, r/tiktokshop is seller-focused.\n"
        "- Never link to mcro.ai in comments unless the commenter specifically asks for tools.\n"
        "- For posts, provide standalone value. The post should be worth reading even if the "
        "reader never visits mcro.ai."
    ),
    analysis_summary=(
        "Seed guidelines for Ali's Reddit account. Primary purpose: build karma through "
        "genuine helpfulness in TikTok Shop and e-commerce subreddits. Secondary purpose: "
        "soft promotion of mcro.ai only when organically relevant. Voice: helpful expert, "
        "not salesman. Reddit culture demands authenticity."
    ),
    top_patterns=[
        "Detailed, multi-paragraph answers to specific questions",
        "Personal experience with concrete numbers and examples",
        "Recommending multiple tools (not just your own)",
        "Sharing failures and what was learned from them",
        "Adding value beyond what was specifically asked",
    ],
    anti_patterns=[
        "Dropping links without context",
        "Starting every answer with a compliment",
        "Copy-paste responses across subreddits",
        "Mentioning mcro.ai in every comment",
        "Short, low-effort comments",
        "Promotional language ('Check out', 'You should try', 'Our tool')",
        "Posting the same content to multiple subreddits",
    ],
    posts_analyzed=0,
    avg_engagement_score=0.0,
)


async def seed_initial_guidelines(db: Database):
    """Insert seed guidelines for all platforms if none exist yet."""
    # X platform (Ali builder persona)
    existing_x = await db.get_active_guideline("x")
    if not existing_x:
        await db.insert_style_guideline(SEED_GUIDELINES)
        logger.info("Seeded X style guidelines (v0)")

    # ELEMNT platform (supplement brand)
    existing_elemnt = await db.get_active_guideline("elemnt")
    if not existing_elemnt:
        await db.insert_style_guideline(ELEMNT_SEED_GUIDELINES)
        logger.info("Seeded ELEMNT style guidelines (v0)")

    # Reddit platform (Ali on Reddit — karma building + MCRO promotion)
    existing_reddit = await db.get_active_guideline("reddit")
    if not existing_reddit:
        await db.insert_style_guideline(REDDIT_SEED_GUIDELINES)
        logger.info("Seeded Reddit style guidelines (v0)")
