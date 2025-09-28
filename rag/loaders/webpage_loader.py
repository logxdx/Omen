from rag.base_loader import BaseLoader, LoaderResult
from rag.source_content import SourceContent

from tools.utils.scraper import scrape_page


class WebPageLoader(BaseLoader):
    def load(self, source: SourceContent, **kwargs) -> LoaderResult:
        url = source.source
        try:
            title = ""
            text = ""
            page = scrape_page(url)

            if page:
                title = page.title
                if page.summary:
                    text = page.summary
                elif page.markdown:
                    text = page.markdown
                else:
                    text = page.cleaned_html

            metadata = {
                "url": url,
                "title": title,
                "status_code": "200" if text else "404",
                "content_type": "webpage",
            }

            return LoaderResult(
                content=text,
                source=url,
                metadata=metadata,
                doc_id=self.generate_doc_id(source_ref=url, content=text),
            )

        except Exception as e:
            raise ValueError(f"Error loading webpage {url}: {str(e)}")
