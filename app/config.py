import os
from dotenv import load_dotenv

load_dotenv()

# AWS Configuration
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_MODEL = os.getenv("BEDROCK_MODEL", "anthropic.claude-3-5-haiku-20241022-v1:0")

# Test Credentials
TEST_USERNAME = os.getenv("TEST_USERNAME", "demo_user")
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "demo_pass")

# Security Configuration
ALLOWED_DOMAINS = [
    d.strip().lower() 
    for d in os.getenv(
        "ALLOWED_DOMAINS", 
        "localhost,127.0.0.1,oraclecloudapps.com"
    ).split(",")
]

# Playwright Configuration
DEFAULT_TIMEOUT = int(os.getenv("DEFAULT_TIMEOUT", "30000"))
DEFAULT_NAVIGATION_TIMEOUT = int(os.getenv("DEFAULT_NAVIGATION_TIMEOUT", "60000"))
SCREENSHOT_ON_FAILURE = os.getenv("SCREENSHOT_ON_FAILURE", "true").lower() == "true"

# Retry Configuration
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY_MS = int(os.getenv("RETRY_DELAY_MS", "1000"))

# Autocomplete Configuration
AUTOCOMPLETE_WAIT_MS = int(os.getenv("AUTOCOMPLETE_WAIT_MS", "1000"))
