"""
Shared Semantic Text Chunker.
"""

from typing import List, Dict, Any


class SemanticChunker:
    """Splits continuous textual documents into tokenized chunks with overlap."""

    def __init__(self, target_chunk_size: int = 350, overlap: int = 50):
        self.target_chunk_size = target_chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [text.strip()]

        chunks = []
        current_chunk_words = []
        current_count = 0
        chunk_idx = 0

        for para in paragraphs:
            words = para.split()
            word_count = len(words)

            if current_count + word_count <= self.target_chunk_size:
                current_chunk_words.extend(words)
                current_count += word_count
            else:
                if current_chunk_words:
                    chunk_str = " ".join(current_chunk_words)
                    chunks.append({
                        "chunk_index": chunk_idx,
                        "text_content": chunk_str,
                        "token_count": int(len(current_chunk_words) * 1.3),
                    })
                    chunk_idx += 1

                    overlap_words = current_chunk_words[-self.overlap:] if len(current_chunk_words) > self.overlap else []
                    current_chunk_words = overlap_words + words
                    current_count = len(current_chunk_words)
                else:
                    for i in range(0, word_count, self.target_chunk_size - self.overlap):
                        batch = words[i:i + self.target_chunk_size]
                        chunks.append({
                            "chunk_index": chunk_idx,
                            "text_content": " ".join(batch),
                            "token_count": int(len(batch) * 1.3),
                        })
                        chunk_idx += 1
                    current_chunk_words = []
                    current_count = 0

        if current_chunk_words:
            chunks.append({
                "chunk_index": chunk_idx,
                "text_content": " ".join(current_chunk_words),
                "token_count": int(len(current_chunk_words) * 1.3),
            })

        return chunks
