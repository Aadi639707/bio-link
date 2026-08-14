import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Owner IDs - only these users can use owner-level commands
OWNER_IDS = [5240784608, 8306853454]

DEVELOPER_USERNAME = "rushdeveloper"
CHANNEL_INVITE = "https://t.me/rushbots"

# Number of warnings before mute
MAX_WARNINGS = 3
