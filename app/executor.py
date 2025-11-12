from __future__ import annotations

import re
import logging
import urllib.parse as urlparse
from typing import Dict, Optional
from pathlib import Path

from playwright.sync_api import sync_playwright, Page, Locator, TimeoutError as PlaywrightTimeoutError

from .schemas import Plan
from .config import (
    TEST_USERNAME, TEST_PASSWORD, ALLOWED_DOMAINS,
    DEFAULT_TIMEOUT, DEFAULT_NAVIGATION_TIMEOUT,
    SCREENSHOT_ON_FAILURE, MAX_RETRIES, RETRY_DELAY_MS,
    AUTOCOMPLETE_WAIT_MS
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def _domain_allowed(url: str) -> bool:
    try:
        parsed = urlparse.urlparse(url)
        host = (parsed.hostname or "").lower()
        return any(host.endswith(allowed) for allowed in ALLOWED_DOMAINS)
    except Exception as e:
        logger.error(f"Error parsing URL {url}: {e}")
        return False

def _mask(s: str) -> str:
    if not s:
        return s
    return re.sub(r".", "•", s)

def _get_robust_locator(page: Page, selector: str) -> Locator:
    # Special: direct textarea by id for worklog or similar
    if selector.lower() in [
        "textarea[label='worklog']",
        "textarea[label='work log']"
    ] or selector.lower().startswith("textarea"):
        if page.locator("#P1_WORK_LOG").count() == 1:
            return page.locator("#P1_WORK_LOG")
        return page.locator("textarea[name='P1_WORK_LOG'], textarea").first

    contains_match = re.search(r"(\w+):contains\(['\"]([^'\"]+)['\"]\)", selector, re.IGNORECASE)
    if contains_match:
        element_type = contains_match.group(1).lower()
        text_content = contains_match.group(2)
        logger.debug(f"Parsed contains selector: element={element_type}, text={text_content}")
        if element_type == 'a':
            return page.locator(f"a:has-text('{text_content}')").first
        elif element_type == 'button':
            try:
                locator = page.get_by_role("button", name=text_content, exact=True)
                if locator.count() > 0:
                    return locator
            except:
                pass
            return page.get_by_role("button", name=text_content, exact=False)
        elif element_type in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'div', 'p'):
            return page.get_by_text(text_content, exact=False)
        else:
            return page.get_by_text(text_content, exact=False)

    label_match = re.search(r"\w*\[label=['\"]([^'\"]+)['\"]\]", selector)
    if label_match:
        label_text = label_match.group(1)
        logger.debug(f"Using get_by_label for: {label_text}")
        return page.get_by_label(label_text, exact=True)

    text_match = re.search(r"^text=['\"]([^'\"]+)['\"]$", selector)
    if text_match:
        text = text_match.group(1)
        logger.debug(f"Using get_by_text for: {text}")
        return page.get_by_text(text, exact=True)

    logger.debug(f"Using CSS locator for: {selector}")
    return page.locator(selector)

def _inject_credentials(value: str, credentials: Dict[str, str]) -> str:
    if not value:
        return value
    for key, val in credentials.items():
        placeholder = f"{{{{{key}}}}}"
        if placeholder in value:
            value = value.replace(placeholder, val)
            logger.debug(f"Injected credential for {key}")
    return value

def _retry_action(func, max_retries: int = MAX_RETRIES, delay_ms: int = RETRY_DELAY_MS):
    for attempt in range(max_retries):
        try:
            return func()
        except PlaywrightTimeoutError as e:
            if attempt == max_retries - 1:
                logger.error(f"Action failed after {max_retries} attempts")
                raise
            wait_time = (delay_ms * (2 ** attempt)) / 1000
            logger.warning(f"Action failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s")
            import time
            time.sleep(wait_time)
        except Exception as e:
            logger.error(f"Non-retryable error: {type(e).__name__}: {e}")
            raise

def run_plan(
    plan: Plan,
    headed: bool = True,
    slow_mo_ms: int = 0,
    credentials: Optional[Dict[str, str]] = None
):
    if credentials is None:
        credentials = {
            "USERNAME": TEST_USERNAME,
            "PASSWORD": TEST_PASSWORD
        }
    artifacts_dir = Path("artifacts")
    videos_dir = artifacts_dir / "videos"
    traces_dir = artifacts_dir / "traces"
    for directory in [artifacts_dir, videos_dir, traces_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    logger.info(f"Starting plan execution with {len(plan.actions)} actions")
    logger.info(f"Mode: {'headed' if headed else 'headless'}, slow_mo={slow_mo_ms}ms")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not headed,
            slow_mo=slow_mo_ms
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(videos_dir),
            ignore_https_errors=True
        )
        context.set_default_timeout(DEFAULT_TIMEOUT)
        context.set_default_navigation_timeout(DEFAULT_NAVIGATION_TIMEOUT)
        page = context.new_page()
        context.tracing.start(screenshots=True, snapshots=True)
        try:
            for step_num, action in enumerate(plan.actions, start=1):
                logger.info(f"Step {step_num}/{len(plan.actions)}: {action.type} - {action.selector or action.value}")
                try:
                    if action.type == "navigate":
                        url = action.value
                        if not url:
                            raise ValueError("Navigate action requires a URL value")
                        if not _domain_allowed(url):
                            raise ValueError(f"Domain not allowed: {url}")
                        logger.info(f"Navigating to: {url}")
                        _retry_action(lambda: page.goto(url, wait_until="domcontentloaded"))
                        page.screenshot(path=str(artifacts_dir / f"step_{step_num:02d}_navigate.png"))
                    elif action.type == "wait":
                        wait_ms = None
                        if action.value is not None:
                            if isinstance(action.value, int):
                                wait_ms = action.value
                            elif isinstance(action.value, str):
                                try:
                                    wait_ms = int(action.value)
                                except ValueError:
                                    logger.warning(f"Invalid wait value '{action.value}'")
                                    wait_ms = action.timeout_ms or 2000
                        else:
                            wait_ms = action.timeout_ms or 2000
                        logger.info(f"Waiting for {wait_ms}ms")
                        page.wait_for_timeout(wait_ms)
                        page.screenshot(path=str(artifacts_dir / f"step_{step_num:02d}_wait.png"))
                    elif action.type == "wait_for_selector":
                        selector = action.value or action.selector
                        if not selector:
                            raise ValueError("wait_for_selector requires a selector")
                        logger.info(f"Waiting for selector: {selector}")
                        locator = _get_robust_locator(page, selector)
                        _retry_action(lambda: locator.wait_for(
                            state="visible",
                            timeout=action.timeout_ms or DEFAULT_TIMEOUT
                        ))
                    elif action.type == "fill":
                        if not action.selector:
                            raise ValueError("fill action requires a selector")
                        value = _inject_credentials(action.value or "", credentials)
                        is_sensitive = any(placeholder in (action.value or "") 
                                        for placeholder in ["{{USERNAME}}", "{{PASSWORD}}"])
                        display_value = _mask(value) if is_sensitive else value
                        logger.info(f"Filling '{action.selector}' with: {display_value}")
                        locator = _get_robust_locator(page, action.selector)
                        def fill_action():
                            try:
                                role = locator.get_attribute("role", timeout=2000) or ""
                                readonly = locator.get_attribute("readonly", timeout=2000)
                                is_combobox = role == "combobox" or readonly is not None
                            except:
                                is_combobox = False
                            locator.focus()
                            if is_combobox:
                                logger.debug("Detected combobox/readonly field, type value and select")
                                locator.fill("")
                                locator.type(value, delay=100)
                                page.wait_for_timeout(AUTOCOMPLETE_WAIT_MS)
                                try:
                                    option = page.locator(f"[role='option']:has-text('{value}')").first
                                    if option.is_visible(timeout=2000):
                                        option.click()
                                    else:
                                        page.keyboard.press("Enter")
                                except:
                                    page.keyboard.press("Enter")
                            else:
                                locator.wait_for(state="visible", timeout=action.timeout_ms or DEFAULT_TIMEOUT)
                                locator.fill(value)
                        _retry_action(fill_action)
                        screenshot_name = f"step_{step_num:02d}_fill_{_mask(value) if is_sensitive else 'input'}.png"
                        page.screenshot(path=str(artifacts_dir / screenshot_name))
                    elif action.type == "select":
                        if not action.selector:
                            raise ValueError("select action requires a selector")
                        value = action.value or ""
                        logger.info(f"Selecting '{value}' in '{action.selector}'")
                        locator = _get_robust_locator(page, action.selector)
                        def select_action():
                            if locator.is_hidden(timeout=2000):
                                logger.debug("Dropdown <select> is hidden, using visible input for custom APEX select")
                                visible_input = locator.locator("xpath=preceding-sibling::input[not(@type='hidden') and not(@readonly)] | following-sibling::input[not(@type='hidden') and not(@readonly)]").filter(has_text="").first
                                if not visible_input or visible_input.count() == 0:
                                    visible_input = locator.locator("xpath=../input[not(@type='hidden') and not(@readonly)]").first
                                visible_input.focus()
                                visible_input.fill("")
                                visible_input.type(value, delay=100)
                                page.wait_for_timeout(800)
                                page.keyboard.press("Enter")
                            else:
                                locator.select_option(label=value)
                        _retry_action(select_action)
                        page.screenshot(path=str(artifacts_dir / f"step_{step_num:02d}_select.png"))
                    elif action.type == "press_key":
                        key = str(action.value or "Tab")
                        logger.info(f"Pressing key: {key}")
                        page.keyboard.press(key)
                        page.wait_for_timeout(150)
                    elif action.type == "click":
                        if not action.selector:
                            raise ValueError("click action requires a selector")
                        logger.info(f"Clicking: {action.selector}")
                        locator = _get_robust_locator(page, action.selector)
                        def click_action():
                            locator.wait_for(state="visible", timeout=action.timeout_ms or DEFAULT_TIMEOUT)
                            locator.click()
                        _retry_action(click_action)
                        page.screenshot(path=str(artifacts_dir / f"step_{step_num:02d}_click.png"))
                    elif action.type == "assert_title":
                        expected = action.value
                        actual = page.title()
                        logger.info(f"Asserting title: expected='{expected}', actual='{actual}'")
                        if expected not in actual:
                            raise AssertionError(f"Title mismatch: expected '{expected}' in '{actual}'")
                    else:
                        logger.warning(f"Unknown action type: {action.type}")
                    logger.info(f"✓ Step {step_num} completed successfully")
                except Exception as step_error:
                    logger.error(f"✗ Step {step_num} failed: {type(step_error).__name__}: {step_error}")
                    if SCREENSHOT_ON_FAILURE:
                        failure_screenshot = artifacts_dir / f"step_{step_num:02d}_FAILURE.png"
                        page.screenshot(path=str(failure_screenshot))
                        logger.info(f"Failure screenshot saved: {failure_screenshot}")
                    raise
            logger.info("✓ Plan execution completed successfully")
        except Exception as e:
            logger.error(f"✗ Plan execution failed: {type(e).__name__}: {e}")
            raise
        finally:
            trace_path = traces_dir / "trace.zip"
            context.tracing.stop(path=str(trace_path))
            logger.info(f"Trace saved: {trace_path}")
            page.close()
            context.close()
            browser.close()
            logger.info(f"Artifacts saved in: {artifacts_dir}")
