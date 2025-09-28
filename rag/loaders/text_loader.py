
from rag.base_loader import BaseLoader, LoaderResult
from rag.source_content import SourceContent


class TextFileLoader(BaseLoader):
    def load(self, source: SourceContent, **kwargs) -> LoaderResult:
        source_ref = source.source_ref
        if not source.path_exists():
            raise FileNotFoundError(f"The following file does not exist: {source.source}")

        with open(source.source, "r", encoding="utf-8") as file:
            content = file.read()

        return LoaderResult(
            content=content,
            source=source_ref,
            doc_id=self.generate_doc_id(source_ref=source_ref, content=content)
        )


class TextLoader(BaseLoader):
    def load(self, source: SourceContent, **kwargs) -> LoaderResult:
        return LoaderResult(
            content=source.source,
            source=source.source_ref,
            doc_id=self.generate_doc_id(content=source.source)
        )
