import os
import pytest

pytestmark = pytest.mark.e2e

# Skip if running in environment without display / CI without playwright
PLAYWRIGHT_DISABLED = os.environ.get("DISABLE_PLAYWRIGHT", "0") == "1"
pytest.skip(reason="Playwright disabled via DISABLE_PLAYWRIGHT env", allow_module_level=True) if PLAYWRIGHT_DISABLED else None

# These tests assume the Flask dev server is running at http://localhost:5001
BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5001")

@pytest.mark.parametrize("path", ["/", "/dashboard"]) 
@pytest.mark.playwright
async def test_minimize_expand(page, path):
    await page.goto(BASE_URL + path)
    trigger = page.locator('#assistantTriggerV2 button')
    # Ensure assistant initially minimized (trigger visible)
    await trigger.wait_for()
    # Open
    await trigger.click()
    panel = page.locator('#ai-assistant-v2')
    await page.wait_for_selector('#ai-assistant-v2:not(.minimized)')
    assert await panel.get_attribute('class').then(lambda c: 'minimized' not in c)
    # Minimize via header button
    await page.locator('#ai-assistant-v2 .btn-min').click()
    await page.wait_for_selector('#ai-assistant-v2.minimized')

@pytest.mark.playwright
async def test_enter_key_send(page):
    await page.goto(BASE_URL + '/')
    await page.locator('#assistantTriggerV2 button').click()
    textarea = page.locator('#ai-assistant-v2 textarea')
    await textarea.click()
    await textarea.fill('Test message one')
    await textarea.press('Enter')
    # User message bubble should appear
    await page.wait_for_selector('.user-msg .msg-text:has-text("Test message one")')

@pytest.mark.playwright
async def test_typing_indicator_lifecycle(page):
    await page.goto(BASE_URL + '/')
    await page.locator('#assistantTriggerV2 button').click()
    textarea = page.locator('#ai-assistant-v2 textarea')
    await textarea.fill('Trigger AI response')
    await textarea.press('Enter')
    typing = page.locator('#ai-assistant-v2 .typing')
    # Typing indicator should show quickly
    await typing.wait_for(state='attached')
    # It should hide after an AI message appears
    await page.wait_for_selector('.ai-msg .msg-text')
    assert await typing.get_attribute('hidden') is not None

@pytest.mark.playwright
async def test_scroll_anchor_behavior(page):
    await page.goto(BASE_URL + '/')
    await page.locator('#assistantTriggerV2 button').click()
    textarea = page.locator('#ai-assistant-v2 textarea')
    # Generate several messages to enable scrolling
    for i in range(8):
        await textarea.fill(f'Message {i}')
        await textarea.press('Enter')
    messages = page.locator('#ai-assistant-v2 .messages')
    # Scroll up a bit
    await messages.evaluate("el => { el.scrollTop = 0; }")
    # Send one more to trigger anchor logic (AI reply may appear asynchronously; we just check anchor existence change later)
    await textarea.fill('Final message')
    await textarea.press('Enter')
    anchor = page.locator('#ai-assistant-v2 .scroll-anchor')
    # Anchor should become visible (may wait for small delay due to DOM updates)
    await anchor.wait_for()
    assert await anchor.is_visible()
    # Click anchor and ensure we are near bottom afterward
    await anchor.click()
    bottom_check = await messages.evaluate("el => (el.scrollHeight - (el.scrollTop + el.clientHeight)) < 5")
    assert bottom_check
