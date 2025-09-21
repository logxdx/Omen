# type:ignore

import os
import re
from textwrap import dedent
import logging
from typing import Optional

import bs4
import unicodedata
from html import unescape
import requests

from urllib.parse import urljoin
from spider_rs import Page  # type: ignore
from browserforge.headers import HeaderGenerator
from html2text import html2text
from litellm import completion
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class ColoredLogging(logging.Formatter):
    grey = "\x1b[38;20m"
    cyan = "\x1b[36;20m"
    yellow = "\x1b[33;20m"
    blue = "\x1b[34;20m"
    bold_blue = "\x1b[34;1m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    base_format = "%(levelname)s - %(message)s [%(filename)s:%(lineno)d]"

    FORMATS = {
        logging.DEBUG: cyan + base_format + reset,
        logging.INFO: blue + base_format + reset,
        logging.WARNING: yellow + base_format + reset,
        logging.ERROR: red + base_format + reset,
        logging.CRITICAL: bold_red + base_format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


handler = logging.StreamHandler()
handler.setFormatter(ColoredLogging())
logging.basicConfig(
    level=logging.ERROR,
    handlers=[handler],
)
logger = logging.getLogger()


for logger_name in logging.root.manager.loggerDict:
    if not logger_name.startswith(__name__):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

# Set the summarization model
BASE_URL = os.getenv("CEREBRAS_BASE_URL")
API_KEY = os.getenv("CEREBRAS_API_KEY")
SUMMARIZATION_MODEL = "llama-3.3-70b"

# These patterns will be used to filter out unwanted URLs
EXCLUDE_PATTERNS = [
    r"\?.*=",  # query strings with parameters
    r"/(login|signup|register|sign-in|sign-up|logout|auth|account|user|profile|credits)/?",  # auth-related
    r"/(cart|checkout|order|payment|invoice|billing)/?",  # e-commerce transactions
    r"/(settings|preferences|config|admin|dashboard|privacy)/?",  # config/user settings
    r"/(newsletter|subscribe|unsubscribe|follow|share|like)/?",  # social/subscription
    r"/(track|tracking|history)/?",  # order/tracking status
    r"/(error|404|403|500|maintenance|unavailable)/?",  # error pages
    r"^/api(/|$)|/api/v\d+(/|$)",  # API endpoints
    r"/(captcha|verify|verification)/?",  # validation
    r"/(download|upload)/?",  # file endpoints
    r"/(preview|print|css|js)/?",  # alternate content formats
    r"(jpg|jpe?g|png|gif|svg|webp|mp4|webm|zip|tar\.gz|exe|dmg|iso|apk|docx?|xlsx?|pptx?|css|js|xml|json|woff|woff2|ico)",  # file extensions
]

social_media_patterns = [
    r"facebook\.",
    r"x\.",
    r"twitter\.",
    r"instagram\.",
    r"linkedin\.",
    r"youtube\.",
    r"reddit\.",
    r"discord\.",
    r"tiktok\.",
    r"pinterest\.",
]

EXCLUDE_REGEXES = [re.compile(pattern, re.IGNORECASE) for pattern in EXCLUDE_PATTERNS]


def get_headers() -> dict:
    """
    Returns a random set of headers.
    """
    headers = HeaderGenerator(
        locale=("en-US", "en"),
    ).generate()

    return headers


class PageResult(BaseModel):
    """
    PageResult Pydantic Model
    Contains the URL, raw HTML, cleaned HTML, markdown, summary (if requested), and links
    """

    url: str = ""
    raw_html: str = ""
    cleaned_html: str = ""
    markdown: str = ""
    summary: str = ""
    links: list[str] = []

    def __repr__(self) -> str:
        return f"PageResult(url={self.url}, raw_html={self.raw_html}, cleaned_html={self.cleaned_html}, markdown={self.markdown}, summary={self.summary}, links={self.links})"

    def __str__(self) -> str:
        return f"URL: {self.url}\n" + (
            f"Summary:\n{self.summary}" if self.summary else f"MD:\n{self.markdown}"
        )


def get_page_content(
    url: str,
    headers: Optional[dict[str, str]] = None,
    subdomains: Optional[bool] = None,
    tld: Optional[bool] = None,
) -> PageResult:
    """
    Scrape the HTML content from a URL and extract all links.

    Args:
        url (str): The URL to scrape and extract links from
        headers (dict[str, str] | None): Optional headers to use for the request
        subdomains (bool | None): Include subdomains in the search
        tld (bool | None): Search for different top-level domains (TLDs)

    Returns:
            PageResult: PageResult object containing the URL, raw HTML, cleaned HTML, markdown, and links

    Raises:
            Exception: If there's an error during scraping

    Example:
            >>> url = "https://example.com"
            >>> content = get_page_content(url)
            >>> print(content)
    """
    if not url:
        logger.warning("[get_page_content]: URL EMPTY")
        return PageResult(url=url)
    try:
        logger.info(f"[get_page_content] FETCHING HTML")

        # If headers are not provided, generate random headers
        if headers is None:
            headers = get_headers()

        # Create a Page object
        page = Page(url=url, headers=headers, subdomains=subdomains, tld=tld)

        # Fetch the page content
        page.fetch()

        # Get raw HTML
        raw_html = page.get_html()

        # Get links from the page
        links = page.get_links()

        # If raw html is empty, return empty PageResult
        if not raw_html:
            logger.warning("[get_page_content]: CANNOT FETCH HTML")
            return PageResult(url=url)

        logger.info(f"[get_page_content] FETCHED")

        return PageResult(
            url=url,
            raw_html=raw_html,
            links=links,
        )

    except Exception as e:
        logger.error(f"[get_page_content] ERROR: {e}")
        return PageResult(url=url)


def soup_html(html: str, baseurl: Optional[str] = None) -> tuple[str, list[str]]:
    """
    HTML Cleanup Magic 🪄

    Args:
            html (str): The raw HTML content to be cleaned
            baseurl (str): The base URL to resolve relative links

    Returns:
            str: Cleaned HTML content

    Raises:
            Exception: If there's an error during cleaning

    Example:
            >>> html = "<html>...</html>"
            >>> content = soup_html(html)
            >>> print(content)
    """
    if not html:
        logger.warning("soup_html: HTML EMPTY")
        return "", []
    try:
        logger.info(f"[soup_html] CLEANING HTML")

        soup = bs4.BeautifulSoup(html, "html.parser")
        links: set[str] = set()

        # 1. Remove elements with invisible attribute
        for tag in soup.find_all(lambda tag: tag.has_attr("invisible")):
            tag.decompose()

        # 2. Remove unnecessary tags
        for tag in soup.find_all(
            [
                "script",
                "noscript",
                "style",
                "img",
                "br",
                "hr",
                "meta",
                "nav",
                "header",
                "footer",
                "svg",
                "input",
                "textarea",
                "select",
                "option",
            ]
        ):
            tag.decompose()

        # Structural tags
        # These tags are essential for the structure of the document and should not be removed
        structural_tags = {
            "html",
            "head",
            "body",
            "a",
            "div",
            "span",
            "section",
            "button",
            "main",
            "article",
            "header",
            "footer",
            "ul",
            "ol",
            "li",
            "tr",
            "td",
            "th",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "p",
            "sup",
            "sub",
            "dl",
            "dt",
            "dd",
            "pre",
            "code",
            "table",
            "thead",
            "tbody",
            "tfoot",
            "caption",
            "col",
            "colgroup",
        }

        # Allowed attributes for tags
        allowed_attrs = {
            # "aria-label",
            "placeholder",
            "name",
            "value",
            "type",
            "href",
            "src",
            "alt",
        }

        # Tags that should be checked for empty content
        check_empty_tags = {
            "span",
            "p",
            "div",
            "a",
        }

        # 3. Soup Magic 🪄
        for tag in soup.find_all(True):

            # clean attributes
            if tag.attrs:
                tag.attrs = {
                    key: tag.attrs[key]
                    for key in allowed_attrs
                    if key in tag.attrs and tag.attrs[key]
                }

            # remove tags without attributes
            if not tag.attrs and tag.name in check_empty_tags:
                tag.unwrap()
                continue

            # replace href with absolute url and apply regex filtering
            if (tag.has_attr("href") or tag.has_attr("src")) and baseurl:

                # relative URL
                if tag.has_attr("href"):
                    rel_url = tag["href"]
                elif tag.has_attr("src"):
                    rel_url = tag["src"]

                # absolute URL
                abs_href = urljoin(baseurl, rel_url)

                if tag.has_attr("href"):
                    tag["href"] = abs_href
                if tag.has_attr("src"):
                    tag["src"] = abs_href

                # add to links set
                links.add(abs_href)

            # remove non-structural tags
            if tag.name not in structural_tags:
                tag.unwrap()
                continue

        # Convert soup back to string
        soup = str(soup).strip()

        # 4. Clean up html

        # Remove control characters
        soup = "".join(c for c in soup if unicodedata.category(c)[0] != "C")

        # Unescape html entities
        soup = unescape(soup)

        # # Collapse newlines with surrounding whitespace
        # soup = re.sub(r"\s*\n\s*", "\n", soup)

        # # Convert multiple spaces/tabs to a single space
        # soup = re.sub(r"[ \t]+", " ", soup)

        # Remove leading/trailing spaces inside tags (but NOT between tags)
        # soup = re.sub(r">\s+", ">", soup)
        # soup = re.sub(r"\s+<", "<", soup)

        # # Rename aria-label to label
        # soup = re.sub(r'aria-label\s*=\s*"', 'label="', soup)

        logger.info(f"[soup_html] CLEANED")

    except Exception as e:
        logger.error(f"[soup_html] ERROR: {e}")
        return "", []

    return soup.strip(), list(links)


def html2md(html: str, instructions: Optional[str] = None) -> str:
    """
    Clean HTML using an Reader-LM-v2

    Args:
            html (str): The raw HTML to be cleaned
            instructions (str): Instructions for the LLM to clean the HTML content

    Returns:
            str: Cleaned Markdown

    Raises:
            Exception: If there's an error during cleaning

    Example:
            >>> html = "<h1>Example</h1><p>This is an example.</p>"
            >>> content = html2md(html)
            >>> print(content)
    """
    if not html:
        logger.warning("[html2md]: HTML EMPTY")
        return ""
    try:
        logger.info(f"[html2md] HTML -> MARKDOWN")

        if not instructions:
            instructions = "Extract the main content from the given HTML and convert it to Markdown format."

        response = str(
            completion(
                base_url="http://localhost:11434/v1",
                api_key="ollama",
                model=f"openai/readerlm-v2",
                messages=[
                    {
                        "role": "user",
                        "content": f"{instructions}\n```html\n{html}\n```",
                    },
                ],
                temperature=0,
            )
            .choices[0]
            .message.content
        ).strip()

        # remove ```markdown and ``` from the response
        markdown = re.sub(
            r"^```markdown\s*|\s*```$", "", response, flags=re.DOTALL
        ).strip()

        logger.info(f"[html2md] MARKDOWN GENERATED")

        return markdown

    except Exception as e:
        logger.error(f"[html2md] ERROR: {e}")
        logger.info(f"[html2md] FALLBACK TO html2text")
        markdown = html2text(html=html, bodywidth=600).strip()
        return markdown


def filter_links(links: list[str], exclude_social_media: bool = True) -> list[str]:
    """
    Filters out unwanted links based on predefined patterns.

    Args:
        links (list[str]): List of links to filter

    Returns:
        list[str]: Filtered list of links
    """
    if not links:
        logger.warning("filter_links: LINKS EMPTY")
        return []

    regexes = EXCLUDE_REGEXES
    if exclude_social_media:
        # Add social media patterns to exclude
        regexes.extend(
            [re.compile(pattern, re.IGNORECASE) for pattern in social_media_patterns]
        )

    filtered_links = []
    for link in links:
        if not any(regex.search(link) for regex in regexes):
            filtered_links.append(link)

    return filtered_links


def summarize_content(content: str, instructions: Optional[str] = None) -> str:
    """
    Summarises the content using an

    Args:
            content (str): The raw content to be summarised
            instructions (str): Optional instructions to guide the summarisation

    Returns:
            str: Summarised content

    Raises:
            Exception: If there's an error during the LLM API call
    """

    if not content:
        logger.warning("summarize_content: CONTENT EMPTY")
        return ""
    try:
        logger.info(f"[summarize_content] Summarizing Content...")

        if not instructions:
            instructions = dedent(
                """
            You are a precise and context-aware summarization assistant. 
            Your task is to generate a concise summary that captures all the essential information, key arguments, and supporting details from the original content.
            Maintain the logical flow, chronological order, and structural integrity of the original material.
            Do not omit significant facts, figures, technical terms, names, or causal relationships. 
            Use clear and coherent language suitable for an educated reader who seeks a faithful, compressed version of the original content without losing context.
            Do not introduce interpretations, opinions, or paraphrasing that alters the meaning. 
            The goal is to compress the material, not reinterpret it.
            The summary should be comprehensive, capturing the essence of the original content while being as brief as possible.
            """
            )

        response = str(
            completion(
                base_url=BASE_URL,
                api_key=API_KEY,
                model=f"openai/{SUMMARIZATION_MODEL}",
                messages=[
                    {
                        "role": "system",
                        "content": dedent(f"{instructions}\n\nMARKDOWN CONTENT:"),
                    },
                    {"role": "user", "content": content},
                ],
            )
            .choices[0]
            .message.content
        ).strip()

        logger.info(f"[summarize_content] SUMMARISED")

        return response

    except Exception as e:
        logger.error(f"[summarize_content] ERROR: {e}")
        return ""


def jina_reader_api(url: str) -> str:
    """
    Get the markdown content from a URL using Jina Reader API
    Args:
            url (str): The URL to scrape and clean
    Returns:
            str: The markdown content for the URL
    Raises:
            Exception: If there's an error during the Jina Reader API call
    Example:
            >>> url = "https://example.com"
            >>> content = jina_reader_api(url)
            >>> print(content)
    """
    if not url:
        logger.warning("JINA READER: NO URL PROVIDED")
        return ""
    try:
        logger.info(f"[jina_reader_api] Initiating...")

        JINA_URL = f"https://r.jina.ai/{url}"
        json_payload = None

        headers = get_headers()
        headers["X-Engine"] = "browser"

        # # pdf handling
        # if url.startswith("file://") and url.endswith(".pdf"):
        #     JINA_URL = "https://r.jina.ai/"
        #     headers["Content-Type"] = "application/json"

        #     filepath = url.replace("file://", "")
        #     filepath = Path(filepath).resolve()
        #     with open(filepath, "rb") as f:
        #         pdf = base64.b64encode(f.read()).decode("utf-8")
        #     json_payload = {"pdf": pdf}

        markdown = requests.get(JINA_URL, headers=headers, json=json_payload)
        markdown = markdown.text

        logger.info(f"[jina_reader_api] SCRAPED")

        return markdown
    except Exception as e:
        logger.error(f"[jina_reader_api] ERROR: {e}")
        return ""


def scrape_page(
    url: str,
    summarise: bool = False,
    use_reader_lm: bool = False,
    instructions: Optional[str] = None,
    subdomains: Optional[bool] = None,
    tld: Optional[bool] = None,
    user_agent: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
) -> PageResult:
    """
    Scrape URL for HTML, clean it, convert to markdown, and optionally summarise it.
    Args:
        url (str): The URL of the website to scrape
        summarise (bool): Summarise markdown using an LLM (default: False)
        use_reader_lm (bool): Use the Reader-LM for HTML to Markdown (default: False)
        instructions (str): Optional instructions to guide the summarisation
        subdomains (bool | None): Include subdomains in the search
        tld (bool | None): Search for different top-level domains (TLDs)
        user_agent (str | None): User agent to use in the request
        headers (dict[str, str] | None): Optional headers to include in the request
    """

    if not url:
        logger.warning("[scrape_page] WARNING: URL EMPTY")
        return PageResult(url=url)
    try:
        logger.info(f"[scrape_page] SCRAPING {url}")

        # If headers are not provided, generate random headers
        if headers is None:
            headers = get_headers()

        # If user_agent is provided, remove it from headers
        if user_agent:
            headers["User-Agent"] = user_agent

        if "arxiv.org/abs" in url:
            url = url.replace("arxiv.org/abs", "arxiv.org/html")

        # pdf handling
        if ".pdf" in url:
            page = PageResult(url=url)
            page.markdown = jina_reader_api(url=url)
        else:
            # get PageResult object with raw_html, links and url
            page = get_page_content(
                url=url, headers=headers, subdomains=subdomains, tld=tld
            )

            # get cleaned html
            page.cleaned_html, links = soup_html(html=page.raw_html, baseurl=url)

            # ensure links are unique
            page.links = list(set(links + page.links))
            page.links = filter_links(page.links)

            # convert cleaned html to markdown
            if use_reader_lm:
                page.markdown = html2md(html=page.cleaned_html)
            else:
                page.markdown = html2text(html=page.cleaned_html, bodywidth=600).strip()

            # get markdown using Jina Reader API if markdown is empty or less than 40% of cleaned HTML
            if (
                not page.raw_html
                or not page.cleaned_html
                or not page.markdown
                or len(page.markdown) < len(page.cleaned_html) * 0.1
            ):
                page.markdown = jina_reader_api(url=url)

        # summarise content using LLM if summarise is True and markdown is not empty
        if summarise and page.markdown:
            page.summary = summarize_content(
                content=page.markdown, instructions=instructions
            )

        logger.info(f"[scrape_page] SCRAPED {url}")

        return page

    except Exception as e:
        logger.error(f"[scrape_page] ERROR: {e}")
        return PageResult(url=url)


if __name__ == "__main__":
    url = "https://news.ycombinator.com/"
    url = "https://spider.cloud/"
    result: str = scrape_page(url, summarise=True)
    print(result)
