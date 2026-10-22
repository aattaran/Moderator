"""Facebook DOM selectors — aria-label and role based for stability."""

# Group post composer
CREATE_POST_PROMPT = '[role="button"]:has-text("Write something")'
CREATE_POST_PROMPT_ALT = '[aria-label="Write something..."]'
POST_TEXT_INPUT = '[role="dialog"] [role="textbox"][contenteditable="true"]'
POST_SUBMIT = '[aria-label="Post"]'
POST_SUBMIT_ALT = 'div[role="button"]:has-text("Post")'

# Feed
POST_ARTICLE = '[role="article"]'
POST_TEXT = '[data-ad-comet-preview="message"]'

# Engagement
LIKE_BUTTON = '[aria-label="Like"]'
COMMENT_BUTTON = '[aria-label="Comment"]'
COMMENT_INPUT = '[aria-label="Write a comment…"], [aria-label="Write a comment..."]'
COMMENT_SUBMIT = '[aria-label="Comment"], [aria-label="Submit"]'
SHARE_BUTTON = '[aria-label="Share"]'

# Member management
MEMBER_REQUESTS_TAB = 'a[href*="/member-requests"]'
APPROVE_BUTTON = '[aria-label="Approve"]'
DECLINE_BUTTON = '[aria-label="Decline"]'

# Navigation / login detection
PROFILE_LINK = '[aria-label="Your profile"]'
LOGIN_FORM = '#email'
