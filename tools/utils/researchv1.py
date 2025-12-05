import os
import re
import json
import logging
from typing import Optional
from textwrap import dedent
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(lineno)d - %(message)s",
)
logger = logging.getLogger()

import requests
from openai import OpenAI
from browserforge.headers import HeaderGenerator
from scraper import scrape_page

SCRAPE_CONCURRENCY = 5

LLM_BASE_URL = str(os.getenv("OLLAMA_BASE_URL"))
LLM_API_KEY = str(os.getenv("CEREBRAS_API_KEY"))
LLM_MODEL = "LFM2:1.2B"


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

    headers = HeaderGenerator(locale=("en-US", "en")).generate()

    results = {"query": query, "results": []}

    try:
        logger.debug(f"Searching for: {query}")
        response = requests.get(
            SEARXNG_URL,
            params=params,
            timeout=30,
            headers=headers,
        )
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
            engines = ["brave", "duckduckgo", "google", "bing"]

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

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_scrape = {
                executor.submit(scrape_page, item[1], True) for item in items_to_scrape
            }
            for future in as_completed(future_to_scrape):
                scraped_content = str(future.result())
                web_results += scraped_content
                num_res += 1

                print(f"\n===\n{scraped_content}\n===\n")

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
                    "content": dedent(
                        """
                        You are an expert article head-writer responsible for generating well-structured, informative, and engaging article drafts in **Markdown** format. Please follow the guidelines below carefully:
                        **🔶 Article Requirements:**

                        * **Format:** Markdown
                        * **Length:** Approximately 1000-1500 words (unless otherwise specified)
                        * **Style:** Clear, concise, informative, and engaging. Aim for a tone appropriate to the target audience (professional, casual, technical, etc.)
                        * **Voice:** Use an active voice and second-person ("you") or third-person perspective, depending on context.
                        * **Readability:** Use short paragraphs, bullet points, and subheadings for clarity.

                        **🧩 Structure:**

                        ```markdown
                        # [Compelling Title with Keyword]

                        ## Introduction
                        - Briefly introduce the topic and its relevance to the reader.
                        - Clearly state the purpose or question the article will answer.

                        ## [Main Section 1: Key Concept or Theme]
                        - Provide definitions, context, or background.
                        - Include examples or statistics where applicable.

                        ## [Main Section 2: Deeper Exploration or Comparison]
                        - Explore nuances, comparisons, or benefits/drawbacks.
                        - Use bullet points or numbered lists where helpful.

                        ## [Main Section 3: Practical Advice or Implementation]
                        - Offer actionable tips, strategies, or real-world applications.

                        ## Conclusion
                        - Summarize key takeaways.
                        - Optionally include a call to action or suggest further reading.
                        ```

                        **✅ Additional Notes:**

                        * **Use headings and subheadings** to logically divide the content.
                        * Include **relevant examples**, **data**, or **citations** if applicable.
                        * Avoid filler. Every paragraph should provide value.
                        * If the topic warrants it, include a short **FAQ** or **Pros & Cons** section.

                        Cite the relevant sources at the end of the article. Use [1], [2], etc in the article to refer to the sources.
                        """
                    ),
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
    output = deep_search("Liquid AI")
    print(f"Output:\n---\n{output}\n---")
    # with open("researchv1.md", "w", encoding="utf-8") as f:
    #     f.write(output)
