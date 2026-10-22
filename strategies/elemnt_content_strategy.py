"""ELEMNT supplement brand content strategy for Facebook, Instagram, and TikTok."""

import logging
import random

from strategies.weight_manager import WeightManager

logger = logging.getLogger(__name__)

ELEMNT_PERSONA = (
    "You are the social media voice for ELEMNT, a premium supplement brand "
    "focused on advanced metabolic and cellular nutrition. Products:\n"
    "- Dihydroberberine 200mg (GlucoVantage® — 5x absorption vs standard berberine, "
    "with Ceylon Cinnamon, Curcumin, Alpha-Lipoic Acid, Lion's Mane)\n"
    "- Metabolic Biome / Akkermansia (3-in-1 synbiotic — prebiotic + probiotic + postbiotic, "
    "stimulates GLP-1, reinforces gut lining, 8 Billion CFU)\n"
    "- NMNH Rich+ Blend (500mg NMNH, 150mg Fisetin, 10mg Spermidine, 100mg Trans-Resveratrol, "
    "50mg CoQ10 Phytosome — higher NAD+ boost than NMN)\n"
    "- Molecular H2 (1600 PPB dissolved hydrogen tablets, MAX ORP -800mV, "
    "rapid dissolving for antioxidant support and athletic recovery)\n\n"
    "Voice: Scientific but accessible. Cite specific ingredients and mechanisms. "
    "Never make medical claims — use 'supports', 'may help', 'designed to'. "
    "Tone is premium, knowledgeable, and trustworthy — not salesy or pushy.\n"
    "Trust signals: Made in USA, GMP Practice, No Fillers, 3rd Party Tested.\n\n"
    "IMPORTANT: You are NOT a person. You are a brand account. Never use first person "
    "singular ('I'). Use 'we' for brand references or write in third person."
)

ELEMNT_STYLE_PROMPTS = {
    "health_tip": (
        "Share a practical, actionable health tip related to {topic}. "
        "Back it up with one specific mechanism or ingredient. "
        "Keep it under {max_chars} characters. No hashtags unless for Instagram."
    ),
    "science_explainer": (
        "Explain a scientific concept about {topic} in simple terms that anyone can understand. "
        "Use an analogy if helpful. Reference a specific ingredient or mechanism from ELEMNT products "
        "if relevant, but don't make it a sales pitch. Under {max_chars} characters."
    ),
    "product_spotlight": (
        "Highlight one specific benefit of an ELEMNT product related to {topic}. "
        "Lead with the benefit, not the product name. Include one scientific detail "
        "(like '5x absorption' or 'stimulates GLP-1'). Under {max_chars} characters."
    ),
    "myth_buster": (
        "Debunk a common misconception about {topic}. Start with the myth, "
        "then explain the reality with scientific backing. Be authoritative but not condescending. "
        "Under {max_chars} characters."
    ),
    "did_you_know": (
        "Share a surprising, lesser-known fact about {topic}. "
        "Make it specific enough to be credible ('Studies show...' or 'Research from...'). "
        "Under {max_chars} characters."
    ),
    "comparison": (
        "Compare two approaches to {topic} — a common/standard method vs an advanced alternative. "
        "Show why the advanced approach is better with one specific data point. "
        "Under {max_chars} characters."
    ),
    "community_question": (
        "Ask the community a genuine, engaging question about {topic}. "
        "Make it personal enough that people want to share their experience. "
        "Under {max_chars} characters."
    ),
}

ELEMNT_TOPIC_DESCRIPTIONS = {
    "blood_sugar": (
        "blood sugar management, insulin sensitivity, metabolic health, "
        "berberine vs dihydroberberine, GlucoVantage® bioavailability, "
        "post-meal glucose spikes, A1C levels, metabolic syndrome"
    ),
    "gut_health": (
        "gut microbiome, Akkermansia muciniphila, GLP-1 stimulation, "
        "prebiotics/probiotics/postbiotics, gut barrier integrity, "
        "leaky gut, butyrate production, synbiotics"
    ),
    "longevity": (
        "NAD+ levels, cellular energy, anti-aging at the cellular level, "
        "NMNH vs NMN comparison, fisetin as a senolytic, spermidine for autophagy, "
        "trans-resveratrol, CoQ10, mitochondrial function"
    ),
    "recovery": (
        "molecular hydrogen (H2), antioxidant defense, athletic recovery, "
        "oxidative stress reduction, ORP (oxidation-reduction potential), "
        "inflammation management, post-workout recovery"
    ),
    "science": (
        "bioavailability and absorption science, phytosome delivery technology, "
        "clinical studies on supplement ingredients, how the body processes nutrients, "
        "patented ingredient advantages (GlucoVantage®)"
    ),
    "lifestyle": (
        "daily wellness routines, supplement stacking protocols, "
        "morning health habits, biohacking basics for beginners, "
        "optimizing energy and focus through nutrition"
    ),
}

PRODUCT_FACTS = {
    "dbh": [
        "GlucoVantage® Dihydroberberine delivers 5x higher absorption than standard berberine",
        "Unlike regular berberine, Dihydroberberine causes no GI distress — it bypasses digestive issues entirely",
        "Each capsule: 200mg Dihydroberberine + 1600mg Ceylon Cinnamon + 500mg Curcumin + 100mg Alpha-Lipoic Acid + 100mg Lion's Mane",
        "GlucoVantage® is clinically shown to have 5x better bioavailability than standard berberine",
    ],
    "ark": [
        "Metabolic Biome is a complete 3-in-1 synbiotic: Prebiotic + Probiotic + Postbiotic in one capsule",
        "Contains Akkermansia muciniphila — stimulates GLP-1 production and reinforces gut lining tight junctions",
        "8 Billion CFU with butyrate-producing postbiotics for total biome support",
        "The tri-phase formula feeds beneficial bacteria (prebiotic), introduces them (probiotic), and amplifies their output (postbiotic)",
    ],
    "nmnh": [
        "NMNH is a more potent NAD+ precursor than NMN — higher cellular absorption via phytosome delivery",
        "The Rich+ Blend: 500mg NMNH + 150mg Fisetin + 10mg Spermidine + 100mg Trans-Resveratrol + 50mg CoQ10 Phytosome",
        "Fisetin acts as a senolytic — helps clear damaged cells so healthy cells can thrive",
        "Spermidine supports autophagy — your body's cellular recycling program",
    ],
    "h2": [
        "Molecular H₂ tablets dissolve rapidly to deliver 1600 PPB dissolved hydrogen — one of the highest concentrations available",
        "MAX ORP of -800mV — a powerful antioxidant defense against oxidative stress",
        "Molecular hydrogen is the smallest molecule — it penetrates cells that larger antioxidants cannot reach",
        "Designed for athletic recovery: supports cellular energy and reduces exercise-induced oxidative stress",
    ],
}

IG_HASHTAGS = {
    "blood_sugar": "#metabolichealth #bloodsugar #berberine #insulinsensitivity #glucovantage #dihydroberberine #healthymetabolism",
    "gut_health": "#guthealth #microbiome #akkermansia #probiotics #gutbarrier #glp1 #synbiotic #digestivehealth",
    "longevity": "#longevity #nad #cellularhealth #antiaging #nmnh #fisetin #spermidine #biohacking",
    "recovery": "#molecularhydrogen #recovery #antioxidant #athleticrecovery #h2 #oxidativestress #fitness",
    "science": "#supplementscience #bioavailability #phytosome #clinicalresearch #evidencebased",
    "lifestyle": "#wellnessjourney #biohacking #morningroutine #supplementstack #healthyhabits",
}

TT_HASHTAGS = {
    "blood_sugar": "#berberine #bloodsugar #metabolichealth #glucovantage #healthtok #fyp",
    "gut_health": "#guthealth #akkermansia #probiotics #glp1 #microbiome #healthtok #fyp",
    "longevity": "#nad #longevity #antiaging #nmnh #biohacking #cellularhealth #fyp",
    "recovery": "#molecularhydrogen #recovery #fitness #antioxidant #athleticrecovery #fyp",
    "science": "#supplementscience #healthtok #bioavailability #fyp",
    "lifestyle": "#biohacking #morningroutine #healthtok #supplementstack #fyp",
}

YT_HASHTAGS = {
    "blood_sugar": "#Shorts #berberine #bloodsugar #metabolichealth #supplements #healthtips",
    "gut_health": "#Shorts #guthealth #akkermansia #probiotics #microbiome #supplements",
    "longevity": "#Shorts #longevity #nad #antiaging #supplements #biohacking",
    "recovery": "#Shorts #molecularhydrogen #recovery #fitness #supplements",
    "science": "#Shorts #supplementscience #health #nutrition",
    "lifestyle": "#Shorts #biohacking #wellness #healthyhabits #supplements",
}

PLATFORM_MAX_CHARS = {
    "youtube": 5000,
    "facebook": 2000,
    "instagram": 2200,
    "tiktok": 300,
    "x": 280,
}


def _get_gemini_client():
    from google import genai
    from config import get_settings
    return genai.Client(api_key=get_settings().GEMINI_API_KEY)


class ElemntContentStrategy:
    """Content strategy for ELEMNT supplement brand on health-focused platforms."""

    def __init__(self, weight_manager: WeightManager, db=None):
        self.weight_manager = weight_manager
        self.db = db

    async def _get_style_preamble(self) -> str:
        """Load the active ELEMNT guideline from the database."""
        if not self.db:
            return ""
        try:
            guideline = await self.db.get_active_guideline("elemnt")
            if guideline:
                return guideline.guidelines_text
        except Exception:
            pass
        return ""

    async def generate_post(self, platform: str = "facebook") -> tuple[str, str, str]:
        """Generate a health content post for the ELEMNT brand.

        Returns (content_text, style, topic).
        """
        style = random.choice(list(ELEMNT_STYLE_PROMPTS.keys()))
        topic = random.choice(list(ELEMNT_TOPIC_DESCRIPTIONS.keys()))

        max_chars = PLATFORM_MAX_CHARS.get(platform, 2000)
        topic_desc = ELEMNT_TOPIC_DESCRIPTIONS[topic]
        template = ELEMNT_STYLE_PROMPTS[style]
        prompt = template.replace("{topic}", topic_desc).replace("{max_chars}", str(max_chars))

        # Prepend persona + learned guidelines + random product fact
        guidelines = await self._get_style_preamble()
        full_prompt = ELEMNT_PERSONA
        if guidelines:
            full_prompt = f"{full_prompt}\n\n{guidelines}"

        # 40% chance to include a specific product fact
        if random.random() < 0.4:
            product_key = random.choice(list(PRODUCT_FACTS.keys()))
            fact = random.choice(PRODUCT_FACTS[product_key])
            full_prompt = f"{full_prompt}\n\nIncorporate this specific fact naturally: {fact}"

        full_prompt = f"{full_prompt}\n\n{prompt}"

        client = _get_gemini_client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=full_prompt,
        )

        if not response.candidates or not response.candidates[0].content.parts:
            raise ValueError(f"Gemini returned empty response (safety filter or quota?)")

        text = ""
        for part in response.candidates[0].content.parts:
            if part.text:
                text = part.text.strip()
                break

        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]

        # Truncate body first, then append hashtags so final length stays within limit
        body_limit = max_chars - 100  # reserve room for hashtags
        if len(text) > body_limit:
            text = text[:body_limit - 3] + "..."

        # Add hashtags for Instagram/TikTok/YouTube
        if platform == "instagram" and topic in IG_HASHTAGS:
            text = f"{text}\n\n{IG_HASHTAGS[topic]}"
        elif platform == "tiktok" and topic in TT_HASHTAGS:
            text = f"{text} {TT_HASHTAGS[topic]}"
        elif platform == "youtube" and topic in YT_HASHTAGS:
            text = f"{text}\n\n{YT_HASHTAGS[topic]}"

        # Final hard cap after hashtags are appended
        if len(text) > max_chars:
            text = text[:max_chars - 3] + "..."

        logger.info("ELEMNT content (%s, %s, %d chars): %s", style, topic, len(text), text[:80])
        return text, style, topic
