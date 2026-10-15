"""Instagram DOM selectors — mobile web interface."""

# Post creation
CREATE_POST_BUTTON = '[aria-label="New post"], svg[aria-label="New post"]'
FILE_INPUT = 'input[type="file"][accept*="image"]'
NEXT_BUTTON = 'button:has-text("Next"), div[role="button"]:has-text("Next")'
CAPTION_INPUT = '[aria-label="Write a caption..."], [data-testid="creation-caption-text"]'
SHARE_BUTTON = 'button:has-text("Share"), div[role="button"]:has-text("Share")'

# Feed
POST_ARTICLE = 'article'
POST_IMAGE = 'article img'
POST_TEXT = 'article span'

# Engagement
LIKE_BUTTON = '[aria-label="Like"], svg[aria-label="Like"]'
UNLIKE_BUTTON = '[aria-label="Unlike"], svg[aria-label="Unlike"]'
COMMENT_INPUT = '[aria-label="Add a comment…"], [aria-label="Add a comment..."], textarea[placeholder="Add a comment…"]'
COMMENT_SUBMIT = '[data-testid="post-comment-input-button"], button[type="submit"]'

# Navigation
HOME_LINK = '[aria-label="Home"]'
PROFILE_LINK = 'img[data-testid="user-avatar"]'

# Login detection
LOGIN_FORM = 'input[name="username"]'
