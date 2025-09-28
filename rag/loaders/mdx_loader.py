import re

from rag.base_loader import BaseLoader, LoaderResult
from rag.source_content import SourceContent

class MDXLoader(BaseLoader):
    def load(self, source: SourceContent, **kwargs) -> LoaderResult:
        source_ref = source.source_ref
        content = source.source

        if source.is_url():
            content = self._load_from_url(source_ref, kwargs)
        elif source.path_exists():
            content = self._load_from_file(source_ref)

        return self._parse_mdx(content, source_ref)

    def _load_from_url(self, url: str, kwargs: dict) -> str:
        import requests

        headers = kwargs.get("headers", {
            "Accept": "text/markdown, text/x-markdown, text/plain",
            "User-Agent": "Mozilla/5.0 (compatible; crewai-tools MDXLoader)"
        })

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            raise ValueError(f"Error fetching MDX from URL {url}: {str(e)}")

    def _load_from_file(self, path: str) -> str:
        with open(path, "r", encoding="utf-8") as file:
            return file.read()

    def _parse_mdx(self, content: str, source_ref: str) -> LoaderResult:
        cleaned_content = content

        # Remove import statements
        cleaned_content = re.sub(r'^import\s+.*?\n', '', cleaned_content, flags=re.MULTILINE)

        # Remove export statements
        cleaned_content = re.sub(r'^export\s+.*?(?:\n|$)', '', cleaned_content, flags=re.MULTILINE)

        # Remove JSX tags (simple approach)
        cleaned_content = re.sub(r'<[^>]+>', '', cleaned_content)

        # Clean up extra whitespace
        cleaned_content = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_content)
        cleaned_content = cleaned_content.strip()

        metadata = {"format": "mdx"}
        return LoaderResult(
            content=cleaned_content,
            source=source_ref,
            metadata=metadata,
            doc_id=self.generate_doc_id(source_ref=source_ref, content=cleaned_content)
        )
