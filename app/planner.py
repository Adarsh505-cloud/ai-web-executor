import json
from typing import Any, Dict
import boto3

from .schemas import Plan
from .config import AWS_REGION, BEDROCK_MODEL

SYSTEM_PROMPT = """You are a planner that converts a user's request into a SAFE, JSON-only plan.
Only use these actions:
- navigate(url)
- fill(selector, value)
- click(selector)
- wait_for_selector(selector, timeout_ms)
- assert_title(value)

Output STRICTLY as JSON:
{"actions":[ {"type":"navigate","value":"https://..."}, ... ]}

NEVER include real credentials. Use placeholders {{USERNAME}} and {{PASSWORD}}.
Use generic, stable CSS selectors if possible. If unsure, still output your best guess.
"""

def build_user_prompt(user_request: str) -> str:
    return f"""User request:
{user_request}

Constraints:
- Only use the specified actions.
- Do not include sensitive data. Use placeholders {{USERNAME}} / {{PASSWORD}}.
- Prefer stable selectors (ids, names, labels).
- Keep the plan short and deterministic.
"""

def _extract_text_from_bedrock_response(resp_body_bytes: bytes) -> str:
    # Bedrock "converse-like" structure for Anthropic models (invoke_model)
    out = json.loads(resp_body_bytes.decode("utf-8"))
    parts = out.get("content", [])
    text = ""
    for p in parts:
        if p.get("type") == "text":
            text += p.get("text", "")
    return text

def plan_with_bedrock(user_request: str) -> Plan:
    runtime = boto3.client("bedrock-runtime", region_name=AWS_REGION)

    body: Dict[str, Any] = {
        "anthropic_version": "bedrock-2023-05-31",
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": build_user_prompt(user_request)}]}
        ],
        "max_tokens": 800,
        "temperature": 0.2,
        "top_p": 0.95
    }

    resp = runtime.invoke_model(modelId=BEDROCK_MODEL, body=json.dumps(body))
    text = _extract_text_from_bedrock_response(resp["body"].read()).strip()

    # Try direct JSON; if model added extra text, try to slice out the JSON object
    try:
        return Plan.model_validate_json(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"Planner did not return JSON: {text}")
        json_only = text[start:end+1]
        return Plan.model_validate_json(json_only)
