"""X.com DOM selectors — centralized so they're easy to update when X changes its UI."""

# Compose / Post
COMPOSE_BUTTON = '[data-testid="SideNav_NewTweet_Button"]'
TWEET_TEXT_INPUT = '[data-testid="tweetTextarea_0"]'
TWEET_BUTTON = '[data-testid="tweetButtonInline"], [data-testid="tweetButton"]'
ADD_TWEET_BUTTON = '[data-testid="addButton"]'
TWEET_TEXT_INPUT_THREAD = '[data-testid="tweetTextarea_0"]:last-of-type'

# Media
MEDIA_INPUT = '[data-testid="fileInput"]'

# Tweet actions (on individual tweets)
REPLY_BUTTON = '[data-testid="reply"]'
LIKE_BUTTON = '[data-testid="like"]'
UNLIKE_BUTTON = '[data-testid="unlike"]'
RETWEET_BUTTON = '[data-testid="retweet"]'
UNRETWEET_BUTTON = '[data-testid="unretweet"]'
RETWEET_CONFIRM = '[data-testid="retweetConfirm"]'

# Tweet container
TWEET_ARTICLE = 'article[data-testid="tweet"]'

# Reply composer (after clicking reply)
REPLY_TEXT_INPUT = '[data-testid="tweetTextarea_0"]'
REPLY_SUBMIT = '[data-testid="tweetButton"]'

# Navigation
NOTIFICATIONS_LINK = 'a[href="/notifications"]'
MENTIONS_TAB = 'a[href="/notifications/mentions"]'

# Login detection
USER_AVATAR = '[data-testid="AppTabBar_Profile_Link"]'
LOGIN_BUTTON = '[data-testid="loginButton"]'

# Metrics (within a tweet article)
METRIC_REPLY = '[data-testid="reply"] span span'
METRIC_RETWEET = '[data-testid="retweet"] span span, [data-testid="unretweet"] span span'
METRIC_LIKE = '[data-testid="like"] span span, [data-testid="unlike"] span span'
METRIC_VIEWS = 'a[href*="/analytics"] span span'

# Profile
PROFILE_TWEETS_TAB = '[data-testid="UserProfileSchema"]'
PROFILE_BIO = '[data-testid="UserDescription"]'
