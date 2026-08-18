import os

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

from ..config import CHROMA_DB_PATH
from ..ingestion.regulation_monitor import invalid_pdf_message

COLLECTION_NAME = "langchain"


def load_documents():

    docs = []

    folders = [
        "data/regulations",
        "data/policies",
        "data/controls"
    ]

    for folder in folders:

        if not os.path.exists(folder):
            continue

        for file in os.listdir(folder):

            if file.endswith(".pdf"):

                path = os.path.join(folder, file)

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

                if "regulations" in folder:
                    doc_type = "regulation"
                elif "policies" in folder:
                    doc_type = "policy"
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
