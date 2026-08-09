"""TikTok web DOM selectors for video upload and engagement."""

# Upload flow (tiktok.com/upload)
UPLOAD_IFRAME = 'iframe[src*="upload"]'
FILE_INPUT = 'input[type="file"][accept*="video"]'
CAPTION_INPUT = '[data-testid="caption-input"], [contenteditable="true"].public-DraftEditor-content'
CAPTION_EDITOR = '.DraftEditor-root [contenteditable="true"]'
# NEVER use `button:has-text("Post")` here. Playwright's :has-text matches any element
# whose SUBTREE contains the text, and query_selector returns the first in DOM order —
# that is the left sidebar nav button (data-tt="Sidebar_Sidebar_Clickable"), not the
# submit. Clicking it navigates away and raises the "Are you sure you want to exit?"
# modal, so the video never publishes. Verified against live TikTok Studio 2026-08-08.
POST_BUTTON = '[data-e2e="post_video_button"]'
DISCARD_BUTTON = '[data-e2e="discard_post_button"]'
# Shown when a click navigates away from a composer holding an unsaved upload.
# Matched on the modal's own text, because 'button:has-text("Cancel")' alone would
# also match unrelated Cancel buttons elsewhere on the composer.
EXIT_CONFIRM_TEXT = "Are you sure you want to exit"
EXIT_CONFIRM_CANCEL = 'button:has-text("Cancel")'

# Audience control. TikTok remembers the LAST USED value per account, so a single
# manual "Friends"/"Only you" post from the phone would silently make every later
# automated post non-public. Never rely on the default — read it and set it.
VISIBILITY_LABEL = "Who can see this post"
VISIBILITY_PUBLIC = "Everyone"
SELECT_TRIGGER = '[class*="Select__trigger"]'
SELECT_OPTION = '[role="option"], [class*="Select__option"], li'

# Onboarding coach-marks render an overlay that swallows pointer events, which can
# block the Post click. Removed from the DOM before interacting with the composer.
JOYRIDE_NODES = '#react-joyride-portal, .react-joyride__overlay, .react-joyride__spotlight'

# Upload page elements
UPLOAD_BUTTON = '[data-testid="upload-button"], button:has-text("Select video")'
UPLOAD_SUCCESS = '[data-testid="upload-success"]'

# Feed
VIDEO_ITEM = '[data-testid="video-item"], article'
VIDEO_TEXT = '[data-testid="video-desc"]'

# Engagement
LIKE_BUTTON = '[data-testid="like-button"], [aria-label="Like"]'
COMMENT_BUTTON = '[data-testid="comment-button"], [aria-label="Comment"]'
COMMENT_INPUT = '[data-testid="comment-input"], [placeholder*="comment"]'
COMMENT_SUBMIT = '[data-testid="comment-submit"], [data-e2e="comment-post"]'

# Login detection
LOGIN_MODAL = '[data-testid="login-modal"]'
# A profile-icon probe on the home page used to live here. TikTok stopped rendering it,
# so it reported False on valid sessions. Presence of the Studio upload widget is the
# real signal: it only renders when authenticated (otherwise TikTok redirects to /login).
STUDIO_UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
STUDIO_CONTENT_URL = "https://www.tiktok.com/tiktokstudio/content"
