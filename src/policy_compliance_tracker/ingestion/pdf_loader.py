"""Small PDF-to-LangChain document adapter backed by pypdf."""

from pathlib import Path

from langchain_core.documents import Document
from pypdf import PdfReader


class PyPDFLoader:
    """Load one PDF into one LangChain document per page."""

    def __init__(self, file_path: str | Path):
        self.file_path = str(file_path)

    def load(self) -> list[Document]:
        reader = PdfReader(self.file_path)
        return [
            Document(
                page_content=page.extract_text() or "",
                metadata={"source": self.file_path, "page": page_number},
            )
            for page_number, page in enumerate(reader.pages)
        ]
