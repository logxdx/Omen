from agents import function_tool

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
from tools.utils.weather import get_weather


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
from tools.utils.scraper import scrape_page


@function_tool
def scrape_url(url: str, summarise: bool = False, instructions: str = "") -> str:
    """
    Scrape a webpage and return the content.

    Args:
        url (str): The URL of the webpage to scrape.
        summarise (bool): Use LLM to summarise the converted markdown content. Defaults to False.
        instructions (str): Works in conjunction with summarization. Special instructions on what information to extract.

    Returns:
        The scraped content.
    """
    result = scrape_page(url, summarise=summarise, instructions=instructions)
    return str(result)


##########################
# Audio & Video Download #
##########################

from tools.utils import download


@function_tool
def download_audio(url: str) -> str:
    """
    Download audio from a video.

    Args:
        url (str): URL of the video
    """
    out = download.download_audio(url)
    return out


@function_tool
def download_video(url: str) -> str:
    """
    Download video from a video.

    Args:
        url (str): URL of the video
    """
    out = download.download_video(url)
    return out


WEB_TOOLS = [
    open_url_in_browser,
    get_weather_info,
    scrape_url,
    download_audio,
    download_video,
]
