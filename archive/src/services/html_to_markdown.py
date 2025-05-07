import asyncio
from playwright.async_api import async_playwright
import html2text
import os  # Add this import for directory operations


async def convert_webpage_to_markdown(url):
    """
    Scrapes a webpage and returns its content in markdown format.

    Args:
        url: The URL to scrape
        save_to_file: Whether to save the markdown to a file
        filename: Name of the file to save to (if save_to_file is True)

    Returns:
        The webpage content converted to markdown
    """
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Navigate to the URL
        await page.goto(url)

        # Wait for content to load
        await page.wait_for_load_state("networkidle")

        # Get the content
        content = await page.content()

        # Convert HTML to markdown
        converter = html2text.HTML2Text()
        converter.ignore_links = False
        markdown = converter.handle(content)

        # Close the browser
        await browser.close()

        return markdown


async def main():
    markdown = await get_page_markdown(save_to_file=True)
    print(f"Markdown content length: {len(markdown)} characters")
    return markdown


if __name__ == "__main__":
    asyncio.run(main())
