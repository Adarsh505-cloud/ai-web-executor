# AI Web Executor (Bedrock + Playwright)

## Setup (Mac)
```bash
# tools
xcode-select --install
brew install awscli python node

# clone and prepare
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install

# AWS creds (Bedrock access)
aws configure
