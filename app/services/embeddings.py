import logging
import os
import ollama
import numpy as np
from typing import List, Union, Dict, Any
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config import EMBEDDING_MODEL, SIMILARITY_THRESHOLD, TOP_K_CHUNKS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self, model_name: str = None):
        """
        Initialize Embedding Service.
        Uses model from config.py by default.
        """
        self.model_name = model_name or EMBEDDING_MODEL
        self.client = ollama.Client()
        self._embedding_cache = {}  # Cache for query embeddings
        logger.info(f"EmbeddingService initialized with model: {self.model_name}")

    def embed_text(self, text: Union[str, List[str]]) -> List[List[float]]:
        """
        Generates embeddings for a string or list of strings.
        Returns a list of vectors.

        Note: Truncates text to ~400 tokens (~1600 chars) to stay within
        the embedding model's 512 token limit.
        """
        try:
            if isinstance(text, str):
                text = [text]

            embeddings = []
            for t in text:
                max_chars = 1600
                if len(t) > max_chars:
                    original_len = len(t)
                    t = t[:max_chars]
                    logger.debug(
                        f"Truncated text from {original_len} to {max_chars} chars"
                    )


                response = self.client.embeddings(model=self.model_name, prompt=t)
                embeddings.append(response['embedding'])

            return embeddings

        except Exception as e:
            logger.error(f"Error generating embeddings with {self.model_name}: {str(e)}")
            raise e

    def calculate_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calculates Cosine Similarity between two vectors.
        """
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        
        dot_product = np.dot(v1, v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
            
        return float(dot_product / (norm_v1 * norm_v2))

    def get_top_k(self, query_vec: List[float], candidates: List[dict], k: int = 3) -> List[dict]:
        """
        Finds the top K most similar candidates.
        Candidates list must have an 'embedding' key.
        """
        scored_candidates = []
        for cand in candidates:
            score = self.calculate_similarity(query_vec, cand['embedding'])
            scored_cand = cand.copy()
            scored_cand['score'] = score
            scored_candidates.append(scored_cand)

        scored_candidates.sort(key=lambda x: x['score'], reverse=True)

        return scored_candidates[:k]

    def find_relevant_chunks(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: int = None,
        threshold: float = None
    ) -> List[Dict[str, Any]]:
        """
        Find relevant chunks using embedding similarity.

        Args:
            query: Query text (e.g., parameter name + description)
            chunks: List of chunks with 'text' or 'content' field
            top_k: Number of top chunks to return (default from config)
            threshold: Minimum similarity threshold (default from config)

        Returns:
            List of chunks with similarity scores, sorted by relevance
        """
        top_k = top_k or TOP_K_CHUNKS
        threshold = threshold or SIMILARITY_THRESHOLD

        query_embedding = self.embed_text(query)[0]

        chunks_with_embeddings = []
        for chunk in chunks:
            if 'embedding' not in chunk:
                text = chunk.get('text') or chunk.get('content') or str(chunk)
                chunk_embedding = self.embed_text(text)[0]
                chunk_copy = chunk.copy()
                chunk_copy['embedding'] = chunk_embedding
                chunks_with_embeddings.append(chunk_copy)
            else:
                chunks_with_embeddings.append(chunk)

        top_chunks = self.get_top_k(query_embedding, chunks_with_embeddings, k=top_k)

        filtered_chunks = [
            chunk for chunk in top_chunks
            if chunk.get('score', 0) >= threshold
        ]

        logger.info(
            f"Found {len(filtered_chunks)}/{len(chunks)} chunks above threshold {threshold} "
            f"for query: {query[:50]}..."
        )

        return filtered_chunks

if __name__ == "__main__":
    service = EmbeddingService()
    try:
        vecs = service.embed_text(["Hello world", "Machine learning is cool"])
        print(f"Embedding dimensions: {len(vecs[0])}")
        sim = service.calculate_similarity(vecs[0], vecs[1])
        print(f"Similarity: {sim}")
    except Exception as e:
        print(f"Embedding test failed: {e}")

