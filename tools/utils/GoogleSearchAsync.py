import asyncio
import random
from urllib.parse import unquote

import aiohttp
from bs4 import BeautifulSoup


class SearchResult:
    def __init__(self, url, title, content):
        self.url = url
        self.title = title
        self.content = content

    def __repr__(self):
        return (
            f"SearchResult(url={self.url}, title={self.title}, content={self.content})"
        )

    def __str__(self):
        return f"Title: {self.title}\nURL: {self.url}\nDescription: {self.content}"

    def to_dict(self):
        return self.__dict__

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


async def _req_async(
    session: aiohttp.ClientSession,
    query: str,
    results: int,
    lang: str,
    start: int,
    safe: str,
    region: str,
) -> str:
    """
    Async version of the request function.
    """
    params = {
        "q": query,
        "num": results + 2,  # Prevents multiple requests
        "hl": lang,
        "start": start,
        "safe": safe,
    }

    if region:
        params["gl"] = region

    cookies = {
        "CONSENT": "PENDING+987",  # Bypasses the consent page
        "SOCS": "CAESHAgBEhIaAB",
    }

    headers = {"User-Agent": get_useragent(), "Accept": "*/*"}

    async with session.get(
        "https://www.google.com/search", params=params, headers=headers, cookies=cookies
    ) as response:
        response.raise_for_status()
        return await response.text()


async def search_async(
    query: str,
    num_results: int = 10,
    lang: str = "en",
    advanced: bool = True,
    sleep_interval: float = 1,
    timeout: float = 5,
    safe: str = "active",
    ssl_verify: bool = True,
    region: str = None,
    start_num: int = 0,
    unique: bool = True,
):
    """
    Async version of the Google search function.

    Args:
        query (str): The search query to query.
        num_results (int): The number of results to fetch. Default is 10.
        lang (str): The language code for the search results. Default is "en".
        advanced (bool): If True, returns a list of SearchResult objects. Default is True.
        sleep_interval (float): Time to wait between requests in seconds. Default is 1.
        timeout (float): Timeout for the request in seconds. Default is 5.
        safe (str): Safe search setting. Default is "active".
        ssl_verify (bool): Whether to verify SSL certificates. Default is True.
        region (str): Region code for the search results. Default is None.
        start_num (int): Starting index for the search results. Default is 0.
        unique (bool): If True, only unique results are returned. Default is True.

    Returns:
        list: A list of search results. If advanced is True, returns SearchResult objects; otherwise, returns URLs.
    """

    # Setup connector and timeout
    connector_kwargs = {}
    if not ssl_verify:
        connector_kwargs["verify_ssl"] = False

    connector = aiohttp.TCPConnector(**connector_kwargs)
    timeout_config = aiohttp.ClientTimeout(total=timeout)

    results = []
    start = start_num
    fetched_results = 0
    fetched_links = set()

    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout_config,
        trust_env=True,  # This enables proxy support from environment variables
    ) as session:

        while fetched_results < num_results:
            try:
                # Send async request
                resp_text = await _req_async(
                    session, query, num_results - start, lang, start, safe, region
                )

                # Parse the response
                soup = BeautifulSoup(resp_text, "html.parser")
                result_block = soup.find_all("div", class_="ezO2md")
                new_results = 0

                for result in result_block:
                    # Find the link tag within the result block
                    link_tag = result.find("a", href=True)
                    # Find the title tag within the link tag
                    title_tag = (
                        link_tag.find("span", class_="CVA68e") if link_tag else None
                    )
                    # Find the description tag within the result block
                    description_tag = result.find("span", class_="FrIlee")

                    # Check if all necessary tags are found
                    if link_tag and title_tag and description_tag:
                        # Extract and decode the link URL
                        link = (
                            unquote(
                                link_tag["href"].split("&")[0].replace("/url?q=", "")
                            )
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

                        # Add result based on the advanced flag
                        if advanced:
                            results.append(SearchResult(link, title, description))
                        else:
                            results.append(link)

                        # Increment counters
                        fetched_results += 1
                        new_results += 1

                        if fetched_results >= num_results:
                            break

                if new_results == 0:
                    break  # Break the loop if no new results were found

                start += 10  # Prepare for the next set of results

                # Sleep between requests
                if sleep_interval > 0:
                    await asyncio.sleep(sleep_interval)

            except Exception as e:
                print(f"Error during search: {e}")
                break

    return results


# Async generator version (more memory efficient for large result sets)
async def search_async_generator(
    query: str,
    num_results: int = 10,
    lang: str = "en",
    advanced: bool = True,
    sleep_interval: float = 1,
    timeout: float = 5,
    safe: str = "active",
    ssl_verify: bool = True,
    region: str = None,
    start_num: int = 0,
    unique: bool = True,
):
    """
    Async generator version of the Google search function.
    Yields results one by one as they are found.

    Args: Same as search_async

    Yields:
        SearchResult or str: Individual search results as they are found.
    """

    # Setup connector and timeout
    connector_kwargs = {}
    if not ssl_verify:
        connector_kwargs["verify_ssl"] = False

    connector = aiohttp.TCPConnector(**connector_kwargs)
    timeout_config = aiohttp.ClientTimeout(total=timeout)

    start = start_num
    fetched_results = 0
    fetched_links = set()

    async with aiohttp.ClientSession(
        connector=connector, timeout=timeout_config, trust_env=True
    ) as session:

        while fetched_results < num_results:
            try:
                # Send async request
                resp_text = await _req_async(
                    session, query, num_results - start, lang, start, safe, region
                )

                # Parse the response
                soup = BeautifulSoup(resp_text, "html.parser")
                result_block = soup.find_all("div", class_="ezO2md")
                new_results = 0

                for result in result_block:
                    # Find the link tag within the result block
                    link_tag = result.find("a", href=True)
                    # Find the title tag within the link tag
                    title_tag = (
                        link_tag.find("span", class_="CVA68e") if link_tag else None
                    )
                    # Find the description tag within the result block
                    description_tag = result.find("span", class_="FrIlee")

                    # Check if all necessary tags are found
                    if link_tag and title_tag and description_tag:
                        # Extract and decode the link URL
                        link = (
                            unquote(
                                link_tag["href"].split("&")[0].replace("/url?q=", "")
                            )
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

                        # Yield result based on the advanced flag
                        if advanced:
                            yield SearchResult(link, title, description)
                        else:
                            yield link

                        # Increment counters
                        fetched_results += 1
                        new_results += 1

                        if fetched_results >= num_results:
                            break

                if new_results == 0:
                    break  # Break the loop if no new results were found

                start += 10  # Prepare for the next set of results

                # Sleep between requests
                if sleep_interval > 0:
                    await asyncio.sleep(sleep_interval)

            except Exception as e:
                print(f"Error during search: {e}")
                break


# Example usage
async def main():
    """
    Example usage of the async search functions.
    """
    print("=== Using search_async (returns list) ===")
    results = await search_async("NVIDIA DGX Spark", num_results=5, ssl_verify=True)

    for i, result in enumerate(results, 1):
        print(f"Result {i}:")
        print(result)
        print("-" * 80)

    print(f"\nTotal results fetched: {len(results)}")

    print("\n=== Using search_async_generator (yields results) ===")
    count = 0
    async for result in search_async_generator(
        "Python asyncio", num_results=3, ssl_verify=True
    ):
        count += 1
        print(f"Result {count}:")
        print(result)
        print("-" * 80)

    print(f"\nTotal results fetched: {count}")


if __name__ == "__main__":
    # Run the async example
    asyncio.run(main())
