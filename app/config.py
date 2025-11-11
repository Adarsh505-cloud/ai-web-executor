import os
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_MODEL = os.getenv("BEDROCK_MODEL", "anthropic.claude-3-5-haiku-20241022-v1:0")

TEST_USERNAME = os.getenv("TEST_USERNAME", "demo_user")
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "demo_pass")

ALLOWED_DOMAINS = [d.strip().lower() for d in os.getenv("ALLOWED_DOMAINS", "localhost,127.0.0.1").split(",")]
