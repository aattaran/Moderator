import { GoogleGenAI } from '@google/genai';
import { readFileSync, existsSync, statSync } from 'fs';
import { extname } from 'path';
import { config } from './utils/config.js';
import { logger } from './utils/logger.js';

const ai = new GoogleGenAI({ apiKey: config.geminiApiKey });

// ═══════════════════════════════════════════════════════
// UGC ANGLE STYLES
// ═══════════════════════════════════════════════════════

const UGC_ANGLE_STYLES = {
    relatable_rant: {
        name: 'Relatable Rant',
        description: 'Person experiencing a relatable problem (brain fog, energy crash, supplement fatigue), discovers this product as the solution.',
        tone: 'Slightly frustrated, then genuinely impressed',
        keywords: /crash|fog|tired|fatigue|energy|sluggish|afternoon|lunch/i,
        narrative_arc: 'Express relatable frustration with a problem → reveal this product changed things → casual low-pressure share',
        verbal_hooks: [
            'Stop taking [generic supplement] if you actually want [benefit]...',
            'I can not believe I was wasting money on [alternative] this whole time...',
            'Why did nobody tell me about this sooner...',
            'Okay so I have been dealing with [problem] for months and finally...',
        ],
        cta_examples: [
            'Honestly just look into it yourself, I think you will be surprised',
            'I have been using it for [time] now and I am not going back',
            'If you deal with [problem] too, this is worth a try',
        ],
    },
    casual_review: {
        name: 'Casual Review',
        description: 'Person already using the product for weeks, casually sharing their honest experience.',
        tone: 'Matter-of-fact, conversational, telling a friend',
        keywords: /review|tried|weeks|month|experience|honest|opinion/i,
        narrative_arc: 'Casually introduce product they have been using → share honest experience and details → matter-of-fact recommendation',
        verbal_hooks: [
            'So I have been testing this out for about a month now and I am genuinely impressed...',
            'Okay honest review time, I have been using this every day for [time]...',
            'Everyone keeps asking me what supplement I take so here it is...',
            'Here is the exact product that fixed my [problem]...',
        ],
        cta_examples: [
            'If you want to try it yourself the link is right there',
            'Definitely worth checking out if you are into [category]',
            'Let me know in the comments if you have tried this one',
        ],
    },
    ingredient_breakdown: {
        name: 'Ingredient Breakdown',
        description: '"I did the research so you don\'t have to" angle. Person reads the label, explains what each ingredient does.',
        tone: 'Informed, slightly nerdy, genuinely surprised by the formula',
        keywords: /research|ingredient|formula|dose|clinically|study|breakdown/i,
        narrative_arc: 'Set up the research angle → break down key ingredients with genuine surprise → wrap up with informed recommendation',
        verbal_hooks: [
            'I spent hours researching this and what I found actually surprised me...',
            'Wait until you hear what this ingredient actually does...',
            'Most supplements hide their doses but look at this label...',
            'I did the research so you do not have to, here is what is actually in this...',
        ],
        cta_examples: [
            'If you care about what goes into your body check this one out',
            'The formula speaks for itself honestly',
            'Save this for when you are comparing supplements',
        ],
    },
    morning_routine: {
        name: 'Morning Routine',
        description: 'Product shown as part of a daily wellness ritual. Person grabs it, takes it with water, explains why it\'s non-negotiable.',
        tone: 'Calm, habitual, low-key confident',
        keywords: /morning|routine|daily|habit|ritual|wake|start/i,
        narrative_arc: 'Show daily routine moment → explain why this product is non-negotiable → calm endorsement',
        verbal_hooks: [
            'My morning routine is finally dialed in and this one thing made the difference...',
            'This is the one supplement I will never skip...',
            'Part of my non-negotiable morning stack...',
            'Three things I do every single morning and number one is this...',
        ],
        cta_examples: [
            'If you want a solid morning routine add this to the list',
            'Check it out if you are building your own wellness stack',
            'Link is in the usual spot',
        ],
    },
    skeptic_converted: {
        name: 'Skeptic Converted',
        description: '"I didn\'t believe supplements worked until..." angle. Journey from skepticism to daily use.',
        tone: 'Honest, self-deprecating, then genuinely enthusiastic',
        keywords: /skeptic|didn.t believe|thought|scam|surprised|wrong|changed/i,
        narrative_arc: 'Express past skepticism or disbelief → reveal the surprising turnaround → honest genuine recommendation',
        verbal_hooks: [
            'I honestly thought this was just another overhyped supplement...',
            'I was the biggest skeptic until I actually tried this...',
            'Gatekeeping this is over, I was wrong about supplements...',
            'I rolled my eyes when someone recommended this to me but...',
        ],
        cta_examples: [
            'If you are skeptical like I was just give it a try',
            'I was wrong and I am not afraid to admit it, you need to try this',
            'Coming from a former non-believer, this one is legit',
        ],
    },
};

// ═══════════════════════════════════════════════════════
// UGC CONCEPTS (content format + visual direction)
// ═══════════════════════════════════════════════════════

const UGC_CONCEPTS = {
    unboxing: {
        name: 'Unboxing',
        description: 'Opening the package, initial reactions, first impressions of the product',
        clipDirection: {
            hook: {
                action: 'holds the product, looks at camera casually',
                camera: 'medium close-up, stationary with slight natural wobble',
                beat_suggestion: 'holds product → looks at camera → begins speaking',
            },
            concept: {
                action: 'holds product near chest while speaking about it',
                camera: 'medium close-up, stationary with slight natural wobble',
                beat_suggestion: 'holds product → talks about it → explains key ingredients',
            },
            cta: {
                action: 'sets product down, addresses camera with a nod',
                camera: 'medium close-up, stationary with slight natural wobble',
            },
        },
        props_required: 'shipping mailer or small cardboard box (opened), packing material or tissue paper',
        settings: ['living room couch', 'desk at home', 'kitchen', 'bedroom'],
    },
    product_demo: {
        name: 'Product Demo / How-to',
        description: 'Showing how the product works — holding it, reading label, explaining the routine',
        clipDirection: {
            hook: {
                action: 'positioned naturally in the scene with product visible, addresses camera directly',
                camera: 'medium close-up, stationary eye-level, slight natural wobble',
                beat_suggestion: 'addresses camera → gestures toward product → begins explanation',
            },
            concept: {
                action: 'picks up product, holds it while talking to camera',
                camera: 'medium close-up, stationary with slight natural wobble',
                beat_suggestion: 'picks up product → holds it → talks to camera',
            },
            cta: {
                action: 'sets product down, addresses camera with a friendly smile',
                camera: 'medium shot, slight natural sway',
            },
        },
        props_required: 'glass of water, the product',
        settings: ['kitchen', 'bathroom', 'desk at home', 'gym'],
    },
    lifestyle: {
        name: 'Lifestyle / Aesthetic',
        description: 'Product woven naturally into a daily routine, calm and aspirational',
        clipDirection: {
            hook: {
                action: 'casually positioned in the scene, addresses camera naturally',
                camera: 'medium close-up, stationary with slight natural wobble',
                beat_suggestion: 'settles into scene → looks at camera → begins speaking',
            },
            concept: {
                action: 'picks up product, holds it while explaining the routine',
                camera: 'medium close-up, stationary with slight natural wobble',
                beat_suggestion: 'picks up product → explains benefits → holds label toward camera',
            },
            cta: {
                action: 'places product down, casual closing words',
                camera: 'medium close-up, stationary with slight natural wobble',
            },
        },
        props_required: 'routine context items (coffee mug, yoga mat, skincare products, water bottle)',
        settings: ['kitchen', 'bathroom', 'home gym', 'bedroom'],
    },
    problem_solution: {
        name: 'Problem / Solution',
        description: 'Relatable frustration, then reveal the product as the solution',
        clipDirection: {
            hook: {
                action: 'positioned naturally in the scene, speaks directly to camera with a slightly frustrated expression',
                camera: 'medium close-up, stationary with slight natural wobble',
                beat_suggestion: 'settles into scene → looks at camera → begins explaining the problem',
            },
            concept: {
                action: 'picks up product, holds it while explaining the solution',
                camera: 'medium close-up, stationary with slight natural wobble',
                beat_suggestion: 'picks up product → explains key ingredients → shows label to camera',
            },
            cta: {
                action: 'sets product down, confident posture, delivers direct recommendation',
                camera: 'medium close-up, stationary with slight natural wobble',
            },
        },
        props_required: 'the product',
        settings: ['car', 'kitchen', 'desk at home', 'living room', 'gym'],
    },
    direct_review: {
        name: 'Direct Review / Testimonial',
        description: 'Straight-to-camera honest review, person shares their personal experience directly',
        clipDirection: {
            hook: {
                action: 'looks directly at camera, product already visible on surface nearby',
                camera: 'medium close-up, stationary with slight natural wobble',
                beat_suggestion: 'looks at camera → begins speaking → slight hand gesture',
            },
            concept: {
                action: 'picks up product, holds it toward camera, points at label details',
                camera: 'medium close-up, stationary with slight natural wobble',
                beat_suggestion: 'holds product up → reads label → explains key ingredients',
            },
            cta: {
                action: 'sets product down, looks directly at camera, casual genuine closing',
                camera: 'medium close-up, stationary with slight natural wobble',
            },
        },
        props_required: 'the product on a nearby surface',
        settings: ['kitchen', 'desk at home', 'car', 'living room', 'bathroom', 'gym'],
    },
};

const CONCEPT_KEYS = Object.keys(UGC_CONCEPTS);

// ═══════════════════════════════════════════════════════
// UGC VISUAL HOOKS (clip 1 attention-grabbing technique)
// ═══════════════════════════════════════════════════════

const UGC_VISUAL_HOOKS = {
    dynamic_movement: {
        name: 'Dynamic Movement',
        description: 'Subtle movement to open the clip — a calm natural gesture or slight shift in position',
        hook_action: 'makes a calm, natural gesture or shifts position slightly while beginning to speak',
        camera_note: 'medium close-up, stationary with slight natural wobble',
    },
    product_action: {
        name: 'Product Action',
        description: 'Opens with a calm product interaction — gently picks up the product, holds it toward camera',
        hook_action: 'gently picks up the product and holds it toward camera while beginning to speak',
        camera_note: 'medium close-up, stationary with slight natural wobble',
    },
    facial_expression: {
        name: 'Facial Expression',
        description: 'Opens with a genuine emotional expression — knowing smile, impressed look, or slight raised eyebrow directly to camera',
        hook_action: 'looks directly at camera with a genuine expression (knowing smile or slightly impressed look) and begins speaking',
        camera_note: 'medium close-up, stationary with slight natural wobble',
    },
    pattern_interrupt: {
        name: 'Pattern Interrupt',
        description: 'Person appears already mid-thought when clip starts, as if the viewer just walked in',
        hook_action: 'begins speaking mid-thought, looking directly at camera as if continuing a conversation',
        camera_note: 'medium close-up, stationary with slight natural wobble',
    },
};

const VISUAL_HOOK_KEYS = Object.keys(UGC_VISUAL_HOOKS);

// ═══════════════════════════════════════════════════════
// VERBAL HOOK & CTA STYLE MAPPINGS
// ═══════════════════════════════════════════════════════

const HOOK_VERBAL_STYLES = {
    negative: {
        label: 'Negative Hook',
        instruction: 'open with a cautionary or self-deprecating statement that creates curiosity — "Stop doing X if you want Y" or "I can not believe I did not know this"',
    },
    curiosity: {
        label: 'Curiosity / Teaser',
        instruction: 'tease a surprising fact or result without revealing it immediately — "Wait until you hear what this ingredient actually does" or "Nobody talks about this but..."',
    },
    fomo: {
        label: 'FOMO',
        instruction: 'leverage social proof and urgency — "Everyone is talking about this" or "This is going viral for a reason"',
    },
    secret: {
        label: 'The Secret',
        instruction: 'position the product as insider knowledge — "Gatekeeping this is over" or "My secret weapon for..."',
    },
    direct: {
        label: 'Direct Claim',
        instruction: 'lead with a specific bold benefit statement — "Here is the exact product that fixed my [problem]" or "This is the only supplement I will never stop taking"',
    },
    question: {
        label: 'Question',
        instruction: 'ask the viewer a relatable question that hooks them in — "Do you ever feel [problem] no matter what you try?" or "Anyone else tired of [common frustration]?"',
    },
    // Aliases for backward compatibility
    shock: { label: 'Direct Claim', instruction: 'lead with a bold attention-grabbing statement — same as "direct"' },
    claim: { label: 'Direct Claim', instruction: 'lead with a specific benefit or stat — same as "direct"' },
};

const CTA_STYLES = {
    soft: {
        label: 'Soft / Curiosity',
        instruction: 'gentle suggestion with no pressure — "Check out [Brand] to see their full lineup" or "Link is in the usual spot" or "Worth checking out"',
    },
    urgency: {
        label: 'Urgency / Scarcity',
        instruction: 'time-sensitive or scarcity angle — "Click the link before it sells out" or "Run do not walk" or "Grab yours before they are gone"',
    },
    social_proof: {
        label: 'Social Proof',
        instruction: 'mention popularity or reviews — "There is a reason this has thousands of five-star reviews" or "Join the people who already switched"',
    },
    benefit: {
        label: 'Benefit Restatement',
        instruction: 'restate the number one benefit as the reason to act — "If you want real [benefit] this is it" or "Your [problem] does not have to stay this way"',
    },
    engagement: {
        label: 'Engagement / Save',
        instruction: 'encourage interaction — "Let me know in the comments if you would try this" or "Save this for your next [activity]" or "Send this to a friend who needs [benefit]"',
    },
};

const STYLE_KEYS = Object.keys(UGC_ANGLE_STYLES);

/**
 * Generate UGC talking-head video prompts for Veo using Gemini.
 *
 * Each angle produces 3 clip prompts (Hook, Concept, CTA) that get stitched
 * into one complete ad video. Same person/setting across all ${clipCount} clips.
 *
 * @param {object} product - Normalized product data
 * @param {object} [options]
 * @param {number} [options.count=2] - Number of angle variations to generate
 * @param {string} [options.aspectRatio='9:16'] - Aspect ratio
 * @param {string} [options.instructions=''] - Additional creative direction
 * @param {string} [options.ugcStyle=''] - Force a specific angle style
 * @param {string} [options.concept=''] - Force a specific content concept
 * @param {string} [options.visualHook=''] - Force a specific visual hook type
 * @param {string[]} [options.actorImagePaths=[]] - Actor reference photos
 * @param {string[]} [options.productImagePaths=[]] - Product/bottle photos
 * @returns {Promise<Array>} Array of angle objects, each with 3 clip prompts
 */
export async function generateUgcAngles(product, options = {}) {
    const {
        count = 2,
        aspectRatio = '9:16',
        instructions = '',
        ugcStyle = '',
        concept = '',
        visualHook = '',
        actorImagePaths = [],
        productImagePaths = [],
        // A/B testing params
        hookStyle = '',       // 'negative' | 'curiosity' | 'fomo' | 'secret' | 'direct' | 'question' | '' (auto)
        ctaStyle = '',        // 'soft' | 'urgency' | 'social_proof' | 'benefit' | 'engagement' | '' (auto)
        toneLevel = '',       // 'casual' | 'energetic' | 'authoritative' | '' (auto)
        settingPreset = '',   // 'kitchen' | 'gym' | 'bathroom' | 'outdoor' | 'car' | '' (auto)
        pose = '',            // 'standing' | 'walking' | 'sitting' | '' (auto — follows concept default)
        bottleCloseup = '',   // 'yes' | 'no' | '' (auto — follows concept default)
        clipCount = 3,        // 3 | 4 | 5 | 6 | 9
        clipDuration = 0,    // 0 = auto (5s for 6+, 8s for 3-5), or explicit seconds
        lang = '',            // 'es' | 'pt' | 'fr' | '' (default: English)
        actorDescription = '', // When set, use this text description instead of actor ref images for persona
        promptStyle = 'structured', // 'structured' (default: promptData JSON) or 'natural' (Kling-optimized prompt strings)
        simple = false,       // Simple mode: no hardcoded product-specific rules
    } = options;

    // Resolve clip duration: explicit value or auto from clip count
    const resolvedDuration = clipDuration > 0 ? clipDuration : (clipCount >= 6 ? 5 : 8);

    logger.divider('UGC SCRIPT GENERATION');
    logger.info('ugc-script', `Product: ${product.brand} — ${product.title}`);
    logger.info('ugc-script', `Generating ${count} UGC angle(s) × ${clipCount} clips each`);
    if (promptStyle === 'natural') logger.info('ugc-script', '  Prompt style: NATURAL (Kling-optimized)');
    if (ugcStyle) logger.info('ugc-script', `  Style: ${ugcStyle}`);
    if (concept) logger.info('ugc-script', `  Concept: ${concept}`);
    if (visualHook) logger.info('ugc-script', `  Visual hook: ${visualHook}`);

    const ingredientContext = product.keyIngredients?.length
        ? product.keyIngredients.map(i => `  • ${i}`).join('\n')
        : '  (no specific ingredients listed)';

    const sellingPointContext = product.sellingPoints?.length
        ? product.sellingPoints.map(s => `  • ${s}`).join('\n')
        : '';

    const bulletContext = product.bullets?.length
        ? product.bullets.map(b => `  • ${b}`).join('\n')
        : '';

    const containerDesc = product.specifications?.containerType
        ? `${product.specifications.containerType}${product.specifications.itemForm ? ', ' + product.specifications.itemForm : ''}`
        : 'product container';

    // ═══════════════════════════════════════════════════════
    // BUILD DYNAMIC SYSTEM PROMPT
    // ═══════════════════════════════════════════════════════

    const systemPrompt = promptStyle === 'natural'
        ? buildNaturalSystemPrompt({
            count, aspectRatio, ugcStyle, concept, visualHook,
            hookStyle, ctaStyle, toneLevel, settingPreset, pose, bottleCloseup, clipCount,
            clipDuration: resolvedDuration, actorImagePaths, actorDescription, product, containerDesc, lang, simple,
        })
        : buildUgcSystemPrompt({
            count, aspectRatio, ugcStyle, concept, visualHook,
            hookStyle, ctaStyle, toneLevel, settingPreset, pose, bottleCloseup, clipCount,
            clipDuration: resolvedDuration, actorImagePaths, actorDescription, product, containerDesc, lang, simple,
        });

    const userPrompt = promptStyle === 'natural'
        ? buildNaturalUserPrompt({
            count, product, containerDesc, ingredientContext,
            sellingPointContext, bulletContext, ugcStyle, concept,
            visualHook, hookStyle, ctaStyle, toneLevel, settingPreset, pose, bottleCloseup, clipCount,
            clipDuration: resolvedDuration, instructions, lang, simple,
        })
        : buildUgcUserPrompt({
            count, product, containerDesc, ingredientContext,
            sellingPointContext, bulletContext, ugcStyle, concept,
            visualHook, hookStyle, ctaStyle, toneLevel, settingPreset, pose, bottleCloseup, clipCount,
            clipDuration: resolvedDuration, instructions, lang, simple,
        });

    // Build multimodal contents: product photos + actor photos + text prompt
    const productParts = prepareActorImageParts(productImagePaths, 'Product');
    if (productParts.length > 0) {
        logger.info('ugc-script', `Product reference: ${productParts.length} photo(s) sent to Gemini`);
    }
    const actorParts = prepareActorImageParts(actorImagePaths);

    const imagePreamble = [];
    if (productParts.length > 0) {
        imagePreamble.push(`[The first ${productParts.length} image(s) show the PRODUCT. Do NOT describe it in text — just use "the product" in scene.props. The model will see the images directly.]`);
    }
    if (actorParts.length > 0) {
        imagePreamble.push(`[The next ${actorParts.length} image(s) show the ACTOR's face. Use "the person" in subject.description. The photos are face-only — choose ONE specific casual outfit (e.g. "black tank top" or "gray hoodie") and use that EXACT text in subject.wardrobe for ALL clips. Do NOT write "as shown in reference" — the photos do not show clothing.]`);
    } else if (actorDescription) {
        imagePreamble.push(`[ACTOR DESCRIPTION (no reference images): ${actorDescription}. Use this description for subject.description and subject.wardrobe fields.]`);
    }

    const contentParts = [
        ...productParts,
        ...actorParts,
        { text: imagePreamble.length > 0 ? `${imagePreamble.join('\n')}\n\n${userPrompt}` : userPrompt },
    ];

    try {
        const response = await ai.models.generateContent({
            model: 'gemini-3-flash-preview',
            contents: [{ role: 'user', parts: contentParts }],
            config: {
                systemInstruction: systemPrompt,
                temperature: 0.7,
                maxOutputTokens: 16384,
            },
        });

        const text = response.text?.trim();
        if (!text) {
            throw new Error('Empty response from Gemini — no UGC angles generated');
        }

        let cleanJson = text;
        if (cleanJson.startsWith('```')) {
            cleanJson = cleanJson.replace(/^```(?:json)?\s*\n?/, '').replace(/\n?```\s*$/, '');
        }

        let angles;
        try {
            angles = JSON.parse(cleanJson);
        } catch (parseErr) {
            logger.warn('ugc-script', 'First parse failed, retrying with stricter instruction...');
            // Rebuild content parts with images + stricter text instruction
            const retryParts = [
                ...productParts,
                ...actorParts,
                { text: `Return ONLY a valid JSON array, nothing else. No markdown, no explanation.\n\n${userPrompt}` },
            ];
            const retryResponse = await ai.models.generateContent({
                model: 'gemini-3-flash-preview',
                contents: [{ role: 'user', parts: retryParts }],
                config: {
                    systemInstruction: systemPrompt,
                    temperature: 0.5,
                    maxOutputTokens: 16384,
                },
            });

            let retryText = retryResponse.text?.trim();
            if (!retryText) throw new Error('Retry returned empty response');
            if (retryText.startsWith('```')) {
                retryText = retryText.replace(/^```(?:json)?\s*\n?/, '').replace(/\n?```\s*$/, '');
            }
            angles = JSON.parse(retryText);
        }

        if (!Array.isArray(angles) || angles.length === 0) {
            throw new Error('Gemini returned empty or non-array angle list');
        }

        // Trim to requested count
        if (angles.length > count) {
            angles = angles.slice(0, count);
        }

        // Validate and normalize
        const validatedAngles = angles.map((angle, idx) => ({
            angleNumber: angle.angleNumber || idx + 1,
            angleName: angle.angleName || `Angle ${idx + 1}`,
            ugcStyle: angle.ugcStyle || ugcStyle || STYLE_KEYS[idx % STYLE_KEYS.length],
            concept: angle.concept || concept || '',
            visualHook: angle.visualHook || visualHook || '',
            persona: angle.persona || '',
            clips: (angle.clips || []).map((clip, cIdx) => ({
                clipNumber: clip.clipNumber || cIdx + 1,
                section: clip.section || ['hook', 'concept', 'cta'][cIdx] || 'hook',
                // Support both structured (promptData) and legacy (prompt) formats
                ...(clip.promptData
                    ? { promptData: clip.promptData }
                    : { prompt: clip.prompt || '' }),
                extensionPrompt: clip.extensionPrompt || null,
                duration: resolvedDuration,
            })),
            aspectRatio: angle.aspectRatio || aspectRatio,
        }));

        // Ensure each angle has expected clip count
        for (const angle of validatedAngles) {
            if (angle.clips.length < clipCount) {
                logger.warn('ugc-script', `Angle ${angle.angleNumber} has ${angle.clips.length} clips (expected ${clipCount})`);
            }
        }

        // ── Word count warning for short clips (5s = target 10-12 words) ──

        logger.success('ugc-script', `Generated ${validatedAngles.length} UGC angle(s) × ${clipCount} clips each`);
        for (const angle of validatedAngles) {
            logger.info('ugc-script', `  Angle ${angle.angleNumber}: "${angle.angleName}" (${angle.ugcStyle})`);
            logger.info('ugc-script', `    Persona: ${angle.persona}`);
            for (const clip of angle.clips) {
                const wordCount = clip.promptData?.dialogue?.line?.split(/\s+/).length || 0;
                const preview = clip.promptData
                    ? `[JSON] ${wordCount}w: "${clip.promptData.dialogue?.line?.substring(0, 60) || ''}..."`
                    : `${clip.prompt.substring(0, 80)}...`;
                logger.info('ugc-script', `    Clip ${clip.clipNumber} [${clip.section}]: ${preview}`);
            }
        }

        return validatedAngles;
    } catch (err) {
        logger.error('ugc-script', 'UGC script generation failed', err);
        throw err;
    }
}

// ═══════════════════════════════════════════════════════
// PROMPT BUILDERS
// ═══════════════════════════════════════════════════════

function buildStyleSection(ugcStyle) {
    if (ugcStyle && UGC_ANGLE_STYLES[ugcStyle]) {
        const s = UGC_ANGLE_STYLES[ugcStyle];
        return `### ASSIGNED STYLE: ${s.name}
Narrative arc: ${s.narrative_arc}
Tone: ${s.tone}
Verbal hook examples (adapt ONE to this product): ${s.verbal_hooks.join(' | ')}
CTA examples (adapt ONE): ${s.cta_examples.join(' | ')}`;
    }
    return `### AVAILABLE STYLES (use a DIFFERENT style for each angle — each style has a distinct narrative arc and tone):
${Object.entries(UGC_ANGLE_STYLES).map(([k, v]) => `- **${k}**: ${v.description} Arc: ${v.narrative_arc}`).join('\n')}`;
}

// Pose overrides for hook clip direction (when --pose is set)
const POSE_OVERRIDES = {
    walking: {
        action: 'walks toward camera inside the room holding phone at selfie angle, talking casually to camera while moving, stays in frame',
        camera: 'selfie POV, gentle natural movement from walking',
        beat_suggestion: 'walks toward camera → talks casually → gestures naturally',
    },
    sitting: {
        action: 'sits comfortably, talking directly to camera',
        camera: 'medium close-up, stationary with slight natural wobble',
        beat_suggestion: 'sits comfortably → looks at camera → begins speaking',
    },
    // standing: no override — uses concept's default hook direction
};

// Bottle close-up overrides for concept + cta clip directions (when --bottle-closeup is set)
const BOTTLE_CLOSEUP_OVERRIDES = {
    no: {
        concept_action: 'holds product at chest level while talking, does NOT hold it up toward camera or show the label close-up',
        cta_action: 'sets product down, addresses camera directly',
    },
    yes: {
        concept_action: 'holds product forward toward camera at chest level, showing the label clearly, keeping it completely away from her face and mouth',
        cta_action: 'holds product forward toward camera at chest level, keeping face completely visible',
    },
};

function buildConceptSection(concept, pose = '', bottleCloseup = '') {
    if (concept && UGC_CONCEPTS[concept]) {
        const c = UGC_CONCEPTS[concept];
        // When pose is set, override the hook's action/camera with pose-specific values
        const poseOverride = pose && POSE_OVERRIDES[pose];
        // const hookAction = c.clipDirection.hook.action;       // original concept default
        // const hookCamera = c.clipDirection.hook.camera;       // original concept default
        // const hookBeats = c.clipDirection.hook.beat_suggestion; // original concept default
        const hookAction = poseOverride ? poseOverride.action : c.clipDirection.hook.action;
        const hookCamera = poseOverride ? poseOverride.camera : c.clipDirection.hook.camera;
        const hookBeats = poseOverride ? poseOverride.beat_suggestion : c.clipDirection.hook.beat_suggestion;
        // When bottleCloseup is set, override concept + cta clip actions
        const bottleOverride = bottleCloseup && BOTTLE_CLOSEUP_OVERRIDES[bottleCloseup];
        // const conceptAction = c.clipDirection.concept.action;  // original concept default
        // const ctaAction = c.clipDirection.cta.action;           // original concept default
        const conceptAction = bottleOverride ? bottleOverride.concept_action : c.clipDirection.concept.action;
        const ctaAction = bottleOverride ? bottleOverride.cta_action : c.clipDirection.cta.action;
        return `### ASSIGNED CONCEPT: ${c.name}
Format: ${c.description}
CLIP 1 (HOOK) direction: action="${hookAction}", camera="${hookCamera}"${hookBeats ? `, beats="${hookBeats}"` : ''}
CLIP 2 (CONCEPT) direction: action="${conceptAction}", camera="${c.clipDirection.concept.camera}"${c.clipDirection.concept.beat_suggestion ? `, beats="${c.clipDirection.concept.beat_suggestion}"` : ''}
CLIP 3 (CTA) direction: action="${ctaAction}", camera="${c.clipDirection.cta.camera}"
Required props: ${c.props_required}
Suggested settings: ${c.settings.join(', ')}
USE THESE CAMERA AND ACTION DIRECTIONS — they define what makes this concept visually distinct.`;
    }
    // Auto-select: when pose/bottleCloseup is set, inject override notes
    const poseNote = pose && POSE_OVERRIDES[pose]
        ? `\nPOSE OVERRIDE FOR CLIP 1: Regardless of concept chosen, Clip 1 (HOOK) MUST use action="${POSE_OVERRIDES[pose].action}", camera="${POSE_OVERRIDES[pose].camera}".`
        : '';
    const bottleNote = bottleCloseup && BOTTLE_CLOSEUP_OVERRIDES[bottleCloseup]
        ? `\nBOTTLE OVERRIDE: Regardless of concept chosen, Clip 2 MUST use action="${BOTTLE_CLOSEUP_OVERRIDES[bottleCloseup].concept_action}". Clip 3 MUST use action="${BOTTLE_CLOSEUP_OVERRIDES[bottleCloseup].cta_action}".`
        : '';
    return `### AVAILABLE CONCEPTS (use a DIFFERENT concept for each angle — each concept has unique camera work, actions, and props):
${Object.entries(UGC_CONCEPTS).map(([k, v]) => `- **${k}**: ${v.description}. Camera: hook="${v.clipDirection.hook.camera}" → concept="${v.clipDirection.concept.camera}" → cta="${v.clipDirection.cta.camera}"`).join('\n')}
CRITICAL: Each concept defines DIFFERENT camera angles, movements, and actions. The ad must LOOK visually different based on the concept chosen.${poseNote}${bottleNote}`;
}

function buildVisualHookSection(visualHook) {
    if (visualHook && UGC_VISUAL_HOOKS[visualHook]) {
        const vh = UGC_VISUAL_HOOKS[visualHook];
        return `### VISUAL HOOK for Clip 1: ${vh.name}
${vh.description}
Opening action: ${vh.hook_action}
Camera note: ${vh.camera_note}`;
    }
    return `### VISUAL HOOKS (choose a DIFFERENT one for each angle's Clip 1 to vary the "stop the scroll" moment):
${Object.entries(UGC_VISUAL_HOOKS).map(([k, v]) => `- **${k}**: ${v.description}. Action: ${v.hook_action}`).join('\n')}`;
}

// ─── Shared Rules (used by both structured and natural prompts) ─────────

function buildClipChoreography(clipCount) {
    const clips = {
        3: [
            { section: 'hook', bottle: false, action: 'casually positioned in the scene, picks up product while beginning to speak', focus: 'stop the scroll' },
            { section: 'concept', bottle: true, action: 'holds product steadily at chest level with both hands while talking', focus: 'mention 1 key ingredient BY NAME and what it does' },
            { section: 'cta', bottle: true, action: 'sets product down gently, addresses camera with a casual nod and smile', focus: 'low-pressure closing' },
        ],
        4: [
            { section: 'hook', bottle: false, action: 'casually positioned in the scene, product on surface nearby, looking at camera', focus: 'stop the scroll' },
            { section: 'story', bottle: false, action: 'gestures naturally, reaches for and picks up product while talking', focus: 'personal backstory, NO product facts' },
            { section: 'benefit', bottle: true, action: 'holds product steadily at chest level with both hands while explaining', focus: 'mention 1 ingredient BY NAME and what it does' },
            { section: 'cta', bottle: true, action: 'sets product down gently, addresses camera with a casual nod and smile', focus: 'personal results + low-pressure closing' },
        ],
        5: [
            { section: 'hook', bottle: false, action: 'casually positioned in the scene, product on surface nearby, looking at camera', focus: 'stop the scroll' },
            { section: 'story', bottle: false, action: 'gestures naturally, reaches for and picks up product while talking', focus: 'personal backstory, NO product facts' },
            { section: 'benefit', bottle: true, action: 'holds product steadily at chest level with both hands while explaining', focus: 'mention 1 ingredient BY NAME and what it does' },
            { section: 'experience', bottle: true, action: 'still holding product, talks to camera with slight nod', focus: 'how it feels day-to-day, real results' },
            { section: 'cta', bottle: true, action: 'sets product down gently, addresses camera with a casual nod and smile', focus: 'casual recommendation' },
        ],
        6: [
            { section: 'hook', bottle: false, action: 'casually positioned in the scene, product on surface nearby, looking at camera', focus: 'stop the scroll' },
            { section: 'setup', bottle: false, action: 'gestures naturally, reaches for and picks up product while describing the problem', focus: 'introduce the problem' },
            { section: 'benefit_1', bottle: true, action: 'holds product steadily at chest level with both hands while explaining', focus: 'first key ingredient BY NAME' },
            { section: 'benefit_2', bottle: true, action: 'continues holding product, slight nod while explaining', focus: 'second key ingredient BY NAME' },
            { section: 'social_proof', bottle: true, action: 'sets product down gently, talks to camera with genuine expression', focus: 'personal results ("I feel X")' },
            { section: 'cta', bottle: false, action: 'product resting on surface, addresses camera with a casual nod and smile', focus: 'low-pressure closing' },
        ],
        9: [
            { section: 'hook', bottle: false, action: 'casually positioned in the scene, looking at camera, product resting on surface nearby', focus: 'stop the scroll' },
            { section: 'setup', bottle: false, action: 'gestures naturally while describing the problem, product visible on surface', focus: 'introduce the problem casually' },
            { section: 'story', bottle: false, action: 'reaches for the product and picks it up while talking', focus: 'personal backstory, how they found the product' },
            { section: 'benefit_1', bottle: true, action: 'holds product steadily at chest level with both hands while explaining', focus: 'one key ingredient BY NAME' },
            { section: 'benefit_2', bottle: true, action: 'continues holding product, slight nod while explaining', focus: 'second key ingredient BY NAME' },
            { section: 'experience', bottle: true, action: 'still holding product, talks to camera with slight smile', focus: 'how it feels, real-life impact' },
            { section: 'social_proof', bottle: true, action: 'sets product down gently on surface, talks with genuine expression', focus: 'personal results ("I feel X", "my energy is Y")' },
            { section: 'lifestyle', bottle: false, action: 'relaxed posture, product resting on surface, talks casually', focus: 'casual aside, how it fits into life' },
            { section: 'cta', bottle: false, action: 'addresses camera directly with a casual nod, product visible on surface', focus: 'low-pressure closing' },
        ],
    };
    return clips[clipCount] || clips[3];
}

function buildCoreRules({ clipCount, clipDuration = 8, pose, actorImagePaths, actorDescription, product, containerDesc, settingPreset, lang, simple = false }) {
    const wordCount = `${Math.round(clipDuration * 2)}-${Math.round(clipDuration * 2.5)}`;
    const choreography = buildClipChoreography(clipCount);

    return `### CLIP CHOREOGRAPHY (${clipCount} clips × ${clipDuration}s each):
${choreography.map((c, i) => `- **Clip ${i + 1} (${c.section.toUpperCase()})** — ${clipDuration}s — action: "${c.action}" — dialogue focus: ${c.focus}`).join('\n')}

### MOVEMENT:
- Camera: static with slight natural wobble. No cinematic moves (dolly, pan, tracking, zoom).
- Actions should be gentle, natural, and calm. The person can gesture while holding the product.

### DIALOGUE (${wordCount} words per clip):
- Casual spoken language. Contractions OK. Write how a real person talks to a friend.
- Every sentence must be a COMPLETE thought. Do NOT use ellipses "…".
- NEVER say "cures", "treats", "prevents" — use "supports", "helps with", "I noticed"
- **TTS PRONUNCIATION**: Break up long scientific/chemical names with hyphens so TTS can pronounce them. Example: "dihydroberberine" → write as "dihydro-berberine". Use simpler everyday names when possible (e.g. "vitamin B1" instead of "benfotiamine", "cinnamon" instead of "ceylon cinnamon"). Max 2 ingredient names per sentence.
- BANNED phrases: "game-changer", "life-changing", "best thing ever", "must-have"
- BANNED topics: GMP, FDA, manufacturing, certifications, "made in USA"
${lang ? `- LANGUAGE: All dialogue in ${lang === 'es' ? 'Spanish (Latin American)' : lang === 'pt' ? 'Brazilian Portuguese' : lang === 'fr' ? 'French' : lang}. All other fields in English.` : ''}

### PRODUCT:
${simple ? `- Use "the product" in scene.props. Describe it EXACTLY as shown in reference photos.` : `- Product: ${product.brand} — ${product.title} | Container: ${containerDesc}
- scene.props: Describe the product EXACTLY as shown in reference photos — same description in every clip.`}
- The PERSON is always the subject, not the product.
- Product and hands MUST NEVER block face or mouth — lip-sync clarity is critical.

### CHARACTER CONSISTENCY:
Each clip is a SEPARATE API call with ZERO memory of previous clips.
- subject.description, subject.wardrobe, scene.location, scene.props must be IDENTICAL TEXT across all ${clipCount} clips.
- NEVER say "the same", "same as before" — repeat the full description each time.

### PERSONA:
${actorImagePaths.length > 0 ? `**ACTOR PHOTOS PROVIDED** — Use "the person" in subject.description. Photos are face-only — choose ONE casual outfit and use that EXACT text in subject.wardrobe for ALL clips.` : actorDescription ? `**ACTOR DESCRIPTION:** "${actorDescription}". Choose a casual outfit for subject.wardrobe. Both fields IDENTICAL across all clips.` : `Generate a UNIQUE persona (age 22-40). Full physical description in subject.description, specific outfit in subject.wardrobe — IDENTICAL across all clips.`}
${settingPreset ? `SETTING: "${settingPreset}" for all clips.` : ''}
- The person is comfortably ${pose === 'sitting' ? 'sitting' : pose === 'walking' ? 'walking' : 'standing'} in the scene.
- Describe setting with 2-3 background details. Clothing: casual everyday.`;
}

// ─── Structured Mode (JSON promptData output) ───────────────────────

function buildUgcSystemPrompt({ count, aspectRatio, ugcStyle, concept, visualHook, hookStyle, ctaStyle, toneLevel, settingPreset, pose, bottleCloseup, clipCount, clipDuration = 8, actorImagePaths, actorDescription, product, containerDesc, lang, simple }) {
    const styleSection = buildStyleSection(ugcStyle);
    const conceptSection = buildConceptSection(concept, pose, bottleCloseup);
    const visualHookSection = buildVisualHookSection(visualHook);
    const coreRules = buildCoreRules({ clipCount, clipDuration, pose, actorImagePaths, actorDescription, product, containerDesc, settingPreset, lang, simple });
    const choreography = buildClipChoreography(clipCount);

    return `You are a UGC ad director. You create structured JSON prompts for AI video generation that produce realistic talking-head supplement review content.

### YOUR GOAL:
Generate ${count} unique UGC video angle(s). Each angle = ${clipCount} clips × ${clipDuration}s each (~${clipCount * clipDuration}s total).

${styleSection}

${conceptSection}

${visualHookSection}

${coreRules}

### OUTPUT FORMAT:
Return ONLY a valid JSON array, no markdown wrapping. Each clip has a \`promptData\` object (structured JSON) and an \`extensionPrompt\` string (motion-only plain text, null for clip 1).

**promptData fields:** shot (composition, camera_motion, frame_rate:"24fps"), subject (description, wardrobe, action, expression), scene (location, time_of_day, props), dialogue (speaker, line, delivery), audio (ambient, voice, music:"none — absolutely no background music or soundtrack"), visual_rules (prohibited_elements, physics), lighting (primary, mood).

**JSON SCHEMA:**
[
  {
    "angleNumber": 1,
    "angleName": "<creative 2-4 word name>",
    "ugcStyle": "<style key>",
    "concept": "<concept key>",
    "visualHook": "<hook key>",
    "persona": "<full persona description>",
    "clips": [
${choreography.map((c, i) => `      { "clipNumber": ${i + 1}, "section": "${c.section}", "promptData": { "shot": {"composition": "medium close-up, eye-level", "camera_motion": "static with slight natural wobble", "frame_rate": "24fps"}, "subject": {"description": "${actorImagePaths.length > 0 ? 'the person' : '<generate>'}", "wardrobe": "<generate: ONE outfit — IDENTICAL all clips>", "action": "${c.action}", "expression": "<generate>"}, "scene": {"location": "<generate: IDENTICAL all clips>", "time_of_day": "<generate>", "props": "the product"}, "dialogue": {"speaker": "the person", "line": "<generate: ${Math.round(clipDuration * 2)}-${Math.round(clipDuration * 2.5)} words — ${c.focus}>", "delivery": "<generate>"}, "audio": {"ambient": "<generate>", "voice": "natural speaking voice", "music": "none — absolutely no background music or soundtrack"}, "visual_rules": {"prohibited_elements": ["text overlays","captions","subtitles","background music","soundtrack","jingles","hands covering face","objects overlapping mouth","product blocking face","drinking","eating"], "physics": "all objects maintain consistent size and position, no morphing"}, "lighting": {"primary": "<generate>", "mood": "<generate>"} }, "extensionPrompt": ${i === 0 ? 'null' : '"<generate: motion-only>"'}, "duration": ${clipDuration} }`).join(',\n')}
    ],
    "aspectRatio": "${aspectRatio}"
  }
]`;
}

function buildNaturalSystemPrompt({ count, aspectRatio, ugcStyle, concept, visualHook, hookStyle, ctaStyle, toneLevel, settingPreset, pose, bottleCloseup, clipCount, clipDuration = 8, actorImagePaths, actorDescription, product, containerDesc, lang, simple }) {
    const styleSection = buildStyleSection(ugcStyle);
    const conceptSection = buildConceptSection(concept, pose, bottleCloseup);
    const coreRules = buildCoreRules({ clipCount, clipDuration, pose, actorImagePaths, actorDescription, product, containerDesc, settingPreset, lang, simple });
    const choreography = buildClipChoreography(clipCount);

    return `You are a UGC ad director who writes natural-language prompts for Kling AI video generation.

### YOUR GOAL:
Generate ${count} UGC video angle(s). Each angle = ${clipCount} clips × ${clipDuration}s each.

${styleSection}

${conceptSection}

${coreRules}

### NATURAL MODE EXTRAS:

**IMPERFECTION CUES (2-3 per clip)**
Add physical imperfection details: messy-chic hair, imperfect grip, quick inhale, slight handheld camera shake, micro-jitter, amateur selfie framing.

**SELFIE CAMERA**
Write "handheld selfie video" or "selfie-style video with micro-jitter". Add "focus on mouth for lip-sync clarity".

**LAYERED AUDIO (4 layers per clip)**
- voice: tone, pacing
- ambient: 2-3 contextual sounds
- sfx: product-specific
- music: "none"

### OUTPUT FORMAT:
Return ONLY a valid JSON array. Each clip has a \`prompt\` string (natural language paragraph) and a \`dialogue\` object with the spoken \`line\`.

The \`prompt\` paragraph: camera line → behaviors → product interaction → "voice script: [dialogue]" → audio layers.

**JSON SCHEMA:**
[
  {
    "angleNumber": 1, "angleName": "<name>", "ugcStyle": "<key>", "concept": "<key>", "visualHook": "<key>",
    "persona": "<persona>",
    "clips": [
${choreography.map((c, i) => `      { "clipNumber": ${i + 1}, "section": "${c.section}", "prompt": "<natural prompt — ${c.bottle ? 'holds product' : 'no product'}, ${c.focus}>", "dialogue": { "line": "<${Math.round(clipDuration * 2)}-${Math.round(clipDuration * 2.5)} words>" }, "extensionPrompt": ${i === 0 ? 'null' : '"<motion-only>"'}, "duration": ${clipDuration} }`).join(',\n')}
    ],
    "aspectRatio": "${aspectRatio}"
  }
]`;
}

function buildUgcUserPrompt({ count, product, containerDesc, ingredientContext, sellingPointContext, bulletContext, ugcStyle, concept, visualHook, hookStyle, ctaStyle, toneLevel, settingPreset, pose, bottleCloseup, clipCount, clipDuration = 8, instructions, lang, simple = false }) {
    const wordCount = `${Math.round(clipDuration * 2)}-${Math.round(clipDuration * 2.5)}`;
    const choreography = buildClipChoreography(clipCount);
    const sectionNames = choreography.map(c => c.section).join(' + ');
    const bottleClips = choreography.filter(c => c.bottle).map(c => c.section.toUpperCase());

    return `Generate ${count} UGC video angle(s) for this product (each angle = ${clipCount} clips: ${sectionNames}):

BRAND: ${product.brand || 'N/A'}
PRODUCT: ${product.title}
CONTAINER: ${containerDesc}

${simple ? '' : `KEY INGREDIENTS (mention 1 BY NAME in ${bottleClips.join('/')} clip(s)):
${ingredientContext}

SELLING POINTS:
${sellingPointContext}

PRODUCT BENEFITS:
${bulletContext}
`}
${ugcStyle ? `STYLE: Use "${ugcStyle}" for all angles.` : 'STYLE: Use a DIFFERENT style for each angle — maximize variety.'}
${concept ? `CONCEPT: Use "${concept}" content format for all angles.` : 'CONCEPT: Use a DIFFERENT concept for each angle.'}
${visualHook ? `VISUAL HOOK: Use "${visualHook}" for clip 1 of all angles.` : ''}
${pose ? `POSE: Hook clip uses "${pose}" pose.` : ''}
${lang ? `LANGUAGE: All dialogue in ${lang === 'es' ? 'Spanish' : lang === 'pt' ? 'Portuguese' : lang === 'fr' ? 'French' : lang}.` : ''}
${instructions ? `SCRIPT GUIDANCE: ${instructions}` : ''}

Rules:
1. Return ONLY the JSON array — no markdown, no explanation
2. Each clip's promptData must have ALL required fields
3. dialogue.line: ONLY spoken text — NO quotation marks
4. **CRITICAL: Each clip is ${clipDuration} seconds. ${wordCount} words per clip.**
5. ${bottleClips.length > 0 ? `Mention 1 key ingredient BY NAME in ${bottleClips.join('/')} clip(s)` : 'Mention the product naturally'}
6. subject.description, scene.location, scene.props IDENTICAL across all ${clipCount} clips
7. extensionPrompt for clips 2+: MOTION-ONLY. Clip 1: null`;
}

function buildNaturalUserPrompt({ count, product, containerDesc, ingredientContext, sellingPointContext, bulletContext, ugcStyle, concept, visualHook, hookStyle, ctaStyle, toneLevel, settingPreset, pose, bottleCloseup, clipCount, clipDuration = 8, instructions, lang, simple = false }) {
    const wordCount = `${Math.round(clipDuration * 2)}-${Math.round(clipDuration * 2.5)}`;
    const choreography = buildClipChoreography(clipCount);
    const bottleClips = choreography.filter(c => c.bottle).map(c => c.section.toUpperCase());

    return `Generate ${count} UGC video angle(s) for this product (each angle = ${clipCount} clips):

BRAND: ${product.brand || 'N/A'}
PRODUCT: ${product.title}
CONTAINER: ${containerDesc}

${simple ? '' : `KEY INGREDIENTS (mention 1 BY NAME in ${bottleClips.join('/')} clip(s)):
${ingredientContext}

SELLING POINTS:
${sellingPointContext}
`}
${ugcStyle ? `STYLE: Use "${ugcStyle}" for all angles.` : 'STYLE: Use a DIFFERENT style for each angle.'}
${concept ? `CONCEPT: Use "${concept}" for all angles.` : 'CONCEPT: Vary concepts across angles.'}
${pose ? `POSE: Hook clip uses "${pose}" pose.` : ''}
${lang ? `LANGUAGE: All dialogue in ${lang === 'es' ? 'Spanish' : lang === 'pt' ? 'Portuguese' : lang === 'fr' ? 'French' : lang}.` : ''}
${instructions ? `SCRIPT GUIDANCE: ${instructions}` : ''}

Rules:
1. Return ONLY the JSON array — no markdown
2. Each clip has a "prompt" string and a "dialogue" object with "line" (spoken text only)
3. **${wordCount} words per clip dialogue. Each clip is ${clipDuration} seconds.**
4. Same person and setting across all clips — repeat visual details in every prompt
5. Clip 1 extensionPrompt: null. Clips 2+: motion-only text`;
}

function prepareActorImageParts(imagePaths, label = 'Actor') {
    const mimeMap = { '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp' };
    const parts = [];

    for (const imgPath of imagePaths.slice(0, 6)) {
        if (!existsSync(imgPath)) continue;
        const stats = statSync(imgPath);
        if (stats.size === 0 || stats.size > 10 * 1024 * 1024) continue;

        const ext = extname(imgPath).toLowerCase();
        const mimeType = mimeMap[ext];
        if (!mimeType) continue;

        parts.push({
            inlineData: {
                data: readFileSync(imgPath).toString('base64'),
                mimeType,
            },
        });
    }

    if (parts.length > 0) {
        logger.info('ugc-script', `${label} reference: ${parts.length} photo(s) sent to Gemini`);
    }
    return parts;
}

export { UGC_ANGLE_STYLES, UGC_CONCEPTS, UGC_VISUAL_HOOKS, CONCEPT_KEYS, VISUAL_HOOK_KEYS };
