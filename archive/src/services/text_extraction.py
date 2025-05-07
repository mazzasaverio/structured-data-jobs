import logfire
from src.utils.browser import setup_browser
from playwright.async_api import Page
import asyncio


async def extract_content(url: str) -> str:
    """
    Extract text content from a job posting URL in a format suitable for LLM processing.

    Args:
        url (str): The URL of the job posting to extract content from

    Returns:
        str: The extracted text content with preserved URLs and structure
    """
    logfire.info(f"Extracting content from URL: {url}")

    try:
        # Setup browser
        playwright, browser, context = await setup_browser(headless=True)

        try:
            # Open the page
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=60000)
            logfire.info(f"Page loaded: {url}")

            # Extract page content
            page_content = await _extract_page_content(page, url)

            return page_content
        finally:
            # Clean up resources
            await context.close()
            await browser.close()
            await playwright.stop()

    except Exception as e:
        logfire.error(f"Error extracting content from {url}: {str(e)}", exc_info=True)
        return f"ERROR: Failed to extract content from {url}. Error: {str(e)}"


async def _extract_page_content(page: Page, url: str) -> str:
    """
    Extract page content including text and URLs in a structured format.

    Args:
        page (Page): The Playwright page object
        url (str): The URL of the page

    Returns:
        str: Structured content with preserved formatting and URLs
    """
    try:
        # Wait for the page to load completely
        await page.wait_for_load_state("networkidle", timeout=30000)

        # Try to expand any "Show more" or similar buttons
        expand_selectors = [
            "button:text-matches('(show|load|view) more', 'i')",
            "a:text-matches('(show|load|view) more', 'i')",
            "button:text-matches('expand', 'i')",
            "a:text-matches('expand', 'i')",
            "button:text-matches('see all', 'i')",
            "a:text-matches('see all', 'i')",
        ]

        for selector in expand_selectors:
            try:
                elements = await page.locator(selector).all()
                for element in elements:
                    try:
                        await element.click()
                        await asyncio.sleep(1)
                    except Exception as click_error:
                        logfire.warning(f"Failed to click element: {str(click_error)}")
            except Exception:
                pass

        # Extract page title
        title = await page.title()

        # Extract content with text and links preserved
        full_content = await page.evaluate(
            """() => {
            function getTextAndLinksRecursive(node, result = []) {
                if (node.nodeType === Node.TEXT_NODE) {
                    const text = node.textContent.trim();
                    if (text) {
                        result.push({ type: 'text', content: text });
                    }
                } else if (node.nodeType === Node.ELEMENT_NODE && node.tagName === 'A' && node.href) {
                    // For links, capture both text and URL
                    const text = node.innerText.trim();
                    if (text) {
                        result.push({ 
                            type: 'link', 
                            content: text,
                            url: node.href
                        });
                    }
                } else if (node.nodeType === Node.ELEMENT_NODE) {
                    try {
                        // Skip hidden elements
                        const style = window.getComputedStyle(node);
                        const isVisible = style && style.display !== 'none' && style.visibility !== 'hidden';
                        
                        if (isVisible) {
                            // Process children
                            for (const child of node.childNodes) {
                                getTextAndLinksRecursive(child, result);
                            }
                            
                            // Add line breaks after block elements
                            if (/^(div|p|h[1-6]|ul|ol|li|table|tr|section|article|header|footer|form)$/i.test(node.tagName)) {
                                result.push({ type: 'linebreak' });
                            }
                        }
                    } catch (error) {
                        // If getComputedStyle fails, still try to process children
                        for (const child of node.childNodes) {
                            getTextAndLinksRecursive(child, result);
                        }
                    }
                }
                return result;
            }
            
            // Start from body
            const bodyContent = getTextAndLinksRecursive(document.body);
            
            // Format the result into a single string with URLs preserved
            let formattedContent = '';
            let lastWasLinebreak = false;
            
            for (const item of bodyContent) {
                if (item.type === 'text') {
                    formattedContent += item.content + ' ';
                    lastWasLinebreak = false;
                } else if (item.type === 'link') {
                    formattedContent += item.content + ' [' + item.url + '] ';
                    lastWasLinebreak = false;
                } else if (item.type === 'linebreak' && !lastWasLinebreak) {
                    formattedContent += '\\n';
                    lastWasLinebreak = true;
                }
            }
            
            return formattedContent.trim().replace(/\\n{3,}/g, '\\n\\n');
        }"""
        )

        # Structure the content for LLM processing
        structured_content = [
            f"JOB POSTING ANALYSIS: {title}",
            f"URL: {url}",
            "\n=== JOB DESCRIPTION AND DETAILS ===\n",
            full_content,
        ]

        result = "\n".join(structured_content)
        logfire.info(
            f"Successfully extracted content from {url}", content_length=len(result)
        )
        return result

    except Exception as e:
        logfire.error(f"Error extracting page content: {str(e)}", exc_info=True)
        # Fallback to minimal extraction
        try:
            minimal_content = (
                f"URL: {url}\nTitle: {await page.title()}\n\n{await page.content()}"
            )
            logfire.warning("Using fallback minimal content extraction")
            return minimal_content
        except Exception:
            return f"URL: {url}\nExtraction failed"
