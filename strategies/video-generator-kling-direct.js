/**
 * Kling Direct API — image-to-video generation.
 *
 * Uses Kling's direct REST API (https://api-singapore.klingai.com)
 * instead of fal.ai proxy. ~40-60% cheaper.
 *
 * Auth: JWT (HS256) from Kling_ACCESS_KEY_ID + Kling_SECRET_KEY
 * Flow: submit task → poll status → download video
 */

import jwt from 'jsonwebtoken';
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { join, basename } from 'path';
import { config } from './utils/config.js';
import { logger } from './utils/logger.js';

const BASE_URL = 'https://api-singapore.klingai.com';
const POLL_INTERVAL_MS = 5000;
const MAX_POLL_MS = 10 * 60 * 1000; // 10 min timeout

// ─── JWT Token ──────────────────────────────────────────

let cachedToken = null;
let tokenExpiry = 0;

function getToken() {
    const now = Math.floor(Date.now() / 1000);
    if (cachedToken && now < tokenExpiry - 60) return cachedToken; // 1 min buffer

    const ak = process.env.Kling_ACCESS_KEY_ID || config.klingAccessKey;
    const sk = process.env.Kling_SECRET_KEY || config.klingSecretKey;
    if (!ak || !sk) throw new Error('Missing Kling_ACCESS_KEY_ID or Kling_SECRET_KEY in .env');

    tokenExpiry = now + 1800; // 30 min
    cachedToken = jwt.sign(
        { iss: ak, exp: tokenExpiry, nbf: now - 5 },
        sk,
        { algorithm: 'HS256', header: { alg: 'HS256', typ: 'JWT' } }
    );
    return cachedToken;
}

function headers() {
    return {
        'Authorization': `Bearer ${getToken()}`,
        'Content-Type': 'application/json',
    };
}

// ─── Core API ───────────────────────────────────────────

async function submitImageToVideo({ image, prompt, negativePrompt, model = 'kling-v3', mode = 'pro', duration = '5', aspectRatio = '9:16', sound = 'on' }) {
    const body = {
        model_name: model,
        mode,
        image,
        prompt,
        duration: String(duration),
        aspect_ratio: aspectRatio,
    };
    if (negativePrompt) body.negative_prompt = negativePrompt;
    if (sound) body.sound = sound;

    const res = await fetch(`${BASE_URL}/v1/videos/image2video`, {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify(body),
    });
    const data = await res.json();

    if (data.code !== 0) {
        throw new Error(`Kling submit failed (${data.code}): ${data.message}`);
    }

    return data.data.task_id;
}

async function pollTask(taskId) {
    const startMs = Date.now();
    let pollCount = 0;

    while (Date.now() - startMs < MAX_POLL_MS) {
        const res = await fetch(`${BASE_URL}/v1/videos/image2video/${taskId}`, {
            headers: headers(),
        });
        const data = await res.json();

        if (data.code !== 0) {
            throw new Error(`Kling poll failed (${data.code}): ${data.message}`);
        }

        const status = data.data.task_status;

        if (status === 'succeed') {
            return data.data.task_result;
        }
        if (status === 'failed') {
            throw new Error(`Kling task failed: ${data.data.task_status_msg || 'unknown'}`);
        }

        pollCount++;
        if (pollCount % 6 === 0) {
            logger.info('kling-direct', `  Still generating... (${Math.round((Date.now() - startMs) / 1000)}s)`);
        }

        await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
    }

    throw new Error(`Kling task timed out after ${MAX_POLL_MS / 1000}s`);
}

async function submitVideoExtend({ videoId, prompt, negativePrompt }) {
    const body = { video_id: videoId };
    if (prompt) body.prompt = prompt;
    if (negativePrompt) body.negative_prompt = negativePrompt;

    const res = await fetch(`${BASE_URL}/v1/videos/video-extend`, {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify(body),
    });
    const data = await res.json();

    if (data.code !== 0) {
        throw new Error(`Kling extend failed (${data.code}): ${data.message}`);
    }

    return data.data.task_id;
}

async function pollExtendTask(taskId) {
    const startMs = Date.now();
    let pollCount = 0;

    while (Date.now() - startMs < MAX_POLL_MS) {
        const res = await fetch(`${BASE_URL}/v1/videos/video-extend/${taskId}`, {
            headers: headers(),
        });
        const data = await res.json();

        if (data.code !== 0) {
            throw new Error(`Kling extend poll failed (${data.code}): ${data.message}`);
        }

        const status = data.data.task_status;

        if (status === 'succeed') {
            return data.data.task_result;
        }
        if (status === 'failed') {
            throw new Error(`Kling extend failed: ${data.data.task_status_msg || 'unknown'}`);
        }

        pollCount++;
        if (pollCount % 6 === 0) {
            logger.info('kling-direct', `  Extending... (${Math.round((Date.now() - startMs) / 1000)}s)`);
        }

        await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
    }

    throw new Error(`Kling extend timed out after ${MAX_POLL_MS / 1000}s`);
}

async function downloadVideo(url, outputPath) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Download failed: ${res.status}`);
    const buf = Buffer.from(await res.arrayBuffer());
    writeFileSync(outputPath, buf);
    return outputPath;
}

// ─── Public API ─────────────────────────────────────────

/**
 * Generate a single video clip from a start frame image.
 *
 * @param {object} options
 * @param {string} options.startFramePath - Path to start frame image
 * @param {string} options.prompt - Text prompt for video generation
 * @param {string} [options.negativePrompt] - What to avoid
 * @param {string} [options.model='kling-v3'] - Model name
 * @param {string} [options.mode='pro'] - 'std' or 'pro'
 * @param {number} [options.duration=5] - Initial generation: 5 or 10 seconds
 * @param {number} [options.targetDuration=0] - Target total duration (0 = no extend). Each extend adds ~4-5s.
 * @param {string} [options.aspectRatio='9:16']
 * @param {string} [options.outputPrefix='kling_direct']
 * @returns {Promise<string>} Path to generated MP4
 */
export async function generateClipDirect(options = {}) {
    const {
        startFramePath,
        prompt,
        negativePrompt = 'blur, distort, low quality, text overlay, watermark, subtitles, captions',
        model = 'kling-v3',
        mode = 'pro',
        duration = 5,
        targetDuration = 0,
        aspectRatio = '9:16',
        outputPrefix = 'kling_direct',
    } = options;

    if (!startFramePath || !existsSync(startFramePath)) {
        throw new Error(`Start frame not found: ${startFramePath}`);
    }

    const outputDir = config.paths.clips;
    mkdirSync(outputDir, { recursive: true });
    const outputPath = join(outputDir, `${outputPrefix}.mp4`);

    const initialDuration = Math.min(duration, 10); // Kling max initial is 10s
    logger.info('kling-direct', `Generating clip: ${model} ${mode}, ${initialDuration}s${targetDuration > initialDuration ? ` → extend to ${targetDuration}s` : ''}, ${aspectRatio}`);
    logger.info('kling-direct', `  Prompt: "${prompt.substring(0, 100)}..."`);
    logger.info('kling-direct', `  Start frame: ${basename(startFramePath)}`);

    // Encode image as base64
    const imageBase64 = readFileSync(startFramePath).toString('base64');

    // Submit initial generation
    const taskId = await submitImageToVideo({
        image: imageBase64,
        prompt,
        negativePrompt,
        model,
        mode,
        duration: String(initialDuration),
        aspectRatio,
        sound: 'on',
    });
    logger.info('kling-direct', `  Task submitted: ${taskId}`);

    // Poll initial generation
    const result = await pollTask(taskId);
    const videoUrl = result.videos?.[0]?.url;
    const videoId = result.videos?.[0]?.id;
    if (!videoUrl) throw new Error('Kling returned no video URL');

    let currentDuration = result.videos[0].duration || initialDuration;
    let currentVideoUrl = videoUrl;
    let currentVideoId = videoId;

    // Extend if targetDuration is set and we haven't reached it
    if (targetDuration > 0 && currentDuration < targetDuration) {
        logger.info('kling-direct', `  Initial clip: ${currentDuration}s — extending to ${targetDuration}s...`);

        while (currentDuration < targetDuration - 2) { // 2s buffer — each extend adds ~4-5s
            const extendTaskId = await submitVideoExtend({
                videoId: currentVideoId,
                prompt,
                negativePrompt,
            });
            logger.info('kling-direct', `  Extend submitted: ${extendTaskId} (current: ${currentDuration}s)`);

            const extResult = await pollExtendTask(extendTaskId);
            const extVideo = extResult.videos?.[0];
            if (!extVideo?.url) throw new Error('Kling extend returned no video');

            currentVideoUrl = extVideo.url;
            currentVideoId = extVideo.id;
            currentDuration = extVideo.duration || (currentDuration + 4);
            logger.info('kling-direct', `  Extended to ${currentDuration}s`);
        }
    }

    logger.info('kling-direct', `  Downloading (${currentDuration}s)...`);
    await downloadVideo(currentVideoUrl, outputPath);
    logger.success('kling-direct', `  Saved: ${outputPath} (${currentDuration}s)`);

    return outputPath;
}

/**
 * Generate multiple clips in parallel (separate shots mode).
 *
 * @param {Array<{startFramePath: string, prompt: string, outputPrefix: string}>} clips
 * @param {object} sharedOptions - model, mode, duration, aspectRatio, negativePrompt
 * @returns {Promise<string[]>} Paths to generated MP4s
 */
export async function generateClipsBatchDirect(clips, sharedOptions = {}) {
    const {
        model = 'kling-v3',
        mode = 'pro',
        duration = 8,
        targetDuration = 0,
        aspectRatio = '9:16',
        negativePrompt = 'blur, distort, low quality, text overlay, watermark, subtitles, captions',
    } = sharedOptions;

    logger.divider(`KLING DIRECT — ${clips.length} clips in parallel`);
    logger.info('kling-direct', `Model: ${model} ${mode}, ${duration}s${targetDuration > duration ? ` → extend to ${targetDuration}s` : ''}, ${aspectRatio}`);

    const results = await Promise.allSettled(
        clips.map(clip => generateClipDirect({
            ...clip,
            model,
            mode,
            duration,
            targetDuration,
            aspectRatio,
            negativePrompt,
        }))
    );

    const paths = [];
    results.forEach((r, i) => {
        if (r.status === 'fulfilled') {
            paths.push(r.value);
        } else {
            logger.error('kling-direct', `  Clip ${i + 1} failed: ${r.reason.message}`);
            paths.push(null);
        }
    });

    const successCount = paths.filter(Boolean).length;
    logger.info('kling-direct', `${successCount}/${clips.length} clips generated`);

    return paths;
}

/**
 * Check account balance.
 * @returns {Promise<object>} Account info
 */
export async function checkBalance() {
    const now = Date.now();
    const res = await fetch(
        `${BASE_URL}/account/costs?start_time=${now - 86400000 * 30}&end_time=${now}`,
        { headers: headers() }
    );
    const data = await res.json();
    if (data.code !== 0) throw new Error(`Account check failed: ${data.message}`);

    const packs = data.data.resource_pack_subscribe_infos || [];
    packs.forEach(p => {
        logger.info('kling-direct', `  Plan: ${p.resource_pack_name} — ${p.remaining_quantity}/${p.total_quantity} units remaining`);
    });

    return packs;
}
