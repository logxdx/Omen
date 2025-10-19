import os
import re
import logging
from textwrap import dedent

import bs4
import requests
import unicodedata
from html import unescape
from typing import Optional
from litellm import completion
from dotenv import load_dotenv
from pydantic import BaseModel
from html2text import html2text
from urllib.parse import urljoin
from spider_rs import Page, Website  # type: ignore
from browserforge.headers import HeaderGenerator

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
    base_format = "[%(filename)s:%(lineno)d] - %(levelname)s | %(message)s"

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
BASE_URL = os.getenv("OLLAMA_BASE_URL")
API_KEY = os.getenv("CEREBRAS_API_KEY")
SUMMARIZATION_MODEL = "LFM2:1.2B"

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

    title: str = ""
    url: str = ""
    raw_html: str = ""
    cleaned_html: str = ""
    markdown: str = ""
    summary: str = ""
    links: list[str] = []

    def __repr__(self) -> str:
        return f"PageResult(title={self.title}, url={self.url}, raw_html={self.raw_html}, cleaned_html={self.cleaned_html}, markdown={self.markdown}, summary={self.summary}, links={self.links})"

    def __str__(self) -> str:
        return (
            f"URL: {self.url}\n"
            + (f"Title: {self.title}\n" if self.title else "")
            + "---\n"
            + (f"{self.summary}" if self.summary else f"{self.markdown}")
        )


def fetch_page_content(
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
            >>> content = fetch_page_content(url)
            >>> print(content)
    """
    if not url:
        logger.warning("[fetch_page_content]: URL EMPTY")
        return PageResult(url=url)
    try:
        logger.info(f"[fetch_page_content] FETCHING HTML")

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
            logger.warning(f"[fetch_page_content]: CANNOT FETCH HTML ({url})")
            return PageResult(url=url)

        logger.info(f"[fetch_page_content] FETCHED")

        return PageResult(
            url=url,
            raw_html=raw_html,
            links=links,
        )

    except Exception as e:
        logger.error(f"[fetch_page_content] ERROR: {e}")
        return PageResult(url=url)


def scrape_page_content(
    url: str,
    headers: dict[str, str] | None = None,
    subdomains: bool | None = None,
    tld: bool | None = None,
):
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
            >>> content = scrape_page_content(url)
            >>> print(content)
    """

    if not url:
        logger.warning("[scrape_page_content]: URL EMPTY")
        return PageResult(url=url)

    try:
        logger.info(f"[scrape_page_content] FETCHING HTML")

        # If headers are not provided, generate random headers
        if headers is None:
            headers = get_headers()

        website: Website = (
            Website(url=url)
            .with_return_page_links(True)
            .with_depth(0)
            .with_budget({"*": 1})
            .with_stealth(True)
        )

        if headers is not None:
            website = website.with_headers(headers)
        if subdomains is not None:
            website = website.with_subdomains(subdomains)
        if tld is not None:
            website = website.with_tld(tld)

        website.scrape(headless=False)
        page = website.get_pages()[0]
        raw_html = str(page.content)

        # If raw html is empty, return empty PageResult
        if not raw_html:
            logger.info(f"[scrape_page_content] Trying with headless browser...")
            website.scrape(headless=True)
            page = website.get_pages()[0]
            raw_html = str(page.content)
            if not raw_html:
                logger.warning(f"[scrape_page_content]: CANNOT FETCH HTML ({url})")
                return PageResult(url=url)

        website.with_budget({"*": 0}).with_depth(1)
        website.crawl()
        links = website.get_links()
        # website.crawl_smart()
        # links += website.get_links()

        links = list(set(links))

        logger.info(f"[scrape_page_content] FETCHED")

        return PageResult(url=url, raw_html=raw_html, links=links)

    except Exception as e:
        logger.error(f"[fetch_page_content] ERROR: {e}")
        return PageResult(url=url)


def soup_html(html: str, baseurl: Optional[str] = None) -> tuple[str, str, list[str]]:
    """
    HTML Cleanup Magic 🪄

    Args:
            html (str): The raw HTML content to be cleaned
            baseurl (str): The base URL to resolve relative links

    Returns:
            Title, Cleaned HTML, Page Links

    Raises:
            Exception: If there's an error during cleaning

    Example:
            >>> html = "<html>...</html>"
            >>> content = soup_html(html)
            >>> print(content)
    """
    if not html:
        logger.warning("soup_html: HTML EMPTY")
        return "", "Empty HTML", []
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
                "br",
                "hr",
                "meta",
                "nav",
                "header",
                "footer",
                "svg",
                "img",
                "input",
                "textarea",
                "select",
                "option",
            ]
        ):
            tag.decompose()

        # Get title before further processing
        title = soup.title.string.strip() if soup.title and soup.title.string else ""

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
            "img",
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

        logger.info(f"[soup_html] CLEANED")

    except Exception as e:
        logger.error(f"[soup_html] ERROR: {e}")
        return "", f"Error: {e}", []

    return title, soup.strip(), list(links)


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
        markdown = html2text(html=html, bodywidth=0).strip()
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
            instructions = dedent("""Summarise the content into bullet points.""")

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

        # If user_agent is provided, update it in headers
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
            page = scrape_page_content(
                url=url, headers=headers, subdomains=subdomains, tld=tld
            )

            links: list[str] = []

            # get cleaned html
            if page.raw_html:
                page.title, page.cleaned_html, links = soup_html(
                    html=page.raw_html, baseurl=url
                )

            # ensure links are unique
            page.links = list(set(links + page.links))
            page.links = filter_links(page.links)

            # convert cleaned html to markdown
            if use_reader_lm:
                page.markdown = html2md(html=page.cleaned_html)
            else:
                page.markdown = html2text(html=page.cleaned_html, bodywidth=0).strip()

            # get markdown using Jina Reader API if markdown is empty
            if not page.raw_html or not page.cleaned_html or not page.markdown:
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


class CrawlingSubscription:
    """
    A subscription class to handle page events.
    """

    def __init__(self):
        logger.info("[CRAWLING STARTED]")

    def __call__(self, page):
        if page.status_code != 200:
            logger.info(page.url + " - " + str(page.status_code))
        else:
            logger.debug(page.url + " - " + str(page.status_code))


def crawl_links(
    url: str,
    headers: dict | None = None,
    user_agent: str | None = None,
    crawl_budget: dict[str, int] | None = None,
    depth: int = 1,
    chrome_intercept: bool = False,
    block_images: bool = False,
    stealth: bool = True,
    subdomains: bool = False,
    tld: bool = False,
    timeout: int = 10000,  # in milliseconds
    whitelist_url: list[str] | None = None,
    blacklist_url: list[str] | None = EXCLUDE_PATTERNS,
    chrome_url: str | None = None,
    proxies: list[str] | None = None,
    external_domains: list[str] | None = None,
    respect_robots_txt: bool = False,
    cache_page: bool = False,
    delay_between_requests: int = 0,
) -> list[str]:
    """
    Crawl a page and return a list of links found on that page.
    Args:
        url (str): The URL of the website to crawl
        headers (dict): Headers to use for the request
        user_agent (str): User agent to use for the request
        crawl_budget (dict[str, int]): Map of domain to number of pages to crawl for that domain
        depth (int): Depth of the crawl, 0 for infinite depth
        chrome_intercept (bool): Enable Chrome network interception
        block_images (bool): Block images from loading
        stealth (bool): Use stealth mode
        subdomains (bool): Include subdomains in the search
        tld (bool): Search for different top-level domains (TLDs)
        timeout (int): Request timeout in milliseconds
        whitelist_url (list[str] | None): List of URLs (path, url, regex pattern) to whitelist
        blacklist_url (list[str] | None): List of URLs (path, url, regex pattern) to blacklist
        chrome_url (str): Remote Chrome URL for headless browsing
        proxies (list[str] | None): List of proxies to use for the request
        external_domains (list[str] | None): List of external domains to include in the crawl
        respect_robots_txt (bool): Respect robots.txt rules
        cache_page (bool): Cache the page content
        delay_between_requests (int): Delay between requests in milliseconds
    """

    if not url:
        logger.warning("[crawl_page] WARNING: URL EMPTY")
        return []

    crawl_result: set[str] = set()

    try:
        logger.info(f"[crawl_page] CRAWLING FOR LINKS FROM {url}")

        # If headers are not provided, generate random headers
        if headers is None:
            headers = get_headers()

        # If user_agent is provided, remove it from headers
        if user_agent:
            if headers.get("User-Agent"):
                del headers["User-Agent"]

        website: Website = Website(url=url)

        if headers is not None:
            website = website.with_headers(headers)
        if user_agent is not None:
            website = website.with_user_agent(user_agent)
        if crawl_budget is not None:
            website = website.with_budget(crawl_budget)
        if subdomains is not None:
            website = website.with_subdomains(subdomains)
        if tld is not None:
            website = website.with_tld(tld)
        if whitelist_url is not None:
            website = website.with_whitelist_url(whitelist_url)
        if blacklist_url is not None:
            website = website.with_blacklist_url(blacklist_url)
        if chrome_url is not None:
            website = website.with_chrome_connection(chrome_url)
        if proxies is not None:
            website = website.with_proxies(proxies)
        if external_domains is not None:
            website = website.with_external_domains(external_domains)

        # Create a Website object
        website: Website = (
            Website(url=url)
            .with_depth(depth)
            .with_chrome_intercept(chrome_intercept, block_images)
            .with_stealth(stealth)
            .with_request_timeout(timeout)
            .with_caching(cache_page)
            .with_respect_robots_txt(respect_robots_txt)
            .with_delay(delay_between_requests)
            .with_return_page_links(True)
        )

        # Use the default crawl method
        website.crawl(on_page_event=CrawlingSubscription(), headless=False)
        # Collect links from the page
        for link in website.get_links():
            crawl_result.add(str(link))

        # Use the default crawl method with headless browser
        website.crawl(on_page_event=CrawlingSubscription(), headless=True)
        # Collect links from the page
        for link in website.get_links():
            crawl_result.add(str(link))

        # Use smart crawl
        website.crawl_smart(on_page_event=CrawlingSubscription())
        # Collect links from the page
        for link in website.get_links():
            crawl_result.add(str(link))
        logger.info("\n[CRAWLING COMPLETED]")

    except Exception as e:
        logger.warning(f"[crawl_page] ERROR: {e}")

    return list(crawl_result)


def crawl_page(
    url: str,
    use_reader_lm: bool = True,
    summarise: bool = False,
    instructions: str = "",
    headers: dict | None = None,
    user_agent: str | None = None,
    crawl_budget: dict[str, int] | None = None,
    depth: int = 1,
    chrome_intercept: bool = False,
    block_images: bool = False,
    stealth: bool = True,
    subdomains: bool = False,
    tld: bool = False,
    timeout: int = 10000,  # in milliseconds
    whitelist_url: list[str] | None = None,
    blacklist_url: list[str] | None = EXCLUDE_PATTERNS,
    chrome_url: str | None = None,
    proxies: list[str] | None = None,
    external_domains: list[str] | None = None,
    respect_robots_txt: bool = False,
    cache_page: bool = False,
    delay_between_requests: int = 0,
) -> list[PageResult]:
    """
    Crawl a website and return a list of pages found on that website.
    Args:
        url (str): The URL of the website to crawl
        use_reader_lm (bool): Use the Reader-LM for HTML to Markdown (default: True)
        summarise (bool): Summarise markdown using an LLM (default: False)
        instructions (str): Optional instructions to guide the summarisation
        headers (dict): Headers to use for the request
        user_agent (str): User agent to use for the request
        crawl_budget (dict[str, int]): Map of domain to number of pages to crawl for that domain
        depth (int): Depth of the crawl, 0 for infinite depth
        chrome_intercept (bool): Enable Chrome network interception
        block_images (bool): Block images from loading
        stealth (bool): Use stealth mode
        subdomains (bool): Include subdomains in the search
        tld (bool): Search for different top-level domains (TLDs)
        timeout (int): Request timeout in milliseconds
        whitelist_url (list[str] | None): List of URLs (path, url, regex pattern) to whitelist
        blacklist_url (list[str] | None): List of URLs (path, url, regex pattern) to blacklist
        chrome_url (str): Remote Chrome URL for headless browsing
        proxies (list[str] | None): List of proxies to use for the request
        external_domains (list[str] | None): List of external domains to include in the crawl
        respect_robots_txt (bool): Respect robots.txt rules
        cache_page (bool): Cache the page content
        delay_between_requests (int): Delay between requests in milliseconds
    """

    if not url:
        logger.warning("[crawl_page] WARNING: URL EMPTY")
        return []

    crawl_result = []

    try:
        logger.info(f"[crawl_page] SCRAPING PAGES FROM {url}")

        links = crawl_links(
            url=url,
            headers=headers,
            user_agent=user_agent,
            crawl_budget=crawl_budget,
            depth=depth,
            chrome_intercept=chrome_intercept,
            block_images=block_images,
            stealth=stealth,
            subdomains=subdomains,
            tld=tld,
            timeout=timeout,
            whitelist_url=whitelist_url,
            blacklist_url=blacklist_url,
            chrome_url=chrome_url,
            proxies=proxies,
            external_domains=external_domains,
            respect_robots_txt=respect_robots_txt,
            cache_page=cache_page,
            delay_between_requests=delay_between_requests,
        )

        for link in links:
            crawl_result.append(
                scrape_page(
                    url=str(link),
                    use_reader_lm=use_reader_lm,
                    summarise=summarise,
                    instructions=instructions,
                    subdomains=subdomains,
                    tld=tld,
                    user_agent=user_agent,
                    headers=headers,
                )
            )

        logger.info(f"[crawl_page] SCRAPED {len(crawl_result)} PAGES")

    except Exception as e:
        print(f"[LOG] Error while crawling: {e}")

    return crawl_result


if __name__ == "__main__":
    url = "https://blog.zeptonow.com/"
    url = "https://news.ycombinator.com/"
    url = "https://spider.cloud/"
    url = "https://openai.com/index/introducing-gpt-oss/"

    result = scrape_page(url, summarise=True)
    output = f"URL: {result.url}\n\n"
    output += f"Markdown\n---\n{result.markdown}\n\n"
    output += f"Summary\n---\n{result.summary}"
    print(output)
    print("\n\n---\n" + "\n".join(result.links) + "\n---\n")

    # for link in result.links:
    #     page = scrape_page(link, summarise=True)
    #     print(str(page) + "\n\n===\n")
