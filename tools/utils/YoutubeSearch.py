import requests
import urllib.parse
import json
from browserforge.headers import HeaderGenerator


class YoutubeSearch:

    def __init__(self):
        self.BASE_URL = "https://youtube.com"

    def _search(
        self, search_terms: str, max_results: int = 10, start: int = 0
    ) -> list[dict]:
        """
        Performs a search on YouTube and returns a list of video results.

        Args:
            search_terms (str): The search query to perform.
            max_results (int, optional): The maximum number of results to return. Defaults to 10.
            start (int, optional): The starting index for the search results. Defaults to 0.

        Returns:
            list: A list of video results.
        """

        encoded_search = urllib.parse.quote_plus(search_terms)
        url = f"{self.BASE_URL}/results?search_query={encoded_search}"

        headers = HeaderGenerator().generate()
        headers["origin"] = "https://youtube.com"
        headers["referer"] = "https://youtube.com"

        response = requests.get(url, headers=headers).text
        while "ytInitialData" not in response:
            response = requests.get(url, headers=headers).text

        results = self._parse_html(response)

        if max_results is not None and len(results) - start > max_results:
            return results[start : start + max_results]
        return results

    def _parse_html(self, response) -> list[dict]:
        """
        Parses the HTML response from YouTube and returns a list of video results.

        Args:
            response (str): The HTML response from YouTube.

        Returns:
            list: A list of video results.
        """

        results = []
        start = response.index("ytInitialData") + len("ytInitialData") + 3
        end = response.index("};", start) + 1
        json_str = response[start:end]
        data = json.loads(json_str)

        for contents in data["contents"]["twoColumnSearchResultsRenderer"][
            "primaryContents"
        ]["sectionListRenderer"]["contents"]:
            for video in contents["itemSectionRenderer"]["contents"]:
                res = {}
                if "videoRenderer" in video.keys():
                    video_data = video.get("videoRenderer", {})

                    res["id"] = video_data.get("videoId", None)
                    res["title"] = (
                        video_data.get("title", {})
                        .get("runs", [[{}]])[0]
                        .get("text", None)
                    )

                    url_suffix = (
                        video_data.get("navigationEndpoint", {})
                        .get("commandMetadata", {})
                        .get("webCommandMetadata", {})
                        .get("url", None)
                    )
                    res["url"] = f"{self.BASE_URL}{url_suffix}" if url_suffix else None
                    res["thumbnails"] = [
                        thumb.get("url", None)
                        for thumb in video_data.get("thumbnail", {}).get(
                            "thumbnails", [{}]
                        )
                    ]
                    res["channel"] = (
                        video_data.get("longBylineText", {})
                        .get("runs", [[{}]])[0]
                        .get("text", None)
                    )
                    res["duration"] = video_data.get("lengthText", {}).get(
                        "simpleText", 0
                    )
                    res["views"] = video_data.get("viewCountText", {}).get(
                        "simpleText", 0
                    )
                    res["publish_time"] = video_data.get("publishedTimeText", {}).get(
                        "simpleText", 0
                    )
                    results.append(res)

            if results:
                return results

        return results

    def search(
        self,
        search_terms: str,
        max_results: int = 10,
        start: int = 0,
    ) -> list[dict]:
        """
        Performs a search on YouTube and returns a list of video results.

        Args:
            search_terms (str): The search query to perform.
            max_results (int, optional): The maximum number of results to return. Defaults to 10.
            start (int, optional): The starting index for the search results. Defaults to 0.

        Returns:
            list | str: A list of video results or a JSON string representing the list of videos.
        """

        return self._search(search_terms, max_results, start)


# Example usage:
if __name__ == "__main__":
    import json

    search = YoutubeSearch()
    query = "gabriela"
    results = search.search(query, max_results=5)
    formatted_output = f"QUERY: {query}\n\n"

    for i, video in enumerate(results, start=1):
        formatted_output += (
            f"{i}. Title: {video['title']}\n"
            f"   URL: https://www.youtube.com/watch?v={video['id']}\n"
            f"   Channel: {video['channel']}\n"
            f"   Duration: {video['duration']}\n"
            f"   Views: {video['views']}\n"
            f"   Published: {video['publish_time']}\n\n")

    print(formatted_output.strip())
