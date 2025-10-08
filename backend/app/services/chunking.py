from typing import List, Dict
from app.core.config import get_settings
from langchain_text_splitters import RecursiveCharacterTextSplitter

settings = get_settings()

def chunk_pages(pages: List[dict]) -> List[Dict]:
    texts = []
    meta = []
    for p in pages:
        texts.append(p["text"])  # type: ignore
        meta.append({"page": p["page"]})

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", ".", "?", "!", " "]
    )
    joined = "\n".join(texts)
    chunks = splitter.split_text(joined)
    results = []
    for idx, ch in enumerate(chunks):
        results.append({"position": idx, "text": ch, "page": 0})
    return results
