"""High-level X.com browser actions using Playwright."""

import logging
import re

from core.playwright_browser import PlaywrightBrowser
from core import x_selectors as S

logger = logging.getLogger(__name__)


def _parse_metric(text: str) -> int:
    """Parse X.com metric strings like '1.2K', '350', '2M' into integers."""
    if not text:
        return 0
    text = text.strip().replace(",", "")
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    for suffix, mult in multipliers.items():
        if text.upper().endswith(suffix):
            try:
                return int(float(text[:-1]) * mult)
            except ValueError:
                return 0
    try:
        return int(text)
    except ValueError:
        return 0


class XActions:
    """Composed browser actions for X.com."""

    def __init__(self, browser: PlaywrightBrowser):
        self.b = browser

    async def ensure_on_x(self):
        """Make sure we're on x.com and logged in."""
        url = self.b.page.url
        if "x.com" not in url and "twitter.com" not in url:
            await self.b.goto("https://x.com")
        if not await self.b.is_logged_in():
            logger.error("Not logged into X — session expired")
            raise RuntimeError("X.com session expired — manual login required")

    async def compose_and_post(self, text: str) -> bool:
        """Compose and post a single tweet."""
        try:
            await self.ensure_on_x()
            await self.b.page.goto("https://x.com/compose/post", wait_until="networkidle", timeout=30000)
            await self.b.human_delay(3000, 5000)
            await self.b.wait_for(S.TWEET_TEXT_INPUT, timeout=15000)
            await self.b.type_text(S.TWEET_TEXT_INPUT, text, delay=20)
            await self.b.human_delay(500, 1000)
            await self.b.click(S.TWEET_BUTTON, timeout=5000)
            await self.b.human_delay(2000, 3000)
            logger.info("Tweet posted successfully")
            return True
        except Exception as e:
            logger.error("Failed to post tweet: %s", e)
            return False

    async def compose_and_post_with_image(self, text: str, image_path: str) -> bool:
        """Compose and post a tweet with an image."""
        try:
            await self.ensure_on_x()
            await self.b.goto("https://x.com/compose/post")
            await self.b.wait_for(S.TWEET_TEXT_INPUT, timeout=10000)

            # Upload image first
            await self.b.upload_file(S.MEDIA_INPUT, image_path)
            await self.b.human_delay(3000, 5000)

            # Type text
            await self.b.type_text(S.TWEET_TEXT_INPUT, text, delay=20)
            await self.b.human_delay(500, 1000)

            # Post
            await self.b.click(S.TWEET_BUTTON, timeout=5000)
            await self.b.human_delay(2000, 3000)
            logger.info("Tweet with image posted successfully")
            return True
        except Exception as e:
            logger.error("Failed to post tweet with image: %s", e)
            return False

    async def compose_and_post_thread(self, tweets: list[str]) -> bool:
        """Post a multi-tweet thread."""
        try:
            await self.ensure_on_x()
            await self.b.goto("https://x.com/compose/post")
            await self.b.wait_for(S.TWEET_TEXT_INPUT, timeout=10000)

            for i, tweet_text in enumerate(tweets):
                if i > 0:
                    # Click "+" to add another tweet
                    await self.b.click(S.ADD_TWEET_BUTTON, timeout=5000)
                    await self.b.human_delay(500, 1000)

                # Type into the latest text area
                text_areas = await self.b.query_all(S.TWEET_TEXT_INPUT)
                if text_areas:
                    last_area = text_areas[-1]
                    await last_area.click()
                    await self.b.page.keyboard.type(tweet_text, delay=20)
                    await self.b.human_delay(300, 600)

            # Post the thread
            await self.b.click(S.TWEET_BUTTON, timeout=5000)
            await self.b.human_delay(2000, 3000)
            logger.info("Thread posted (%d tweets)", len(tweets))
            return True
        except Exception as e:
            logger.error("Failed to post thread: %s", e)
            return False

    async def read_profile_context(self, username: str) -> str:
        """Read bio + latest post text from a user's profile for filtering.
        Assumes we're already on the profile page."""
        parts = []
        try:
            bio_el = await self.b.page.query_selector(S.PROFILE_BIO)
            if bio_el:
                parts.append((await bio_el.text_content() or "").strip())
        except Exception:
            pass
        try:
            tweets = await self.b.query_all(S.TWEET_ARTICLE)
            if tweets:
                text_el = await tweets[0].query_selector('[data-testid="tweetText"]')
                if text_el:
                    parts.append((await text_el.text_content() or "").strip())
        except Exception:
            pass
        return " ".join(parts)

    async def like_latest_post(self, username: str) -> bool:
        """Navigate to a user's profile and like their latest post."""
        try:
            await self.ensure_on_x()
            await self.b.goto(f"https://x.com/{username}")
            await self.b.wait_for(S.TWEET_ARTICLE, timeout=15000)
            await self.b.human_delay(1000, 2000)

            # Find the first tweet's like button
            tweets = await self.b.query_all(S.TWEET_ARTICLE)
            if not tweets:
                logger.warning("No tweets found for @%s", username)
                return False

            like_btn = await tweets[0].query_selector(S.LIKE_BUTTON)
            if like_btn:
                await like_btn.click()
                await self.b.human_delay(500, 1000)
                logger.info("Liked post from @%s", username)
                return True
            else:
                # Already liked
                logger.info("Post from @%s already liked", username)
                return True
        except Exception as e:
            logger.error("Failed to like post from @%s: %s", username, e)
            return False

    async def retweet_latest_post(self, username: str) -> bool:
        """Navigate to a user's profile and retweet their latest post."""
        try:
            await self.ensure_on_x()
            await self.b.goto(f"https://x.com/{username}")
            await self.b.wait_for(S.TWEET_ARTICLE, timeout=15000)
            await self.b.human_delay(1000, 2000)

            tweets = await self.b.query_all(S.TWEET_ARTICLE)
            if not tweets:
                return False

            rt_btn = await tweets[0].query_selector(S.RETWEET_BUTTON)
            if rt_btn:
                await rt_btn.click()
                await self.b.human_delay(500, 1000)
                # Click "Repost" in the dropdown
                await self.b.click(S.RETWEET_CONFIRM, timeout=5000)
                await self.b.human_delay(500, 1000)
                logger.info("Retweeted post from @%s", username)
                return True
            return True  # already retweeted
        except Exception as e:
            logger.error("Failed to retweet post from @%s: %s", username, e)
            return False

    async def reply_to_latest_post(self, username: str, text: str) -> bool:
        """Navigate to a user's profile, find a recent post, and reply to it."""
        try:
            await self.ensure_on_x()
            await self.b.goto(f"https://x.com/{username}")
            await self.b.wait_for(S.TWEET_ARTICLE, timeout=15000)
            await self.b.human_delay(1000, 2000)

            tweets = await self.b.query_all(S.TWEET_ARTICLE)
            if not tweets:
                return False

            # Click reply on the first tweet
            reply_btn = await tweets[0].query_selector(S.REPLY_BUTTON)
            if not reply_btn:
                return False

            await reply_btn.click()
            await self.b.human_delay(1000, 2000)

            # Type reply
            await self.b.wait_for(S.REPLY_TEXT_INPUT, timeout=10000)
            await self.b.type_text(S.REPLY_TEXT_INPUT, text, delay=20)
            await self.b.human_delay(500, 1000)

            # Submit
            await self.b.click(S.REPLY_SUBMIT, timeout=5000)
            await self.b.human_delay(2000, 3000)
            logger.info("Replied to @%s", username)
            return True
        except Exception as e:
            logger.error("Failed to reply to @%s: %s", username, e)
            return False

    async def get_mentions(self, max_count: int = 5) -> list[dict]:
        """Get recent mentions from notifications."""
        try:
            await self.ensure_on_x()
            await self.b.goto("https://x.com/notifications/mentions")
            await self.b.wait_for(S.TWEET_ARTICLE, timeout=15000)
            await self.b.human_delay(1000, 2000)

            tweets = await self.b.query_all(S.TWEET_ARTICLE)
            mentions = []
            for tweet in tweets[:max_count]:
                text_el = await tweet.query_selector('[data-testid="tweetText"]')
                text = (await text_el.text_content() or "") if text_el else ""
                mentions.append({"text": text.strip(), "element": tweet})

            logger.info("Found %d mentions", len(mentions))
            return mentions
        except Exception as e:
            logger.error("Failed to get mentions: %s", e)
            return []

    async def reply_to_mention(self, tweet_element, text: str) -> bool:
        """Reply to a specific mention tweet element."""
        try:
            reply_btn = await tweet_element.query_selector(S.REPLY_BUTTON)
            if not reply_btn:
                return False

            await reply_btn.click()
            await self.b.human_delay(1000, 2000)

            await self.b.wait_for(S.REPLY_TEXT_INPUT, timeout=10000)
            await self.b.type_text(S.REPLY_TEXT_INPUT, text, delay=20)
            await self.b.human_delay(500, 1000)

            await self.b.click(S.REPLY_SUBMIT, timeout=5000)
            await self.b.human_delay(2000, 3000)
            logger.info("Replied to mention")
            return True
        except Exception as e:
            logger.error("Failed to reply to mention: %s", e)
            return False

    async def read_latest_post_text(self, username: str) -> str:
        """Navigate to a user's profile and read their latest post's text."""
        try:
            await self.ensure_on_x()
            await self.b.goto(f"https://x.com/{username}")
            await self.b.wait_for(S.TWEET_ARTICLE, timeout=15000)
            await self.b.human_delay(1000, 2000)

            tweets = await self.b.query_all(S.TWEET_ARTICLE)
            if not tweets:
                return ""

            text_el = await tweets[0].query_selector('[data-testid="tweetText"]')
            text = (await text_el.text_content() or "") if text_el else ""
            logger.info("Read post from @%s: %s", username, text.strip()[:80])
            return text.strip()
        except Exception as e:
            logger.error("Failed to read post from @%s: %s", username, e)
            return ""

    async def get_trending_topics(self, max_count: int = 10) -> list[str]:
        """Scrape trending topics from X's Explore page."""
        try:
            await self.ensure_on_x()
            await self.b.goto("https://x.com/explore/tabs/trending")
            await self.b.human_delay(2000, 3000)

            # Trending topics are in span elements within the explore page
            trends = []
            # Try the trend containers
            trend_elements = await self.b.query_all('[data-testid="trend"] span')
            seen = set()
            for el in trend_elements:
                text = (await el.text_content() or "").strip()
                # Filter out metadata like "Trending", "1,234 posts", numbers
                if (text and len(text) > 2 and not text.startswith("Trending")
                        and not text.endswith("posts") and not text.replace(",", "").isdigit()
                        and text.lower() not in seen):
                    seen.add(text.lower())
                    trends.append(text)
                    if len(trends) >= max_count:
                        break

            logger.info("Found %d trending topics", len(trends))
            return trends
        except Exception as e:
            logger.debug("Failed to get trending topics: %s", e)
            return []

    async def get_smart_mentions(self, max_count: int = 10) -> list[dict]:
        """Get mentions with metadata for smart filtering."""
        try:
            await self.ensure_on_x()
            await self.b.goto("https://x.com/notifications/mentions")
            await self.b.wait_for(S.TWEET_ARTICLE, timeout=15000)
            await self.b.human_delay(1000, 2000)

            tweets = await self.b.query_all(S.TWEET_ARTICLE)
            mentions = []
            for tweet in tweets[:max_count]:
                text_el = await tweet.query_selector('[data-testid="tweetText"]')
                text = (await text_el.text_content() or "") if text_el else ""

                # Get author name
                author_el = await tweet.query_selector('[data-testid="User-Name"] a')
                author = ""
                if author_el:
                    href = await author_el.get_attribute("href")
                    author = href.strip("/") if href else ""

                # Get engagement as a quality signal
                like_el = await tweet.query_selector(S.METRIC_LIKE)
                likes = _parse_metric((await like_el.text_content()) if like_el else "")

                reply_el = await tweet.query_selector(S.METRIC_REPLY)
                replies = _parse_metric((await reply_el.text_content()) if reply_el else "")

                mentions.append({
                    "text": text.strip(),
                    "author": author,
                    "likes": likes,
                    "replies": replies,
                    "element": tweet,
                })

            logger.info("Found %d mentions", len(mentions))
            return mentions
        except Exception as e:
            logger.error("Failed to get mentions: %s", e)
            return []

    async def discover_accounts_from_feed(self, max_count: int = 20) -> list[dict]:
        """Discover new accounts from the For You feed."""
        try:
            await self.ensure_on_x()
            await self.b.goto("https://x.com/home")
            await self.b.wait_for(S.TWEET_ARTICLE, timeout=15000)
            await self.b.human_delay(1000, 2000)

            # Scroll a few times to load more tweets
            for _ in range(3):
                await self.b.scroll_down(800)
                await self.b.human_delay(1000, 2000)

            tweets = await self.b.query_all(S.TWEET_ARTICLE)
            accounts = {}
            for tweet in tweets:
                try:
                    # Get author link
                    author_el = await tweet.query_selector('[data-testid="User-Name"] a[role="link"]')
                    if not author_el:
                        continue
                    href = await author_el.get_attribute("href")
                    if not href:
                        continue
                    username = href.strip("/").split("/")[0] if "/" in href.strip("/") else href.strip("/")
                    if not username or username in accounts:
                        continue

                    # Get engagement metrics as quality signal
                    like_el = await tweet.query_selector(S.METRIC_LIKE)
                    likes = _parse_metric((await like_el.text_content()) if like_el else "")

                    rt_el = await tweet.query_selector(S.METRIC_RETWEET)
                    retweets = _parse_metric((await rt_el.text_content()) if rt_el else "")

                    accounts[username] = {
                        "username": username,
                        "engagement_signal": likes + retweets,
                    }
                except Exception:
                    continue

            result = sorted(accounts.values(), key=lambda a: a["engagement_signal"], reverse=True)
            logger.info("Discovered %d accounts from feed", len(result))
            return result[:max_count]
        except Exception as e:
            logger.error("Failed to discover accounts from feed: %s", e)
            return []

    async def discover_accounts_from_trending(self, max_count: int = 15) -> list[dict]:
        """Discover accounts from trending topics — find who's posting popular content."""
        try:
            await self.ensure_on_x()
            await self.b.goto("https://x.com/explore/tabs/trending")
            await self.b.human_delay(2000, 3000)

            # Click on first few trends to find active accounts
            trend_elements = await self.b.query_all('[data-testid="trend"]')
            accounts = {}

            for trend in trend_elements[:3]:
                try:
                    await trend.click()
                    await self.b.human_delay(2000, 3000)
                    await self.b.wait_for(S.TWEET_ARTICLE, timeout=10000)

                    tweets = await self.b.query_all(S.TWEET_ARTICLE)
                    for tweet in tweets[:5]:
                        try:
                            author_el = await tweet.query_selector('[data-testid="User-Name"] a[role="link"]')
                            if not author_el:
                                continue
                            href = await author_el.get_attribute("href")
                            if not href:
                                continue
                            username = href.strip("/").split("/")[0] if "/" in href.strip("/") else href.strip("/")
                            if not username or username in accounts:
                                continue

                            like_el = await tweet.query_selector(S.METRIC_LIKE)
                            likes = _parse_metric((await like_el.text_content()) if like_el else "")

                            accounts[username] = {
                                "username": username,
                                "engagement_signal": likes,
                                "source": "trending",
                            }
                        except Exception:
                            continue

                    # Go back to trending
                    await self.b.page.go_back()
                    await self.b.human_delay(1000, 2000)
                except Exception:
                    continue

            result = sorted(accounts.values(), key=lambda a: a["engagement_signal"], reverse=True)
            logger.info("Discovered %d accounts from trending", len(result))
            return result[:max_count]
        except Exception as e:
            logger.error("Failed to discover from trending: %s", e)
            return []

    async def get_account_info(self, username: str) -> dict | None:
        """Get follower count and bio from a profile page."""
        try:
            await self.ensure_on_x()
            await self.b.goto(f"https://x.com/{username}")
            await self.b.human_delay(1500, 2500)

            # Get follower count
            followers_text = ""
            follower_links = await self.b.query_all(f'a[href="/{username}/verified_followers"]')
            if not follower_links:
                follower_links = await self.b.query_all(f'a[href="/{username}/followers"]')
            if follower_links:
                followers_text = (await follower_links[0].text_content() or "").strip()

            followers = _parse_metric(followers_text.split()[0] if followers_text else "0")

            return {"username": username, "followers": followers}
        except Exception as e:
            logger.debug("Failed to get info for @%s: %s", username, e)
            return None

    # ── Campaign actions ──────────────────────────────────────

    async def get_tweet_replies(self, tweet_url: str, keyword: str, max_count: int = 50) -> list[str]:
        """Navigate to a tweet and scrape usernames who replied with a keyword."""
        try:
            await self.ensure_on_x()
            await self.b.goto(tweet_url)
            await self.b.wait_for(S.TWEET_ARTICLE, timeout=15000)
            await self.b.human_delay(2000, 3000)

            # Scroll to load replies
            for _ in range(5):
                await self.b.scroll_down(600)
                await self.b.human_delay(1000, 2000)

            tweets = await self.b.query_all(S.TWEET_ARTICLE)
            matched_users = []
            keyword_lower = keyword.lower()

            for tweet in tweets[1:]:  # skip the original tweet
                try:
                    text_el = await tweet.query_selector('[data-testid="tweetText"]')
                    text = (await text_el.text_content() or "") if text_el else ""

                    if keyword_lower in text.lower():
                        author_el = await tweet.query_selector('[data-testid="User-Name"] a[role="link"]')
                        if author_el:
                            href = await author_el.get_attribute("href")
                            if href:
                                username = href.strip("/").split("/")[0] if "/" in href.strip("/") else href.strip("/")
                                if username and username not in matched_users:
                                    matched_users.append(username)
                except Exception:
                    continue

                if len(matched_users) >= max_count:
                    break

            logger.info("Found %d replies with keyword '%s'", len(matched_users), keyword)
            return matched_users
        except Exception as e:
            logger.error("Failed to scrape replies: %s", e)
            return []

    async def check_if_following(self, username: str) -> bool | None:
        """Check if a user is following our account.

        Returns:
            True if following, False if not following,
            None if the account is suspended/unavailable (caller should skip).
        """
        try:
            await self.ensure_on_x()
            await self.b.goto(f"https://x.com/{username}")
            await self.b.human_delay(1500, 2500)

            page_text = await self.b.page.content()

            # Handle suspended / unavailable accounts
            if "Account suspended" in page_text:
                logger.info("@%s is suspended — skipping", username)
                return None
            if "This account doesn" in page_text and "exist" in page_text:
                logger.info("@%s does not exist — skipping", username)
                return None
            if "These tweets are protected" in page_text or "This account's Tweets are protected" in page_text:
                logger.info("@%s is protected/private — skipping", username)
                return None

            # Look for "Follows you" badge
            return "Follows you" in page_text
        except Exception as e:
            logger.debug("Failed to check follow status for @%s: %s", username, e)
            return None

    async def send_dm(self, username: str, message: str) -> bool:
        """Send a direct message to a user."""
        try:
            await self.ensure_on_x()
            await self.b.goto(f"https://x.com/messages")
            await self.b.human_delay(2000, 3000)

            # Click new message
            new_msg_btn = await self.b.page.query_selector('[data-testid="NewDM_Button"]')
            if not new_msg_btn:
                # Try the compose icon
                new_msg_btn = await self.b.page.query_selector('a[href="/messages/compose"]')
            if new_msg_btn:
                await new_msg_btn.click()
            else:
                await self.b.goto("https://x.com/messages/compose")
            await self.b.human_delay(1000, 2000)

            # Search for user
            search_input = await self.b.page.wait_for_selector(
                'input[data-testid="searchPeople"]', timeout=10000
            )
            await search_input.fill(username)
            await self.b.human_delay(1500, 2500)

            # Click the user result
            user_result = await self.b.page.wait_for_selector(
                f'[data-testid="typeaheadResult"]', timeout=10000
            )
            await user_result.click()
            await self.b.human_delay(500, 1000)

            # Click Next
            next_btn = await self.b.page.query_selector('[data-testid="nextButton"]')
            if next_btn:
                await next_btn.click()
                await self.b.human_delay(1000, 2000)

            # Type message
            msg_input = await self.b.page.wait_for_selector(
                '[data-testid="dmComposerTextInput"]', timeout=10000
            )
            await msg_input.fill(message)
            await self.b.human_delay(500, 1000)

            # Send
            send_btn = await self.b.page.query_selector('[data-testid="dmComposerSendButton"]')
            if send_btn:
                await send_btn.click()
                await self.b.human_delay(1000, 2000)
                logger.info("DM sent to @%s", username)
                return True

            return False
        except Exception as e:
            logger.error("Failed to DM @%s: %s", username, e)
            return False

    async def get_own_latest_tweet_url(self, username: str) -> str | None:
        """Get the URL of our most recent tweet."""
        try:
            await self.ensure_on_x()
            await self.b.goto(f"https://x.com/{username}")
            await self.b.wait_for(S.TWEET_ARTICLE, timeout=15000)
            await self.b.human_delay(1000, 2000)

            tweets = await self.b.query_all(S.TWEET_ARTICLE)
            if not tweets:
                return None

            # Find the tweet's permalink
            time_el = await tweets[0].query_selector("time")
            if time_el:
                parent = await time_el.evaluate_handle("el => el.closest('a')")
                if parent:
                    href = await parent.get_attribute("href")
                    if href:
                        return f"https://x.com{href}" if href.startswith("/") else href

            return None
        except Exception as e:
            logger.error("Failed to get latest tweet URL: %s", e)
            return None

    async def scrape_profile_metrics(self, username: str, max_posts: int = 10) -> list[dict]:
        """Scrape engagement metrics from a user's profile."""
        try:
            await self.ensure_on_x()
            await self.b.goto(f"https://x.com/{username}")
            await self.b.wait_for(S.TWEET_ARTICLE, timeout=15000)
            await self.b.human_delay(1000, 2000)

            tweets = await self.b.query_all(S.TWEET_ARTICLE)
            metrics = []
            for tweet in tweets[:max_posts]:
                text_el = await tweet.query_selector('[data-testid="tweetText"]')
                text = (await text_el.text_content() or "") if text_el else ""

                likes_el = await tweet.query_selector(S.METRIC_LIKE)
                likes = _parse_metric((await likes_el.text_content()) if likes_el else "")

                rt_el = await tweet.query_selector(S.METRIC_RETWEET)
                retweets = _parse_metric((await rt_el.text_content()) if rt_el else "")

                reply_el = await tweet.query_selector(S.METRIC_REPLY)
                replies = _parse_metric((await reply_el.text_content()) if reply_el else "")

                metrics.append({
                    "text": text.strip()[:100],
                    "likes": likes,
                    "retweets": retweets,
                    "replies": replies,
                })

            logger.info("Scraped metrics for %d posts from @%s", len(metrics), username)
            return metrics
        except Exception as e:
            logger.error("Failed to scrape metrics for @%s: %s", username, e)
            return []
