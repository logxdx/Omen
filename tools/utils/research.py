import asyncio
import json
import os
import re
from typing import Optional
import logging
from datetime import datetime
from textwrap import dedent

from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(lineno)d - %(message)s",
)
logger = logging.getLogger(__name__)

import requests
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    DefaultMarkdownGenerator,
    LLMContentFilter,
    LLMExtractionStrategy,
    LLMConfig,
)
from openai import OpenAI

SCRAPE_CONCURRENCY = 2

LLM_BASE_URL = str(os.getenv("CEREBRAS_BASE_URL"))
LLM_API_KEY = str(os.getenv("CEREBRAS_API_KEY"))
LLM_MODEL = "gpt-oss-120b"

# Async URL scraper function
async def async_scrape_url(url: str, query: str) -> str:
    """
    Asynchronously scrape content from a URL based on a query.

    Args:
        url: The URL to scrape
        query: The search query to filter content

    Returns:
        str: Extracted content in markdown format or error message
    """
    logger.debug(f"Starting async scrape of URL: {url}")
    logger.debug(f"Search query: {query}")

    if (
        not url
        or not isinstance(url, str)
        or not url.startswith(("http://", "https://"))
    ):
        error_msg = f"Invalid URL provided: {url}"
        logger.error(error_msg)
        return error_msg

    # url = "https://r.jina.ai/" + url

    if not query or not isinstance(query, str):
        error_msg = "Invalid search query provided"
        logger.error(error_msg)
        return error_msg

    # Log the start of the scraping operation
    start_time = datetime.now()
    logger.debug(f"Scraping started at {start_time}")

    # Configure browser with detailed logging
    browser_config = BrowserConfig(
        user_agent_mode="random",
        verbose=True,
    )

    logger.debug("Browser configuration completed")

    instruction = dedent(
        f"""
                         Extract each and every information relevant to \"{query}\".
                         Include key concepts, explanations, examples, and essential details. 
                         Keep all explanations, terminologies and examples intact.
                         Format the output as a clean structured markdown.
                         Return "NO RESULTS" if no relevant information is found.
                        """
    )

    llm_config = LLMConfig(
        provider=f"openai/{LLM_MODEL}",
        api_token=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        temperature=0.3,
    )

    llm_strategy = LLMExtractionStrategy(
        llm_config=llm_config,
        instruction=instruction,
        chunk_token_threshold=2048,
        overlap_rate=0.2,
        apply_chunking=True,
        input_format="markdown",
        verbose=True,
    )

    llm_filter = LLMContentFilter(
        llm_config=llm_config,
        instruction=instruction,
        chunk_token_threshold=2048,
        overlap_rate=0.2,
        verbose=True,
    )

    markdown_generator = DefaultMarkdownGenerator(
        content_filter=llm_filter,
        options={
            "body_width": 100,
            "ignore_emphasis": True,
            "ignore_links": True,
            "ignore_images": True,
            "escape_html": True,
        },
    )

    crawl_config = CrawlerRunConfig(
        extraction_strategy=llm_strategy,
        # markdown_generator=markdown_generator,
        exclude_social_media_links=True,
        keep_data_attributes=False,
        process_iframes=False,
        remove_overlay_elements=True,
        excluded_tags=[
            "form",
            "header",
            "footer",
            "script",
            "style",
            "nav",
            "img",
            "a",
        ],
        verbose=True,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Use a distinct name to avoid shadowing and help type-checkers
        crawler_result = await crawler.arun(url=url, config=crawl_config)  # type: ignore[assignment]

        if getattr(crawler_result, "success", False):
            try:
                extracted_content = getattr(crawler_result, "extracted_content", "")
                logger.debug("Content extracted successfully.")
                response = json.loads(extracted_content)

                result = ""
                for item in response:
                    error = item.get("error", None)
                    if error == "true":
                        logger.debug(f"Error in item: {item.get('index')}")
                        continue
                    content = item.get("content", "")
                    if isinstance(content, list):
                        content = " ".join(content)
                    elif isinstance(content, str):
                        content = content.strip()
                    if content:
                        result += content + "\n"
                    else:
                        logger.debug(f"No content found in item: {item.get('index')}")
                        continue

                result = result.strip()
                logger.debug("Content parsed successfully.")
                logger.debug(f"Content length: {len(result)}")

                logger.debug("---")
                logger.debug("Filter Usage")
                llm_filter.show_usage()
                logger.debug("---")
                logger.debug("Extraction Usage")
                llm_strategy.show_usage()
                logger.debug("---")

                return result
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                logger.error(f"Error parsing JSON response: {e}")
                return "Could not parse the extracted content."
        else:
            logger.error(
                f"Error in scraping: {getattr(crawler_result, 'error_message', 'Unknown error')}"
            )
            return "Could not scrape the URL."


# Synchronous URL Scraper function
def scrape_url(url: str, query: str) -> str:
    """
    Synchronous wrapper for async_scrape_url to maintain backward compatibility.

    Args:
        url: The URL to scrape
        query: The search query to filter content

    Returns:
        str: Extracted content or error message
    """
    logger.debug(f"Starting synchronous scrape of URL: {url}")
    try:
        result = asyncio.run(async_scrape_url(url, query))
        logger.debug("Synchronous scrape completed successfully")
        return result
    except Exception as e:
        error_msg = f"Error in synchronous scrape: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


# Web Search function
SEARXNG_URL = "http://localhost:9090/search"


def webSearch(
    query: str,
    num_results: int = 10,
    engines: list[str] = ["brave", "duckduckgo", "bing", "google"],
    categories: Optional[list[str]] = None,
) -> dict:
    """
    Perform a web search across multiple search engines.

    Args:
        query: The search query string
        num_results: Number of results to return per engine
        engines: List of search engines to use
        categories: Optional list of search categories to filter by

    Returns:
        dict: Search results or error information
    """
    logger.debug(f"Initiating web search for query: {query}")
    logger.debug(
        f"Search parameters - Results: {num_results}, Engines: {engines}, Categories: {categories}"
    )

    if not query or not isinstance(query, str):
        error_msg = "Invalid search query provided"
        logger.error(error_msg)
        return {"error": error_msg, "status": "error"}

    if num_results < 1 or num_results > 20:
        logger.warning(
            f"num_results {num_results} is outside recommended range (1-20), using default 10"
        )
        num_results = 10

    if not engines:
        engines = ["brave", "duckduckgo", "bing", "google"]
    logger.debug(f"Proceeding with search using engines: {engines}")

    engines = ",".join(engines)  # type: ignore

    params = {
        "q": query,
        "engines": engines,
        "format": "json",
        "language": "en",
    }

    if categories:
        params["categories"] = ",".join(categories)

    results = {"query": query, "results": []}

    try:
        logger.debug(f"Searching for: {query}")
        response = requests.get(SEARXNG_URL, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()
        search_results = data.get("results", [])[:num_results]

        # Log search metrics
        logger.debug(f"Retrieved {len(search_results)} results")

        results["results"].extend(search_results)

    except requests.exceptions.RequestException as e:
        logger.error(f"Error searching: {str(e)}", exc_info=True)
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error parsing response: {str(e)}", exc_info=True)

    total_results = len(results.get("results", []))
    logger.debug(f"Search completed. Total results: {total_results}")
    return results


# Deep Search function
NUMBER_OF_URLS_TO_SCRAPE = 10


def deep_search(
    query: str, category: str = "web", num_results: int = NUMBER_OF_URLS_TO_SCRAPE
) -> str:
    """
    Perform search for query across multiple sources.

    Args:
        query: The query to search for.
        category: The category to filter the search results (web, academic, news). Default is "web".
        num_results: The number of search results to return. Default is 10.

    Returns:
        str: A detailed analysis on the query.
    """

    engines = []
    match category.lower():
        case "academic":
            engines = ["arxiv", "google scholar", "pubmed", "springer", "wolframalpha"]
        case "news":
            engines = [
                "bing news",
                "duckduckgo news",
                "google news",
                "brave news",
                "yahoo news",
            ]
        case _:
            engines = ["brave", "duckduckgo", "google", "bing", "yahoo"]

    # perform web search
    results = webSearch(
        query=query,
        engines=engines,
        num_results=num_results,
    )
    web_results: str = ""
    num_res = 0

    # Build list of items to scrape (preserve original order)
    items_to_scrape: list[tuple[int, str, str, str]] = []
    try:
        idx = 1
        for result in results.get("results", []):
            if idx > num_results:
                break
            url = result.get("url", "")
            if not url:
                continue
            if "arxiv" in url:
                url = url.replace("/abs/", "/html/")
            title = result.get("title", "")
            category_val = result.get("category", "")
            items_to_scrape.append((idx, url, title, category_val))
            idx += 1
    except Exception as e:
        logger.error(f"Error preparing items to scrape: {e}")
        return "An error occurred while preparing the web results."

    # Concurrency control
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        max_workers = max(1, min(SCRAPE_CONCURRENCY, len(items_to_scrape) or 1))

        logger.debug(f"Starting concurrent scraping with max_workers={max_workers}")

        def _scrape_and_summarize(item: tuple[int, str, str, str]):
            order, url, title, category_local = item
            try:
                content = scrape_url(url=url, query=query)
                if not content.strip() or "error:" in content.lower():
                    logger.error(f"No relevant content from: {url}")
                    return order, None

                logger.debug(f"[{order}] URL scraped: {url} (len={len(content)})")

                if len(content) > 20000:
                    try:
                        client_local = OpenAI(
                            base_url=LLM_BASE_URL, api_key=LLM_API_KEY
                        )
                        content = (
                            client_local.chat.completions.create(
                                model=LLM_MODEL,
                                messages=[
                                    {
                                        "role": "system",
                                        "content": (
                                            f"Extract and summarise information from the given content which answers or completely fulfills the query: {query}. "
                                            "Structure the output in a clean markdown format. Remove any unnecessary information."
                                        ),
                                    },
                                    {"role": "user", "content": f"CONTENT: {content}"},
                                ],
                            )
                            .choices[0]
                            .message.content
                        )
                    except Exception as e_inner:
                        logger.error(f"Summarization failed for {url}: {e_inner}")

                header = f"\n---\n{order}. {title}\n{url}\n"
                safe_content = content if isinstance(content, str) else str(content)
                return order, header + safe_content + "\n---\n"
            except Exception as e_worker:
                logger.error(f"Error scraping {url}: {e_worker}")
                return order, None

        results_by_order: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(_scrape_and_summarize, item): item[0]
                for item in items_to_scrape
            }
            for future in as_completed(future_map):
                order, payload = future.result()
                if payload:
                    results_by_order[order] = payload

        # Assemble results in original order
        for order in sorted(results_by_order.keys()):
            web_results += results_by_order[order]
            num_res += 1
    except Exception as e:
        logger.error(f"Error in concurrent scraping: {e}")
        return "An error occurred while browsing the web."

    client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

    deep_search_results = str(
        client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Draft a professional article for the query using the web search results in markdown format. Cite the relevant sources at the end of the article. Use [1], [2], etc in the article to refer to the sources.",
                },
                {
                    "role": "user",
                    "content": f"QUERY: {query}\nWEB_RESULTS: {web_results}",
                },
            ],
        )
        .choices[0]
        .message.content
    ).strip()

    thinking = re.search(r"<think>(.*?)</think>", deep_search_results, re.DOTALL)
    thinking = thinking.group(1).strip() if thinking else ""
    if thinking:
        logger.debug(f"\nREASONING\n---\n{thinking}\n---\n")

    # Remove reasoning from the deep search response
    deep_search_results = re.sub(
        r"<think>(.*?)</think>", "", deep_search_results, flags=re.DOTALL
    ).strip()

    logger.debug(f"{num_res} Results found.\n==============\n\n")
    return deep_search_results


if __name__ == "__main__":
    output = deep_search("Samsung Galaxy S25 Ultra features", num_results=4)
    print(f"Output:\n---\n{output}\n---")
    with open("deep_search_output.md", "w", encoding="utf-8") as f:
        f.write(output)
