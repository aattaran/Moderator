"""Generate UGC-style influencer images holding ELEMNT products via Gemini.

Uses image+text → image: passes a reference product photo + text prompt
so Gemini matches the actual bottle design, label, and colors.
"""

import logging
import random
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)

_IMAGE_MODEL = "gemini-2.5-flash-image"

# ── Product reference images ──────────────────────────────────

PRODUCT_REFS = {
    "dbh": {
        # Auto-discovers all clean reference images in this folder.
        # Drop new bottle angles or label macros in here — code picks them up.
        # Files starting with "Gemini_Generated_" or "IMG_" are excluded as
        # AI-generated/lifestyle composites that confuse Gemini.
        "images_dir": "data/product_images/DBH (product 1)/angles",
        "name": "ELEMNT Dihydroberberine",
        "topics": ["blood_sugar", "science"],
    },
    "ark": {
        "images_dir": "data/product_images/ARK (product 3)/Image Listing",
        "name": "ELEMNT Metabolic Biome (Akkermansia)",
        "topics": ["gut_health"],
    },
    "nmnh": {
        "images_dir": "data/product_images/NMNH (product 2)/Listing",
        "name": "ELEMNT NMNH",
        "topics": ["longevity"],
    },
    "h2": {
        "images_dir": "data/product_images/H2 tablet (product 4)/Listing images",
        "name": "ELEMNT Molecular H2",
        "topics": ["recovery"],
    },
    "custom": {
        # Drop product images in data/product_images/custom/ — auto-discovered.
        "images_dir": "data/product_images/custom",
        "name": "Custom Product",
        "topics": ["custom"],
    },
}

# ── Named influencer presets (consistent characters) ──────────

INFLUENCER_PRESETS = {
    "maya": (
        "Maya, late 20s Middle Eastern woman, olive skin, dark wavy hair past shoulders, "
        "minimal natural makeup, warm brown eyes, athletic build, wearing casual activewear"
    ),
    "jordan": (
        "Jordan, early 30s biracial man, light brown skin, short fade haircut, "
        "well-groomed beard, athletic build, bright genuine smile, wearing fitted t-shirt"
    ),
    "elena": (
        "Elena, mid-30s Eastern European woman, fair skin, straight blonde hair shoulder length, "
        "blue-green eyes, slim athletic build, natural minimal makeup, wearing athleisure"
    ),
    "kai": (
        "Kai, late 20s East Asian man, clear skin, styled black hair, clean-shaven, "
        "lean fit build, friendly expression, wearing modern casual clothes"
    ),
    "priya": (
        "Priya, early 30s South Asian woman, warm brown skin, long dark straight hair, "
        "dark eyes, natural dewy makeup, fit build, wearing comfortable workout clothes"
    ),
    "alex": (
        "Alex, mid-20s white man, lightly tanned skin, sandy brown medium-length hair, "
        "hazel eyes, casual scruff, surfer-fit build, wearing relaxed outdoor clothes"
    ),
}

# ── Platform-specific output formats ─────────────────────────

PLATFORM_FORMATS = {
    "instagram": {"width": 1080, "height": 1350, "ratio": "4:5", "label": "portrait"},
    "facebook": {"width": 1200, "height": 630, "ratio": "1.91:1", "label": "landscape"},
    "tiktok": {"width": 1080, "height": 1920, "ratio": "9:16", "label": "tall vertical"},
    "youtube": {"width": 1280, "height": 720, "ratio": "16:9", "label": "landscape"},
    "x": {"width": 1200, "height": 675, "ratio": "16:9", "label": "landscape"},
}

# ── Scene templates by category ──────────────────────────────

# ── Organic scenes: product naturally blended into real moments ─

TAKING_PRODUCT_SCENES = [
    "pouring product from the container into their palm, a glass of water on the counter beside them, morning kitchen light",
    "about to use the product, holding it in one hand with a glass of water in the other hand, bathroom mirror, morning routine",
    "opening the product cap, standing in a bright kitchen, casual relaxed expression",
    "mid-sip of water after using the product, the container sitting on a marble countertop beside a coffee mug",
]

PRODUCT_IN_CONTEXT_SCENES = [
    "showing the contents of their open gym bag — the product visible among a protein shaker, earbuds, towel, and keys. Shot from above, locker room bench",
    "bathroom shelf shelfie — the product on a shelf among skincare items, toothbrush holder, and plants. Clean minimal aesthetic, soft light",
    "kitchen counter morning scene — the product next to a coffee mug, a journal, and a bowl of fruit. Warm natural light, cozy routine feel",
    "work desk setup — the product beside a laptop, water bottle, and planner. Focused productive vibe, soft window light",
    "travel flat lay — the product among a passport, headphones, snacks, and sunglasses in an open carry-on bag. Bright overhead light",
    "morning routine setup on a clean countertop, the product open beside everyday wellness items. Organized, intentional feel",
    "packing the product into a gym bag alongside sneakers and a towel, getting ready to head out, entryway with natural light",
    "reaching for the product from a shelf, morning light on their face, just woke up energy",
]

LIFESTYLE_SCENES = [
    "in a modern kitchen with natural morning light, making a smoothie on a clean marble countertop, the product nearby",
    "on a cozy living room couch with soft throw blankets, morning sunlight through sheer curtains, product on the coffee table",
    "at a breakfast table with healthy food, fruit, and a glass of water, the product among the breakfast spread",
    "organized morning ritual on a marble countertop — the product front and center among other wellness items",
]

ACTIVE_SCENES = [
    "post-workout sweaty selfie at the gym, the product on the gym floor beside their water bottle and towel",
    "on a yoga mat in a bright studio, the product placed at the edge of the mat, peaceful zen vibe, soft natural light",
    "on a running trail catching their breath on a bench, the product in hand, athletic wear, dappled sunlight through trees",
    "at a rock climbing gym, taking a break, the product on a bench beside chalk bag, energized expression",
    "stretching in a park after a morning run, the product on the grass beside them, dewy golden morning light",
]

OUTDOOR_SCENES = [
    "at an outdoor cafe terrace, the product on the table next to an espresso, warm afternoon light, city vibes",
    "on a park bench during golden hour, product casually beside them, trees in soft bokeh background",
    "on a rooftop at sunset, the product on a ledge with city skyline behind, urban wellness aesthetic",
    "at a beach boardwalk, sitting on a railing, the product in a tote bag that's partially open, ocean breeze feel",
]

SOCIAL_SCENES = [
    "showing the product to camera, pointing at the label, educational influencer style, bright ring light",
    "unboxing moment — just opened a package, holding the product up with excited expression, cozy home background",
    "two friends at brunch, one showing the product to the other across the table, natural candid moment",
    "morning in bed, just waking up, the product on the nightstand next to an alarm clock and glass of water",
]

SELFIE_SCENES = [
    "taking a mirror selfie in a gym locker room, holding the product in one hand, phone in the other, gym clothes, slightly sweaty",
    "taking a selfie in a messy kitchen, holding the product up casually in one hand, morning hair, pajamas, coffee in background",
    "selfie in a backyard garden, holding the product in one hand, sun hat, casual outdoor clothes, plants and fence in background",
    "walking a dog on a sidewalk, taking a one-handed selfie while holding the product, leash in other hand, neighborhood street",
    "car selfie in the driver's seat, holding the product up, sunglasses pushed up on head, casual vibe, steering wheel visible",
    "bathroom mirror selfie, holding the product, messy counter with toothbrush and skincare items visible, morning routine",
    "selfie at a coffee shop, holding the product next to a latte, laptop bag on the chair, casual work-from-cafe vibe",
    "post-yoga selfie on the mat, slightly flushed, holding the product, studio or living room floor, hair tied up messy",
    "kitchen selfie while cooking, holding the product in one hand, cutting board and vegetables on counter behind",
    "outdoor hiking trail selfie, holding the product, backpack straps visible, trees and trail in background, slightly out of breath",
]

# ── Ingredient infographic scenes (text overlay with benefits) ─

INGREDIENT_INFOGRAPHIC_SCENES = {
    "dbh": (
        "Create a visually explosive, dynamic product infographic for ELEMNT Dihydroberberine. "
        "The bottle is the centerpiece, slightly angled with dramatic studio lighting — glowing rim light "
        "on one side, deep shadows on the other. Capsules are bursting out of the bottle mid-air, frozen in motion. "
        "Around the bottle, ingredient graphics EXPLODE outward like an energy burst: "
        "each ingredient has its own visual icon and bold text — "
        "a CINNAMON STICK shattering with particles + 'Ceylon Cinnamon — Insulin Support', "
        "a GOLDEN TURMERIC ROOT breaking apart with dust + 'Curcumin — Anti-Inflammatory', "
        "a GLOWING MOLECULAR STRUCTURE orbiting + 'GlucoVantage® — 5x Absorption', "
        "a LIGHTNING BOLT icon + 'Alpha-Lipoic Acid — Antioxidant Power', "
        "a MUSHROOM with bioluminescent glow + 'Lion\\'s Mane — Cognitive Clarity'. "
        "Background: deep dark navy with glowing teal particle trails, lens flares, light streaks. "
        "Dynamic diagonal composition, not centered. Speed lines and energy waves radiating from bottle. "
        "Think sci-fi meets premium supplement. Ultra-modern, scroll-stopping, magazine-ad quality. "
        "Bold chunky sans-serif typography. NO person in image."
    ),
    "ark": (
        "Create a visually explosive, dynamic product infographic for ELEMNT Metabolic Biome (Akkermansia). "
        "The bottle is the centerpiece with dramatic lighting — cool green glow emanating from within. "
        "Around the bottle, a MICROBIOME UNIVERSE visualization: "
        "glowing bacteria clusters, gut lining cross-section illustration, molecular bonds floating. "
        "Each ingredient bursts outward with its own visual element: "
        "a MICROSCOPE VIEW of bacteria + 'Akkermansia — Gut Lining Reinforcement', "
        "a GLOWING GLP-1 MOLECULE diagram + 'Stimulates GLP-1 Naturally', "
        "a SHIELD icon with gut wall illustration + '8 Billion CFU Live Cultures', "
        "THREE INTERLOCKING RINGS + '3-in-1: Prebiotic + Probiotic + Postbiotic', "
        "a CELLULAR MESH pattern + 'Butyrate Production — Gut Fuel'. "
        "Background: deep black with bioluminescent green particle clouds, floating molecular structures, "
        "organic flowing lines like intestinal villi. Dynamic asymmetric layout. "
        "Think National Geographic microscopy meets premium branding. Scroll-stopping. "
        "Bold modern typography with green accent glow. NO person in image."
    ),
    "nmnh": (
        "Create a visually explosive, dynamic product infographic for ELEMNT NMNH Rich+ Blend. "
        "The bottle is the centerpiece with purple-violet energy radiating outward like a supernova. "
        "Capsules floating around the bottle surrounded by glowing molecular visualizations. "
        "Each ingredient has its own dramatic visual: "
        "a DNA HELIX unwinding with glowing nodes + '500mg NMNH — Superior NAD+ Boost', "
        "a CELL being CLEARED by light waves + '150mg Fisetin — Senolytic Cell Cleaner', "
        "an AUTOPHAGY DIAGRAM with recycling arrows + '10mg Spermidine — Cellular Renewal', "
        "a GRAPE VINE with molecular overlay + '100mg Trans-Resveratrol — Longevity', "
        "a MITOCHONDRIA glowing with energy + '50mg CoQ10 Phytosome — Cellular Energy'. "
        "Background: deep space black with purple nebula clouds, floating DNA strands, "
        "glowing cellular structures, light speed streaks. Diagonal dynamic composition. "
        "Think interstellar science meets anti-aging tech. Ultra-premium, visually rich. "
        "Bold typography with violet/purple neon accent. NO person in image."
    ),
    "h2": (
        "Create a visually explosive, dynamic product infographic for ELEMNT Molecular H2. "
        "The bottle is the centerpiece with WATER SPLASH and hydrogen BUBBLES bursting outward dramatically. "
        "A tablet is mid-dissolve in a glass of water next to the bottle, fizzing with visible H2 molecules. "
        "Dynamic visual callouts burst from the splash: "
        "a WATER MOLECULE (H2O) diagram shattering into H2 + '1600 PPB Dissolved Hydrogen', "
        "a VOLTAGE METER visual + 'MAX ORP -800mV Antioxidant Power', "
        "a FIZZING TABLET cross-section + 'Rapid Dissolving Technology', "
        "a SHIELD deflecting FREE RADICALS + 'Antioxidant Defense System', "
        "a RUNNER SILHOUETTE with energy waves + 'Athletic Recovery Accelerator'. "
        "Background: deep ocean blue with water caustic light patterns, hydrogen bubble trails, "
        "crystalline water droplets frozen in mid-air, light refracting through water. "
        "Dynamic diagonal composition with splash energy. Think underwater photography meets sports science. "
        "Bold typography with electric blue accent glow. NO person in image."
    ),
}

ALL_SCENES = (
    TAKING_PRODUCT_SCENES + PRODUCT_IN_CONTEXT_SCENES +
    LIFESTYLE_SCENES + ACTIVE_SCENES + OUTDOOR_SCENES + SOCIAL_SCENES +
    SELFIE_SCENES
)


def _get_product_for_topic(topic: str) -> dict:
    """Match content topic to the right product."""
    for product in PRODUCT_REFS.values():
        if topic in product["topics"]:
            return product
    return PRODUCT_REFS["dbh"]


class UGCImageGenerator:
    """Generate UGC influencer images using product reference photos + text prompts."""

    def __init__(self, api_key: str, output_dir: Path = Path("data/media/ugc")):
        if not api_key:
            raise ValueError("GEMINI_API_KEY required")
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate(self, topic: str = "blood_sugar") -> Path:
        """Generate a UGC image (default Instagram 4:5 format). Backward compatible."""
        return await self.generate_for_platform(topic, platform="instagram")

    async def generate_for_platform(self, topic: str = "blood_sugar", platform: str = "instagram", skip_infographic: bool = False) -> Path:
        """Generate a UGC image sized for a specific platform.

        Sends: reference product image + detailed text prompt with influencer preset.
        Returns: path to generated image at correct platform dimensions.
        """
        from google.genai import types as genai_types

        product = _get_product_for_topic(topic)
        fmt = PLATFORM_FORMATS.get(platform, PLATFORM_FORMATS["instagram"])

        # 20% chance: ingredient infographic (no person, text overlay with benefits)
        product_key = next((k for k, v in PRODUCT_REFS.items() if v is product), "dbh")
        if not skip_infographic and random.random() < 0.2 and product_key in INGREDIENT_INFOGRAPHIC_SCENES:
            return await self._generate_infographic(product, product_key, fmt, topic, platform)

        scene = random.choice(ALL_SCENES)
        influencer_key = random.choice(list(INFLUENCER_PRESETS.keys()))
        influencer_desc = INFLUENCER_PRESETS[influencer_key]

        # Pick a reference image that exists
        ref_image_path = None
        for img in product["images"]:
            if Path(img).exists():
                ref_image_path = img
                break

        if not ref_image_path:
            raise FileNotFoundError(f"No reference images found for {product['name']}")

        # Read the reference image
        ref_bytes = Path(ref_image_path).read_bytes()
        mime = "image/jpeg" if ref_image_path.endswith(".jpg") else "image/png"

        # Build prompt emphasizing raw, imperfect UGC feel
        prompt_text = (
            f"Create a raw, unpolished UGC photo of {influencer_desc}, "
            f"{scene}. "
            f"The product must match the reference image exactly — same label, colors, shape. "
            f"This is {product['name']}. "
            f"CRITICAL PHYSICAL ACCURACY: "
            f"If the person is holding the product: their fingers must wrap around it realistically — "
            f"thumb on one side, fingers on the other, proper grip matching the product's size and shape. "
            f"The hand position must match the product position exactly — no floating product, no gap "
            f"between fingers and product surface. Shadows from the hand fall onto the product and vice versa. "
            f"If the person is dispensing or opening the product: show a natural, realistic interaction "
            f"matching how this type of product is actually used. "
            f"If the product is on a surface: it sits with proper weight — slight shadow underneath, "
            f"reflected ambient light, same perspective as surrounding objects. "
            f"STYLE RULES for authentic UGC: "
            f"- Shot on smartphone, candid feel, slight grain. "
            f"- Imperfect framing — off-center, maybe slightly tilted. "
            f"- The person is NOT posing. Caught mid-action, natural expression. "
            f"- Background is lived-in, not pristine. "
            f"- Natural lighting, uneven shadows are fine. "
            f"- The bottle is NOT the hero of the shot — the moment is. The bottle just happens "
            f"to be there as part of their routine. "
            f"No text overlays, no watermarks. "
            f"IMPORTANT: {fmt['label']} format, {fmt['ratio']} aspect ratio "
            f"({fmt['width']}x{fmt['height']} pixels). "
            f"{'Portrait orientation.' if fmt['height'] > fmt['width'] else 'Landscape orientation.'}"
        )

        logger.info(
            "UGC image: topic=%s, product=%s, influencer=%s, platform=%s, scene=%s",
            topic, product["name"], influencer_key, platform, scene[:40],
        )

        # Send reference image + text prompt together
        # Use asyncio.to_thread to avoid blocking the event loop (Gemini SDK is synchronous)
        import asyncio as _asyncio
        response = await _asyncio.to_thread(
            self.client.models.generate_content,
            model=_IMAGE_MODEL,
            contents=[
                genai_types.Part.from_bytes(data=ref_bytes, mime_type=mime),
                prompt_text,
            ],
            config=genai_types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                path = self.output_dir / f"ugc_{topic}_{influencer_key}_{platform}_{uuid4().hex[:8]}.png"
                path.write_bytes(part.inline_data.data)

                # Resize to exact platform dimensions
                self._resize_to_platform(path, fmt["width"], fmt["height"])

                logger.info("UGC image generated: %s (%d bytes)", path, path.stat().st_size)
                return path

        raise RuntimeError("No image returned from Gemini")

    @staticmethod
    def _resize_to_platform(path: Path, target_w: int, target_h: int):
        """Resize/crop image to exact platform dimensions."""
        try:
            from PIL import Image
            img = Image.open(path)
            target_ratio = target_w / target_h

            w, h = img.size
            current_ratio = w / h

            if current_ratio > target_ratio:
                # Too wide — crop sides
                new_w = int(h * target_ratio)
                left = (w - new_w) // 2
                img = img.crop((left, 0, left + new_w, h))
            elif current_ratio < target_ratio:
                # Too tall — crop top/bottom
                new_h = int(w / target_ratio)
                top = (h - new_h) // 2
                img = img.crop((0, top, w, top + new_h))

            img = img.resize((target_w, target_h), Image.LANCZOS)
            img.save(path, quality=95)
        except Exception as e:
            logger.warning("Failed to resize UGC image: %s", e)

    async def _generate_infographic(self, product: dict, product_key: str, fmt: dict, topic: str, platform: str) -> Path:
        """Generate a product infographic with ingredient callouts."""
        from google.genai import types as genai_types

        ref_image_path = None
        for img in product["images"]:
            if Path(img).exists():
                ref_image_path = img
                break

        if not ref_image_path:
            raise FileNotFoundError(f"No reference images found for {product['name']}")

        ref_bytes = Path(ref_image_path).read_bytes()
        mime = "image/jpeg" if ref_image_path.endswith(".jpg") else "image/png"

        scene = INGREDIENT_INFOGRAPHIC_SCENES[product_key]
        prompt_text = (
            f"{scene} "
            f"The bottle must look exactly like the reference image — same label, colors, shape. "
            f"IMPORTANT: The image MUST be {fmt['label']} format, {fmt['ratio']} aspect ratio "
            f"({fmt['width']}x{fmt['height']} pixels). "
            f"{'Portrait orientation.' if fmt['height'] > fmt['width'] else 'Landscape orientation.'}"
        )

        logger.info("Infographic: product=%s, platform=%s", product["name"], platform)

        import asyncio as _asyncio
        response = await _asyncio.to_thread(
            self.client.models.generate_content,
            model=_IMAGE_MODEL,
            contents=[
                genai_types.Part.from_bytes(data=ref_bytes, mime_type=mime),
                prompt_text,
            ],
            config=genai_types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )

        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                path = self.output_dir / f"infographic_{product_key}_{platform}_{uuid4().hex[:8]}.png"
                path.write_bytes(part.inline_data.data)
                self._resize_to_platform(path, fmt["width"], fmt["height"])
                logger.info("Infographic generated: %s (%d bytes)", path, path.stat().st_size)
                return path

        raise RuntimeError("No image returned from Gemini")

    # Keep old method name for backward compatibility
    @staticmethod
    def _resize_to_instagram(path: Path):
        """Resize/crop image to 1080x1350 (4:5 portrait) for Instagram."""
        UGCImageGenerator._resize_to_platform(path, 1080, 1350)
