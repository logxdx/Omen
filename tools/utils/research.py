import os
import json
import logging
import re
import threading
import time
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from sklearn.metrics.pairwise import cosine_similarity

from pydantic import BaseModel
from litellm import completion, embedding
from dotenv import load_dotenv

from SearxSearch import search, SearchResults, Filters
from scraper import scrape_page, PageResult

load_dotenv()

BASE_URL = os.getenv("GROQ_BASE_URL")

RESEARCH_API_KEY = os.getenv("RESEARCH_API_KEY")
RESEARCH_MODEL = "openai/openai/gpt-oss-120b"

SUBMODULAR_BASE_URL = os.getenv("OLLAMA_BASE_URL")
SUBMODULAR_API_KEY = os.getenv("OLLAMA_API_KEY")
SUBMODULAR_MODEL = "openai/may"

EMBEDDING_BASE_URL = os.getenv("OLLAMA_BASE_URL")
EMBEDDING_API_KEY = os.getenv("OLLAMA_API_KEY")
EMBEDDING_MODEL = "openai/qwen3-embed:0.6b"
DIMENSIONS = 1024

CONCURRENCY = 5

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ResearchQuery(BaseModel):
    """Represents a decomposed research query"""

    original_query: str
    sub_queries: List[str]
    diversity_score: float = 0.0
    coverage_score: float = 0.0
    filters: Optional[Filters] = None


class ResearchResult(BaseModel):
    """Represents the result of researching a single query"""

    query: str
    sources: List[Dict[str, Any]]
    content: str
    summary: str
    timestamp: str


class SubmodularQueryDecomposer:
    """
    Implements submodular optimization for diverse query generation.
    Based on the approach described in Jina AI's deep research methodology.
    """

    def generate_candidate_queries(
        self, original_query: str, num_candidates: int = 20
    ) -> List[str]:
        """
        Generate candidate queries using LLM with diverse perspectives
        """
        prompt = f"""
        Generate {num_candidates} diverse search queries for the research topic: "{original_query}"

        Create queries that cover different aspects, perspectives, and angles of the topic.
        Each query should be optimized for web search and include specific keywords.

        Focus on diversity across these dimensions:
        1. Different subtopics and aspects
        2. Various stakeholder perspectives
        3. Temporal aspects (current, historical, future)
        4. Geographic and regional variations
        5. Technical vs practical approaches
        6. Challenges vs solutions
        7. Theoretical vs applied aspects

        Return only the queries as a JSON object, no explanations.
        JSON Structure: {'{"queries": ["query 1", "query 2", "query 3"]}'}
        """

        try:
            response = completion(
                base_url=SUBMODULAR_BASE_URL,
                api_key=SUBMODULAR_API_KEY,
                model=SUBMODULAR_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,  # Higher temperature for diversity
                max_tokens=1000,
            )

            queries_text = str(response.choices[0].message.content).strip()  # type: ignore

            queries: list = json.loads(queries_text).get("queries", [])

            # Clean and filter candidates
            candidates = [q for q in queries if len(q.split()) >= 3][:num_candidates]

            logger.info(f"Generated {len(candidates)} candidate queries")
            return candidates

        except Exception as e:
            logger.error(f"Error generating candidate queries: {e}")
            return [original_query]

    def compute_query_similarity_matrix(self, queries: List[str]) -> np.ndarray:
        """
        Compute pairwise similarity matrix between queries using OpenAI embeddings and cosine similarity
        """
        try:
            # Generate embeddings for all queries
            embeddings = self.get_embeddings(queries)

            # Compute cosine similarity matrix
            similarity_matrix = cosine_similarity(embeddings)  # type: ignore

            # Ensure diagonal is 0 (no self-similarity)
            np.fill_diagonal(similarity_matrix, 0)

            return similarity_matrix

        except Exception as e:
            logger.error(f"Error computing similarity matrix: {e}")
            # Return zero matrix as fallback
            n = len(queries)
            return np.zeros((n, n))

    def facility_location_function(
        self, selected: Set[int], similarity_matrix: np.ndarray
    ) -> float:
        """
        Submodular facility location function for coverage maximization
        """
        if not selected:
            return 0.0

        coverage = 0.0
        for i in range(len(similarity_matrix)):
            if i not in selected:
                # Maximum similarity to any selected query
                max_sim = (
                    max(similarity_matrix[i, j] for j in selected) if selected else 0
                )
                coverage += max_sim

        return coverage

    def graph_cut_function(
        self, selected: Set[int], similarity_matrix: np.ndarray
    ) -> float:
        """
        Submodular graph cut function for diversity maximization
        """
        if len(selected) <= 1:
            return 0.0

        total_similarity = 0.0
        selected_list = list(selected)

        # Sum similarities between all pairs in selected set
        for i in range(len(selected_list)):
            for j in range(i + 1, len(selected_list)):
                total_similarity += similarity_matrix[
                    selected_list[i], selected_list[j]
                ]

        return total_similarity

    def combined_submodular_function(
        self,
        selected: Set[int],
        similarity_matrix: np.ndarray,
        alpha: float = 0.6,
    ) -> float:
        """
        Combined submodular function balancing coverage and diversity
        """
        coverage_score = self.facility_location_function(selected, similarity_matrix)
        diversity_score = self.graph_cut_function(selected, similarity_matrix)

        # Normalize scores
        max_coverage = np.sum(np.max(similarity_matrix, axis=1))
        max_diversity = np.sum(similarity_matrix) / 2

        normalized_coverage = coverage_score / max_coverage if max_coverage > 0 else 0
        normalized_diversity = (
            diversity_score / max_diversity if max_diversity > 0 else 0
        )

        # Combined score with weight alpha for coverage vs diversity
        combined_score = (
            alpha * normalized_coverage + (1 - alpha) * normalized_diversity
        )

        return combined_score

    def greedy_submodular_selection(
        self, candidates: List[str], k: int = 5, alpha: float = 0.6
    ) -> Tuple[List[str], float, float]:
        """
        Greedy algorithm for submodular function maximization
        Returns selected queries, coverage score, and diversity score
        """
        if len(candidates) <= k:
            return candidates, 1.0, 1.0

        # Compute similarity matrix
        similarity_matrix = self.compute_query_similarity_matrix(candidates)

        selected = set()
        unselected = set(range(len(candidates)))

        for _ in range(k):
            if not unselected:
                break

            best_idx = None
            best_score = -float("inf")

            # Try adding each unselected query
            for idx in unselected:
                temp_selected = selected | {idx}
                score = self.combined_submodular_function(
                    temp_selected, similarity_matrix, alpha
                )
                if score > best_score:
                    best_score = score
                    best_idx = idx

            if best_idx is not None:
                selected.add(best_idx)
                unselected.remove(best_idx)

        # Get final scores
        final_coverage = self.facility_location_function(selected, similarity_matrix)
        final_diversity = self.graph_cut_function(selected, similarity_matrix)

        selected_queries = [candidates[i] for i in selected]

        return selected_queries, final_coverage, final_diversity

    def decompose_query(
        self, original_query: str, num_queries: int = 5
    ) -> ResearchQuery:
        """
        Main method to decompose query using submodular optimization
        """
        logger.info(
            f"Decomposing query using submodular optimization: {original_query}"
        )

        # Generate candidate queries
        candidates = self.generate_candidate_queries(original_query, num_candidates=20)

        if len(candidates) <= num_queries:
            return ResearchQuery(
                original_query=original_query,
                sub_queries=candidates,
                diversity_score=1.0,
                coverage_score=1.0,
            )

        # Apply submodular selection
        selected_queries, coverage_score, diversity_score = (
            self.greedy_submodular_selection(candidates, k=num_queries, alpha=0.6)
        )

        logger.info(
            f"Selected {len(selected_queries)} diverse queries with coverage={coverage_score:.3f}, diversity={diversity_score:.3f}"
        )

        return ResearchQuery(
            original_query=original_query,
            sub_queries=selected_queries,
            diversity_score=diversity_score,
            coverage_score=coverage_score,
        )

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts using OpenAI embeddings
        """
        embeddings = []
        for text in texts:
            try:
                response = embedding(
                    model=EMBEDDING_MODEL,
                    # dimensions=DIMENSIONS,
                    input=text,
                    api_key=EMBEDDING_API_KEY,
                    api_base=EMBEDDING_BASE_URL,
                )
                embeddings.append(response.data[0].get("embedding", [0.0] * DIMENSIONS))  # type: ignore
            except Exception as e:
                logger.error(f"Error generating embedding for text: {text[:50]}... {e}")
                # Use zero vector as fallback
                embeddings.append(
                    [0.0] * DIMENSIONS
                )  # Assuming 768 dimensions for openai/embeddinggemma
        return embeddings


class DeepResearchSystem:
    """
    A comprehensive deep research system that:
    1. Decomposes user queries into focused sub-queries using submodular optimization
    2. Searches the web using SearxSearch
    3. Scrapes and processes relevant content
    4. Compiles detailed reports
    5. Supports background execution
    """

    def __init__(self, output_dir: str = "research_reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # Configuration
        self.max_sources_per_query = 5
        self.max_concurrent_scrapes = CONCURRENCY

        # Initialize submodular decomposer
        self.query_decomposer = SubmodularQueryDecomposer()

        # Background execution tracking
        self.active_researches: Dict[str, Dict[str, Any]] = {}
        self.executor = ThreadPoolExecutor(max_workers=CONCURRENCY)

    def decompose_query(self, query: str) -> ResearchQuery:
        """
        Break down a complex query into multiple focused sub-queries using submodular optimization
        """
        return self.query_decomposer.decompose_query(query, num_queries=5)

    def search_web(
        self, query: str, filters: Optional[Filters] = None
    ) -> SearchResults:
        """
        Perform web search using SearxSearch
        """
        logger.info(f"Searching web for: {query}")

        try:
            results = search(
                query=query,
                max_results=self.max_sources_per_query,
                category="general",
                language="en",
                safe=1,
                filters=filters,
            )

            logger.info(f"Found {len(results.results)} sources for query: {query}")
            return results

        except Exception as e:
            logger.error(f"Error searching web for '{query}': {e}")
            return SearchResults(query=query)

    def scrape_content(self, url: str, query_context: str) -> Optional[PageResult]:
        """
        Scrape and process content from a URL
        """
        logger.info(f"Scraping content from: {url}")

        try:
            # Scrape the page with summarization
            result = scrape_page(
                url=url,
                use_reader_lm=True,
            )

            if result.markdown:
                logger.info(f"Successfully scraped content from: {url}")
                return result
            else:
                logger.warning(f"No content extracted from: {url}")
                return None

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None

    def filter_relevant_content(
        self, search_results: SearchResults, query: str
    ) -> List[Dict[str, Any]]:
        """
        Filter search results to find the most relevant sources
        """
        logger.info(f"Filtering {len(search_results.results)} sources for relevance")

        relevant_sources = []

        for result in search_results.results:
            # Basic relevance filtering based on title and description
            combined_text = f"{result.title} {result.description}".lower()
            query_terms = query.lower().split()

            # Calculate relevance score
            score = sum(1 for term in query_terms if term in combined_text)

            if score > 0:  # At least one query term matches
                relevant_sources.append(
                    {
                        "title": result.title,
                        "url": result.link,
                        "description": result.description,
                        "score": score,
                        "category": result.category,
                    }
                )

        # Sort by relevance score
        relevant_sources.sort(key=lambda x: x["score"], reverse=True)

        logger.info(f"Filtered to {len(relevant_sources)} relevant sources")
        return relevant_sources[: self.max_sources_per_query]

    def compile_report(
        self,
        research_results: List[ResearchResult],
        original_query: str,
        decomposition_info: ResearchQuery,
    ) -> str:
        """
        Compile all research results into a comprehensive report
        """
        logger.info("Compiling research report")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        report = f"""# Deep Research Report
**Original Query:** {original_query}
**Generated:** {timestamp}

## Executive Summary

This report provides comprehensive research findings based on web sources and content analysis using submodular optimization for diverse query generation.

## Research Methodology

- **Query Decomposition**: Used submodular optimization to generate {len(research_results)} diverse sub-queries
- **Diversity Score**: {decomposition_info.diversity_score:.3f}
- **Coverage Score**: {decomposition_info.coverage_score:.3f}
- **Web Search**: SearxNG search engine was used to find relevant sources
- **Content Extraction**: Web pages were scraped and processed for relevant information
- **Analysis**: Content was summarized and compiled into this report

## Query Decomposition Analysis

The original query was decomposed into the following diverse sub-queries using submodular optimization:

"""

        for i, sub_query in enumerate(decomposition_info.sub_queries, 1):
            report += f"{i}. {sub_query}\n"

        report += "\n## Detailed Findings\n"

        for i, result in enumerate(research_results, 1):
            report += f"""
### {i}. Research Focus: {result.query}

**Timestamp:** {result.timestamp}
**Sources Analyzed:** {len(result.sources)}

#### Key Sources:
"""
            for source in result.sources[:3]:  # Top 3 sources
                report += f"""
- **{source['title']}**
  - URL: {source['url']}
  - Relevance Score: {source['score']}
  - Description: {source['description']}
"""

            report += f"""
#### Content Summary:
{result.summary}

#### Detailed Content:
{result.content}

---
"""

        report += """
## Conclusion

This research provides a comprehensive overview of the topic based on current web sources. The findings are compiled from multiple diverse perspectives using submodular optimization to ensure maximum coverage while minimizing redundancy.

## Methodology Notes

The submodular optimization approach ensures:
- **Coverage**: Maximum representation of different aspects of the topic
- **Diversity**: Minimal redundancy between selected queries
- **Relevance**: Each query targets specific, searchable aspects
- **Balance**: Optimal trade-off between exploration and exploitation

## Sources
All information in this report is derived from publicly available web sources accessed during the research process.
"""

        return report

    def save_report(self, report: str, filename: Optional[str] = None) -> str:
        """
        Save the research report to a file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"research_report_{timestamp}.md"

        filepath = self.output_dir / filename

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(report)

            logger.info(f"Report saved to: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"Error saving report: {e}")
            return ""

    def research_single_query(self, query: str) -> ResearchResult:
        """
        Perform complete research for a single query
        """
        logger.info(f"Starting research for: {query}")

        # Search the web
        search_results = self.search_web(query)

        # Filter relevant sources
        relevant_sources = self.filter_relevant_content(search_results, query)

        # Scrape content from relevant sources
        scraped_content = []
        content_summaries = []

        with ThreadPoolExecutor(max_workers=self.max_concurrent_scrapes) as executor:
            future_to_url = {
                executor.submit(self.scrape_content, source["url"], query): source
                for source in relevant_sources
            }

            for future in as_completed(future_to_url):
                source = future_to_url[future]
                try:
                    result = future.result()
                    if result and result.markdown:
                        scraped_content.append(result.markdown)
                        if result.summary:
                            content_summaries.append(result.summary)
                except Exception as e:
                    logger.error(f"Error processing {source['url']}: {e}")

        # Compile content
        combined_content = "\n\n".join(scraped_content)
        combined_summary = "\n\n".join(content_summaries)

        return ResearchResult(
            query=query,
            sources=relevant_sources,
            content=combined_content,
            summary=combined_summary,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def perform_research(self, query: str, background: bool = False) -> Optional[str]:
        """
        Main research method - can run in background or foreground
        """
        if background:
            return self._start_background_research(query)
        else:
            return self._perform_foreground_research(query)

    def _perform_foreground_research(self, query: str) -> str:
        """
        Perform research in the foreground
        """
        logger.info(f"Starting foreground research for: {query}")

        # Decompose query using submodular optimization
        decomposed = self.decompose_query(query)

        # Research each sub-query
        research_results = []
        for sub_query in decomposed.sub_queries:
            result = self.research_single_query(sub_query)
            research_results.append(result)

        # Compile report with decomposition info
        report = self.compile_report(research_results, query, decomposed)

        # Save report
        filepath = self.save_report(report)

        logger.info(f"Research completed. Report saved to: {filepath}")
        return filepath

    def _start_background_research(self, query: str) -> str:
        """
        Start research in background thread
        """
        research_id = f"research_{int(time.time())}"

        def background_task():
            try:
                filepath = self._perform_foreground_research(query)
                self.active_researches[research_id]["status"] = "completed"
                self.active_researches[research_id]["filepath"] = filepath
                logger.info(f"Background research {research_id} completed")
            except Exception as e:
                self.active_researches[research_id]["status"] = "error"
                self.active_researches[research_id]["error"] = str(e)
                logger.error(f"Background research {research_id} failed: {e}")

        # Start background thread
        thread = threading.Thread(target=background_task, daemon=True)
        thread.start()

        # Track the research
        self.active_researches[research_id] = {
            "query": query,
            "status": "running",
            "start_time": datetime.now().isoformat(),
            "thread": thread,
        }

        logger.info(f"Started background research with ID: {research_id}")
        return research_id

    def get_research_status(self, research_id: str) -> Dict[str, Any]:
        """
        Get the status of a background research task
        """
        if research_id in self.active_researches:
            return self.active_researches[research_id]
        else:
            return {"status": "not_found"}

    def list_active_researches(self) -> List[Dict[str, Any]]:
        """
        List all active background research tasks
        """
        return [
            {
                "id": rid,
                "query": info["query"],
                "status": info["status"],
                "start_time": info["start_time"],
            }
            for rid, info in self.active_researches.items()
        ]


# Convenience functions for easy usage
def research_topic(query: str, background: bool = False) -> str:
    """
    Convenience function to perform research on a topic
    """
    system = DeepResearchSystem()
    return str(system.perform_research(query, background=background))


def get_research_status(research_id: str) -> Dict[str, Any]:
    """
    Convenience function to check research status
    """
    system = DeepResearchSystem()
    return system.get_research_status(research_id)


if __name__ == "__main__":
    # Example usage
    query = "What are the latest developments in quantum computing?"
    result_path = research_topic(query, background=False)
    print(f"Research report saved to: {result_path}")
