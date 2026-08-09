# Moderator

Autonomous social media agent that posts, engages, and grows your X (Twitter) account 24/7. Runs as your digital twin — build-in-public style.

## What it does

- **Posts tweets, threads, and image posts** 8x/day at random hours using Gemini 2.5 Flash
- **Comments on target accounts** with context-aware replies (reads the post first)
- **Likes and retweets** from discovered accounts
- **Replies to mentions** with smart filtering (skip spam, prioritize quality)
- **Discovers new accounts** from feed and trending topics
- **Runs freebie campaigns** — post giveaway tweet, monitor replies, auto-DM download links
- **Learns from engagement** — adaptive weights adjust styles, topics, and post types
- **Self-reflects** — every 3 days, Gemini analyzes posts and evolves style guidelines

## Architecture

```
Gemini 2.5 Flash (content) → Playwright (browser) → X.com
     ↕                              ↕
  SQLite DB ←── Weight Manager ←── Metrics Scraper
     ↕
  Content Reflector (every 3 days)
```

- **No Anthropic API** — Gemini for all content generation
- **No X API** — Playwright browser automation with auth cookies
- **Runs in Docker** on a $12/month DigitalOcean droplet

## Stack

Python 3.11 | Playwright (Chromium) | Gemini 2.5 Flash | APScheduler | SQLite WAL | Docker

## Quick Start

```bash
# 1. Clone and configure
git clone https://github.com/aattaran/Moderator.git && cd Moderator
cp .env.example .env   # edit — set GEMINI_API_KEY

# 2. Export X.com session from Chrome (close Chrome first)
python scripts/export_session.py

# 3. Build and run
docker compose build && docker compose up -d

# 4. Check logs
docker compose logs --tail 30
```

## CLI

```bash
python main.py run                      # Continuous scheduled mode
python main.py post                     # Single tweet
python main.py engage                   # Engagement cycle
python main.py reflect                  # Content reflection
python main.py status                   # Show status + weights
python main.py campaign launch skills   # Launch freebie campaign
python main.py campaign status          # Campaign stats
```

## Freebie Campaigns

Growth hack: post valuable content, users reply with keyword + follow, bot auto-DMs download link.

| Campaign | Keyword | What they get |
|----------|---------|---------------|
| `skills` | SKILLS | 7 Claude Code skills (debug, review, audit, etc.) |
| `fleet` | FLEET | Fleet Commander plugin for agent teams |
| `ppc` | PPC | Amazon PPC automation rules |
| `video` | VIDEO | AI video ad pipeline templates |
| `setup` | SETUP | Solo founder AI dev setup |

## Smart Feedback Loop

1. **Day 1**: Seed guidelines (proven patterns)
2. **Day 5+**: First reflection — analyzes own posts
3. **Every 3 days**: Guidelines evolve from engagement data
4. **Continuous**: Weights shift toward what works

## Deployment

DigitalOcean droplet (1 vCPU, 2GB RAM, $12/month):

```bash
ssh -i ~/.ssh/id_moderator root@SERVER_IP "cd /opt/moderator && docker compose logs --tail 30"
```
