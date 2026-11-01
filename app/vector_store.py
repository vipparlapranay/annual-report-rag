import hashlib
import re
from collections.abc import Sequence

import chromadb

from app.config import Settings, settings
from app.documents import DocumentChunk

_DIMENSIONS = 384
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)?", re.IGNORECASE)
_STOP_WORDS = {
    "a", "an", "and", "are", "at", "did", "do", "does", "for", "how",
    "in", "is", "it", "many", "much", "of", "on", "the", "their", "was",
    "were", "what", "when", "where", "which", "who", "why", "with", "year",
}


def _terms(text: str) -> set[str]:
    terms = set(_TOKEN_PATTERN.findall(text.lower()))
    normalized = set()
    for term in terms:
        if term in _STOP_WORDS or len(term) <= 1:
            continue
        if term.endswith("ies") and len(term) > 5:
            term = term[:-3] + "y"
        elif term.endswith("ing") and len(term) > 5:
            term = term[:-3]
        elif term.endswith("ed") and len(term) > 4:
            term = term[:-2]
        elif term.endswith("es") and len(term) > 4:
            term = term[:-2]
        elif term.endswith("s") and len(term) > 3:
            term = term[:-1]
        if term.endswith("generat"):
            term += "e"
        normalized.add(term)
    return normalized


def embed(text: str) -> list[float]:
    vector = [0.0] * _DIMENSIONS
    tokens = _TOKEN_PATTERN.findall(text.lower())
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        number = int.from_bytes(digest, "big")
        index = number % _DIMENSIONS
        vector[index] += 1.0 if (number >> 8) & 1 else -1.0
    norm = sum(value * value for value in vector) ** 0.5
    return [value / norm for value in vector] if norm else vector


class ReportStore:
    def __init__(self, config: Settings = settings, ephemeral: bool = False) -> None:
        if ephemeral:
            self.client = chromadb.EphemeralClient()
        else:
            config.chroma_path.mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(path=str(config.chroma_path))
        self.collection = self.client.get_or_create_collection(
            name=config.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, chunks: Sequence[DocumentChunk]) -> int:
        if not chunks:
            return 0
        ids = [
            hashlib.sha256(
                f"{chunk.source}:{chunk.page}:{chunk.text}".encode("utf-8")
            ).hexdigest()
            for chunk in chunks
        ]
        unique: dict[str, DocumentChunk] = dict(zip(ids, chunks, strict=True))
        self.collection.upsert(
            ids=list(unique),
            documents=[chunk.text for chunk in unique.values()],
            embeddings=[embed(chunk.text) for chunk in unique.values()],
            metadatas=[
                {"source": chunk.source, "page": chunk.page or 0}
                for chunk in unique.values()
            ],
        )
        return len(unique)

    def search(self, query: str, top_k: int) -> list[DocumentChunk]:
        if not self.count:
            return []
        result = self.collection.query(
            query_embeddings=[embed(query)],
            n_results=self.count,
            include=["documents", "metadatas", "distances"],
        )
        documents = result["documents"][0] if result["documents"] else []
        metadatas = result["metadatas"][0] if result["metadatas"] else []
        distances = result["distances"][0] if result["distances"] else []
        query_terms = _terms(query)
        ranked: list[tuple[float, DocumentChunk]] = []
        for text, metadata, distance in zip(documents, metadatas, distances):
            page = int(metadata["page"]) or None
            chunk = DocumentChunk(text=text, source=str(metadata["source"]), page=page)
            chunk_terms = _terms(text)
            lexical = (
                len(query_terms & chunk_terms) / len(query_terms)
                if query_terms
                else 0.0
            )
            semantic = max(0.0, 1.0 - float(distance))
            score = 0.8 * lexical + 0.2 * semantic
            ranked.append(
                (
                    score,
                    chunk,
                )
            )
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [chunk for score, chunk in ranked[:top_k] if score > 0]

    @property
    def count(self) -> int:
        return self.collection.count()
