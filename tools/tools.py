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
        query: Search query string
        max_results: Maximum number of results to return

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
        query: Search query string
        max_results: Maximum number of results to return

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
        query: Search query string
        max_results: Maximum number of results to return

    Returns:
        List of search results
    """
    search = YoutubeSearch.YoutubeSearch()
    return search.search(query, max_results=num_results)


#######################
# Open url in browser #
#######################
import webbrowser


@function_tool
def open_url_in_browser(link: str) -> str:
    """
    Open a link in the default web browser.

    Args:
        link: The URL to open in the browser

    Returns:
        str: Status message indicating success or failure
    """

    if not link or not isinstance(link, str):
        error_msg = "Invalid URL provided"
        return error_msg

    # Ensure URL has proper scheme
    if not link.startswith(("http://", "https://")):
        link = "https://" + link

    try:
        browser = webbrowser.get()
        if not browser.open(link):
            raise Exception("Browser returned False when attempting to open URL")

        success_msg = f"Successfully opened {link} in your default browser"
        return success_msg

    except Exception as e:
        error_msg = f"Failed to open {link} in browser: {str(e)}"
        return f"Error: {error_msg}"


###########
# Weather #
###########
from .utils.weather import get_weather


@function_tool
def get_weather_info(location: str) -> str:
    """
    Get weather information for a specific location.

    Args:
        location: The location to get weather information for.

    Returns:
        A dictionary containing weather information.
    """
    return get_weather(location)


###############
# URL Scraper #
###############
from .utils.scraper import scrape_page


@function_tool
def scrape_url(url: str, summarise: bool = False) -> str:
    """
    Scrape a webpage and return the content.

    Args:
        url: The URL of the webpage to scrape.
        summarise: Whether to summarize the content.

    Returns:
        The scraped content.
    """
    result = scrape_page(url, summarise=summarise)
    return str(result)


####################
# Filesystem tools #
####################
from .utils.filesystem import (
    list_files_in_sandbox,
    read_file_in_sandbox,
    write_file_in_sandbox,
    create_directory_in_sandbox,
    delete_file_in_sandbox,
    delete_directory_in_sandbox,
    move_file_in_sandbox,
    copy_file_in_sandbox,
    edit_file_section_in_sandbox,
    append_to_file_in_sandbox,
)


@function_tool
def list_files(relative_path: str = "") -> list[str]:
    """
    List files and directories in the filesystem at the given relative path.

    Args:
        relative_path: Relative path within the filesystem (default: root)

    Returns:
        List of file and directory names
    """
    return list_files_in_sandbox(relative_path)


@function_tool
def read_file(relative_path: str) -> str:
    """
    Read the content of a file in the filesystem.

    Args:
        relative_path: Relative path to the file within the filesystem

    Returns:
        Content of the file as a string
    """
    return read_file_in_sandbox(relative_path)


@function_tool
def write_file(relative_path: str, content: str) -> str:
    """
    Write content to a file in the filesystem.

    Args:
        relative_path: Relative path to the file within the filesystem
        content: Content to write to the file

    Returns:
        Success message
    """
    write_file_in_sandbox(relative_path, content)
    return f"Successfully wrote to {relative_path}"


@function_tool
def create_directory(relative_path: str) -> str:
    """
    Create a directory in the filesystem.

    Args:
        relative_path: Relative path to the directory within the filesystem

    Returns:
        Success message
    """
    create_directory_in_sandbox(relative_path)
    return f"Successfully created directory {relative_path}"


@function_tool
def delete_file(relative_path: str) -> str:
    """
    Delete a file in the filesystem.

    Args:
        relative_path: Relative path to the file within the filesystem

    Returns:
        Success message
    """
    delete_file_in_sandbox(relative_path)
    return f"Successfully deleted file {relative_path}"


@function_tool
def delete_directory(relative_path: str) -> str:
    """
    Delete a directory in the filesystem (must be empty).

    Args:
        relative_path: Relative path to the directory within the filesystem

    Returns:
        Success message
    """
    delete_directory_in_sandbox(relative_path)
    return f"Successfully deleted directory {relative_path}"


@function_tool
def move_file(src_relative_path: str, dst_relative_path: str) -> str:
    """
    Move a file within the filesystem.

    Args:
        src_relative_path: Relative path to the source file
        dst_relative_path: Relative path to the destination

    Returns:
        Success message
    """
    move_file_in_sandbox(src_relative_path, dst_relative_path)
    return f"Successfully moved {src_relative_path} to {dst_relative_path}"


@function_tool
def copy_file(src_relative_path: str, dst_relative_path: str) -> str:
    """
    Copy a file within the filesystem.

    Args:
        src_relative_path: Relative path to the source file
        dst_relative_path: Relative path to the destination

    Returns:
        Success message
    """
    copy_file_in_sandbox(src_relative_path, dst_relative_path)
    return f"Successfully copied {src_relative_path} to {dst_relative_path}"


@function_tool
def edit_file_section(
    relative_path: str, original_section: str, new_content: str
) -> str:
    """
    Edit a specific section of a file in the filesystem by replacing the original_section with new_content.

    Args:
        relative_path: Relative path to the file within the filesystem
        original_section: The exact text section to replace
        new_content: The new content to replace the original section with

    Returns:
        Success message
    """
    edit_file_section_in_sandbox(relative_path, original_section, new_content)
    return f"Successfully edited section in {relative_path}"


@function_tool
def append_to_file(relative_path: str, content: str) -> str:
    """
    Append content to a file in the filesystem without overwriting existing content.

    Args:
        relative_path: Relative path to the file within the filesystem
        content: Content to append to the file

    Returns:
        Success message
    """
    append_to_file_in_sandbox(relative_path, content)
    return f"Successfully appended to {relative_path}"


##################
# Date-Time Tool #
##################
import datetime


@function_tool
def get_current_datetime() -> str:
    """
    Get the current date and time in IST.

    Returns:
        Current date and time in YYYY-MM-DD HH:MM:SS format (IST)
    """
    ist_offset = datetime.timedelta(hours=5, minutes=30)
    current_utc = datetime.datetime.now(datetime.timezone.utc)
    ist_time = current_utc + ist_offset
    return ist_time.strftime("%Y-%m-%d %H:%M:%S")
