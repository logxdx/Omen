import random
from time import sleep
from urllib.parse import unquote

from bs4 import BeautifulSoup
from requests import get, Response


class SearchResult:
    def __init__(self, url, title, snippet):
        self.url = url
        self.title = title
        self.snippet = snippet

    def __repr__(self):
        return (
            f"SearchResult(url={self.url}, title={self.title}, snippet={self.snippet})"
        )

    def __str__(self):
        return f"Title: {self.title}\nURL: {self.url}\nDescription: {self.snippet}"

    def to_dict(self) -> dict:
        return {"url": self.url, "title": self.title, "snippet": self.snippet}

    def get(self, key, default=None):
        return getattr(self, key, default)


def get_useragent() -> str:
    """
    Generates a random user agent string mimicking the format of various software versions.

    The user agent string is composed of:
    - Lynx version: Lynx/x.y.z where x is 2-3, y is 8-9, and z is 0-2
    - libwww version: libwww-FM/x.y where x is 2-3 and y is 13-15
    - SSL-MM version: SSL-MM/x.y where x is 1-2 and y is 3-5
    - OpenSSL version: OpenSSL/x.y.z where x is 1-3, y is 0-4, and z is 0-9

    Returns:
        str: A randomly generated user agent string.
    """
    lynx_version = (
        f"Lynx/{random.randint(2, 3)}.{random.randint(8, 9)}.{random.randint(0, 2)}"
    )
    libwww_version = f"libwww-FM/{random.randint(2, 3)}.{random.randint(13, 15)}"
    ssl_mm_version = f"SSL-MM/{random.randint(1, 2)}.{random.randint(3, 5)}"
    openssl_version = (
        f"OpenSSL/{random.randint(1, 3)}.{random.randint(0, 4)}.{random.randint(0, 9)}"
    )
    return f"{lynx_version} {libwww_version} {ssl_mm_version} {openssl_version}"


def _req(
    query, results, lang, start, proxies, timeout, safe, ssl_verify, region
) -> Response:
    resp = get(
        url="https://www.google.com/search",
        headers={"User-Agent": get_useragent(), "Accept": "*/*"},
        params={
            "q": query,
            "num": results + 2,  # Prevents multiple requests
            "hl": lang,
            "start": start,
            "safe": safe,
            "gl": region,
        },
        proxies=proxies,
        timeout=timeout,
        verify=ssl_verify,
        cookies={
            "CONSENT": "PENDING+987",  # Bypasses the consent page
            "SOCS": "CAESHAgBEhIaAB",
        },
    )
    resp.raise_for_status()
    return resp


def search(
    query: str,
    num_results: int = 10,
    lang: str = "en-US",
    proxy: str | None = None,
    advanced: bool = True,
    sleep_interval: float = 1,
    timeout: float = 5,
    safe: str = "moderate",
    ssl_verify: bool = True,
    region: str = "US",
    start_num: int = 0,
    unique: bool = True,
):
    """
    Search the Google search engine for a given query and return the results.
    Args:
        query (str): The search query to query.
        num_results (int): The number of results to fetch. Default is 10.
        lang (str): The language code for the search results. Default is "en".
        proxy (str): Proxy URL to use for the request. Default is None.
        advanced (bool): If True, returns a list of SearchResult objects. Default is True.
        sleep_interval (float): Time to wait between requests in seconds. Default is 1.
        timeout (float): Timeout for the request in seconds. Default is 5.
        safe (str): Safe search setting. Default is "moderate".
        ssl_verify (bool): Whether to verify SSL certificates. Default is True.
        region (str): Region code for the search results. Default is None.
        start_num (int): Starting index for the search results. Default is 0.
        unique (bool): If True, only unique results are returned. Default is True.
    Returns:
        generator: A generator yielding search results. If advanced is True, yields SearchResult objects; otherwise, yields URLs.
    """

    # Proxy setup
    proxies = (
        {"https": proxy, "http": proxy}
        if proxy
        and (
            proxy.startswith("https")
            or proxy.startswith("http")
            or proxy.startswith("socks5")
        )
        else None
    )

    start = start_num
    fetched_results = 0  # Keep track of the total fetched results
    fetched_links = set()  # to keep track of links that are already seen previously

    while fetched_results < num_results:
        # Send request
        resp = _req(
            query,
            num_results - start,
            lang,
            start,
            proxies,
            timeout,
            safe,
            ssl_verify,
            region,
        )

        # put in file - comment for debugging purpose
        # with open('google.html', 'w') as f:
        #     f.write(resp.text)

        # Parse
        soup = BeautifulSoup(resp.text, "html.parser")
        result_block = soup.find_all("div", class_="ezO2md")
        new_results = 0  # Keep track of new results in this iteration

        for result in result_block:
            # Find the link tag within the result block
            link_tag = result.find("a", href=True)
            # Find the title tag within the link tag
            title_tag = link_tag.find("span", class_="CVA68e") if link_tag else None
            # Find the description tag within the result block
            description_tag = result.find("span", class_="FrIlee")

            # Check if all necessary tags are found
            if link_tag and title_tag and description_tag:
                # Extract and decode the link URL
                link = (
                    unquote(link_tag["href"].split("&")[0].replace("/url?q=", ""))
                    if link_tag
                    else ""
                )
            # Extract and decode the link URL
            link = (
                unquote(link_tag["href"].split("&")[0].replace("/url?q=", ""))
                if link_tag
                else ""
            )
            # Check if the link has already been fetched and if unique results are required
            if link in fetched_links and unique:
                continue  # Skip this result if the link is not unique
            # Add the link to the set of fetched links
            fetched_links.add(link)
            # Extract the title text
            title = title_tag.text if title_tag else ""
            # Extract the description text
            description = description_tag.text if description_tag else ""
            # Increment the count of fetched results
            fetched_results += 1
            # Increment the count of new results in this iteration
            new_results += 1
            # Yield the result based on the advanced flag
            if advanced:
                yield SearchResult(
                    link, title, description
                )  # Yield a SearchResult object
            else:
                yield link  # Yield only the link

            if fetched_results >= num_results:
                break  # Stop if we have fetched the desired number of results

        if new_results == 0:
            # If you want to have printed to your screen that the desired amount of queries can not been fulfilled, uncomment the line below:
            # print(f"Only {fetched_results} results found for query requiring {num_results} results. Moving on to the next query.")
            break  # Break the loop if no new results were found in this iteration

        start += 10  # Prepare for the next set of results
        sleep(sleep_interval)


if __name__ == "__main__":
    # Example usage

    no_of_fetched_results = 0
    results = search("NVIDIA DGX Spark", num_results=10, ssl_verify=True)
    for result in results:
        print(result)
        # print(f"Title: {result.title}")
        # print(f"URL: {result.url}")
        # print(f"Description: {result.description}")
        print("-" * 80)
        no_of_fetched_results += 1

    print("Search completed.")
    print("Total results fetched:", no_of_fetched_results)


# from search_ai import search, Filters, Proxy
# from typing import Literal


# def google_search(
#     query: str,
#     mode: Literal["news"] | Literal["search"] = "search",
#     num_results: int = 5,
#     filters: Filters | None = None,
#     safe: bool = False,
#     proxy: Proxy | None = None,
# ):
#     results = search(
#         query=query,
#         filters=filters,
#         mode=mode,
#         count=num_results,
#         safe=safe,
#         proxy=proxy,
#     )

#     for i in range(len(results)):
#         results[i].link = str(results[i].link)

#     return results


# if __name__ == "__main__":
#     results = google_search("SmolLM 3", num_results=3)
#     for result in results:
#         print(f"---\n{result.title}\n{result.link}\n{result.description}")
#     print("---")
