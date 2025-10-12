from agents import function_tool

#####################
# DuckDuckGo Search #
#####################
from tools.utils import DuckDuckGoSearch


@function_tool
def duckduckgo_search(
    query: str,
    max_results: int = 5,
) -> str:
    """
    Perform a web search using DuckDuckGo.

    Args:
        query (str): Search query string
        max_results (int): Maximum number of results to return (default: 5)

    Returns:
        List of search results
    """
    formatted_output = f"QUERY: {query}\n\n"
    for i, result in enumerate(
        DuckDuckGoSearch.search(query, max_results=max_results), 1
    ):
        formatted_output += f"{i}. {result}\n\n"
    return formatted_output.strip()


##################
# Searxng Search #
##################
from tools.utils import SearxSearch


@function_tool
def searx_search(
    query: str,
    num_results: int = 5,
) -> str:
    """
    Perform a web search using Searxng.

    Args:
        query (str): Search query string
        max_results (int): Maximum number of results to return (default: 5)

    Returns:
        List of search results
    """

    search_results = SearxSearch.search(query=query, max_results=num_results)
    formatted_output = f"QUERY: {search_results.query}\n\n"

    if search_results.answers:
        for answer in search_results.answers:
            formatted_output += f"{answer}\n\n"

    for i, result in enumerate(search_results.results, 1):
        formatted_output += (
            f"{i}. [{result.title}]({result.link})\nSnippet: {result.description}\n\n"
        )
    return formatted_output.strip()


##################
# Youtube Search #
##################
from tools.utils import YoutubeSearch


@function_tool
def search_youtube_videos(query: str, num_results: int = 5) -> str:
    """
    Perform a web search for YouTube videos.

    Args:
        query (str): Search query string
        max_results (int): Maximum number of results to return (default: 5)

    Returns:
        List of search results
    """
    search = YoutubeSearch.YoutubeSearch()
    results = search.search(query, max_results=num_results)
    formatted_output = f"QUERY: {query}\n\n"

    for i, video in enumerate(results, start=1):
        formatted_output += (
            f"{i}. Title: {video['title']}\n"
            f"   URL: https://www.youtube.com/watch?v={video['id']}\n"
            f"   Channel: {video['channel']}\n"
            f"   Duration: {video['duration']}\n"
            f"   Views: {video['views']}\n"
            f"   Published: {video['publish_time']}\n\n"
        )
    return formatted_output.strip()


SEARCH_TOOLS = [searx_search, search_youtube_videos]
