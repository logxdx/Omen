from enum import Enum
from pathlib import Path
from urllib.parse import urlparse, ParseResult
import os
from rag.chunkers.base_chunker import BaseChunker
from rag.base_loader import BaseLoader


class DataType(str, Enum):
    PDF_FILE = "pdf_file"
    TEXT_FILE = "text_file"
    CSV = "csv"
    JSON = "json"
    XML = "xml"
    DOCX = "docx"
    MDX = "mdx"

    # Repository types
    DIRECTORY = "directory"

    # Web types
    WEBSITE = "website"
    YOUTUBE_VIDEO = "youtube_video"
    YOUTUBE_CHANNEL = "youtube_channel"

    # Raw types
    TEXT = "text"

    def get_chunker(self) -> BaseChunker:
        from importlib import import_module

        chunkers = {
            DataType.PDF_FILE: ("text_chunker", "TextChunker"),
            DataType.TEXT_FILE: ("text_chunker", "TextChunker"),
            DataType.TEXT: ("text_chunker", "TextChunker"),
            DataType.DOCX: ("text_chunker", "DocxChunker"),
            DataType.MDX: ("text_chunker", "MdxChunker"),
            # Structured formats
            DataType.CSV: ("structured_chunker", "CsvChunker"),
            DataType.JSON: ("structured_chunker", "JsonChunker"),
            DataType.XML: ("structured_chunker", "XmlChunker"),
            DataType.WEBSITE: ("web_chunker", "WebsiteChunker"),
            DataType.DIRECTORY: ("text_chunker", "TextChunker"),
            DataType.YOUTUBE_VIDEO: ("text_chunker", "TextChunker"),
            DataType.YOUTUBE_CHANNEL: ("text_chunker", "TextChunker"),
        }

        if self not in chunkers:
            raise ValueError(f"No chunker defined for {self}")
        module_name, class_name = chunkers[self]
        module_path = f"rag.chunkers.{module_name}"

        try:
            module = import_module(module_path)
            return getattr(module, class_name)()
        except Exception as e:
            raise ValueError(f"Error loading chunker for {self}: {e}")

    def get_loader(self) -> BaseLoader:
        from importlib import import_module

        loaders = {
            DataType.PDF_FILE: ("pdf_loader", "PDFLoader"),
            DataType.TEXT_FILE: ("text_loader", "TextFileLoader"),
            DataType.TEXT: ("text_loader", "TextLoader"),
            DataType.XML: ("xml_loader", "XMLLoader"),
            DataType.WEBSITE: ("webpage_loader", "WebPageLoader"),
            DataType.MDX: ("mdx_loader", "MDXLoader"),
            DataType.JSON: ("json_loader", "JSONLoader"),
            DataType.DOCX: ("docx_loader", "DOCXLoader"),
            DataType.CSV: ("csv_loader", "CSVLoader"),
            DataType.DIRECTORY: ("directory_loader", "DirectoryLoader"),
            DataType.YOUTUBE_VIDEO: ("youtube_video_loader", "YoutubeVideoLoader"),
            DataType.YOUTUBE_CHANNEL: (
                "youtube_channel_loader",
                "YoutubeChannelLoader",
            ),
        }

        if self not in loaders:
            raise ValueError(f"No loader defined for {self}")
        module_name, class_name = loaders[self]
        module_path = f"rag.loaders.{module_name}"
        try:
            module = import_module(module_path)
            return getattr(module, class_name)()
        except Exception as e:
            raise ValueError(f"Error loading loader for {self}: {e}")


class DataTypes:
    @staticmethod
    def from_content(content: str | Path | None = None) -> DataType:
        if content is None:
            return DataType.TEXT

        if isinstance(content, Path):
            content = str(content)

        is_url = False
        url: ParseResult = ParseResult("", "", "", "", "", "")

        if isinstance(content, str):
            try:
                url = urlparse(content)
                is_url = (url.scheme and url.netloc) or url.scheme == "file"
            except Exception:
                pass

        def get_file_type(path: str) -> DataType | None:
            mapping = {
                ".pdf": DataType.PDF_FILE,
                ".csv": DataType.CSV,
                ".mdx": DataType.MDX,
                ".md": DataType.MDX,
                ".docx": DataType.DOCX,
                ".json": DataType.JSON,
                ".xml": DataType.XML,
                ".txt": DataType.TEXT_FILE,
            }
            for ext, dtype in mapping.items():
                if path.endswith(ext):
                    return dtype
            return None

        if is_url:
            dtype = get_file_type(url.path)
            if dtype:
                return dtype

            return DataType.WEBSITE

        if os.path.isfile(content):
            dtype = get_file_type(content)
            if dtype:
                return dtype

            if os.path.exists(content):
                return DataType.TEXT_FILE
        elif os.path.isdir(content):
            return DataType.DIRECTORY

        return DataType.TEXT
