import os
from typing import Literal
from crewai import Agent, Task, LLM, Crew, Process
from crewai.tools import tool
from datetime import datetime
from textwrap import dedent
from dotenv import load_dotenv

from crews.WebSearchCrew.ScrapeWebsite import scrape_page

from search_ai import search, Filters

from ddgs import DDGS

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")

CEREBRAS_BASE_URL = os.getenv("CEREBRAS_BASE_URL")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")

POLLINATIONS_BASE_URL = os.getenv("POLLINATIONS_BASE_URL")
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY")


SEARCH_MODEL = "may"
SEARCH_LLM = LLM(
    base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY, model=f"openai/{SEARCH_MODEL}"
)

ANALYST_MODEL = "qwen3:1.7b"
ANALYST_LLM = LLM(
    base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY, model=f"openai/{ANALYST_MODEL}"
)

FORMATTING_MODEL = "june"
JOURNALIST_LLM = LLM(
    base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY, model=f"openai/{FORMATTING_MODEL}"
)


SEARCH_MODEL = "llama-3.3-70b"
SEARCH_LLM = LLM(
    base_url=CEREBRAS_BASE_URL, api_key=CEREBRAS_API_KEY, model=f"openai/{SEARCH_MODEL}"
)

ANALYST_MODEL = "gpt-oss-120b"
ANALYST_MODEL = "qwen-3-235b-a22b-thinking-2507"
ANALYST_LLM = LLM(
    base_url=CEREBRAS_BASE_URL,
    api_key=CEREBRAS_API_KEY,
    model=f"openai/{ANALYST_MODEL}",
)

FORMATTING_MODEL = "gpt-oss-120b"
JOURNALIST_LLM = LLM(
    base_url=CEREBRAS_BASE_URL,
    api_key=CEREBRAS_API_KEY,
    model=f"openai/{FORMATTING_MODEL}",
)


# SEARCH_MODEL = "openai/openai"
# SEARCH_LLM = LLM(base_url=POLLINATIONS_BASE_URL, api_key=POLLINATIONS_API_KEY, model=SEARCH_MODEL)

# ANALYST_MODEL = "openai/openai"
# ANALYST_LLM = LLM(base_url=POLLINATIONS_BASE_URL, api_key=POLLINATIONS_API_KEY, model=ANALYST_MODEL)

# FORMATTING_MODEL = "openai/openai"
# JOURNALIST_LLM = LLM(base_url=POLLINATIONS_BASE_URL, api_key=POLLINATIONS_API_KEY, model=FORMATTING_MODEL)

ddgs = DDGS()

@tool
def google_search(
    query: str, count: int = 5, mode: Literal["news", "search"] = "search"
):
    """
    Google Search for query, returns 'count' number of results.

    Args:
        query: The search query
        count: Number of results to return
        mode: Mode of search (news / search [default])

    Returns:
        List of search results
    """
    # filters = Filters(exclude_sites=["instagram.com", "facebook.com", "youtube.com"])
    # return search(query=query, count=count, mode=mode, filters=filters, region="us-en")
    return ddgs.text(query=query)[:count]


@tool
def scrape_url(url: str, summarise: bool = True):
    """
    Scrape a url and return the markdown content.
    Summarises content by default.

    Args:
        url: The URL to scrape
        summarise: Returns a summary of the content (default: True)

    Returns:
        Markdown content of the website
    """
    print("=" * 50)
    print(f"URL: {url}")
    print(f"SUMMARISE: {summarise}")
    print("=" * 50)
    page = scrape_page(url=url, summarise=summarise, use_reader_lm=False)

    if summarise:
        return page.summary
    else:
        return page.markdown


class WebSearchCrew:
    """Web Search Crew"""

    def __init__(
        self,
        user_query: str,
        verbose: bool = False,
        deep_search: bool = False,
        collaborate: bool = False,
    ):
        """
                Initialize the WebSearchCrew.

        Args:
            user_query: The search query
            verbose: If True, enables verbose output.
            deep_search: If True, enables deep search.
            collaborate: If True, allows the analyst agent to collaborate with the web search & journalist agent for better results (!! longer processing time !!).
        """
        print("\n" + "=" * 50)
        print(f"QUERY: {user_query}")
        print(f"DEEP SEARCH: {deep_search}")
        print(f"COLLABORATE: {collaborate}")
        print("=" * 50)
        self.verbose = verbose
        self.user_query = user_query
        self.number_of_results = 10 if deep_search else 5

        ## Agents
        # Agent 0: Web Searcher
        Searcher = Agent(
            role="Web Searcher",
            goal="Search the web about the user query using the 'google_search' tool.",
            backstory="""
			You are an expert at using google search to obtain relevant information based on the user query.
			""",
            verbose=self.verbose,
            allow_delegation=False,
            llm=SEARCH_LLM,
            tools=[google_search],
        )

        # Agent 1: Search Results Reranker
        Reranker = Agent(
            role="Expert Information Reranker",
            goal="Obtain more information about the search results using the 'scrape_url' tool (optional) and rerank them according to relevance, quality and uniqueness w.r.t. the user query in the order of Highest to Lowest.",
            backstory="""You are an expert at analyzing information quality and relevance. 
			You can assess which search results are most valuable for answering 
			the user's query and format them in a clear, organized manner. You return the 
			content as is without information loss or change.""",
            verbose=self.verbose,
            allow_delegation=collaborate,
            llm=ANALYST_LLM,
            tools=[scrape_url],
        )

        # Agent 2: Journalist
        Journalist = Agent(
            role="Professional Journalist",
            goal="Write a professional article based on the given search results in markdown format",
            backstory="""You are a professional journalist with expertise in writing 
			articles on a wide range of topics. You write professional articles in a clear, 
			organized manner in markdown format. Return the content without information loss or change.""",
            verbose=self.verbose,
            allow_delegation=False,
            llm=JOURNALIST_LLM,
        )

        ## Tasks

        # Task 0: Search
        SearchTask = Task(
            description=dedent(
                f"""
			## USER QUERY: '{self.user_query}'
			### Current Date (YYYY-MM-DD): {datetime.now().strftime("%Y-%m-%d")}
			Search for {self.number_of_results} results using the 'google_search' tool.
			"""
            ),
            expected_output=dedent(
                """
			Compile the search results in the following format:

			1. TITLE
				URL
				CONTENT
			2. TITLE
				URL
				CONTENT
			etc.
			and so on for each query.
			The content should be to the point without any information loss or change.
			"""
            ),
            agent=Searcher,
        )

        # Task 1: Analyse & Rerank Results
        RerankTask = Task(
            description=dedent(
                f"""
			## USER QUERY: '{self.user_query}'
			### Current Date (YYYY-MM-DD): {datetime.now().strftime("%Y-%m-%d")}
			Use the 'scrape_url' tool to obtain more information from any URL, if neccessary, to provide a better analysis.
			Rerank the search results based on relevance and quality w.r.t the user query in the order of best to worst.
			IGNORE results that are irrelevant to the user query.
			"""
            ),
            expected_output=dedent(
                """
			Compile the relevant search results in the following format:

			1. TITLE
				URL
				CONTENT (5 to 10 sentences)
			2. TITLE
				URL
				CONTENT (5 to 10 sentences)
			etc.
			and so on for each query.

			For each result, the content should be concise and should capture all the essential information, key arguments, and supporting details from the original scraped content.
            Maintain the logical flow, chronological order, and structural integrity of the original material.
            Do not omit significant facts, figures, technical terms, names, or causal relationships. 
            Use clear and coherent language suitable for an educated reader who seeks a faithful, compressed version of the original content without losing context.
            Do not introduce interpretations, opinions, or paraphrasing that alters the meaning. 
            The goal is to compress the material, not reinterpret it.
			"""
            ),
            agent=Reranker,
            context=[SearchTask],
        )

        # Task 2: Format results
        JournalistTask = Task(
            description=dedent(
                f"""
			## USER QUERY: '{self.user_query}'
			### Current Date (YYYY-MM-DD): {datetime.now().strftime("%Y-%m-%d")}
			Write a coherent article based on the provided search results in markdown format.
			The article should be concise and informative, with a clear and brief summary of the key points.
			"""
            ),
            expected_output=dedent(
                """
			## Key Findings
			(numbered list of key findings here without brackets)

			(Article in markdown format here without brackets)

			## Sources
			(numbered list of sources with full urls here without brackets)
			"""
            ),
            agent=Journalist,
            context=[RerankTask],
        )

        # Create and run crew
        self.crew = Crew(
            agents=[Searcher, Reranker, Journalist],
            tasks=[SearchTask, RerankTask, JournalistTask],
            process=Process.sequential,
            verbose=True,
        )

    def run(self):
        result = self.crew.kickoff()
        return str(result)


def aggregate_web_search_results_using_crew(
    user_query: str,
    verbose: bool = False,
    deep_search: bool = False,
    collaborate: bool = False,
):
    """Initialize the WebSearchCrew.

    Args:
        user_query: The search query
        verbose: If True, enables verbose output.
        deep_search: If True, enables deep search.
        collaborate: If True, allows the analyst agent to collaborate with the web search & journalist agent for better results (!! longer processing time !!).
    """

    crew = WebSearchCrew(
        user_query=user_query,
        verbose=verbose,
        deep_search=deep_search,
        collaborate=collaborate,
    )
    result = crew.run()
    return str(result)


def main():
    """Main function to demonstrate the search crew"""

    # Example queries to test
    test_queries = [
        "What are the latest developments in vision language models in 2025?",
        "How does climate change affect ocean temperatures?",
        "What are the benefits and risks of cryptocurrency investments?",
        "What are the latest developments in quantum computing?",
        "What are the latest developments in AI?",
        "What are the latest developments in blockchain?",
    ]

    print("=== CrewAI Web Search System ===\n")

    # Interactive mode
    while True:
        print("\n=============================")
        print("1. Enter a custom search query")
        print("2. Use a test query")
        print("3. Exit")

        choice = input("\nSelect an option (1-3): ").strip()

        if choice == "1":
            user_query = input("\nEnter your search query: ").strip()
            if not user_query:
                print("Please enter a valid query.")
                continue

        elif choice == "2":
            print("\nTest queries:")
            for i, query in enumerate(test_queries, 1):
                print(f"{i}. {query}")

            try:
                test_choice = (
                    int(input(f"\nSelect a test query (1-{len(test_queries)}): ")) - 1
                )
                if 0 <= test_choice < len(test_queries):
                    user_query = test_queries[test_choice]
                else:
                    print("Invalid selection.")
                    continue
            except ValueError:
                print("Please enter a valid number.")
                continue

        elif choice == "3":
            break

        else:
            print("!! Invalid option !! Please try again.")
            continue

        deep_search = input("\nEnable deep search? (y/n): ").strip().lower() == "y"
        collaborate = input("\nEnable collaboration? (y/n): ").strip().lower() == "y"

        try:
            results = aggregate_web_search_results_using_crew(
                user_query=user_query,
                verbose=False,
                deep_search=deep_search,
                collaborate=collaborate,
            )

            print("\n" + "=" * 30)
            print("SEARCH RESULTS:")
            print("=" * 30)
            print(results)

            with open("search_results.txt", "w", encoding="utf-8") as f:
                f.write(results)

            exit()

        except Exception as e:
            print(f"\nError during search: {e}")
            print("Please try again with a different query.")


if __name__ == "__main__":
    main()
