import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import numpy as np

from app.services.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class RAGService:

    def __init__(self, knowledge_base_path: str = "config/domain_knowledge.md"):

        self.knowledge_base_path = Path(knowledge_base_path)
        self.embedding_service = EmbeddingService()
        self.knowledge_chunks: List[Dict[str, str]] = []
        self.knowledge_embeddings: Optional[np.ndarray] = None
        self._initialized = False

    def initialize(self) -> bool:

        try:
            if not self.knowledge_base_path.exists():
                logger.warning(f"Knowledge base not found: {self.knowledge_base_path}")
                return False

            # Load knowledge base
            with open(self.knowledge_base_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse into chunks (by section)
            self.knowledge_chunks = self._parse_knowledge_base(content)

            if not self.knowledge_chunks:
                logger.warning("No knowledge chunks found")
                return False

            # Embed all chunks
            chunk_texts = [chunk['text'] for chunk in self.knowledge_chunks]
            embeddings_list = self.embedding_service.embed_text(chunk_texts)
            self.knowledge_embeddings = np.array(embeddings_list)

            self._initialized = True
            logger.info(f"RAG initialized with {len(self.knowledge_chunks)} knowledge chunks")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize RAG: {e}")
            return False

    def _parse_knowledge_base(self, content: str) -> List[Dict[str, str]]:
        """
        Parse markdown content into knowledge chunks.

        Strategy: Split by ### headers (subsections)

        Args:
            content: Markdown content

        Returns:
            List of knowledge chunks with metadata
        """
        chunks = []
        lines = content.split('\n')
        current_section = ""
        current_subsection = ""
        current_text = []

        for line in lines:
            # Main section (##)
            if line.startswith('## '):
                # Save previous chunk
                if current_text:
                    chunks.append({
                        'section': current_section,
                        'subsection': current_subsection,
                        'text': '\n'.join(current_text).strip(),
                        'title': f"{current_section} - {current_subsection}" if current_subsection else current_section
                    })
                    current_text = []

                current_section = line.replace('##', '').strip()
                current_subsection = ""

            # Subsection (###)
            elif line.startswith('### '):
                # Save previous chunk
                if current_text:
                    chunks.append({
                        'section': current_section,
                        'subsection': current_subsection,
                        'text': '\n'.join(current_text).strip(),
                        'title': f"{current_section} - {current_subsection}" if current_subsection else current_section
                    })
                    current_text = []

                current_subsection = line.replace('###', '').strip()

            else:
                current_text.append(line)

        # Save last chunk
        if current_text:
            chunks.append({
                'section': current_section,
                'subsection': current_subsection,
                'text': '\n'.join(current_text).strip(),
                'title': f"{current_section} - {current_subsection}" if current_subsection else current_section
            })

        # Filter out empty chunks
        chunks = [c for c in chunks if c['text']]

        return chunks

    def retrieve_knowledge(
        self,
        query: str,
        top_k: int = 3,
        min_similarity: float = 0.5
    ) -> List[Tuple[Dict[str, str], float]]:
        """
        Retrieve relevant knowledge chunks for a query.

        Args:
            query: Query text (e.g., parameter name + description)
            top_k: Number of top chunks to retrieve
            min_similarity: Minimum similarity threshold

        Returns:
            List of (chunk, similarity_score) tuples
        """
        if not self._initialized:
            logger.warning("RAG not initialized, call initialize() first")
            return []

        try:
            # Embed query
            query_embeddings = self.embedding_service.embed_text(query)
            query_embedding = np.array(query_embeddings[0])

            # Compute similarities with all knowledge chunks
            similarities = []
            for knowledge_embedding in self.knowledge_embeddings:
                similarity = self.embedding_service.calculate_similarity(
                    query_embedding.tolist(),
                    knowledge_embedding.tolist()
                )
                similarities.append(similarity)

            similarities = np.array(similarities)

            # Get top-k indices
            top_indices = np.argsort(similarities)[::-1][:top_k]

            # Filter by minimum similarity and return results
            results = []
            for idx in top_indices:
                similarity = similarities[idx]
                if similarity >= min_similarity:
                    results.append((self.knowledge_chunks[idx], float(similarity)))

            logger.debug(f"Retrieved {len(results)} knowledge chunks for query: {query[:50]}...")
            return results

        except Exception as e:
            logger.error(f"Failed to retrieve knowledge: {e}")
            return []

    def get_context_for_parameter(
        self,
        param_name: str,
        param_description: str,
        top_k: int = 2
    ) -> str:
        """
        Get domain knowledge context for a parameter.

        Args:
            param_name: Parameter name
            param_description: Parameter description
            top_k: Number of knowledge chunks to retrieve

        Returns:
            Formatted context string
        """
        if not self._initialized:
            return ""

        # Create query from parameter info
        query = f"{param_name}: {param_description}"

        # Retrieve relevant knowledge
        results = self.retrieve_knowledge(query, top_k=top_k)

        if not results:
            return ""

        # Format context
        context_parts = ["Domain Knowledge Context:"]
        for chunk, similarity in results:
            context_parts.append(f"\n[{chunk['title']}] (similarity: {similarity:.2f})")
            context_parts.append(chunk['text'][:500])  # Limit to 500 chars per chunk

        return '\n'.join(context_parts)

