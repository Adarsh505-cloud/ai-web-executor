import re
import urllib.parse as urlparse
from typing import Dict
from playwright.sync_api import sync_playwright, Page, Locator

from .schemas import Plan
from .config import TEST_USERNAME, TEST_PASSWORD, ALLOWED_DOMAINS

def _domain_allowed(url: str) -> bool:
    try:
        parsed = urlparse.urlparse(url)
        host = (parsed.hostname or "").lower()
        return any(host.endswith(allowed) for allowed in ALLOWED_DOMAINS)
    except Exception:
        return False

def _mask(s: str) -> str:
    if not s: return s
    return re.sub(r".", "•", s)

def _get_robust_locator(page: Page, selector: str) -> Locator:
    """
    Translates AI-generated selectors into robust Playwright locators.
    Handles:
    - "element:contains('text')" -> get_by_role("element", name="text")
    - "element[label='text']"  -> get_by_label("text")
    - "text='text'"            -> get_by_text("text")
    """
    if not selector:
        raise ValueError("Selector cannot be empty")

    # 1. Try :contains('...')
    # e.g., "a:contains('Add Daily Timesheet')"
    contains_match = re.search(r"(\w+):contains\('(.+)'\)", selector)
    if contains_match:
        role = contains_match.group(1).lower()
        name = contains_match.group(2)
        if role == 'a':
            role = 'link'
        elif role == 'button':
            role = 'button'
        # Use exact=True for reliability
        return page.get_by_role(role, name=name, exact=True)

    # 2. Try [label='...']
    # e.g., "input[label='Project']"
    label_match = re.search(r"\w*\[label='(.+)'\]", selector) # Made \w* optional
    if label_match:
        label_text = label_match.group(1)
        # Use exact=True for reliability
        return page.get_by_label(label_text, exact=True)

    # 3. NEW: Try text='...'
    # e.g., "text='Quick Links'"
    text_match = re.search(r"^text='(.+)'$", selector)
    if text_match:
        text = text_match.group(1)
        return page.get_by_text(text, exact=True)

    # 4. Default to CSS selector
    # This handles #id, .class, and [placeholder='...']
    return page.locator(selector)



def run_plan(plan: Plan, secrets: Dict[str, str] | None = None, headed: bool = True, slow_mo_ms: int = 150):
    secrets = secrets or {"USERNAME": TEST_USERNAME, "PASSWORD": TEST_PASSWORD}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed, slow_mo=slow_mo_ms)
        context = browser.new_context(record_video_dir="artifacts/videos")
        page = context.new_page()

        # Start trace for debugging
        context.tracing.start(screenshots=True, snapshots=True, sources=False)

        try:
            step_num = 0
            for a in plan.actions:
                step_num += 1

                if a.type == "navigate":
                    if not a.value:
                        raise ValueError("navigate requires value=url")
                    if not _domain_allowed(a.value):
                        raise PermissionError(f"Blocked navigate to disallowed domain: {a.value}")
                    page.goto(a.value, wait_until="domcontentloaded", timeout=a.timeout_ms or 10000)
                    page.screenshot(path=f"artifacts/step_{step_num:02d}_navigate.png")

                elif a.type == "wait_for_selector":
                    # Get selector from either 'selector' or 'value' field
                    selector_str = a.selector or a.value
                    if not selector_str:
                        raise ValueError("wait_for_selector requires a selector in either 'selector' or 'value' field")
                    
                    locator = _get_robust_locator(page, selector_str) # Use new helper
                    locator.wait_for(timeout=a.timeout_ms or 10000)
                    page.screenshot(path=f"artifacts/step_{step_num:02d}_wait.png")

                elif a.type == "fill":
                    if not (a.selector and a.value is not None):
                        raise ValueError("fill requires selector and value")
                    value = a.value
                    if value == "{{USERNAME}}":
                        value = secrets["USERNAME"]
                    elif value == "{{PASSWORD}}":
                        value = secrets["PASSWORD"]

                    page.locator(a.selector).fill(value, timeout=a.timeout_ms or 10000)
                    # Mask secrets in artifact filename
                    safe_val = a.value
                    if safe_val in ("{{USERNAME}}", "{{PASSWORD}}"):
                        safe_val = _mask("secret")
                    page.screenshot(path=f"artifacts/step_{step_num:02d}_fill.png")

                elif a.type == "click":
                    if not a.selector:
                        raise ValueError("click requires selector")
                    
                    locator = _get_robust_locator(page, a.selector) # Use new helper
                    locator.click(timeout=a.timeout_ms or 10000)
                    page.screenshot(path=f"artifacts/step_{step_num:02d}_click.png")

                elif a.type == "assert_title":
                    if not a.value:
                        raise ValueError("assert_title requires value")
                    page.wait_for_timeout(300)
                    title = page.title()
                    assert a.value in title, f'Expected "{a.value}" in title, got "{title}"'
                    page.screenshot(path=f"artifacts/step_{step_num:02d}_assert.png")

                else:
                    raise ValueError(f"Unsupported action {a.type}")

        finally:
            # Save trace for post-mortem
            context.tracing.stop(path="artifacts/trace.zip")
            context.close()
            browser.close()
