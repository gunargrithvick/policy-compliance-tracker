import os
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

from ..config import CHROMA_DB_PATH
from ..ingestion.regulation_monitor import invalid_pdf_message
from ..ingestion.pdf_loader import PyPDFLoader

COLLECTION_NAME = "langchain"
PROJECT_ROOT = next(
    (
        candidate
        for candidate in (
            Path.cwd(),
            Path(__file__).resolve().parents[3],
            Path(__file__).resolve().parents[2],
        )
        if (candidate / "data").is_dir()
    ),
    Path.cwd(),
)


def load_documents():

    docs = []

    folders = [
        PROJECT_ROOT / "data" / "regulations",
        PROJECT_ROOT / "data" / "policies",
        PROJECT_ROOT / "data" / "controls",
        PROJECT_ROOT / "data" / "frameworks",
    ]

    for folder in folders:
        folder_text = str(folder)

        if not os.path.exists(folder):
            continue

        for file in os.listdir(folder):

            if file.endswith(".pdf"):

                path = os.path.join(str(folder), file)

                message = invalid_pdf_message(path)
                if message:
                    print(f"Skipping invalid PDF {path}: {message}")
                    continue

                loader = PyPDFLoader(path)

                try:
                    loaded_docs = loader.load()
                except Exception as exc:
                    print(f"Skipping unreadable PDF {path}: {exc}")
                    continue

                if "regulations" in folder_text:
                    doc_type = "regulation"
                elif "policies" in folder_text:
                    doc_type = "policy"
                elif "frameworks" in folder_text:
                    doc_type = "framework"
                else:
                    doc_type = "control"

                for doc in loaded_docs:
                    doc.metadata["doc_type"] = doc_type

                docs.extend(loaded_docs)

    return docs


def reset_vector_index(embeddings):
    """Remove only the Chroma collection, preserving the tracker SQLite database."""
    existing = Chroma(
        persist_directory=CHROMA_DB_PATH,
        embedding_function=embeddings,
        collection_name=COLLECTION_NAME,
    )
    existing.delete_collection()


def main():

    documents = load_documents()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )

    chunks = splitter.split_documents(documents)

    if not chunks:
        print("No readable PDF content found. Vector database was not updated.")
        return

    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
    reset_vector_index(embeddings)
    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=CHROMA_DB_PATH,
        collection_name=COLLECTION_NAME,
    )
    print("Vector database created successfully")


if __name__ == "__main__":
    main()
