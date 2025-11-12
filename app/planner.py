from __future__ import annotations

import json
import time
import logging
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError, BotoCoreError

from .schemas import Plan
from .config import AWS_REGION, BEDROCK_MODEL

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a planner that converts a user's request into a SAFE, JSON-only plan.

Only use these actions:
- navigate(url) - value: string URL (use EXACT URL provided by user)
- fill(selector, value) - value: string to fill (handles both inputs and autocomplete)
- click(selector) - no value needed
- wait_for_selector(selector, timeout_ms) - value: selector string
- assert_title(value) - value: string title
- wait(timeout_ms) - value: integer milliseconds
- select(selector, value) - value: string option to select (for <select> dropdowns)
- press_key(key) - value: key name like "Enter", "Tab", "Escape"

Output STRICTLY as JSON:
{"actions":[ {"type":"navigate","value":"https://..."}, {"type":"wait","value":3000}, ... ]}

IMPORTANT RULES:
1. If user provides a specific URL with session ID, use it EXACTLY as given
2. If user mentions specific button IDs or selectors, use them exactly
3. For autocomplete fields (Project, Service, Task), use fill action with the value
4. For standard dropdowns (Status, Work Mode, Shift), use select action
5. Use wait action after navigation or before interacting with dynamic content
6. For wait actions, value should be integer milliseconds
7. NEVER include real credentials - use {{USERNAME}} and {{PASSWORD}} placeholders

Selector best practices:
- Button IDs: #buttonId
- Input placeholders: input[placeholder='Username']
- Labels: input[label='Field Name'] or select[label='Dropdown Name']
- Links: a:contains('Link Text')
- Buttons: button:contains('Button Text')
- Text areas: textarea[label='Field Name']

Keep plans short, deterministic, and robust.
"""

def build_user_prompt(user_request: str) -> str:
    return f"""User request:
{user_request}

Constraints:
- Only use the specified actions
- Do not include sensitive data - use placeholders {{{{USERNAME}}}} and {{{{PASSWORD}}}}
- Prefer stable selectors (IDs, placeholders, labels)
- Use wait() after login and before form interactions
- For autocomplete fields, use fill action (they will auto-select)
- For standard dropdowns, use select action
"""

def _extract_text_from_bedrock_response(resp_body_bytes: bytes) -> str:
    """Extract text content from Bedrock response for Anthropic models."""
    try:
        out = json.loads(resp_body_bytes.decode("utf-8"))
        parts = out.get("content", [])
        text = ""
        for p in parts:
            if p.get("type") == "text":
                text += p.get("text", "")
        return text
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Failed to decode Bedrock response: {e}")
        raise ValueError(f"Invalid response from Bedrock: {e}")

def plan_with_bedrock(user_request: str, max_retries: int = 3) -> Plan:
    """
    Generate an execution plan using AWS Bedrock (Claude).
    
    Args:
        user_request: Natural language description of the automation task
        max_retries: Maximum number of retry attempts for transient failures
        
    Returns:
        Plan: Validated plan with list of actions to execute
        
    Raises:
        ValueError: If the response cannot be parsed as valid JSON
        RuntimeError: If all retry attempts are exhausted
        ClientError: For non-retryable AWS API errors
    """
    runtime = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    
    body: Dict[str, Any] = {
        "anthropic_version": "bedrock-2023-05-31",
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": build_user_prompt(user_request)}]}
        ],
        "max_tokens": 1200,
        "temperature": 0.1,
        "top_p": 0.9
    }
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Requesting plan from Bedrock (attempt {attempt + 1}/{max_retries})")
            
            resp = runtime.invoke_model(modelId=BEDROCK_MODEL, body=json.dumps(body))
            text = _extract_text_from_bedrock_response(resp["body"].read()).strip()
            
            logger.debug(f"Bedrock raw response: {text[:200]}...")
            
            # Try direct JSON parsing first
            try:
                plan = Plan.model_validate_json(text)
                logger.info(f"Successfully generated plan with {len(plan.actions)} actions")
                return plan
            except Exception as parse_error:
                logger.warning(f"Direct JSON parsing failed, attempting extraction: {parse_error}")
                
                # Try to extract JSON object from response
                start = text.find("{")
                end = text.rfind("}")
                
                if start == -1 or end == -1:
                    raise ValueError(f"No JSON object found in response: {text}")
                
                json_only = text[start:end+1]
                plan = Plan.model_validate_json(json_only)
                logger.info(f"Successfully extracted and validated plan with {len(plan.actions)} actions")
                return plan
                
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            
            if error_code == 'ThrottlingException':
                wait_time = (2 ** attempt)
                logger.warning(f"Throttled by Bedrock API, retrying in {wait_time}s")
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                    continue
                else:
                    raise RuntimeError(f"Exhausted retries due to throttling: {error_message}")
                    
            elif error_code == 'ValidationException':
                logger.error(f"Invalid request to Bedrock: {error_message}")
                raise ValueError(f"Invalid Bedrock request: {error_message}")
                
            elif error_code == 'ModelNotReadyException':
                wait_time = (2 ** attempt)
                logger.warning(f"Model not ready, retrying in {wait_time}s")
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                    continue
                else:
                    raise RuntimeError(f"Model not ready after {max_retries} attempts")
                    
            elif error_code in ['ServiceUnavailableException', 'InternalServerException']:
                wait_time = (2 ** attempt)
                logger.warning(f"Service error ({error_code}), retrying in {wait_time}s")
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                    continue
                else:
                    raise RuntimeError(f"Service unavailable after {max_retries} attempts: {error_message}")
            else:
                logger.error(f"Non-retryable Bedrock error ({error_code}): {error_message}")
                raise
                
        except BotoCoreError as e:
            logger.error(f"Boto3 core error: {e}")
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt)
                logger.info(f"Retrying after boto3 error in {wait_time}s")
                time.sleep(wait_time)
                continue
            else:
                raise RuntimeError(f"Boto3 error after {max_retries} attempts: {e}")
                
        except ValueError as e:
            logger.error(f"Failed to parse Bedrock response as valid plan: {e}")
            raise
            
        except Exception as e:
            logger.error(f"Unexpected error in planner: {type(e).__name__}: {e}")
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt)
                logger.info(f"Retrying after unexpected error in {wait_time}s")
                time.sleep(wait_time)
                continue
            else:
                raise RuntimeError(f"Unexpected error after {max_retries} attempts: {e}")
    
    raise RuntimeError(f"Failed to generate plan after {max_retries} attempts")
