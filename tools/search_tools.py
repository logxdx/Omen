from agents import function_tool

#####################
# DuckDuckGo Search #
#####################
from .utils import DuckDuckGoSearch


@function_tool
def duckduckgo_search(
    query: str,
    max_results: int = 5,
) -> list[DuckDuckGoSearch.SearchResult]:
    """
    Perform a web search using DuckDuckGo.

    Args:
        query (str): Search query string
        max_results (int): Maximum number of results to return (default: 5)

    Returns:
        List of search results
    """
    return DuckDuckGoSearch.search(query, max_results=max_results)


##################
# Searxng Search #
##################
from .utils import SearxSearch


@function_tool
def searx_search(
    query: str,
    num_results: int = 5,
) -> SearxSearch.SearchResults:
    """
    Perform a web search using Searxng.

    Args:
        query (str): Search query string
        max_results (int): Maximum number of results to return (default: 5)

    Returns:
        List of search results
    """

    return SearxSearch.search(query=query, max_results=num_results)


##################
# Youtube Search #
##################
from .utils import YoutubeSearch


@function_tool
def search_youtube_videos(query: str, num_results: int = 5) -> list[dict]:
    """
    Perform a web search for YouTube videos.

    Args:
        query (str): Search query string
        max_results (int): Maximum number of results to return (default: 5)

    Returns:
        List of search results
    """
    search = YoutubeSearch.YoutubeSearch()
    return search.search(query, max_results=num_results)
