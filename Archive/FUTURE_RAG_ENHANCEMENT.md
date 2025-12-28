# Future RAG Enhancement: Make RAG Actually Useful

## Current Problem

RAG is implemented but **not actually used** for extraction. It only adds a `rag_context` field to results.

**Value**: ~5% (transparency only)

---

## Proposed Enhancement: LLM Fallback with RAG

### Use Case

When programmatic extraction fails (value not found, ambiguous, or new parameter), fall back to LLM with RAG context.

---

## Implementation

### Step 1: Add LLM Extraction Method

Add to `app/services/extractors/crif.py`:

```python
def _extract_with_llm_and_rag(
    self,
    spec,
    chunk: Dict[str, Any],
    rag_context: str
) -> Dict:
    """
    Extract parameter using LLM with RAG context.
    Used as fallback when programmatic extraction fails.
    """
    # Build prompt with RAG context
    prompt = f"""
You are extracting structured data from a credit bureau report.

{rag_context}

Document Section:
{chunk['content']}

Extract the following parameter:
- Name: {spec.name}
- Description: {spec.description}
- Expected Type: {spec.expected_type}

Instructions:
1. Use the domain knowledge above to understand what to look for
2. Extract the exact value from the document
3. If not found, return "NOT_FOUND"
4. If not applicable, return "NOT_APPLICABLE"

Return only the extracted value, nothing else.
"""

    try:
        # Call LLM
        response = self.llm_service.generate(prompt)
        value = response.strip()
        
        # Parse response
        if value == "NOT_FOUND":
            return {
                "value": None,
                "source": chunk['source'],
                "confidence": 0.0,
                "status": ExtractionStatus.NOT_FOUND,
                "extraction_method": "llm_with_rag",
                "rag_context": rag_context
            }
        elif value == "NOT_APPLICABLE":
            return {
                "value": None,
                "source": chunk['source'],
                "confidence": 0.0,
                "status": ExtractionStatus.NOT_APPLICABLE,
                "extraction_method": "llm_with_rag",
                "rag_context": rag_context
            }
        else:
            # Convert to expected type
            if spec.expected_type == "int":
                value = int(value)
            elif spec.expected_type == "float":
                value = float(value)
            elif spec.expected_type == "bool":
                value = value.lower() in ["true", "yes", "1"]
            
            return {
                "value": value,
                "source": chunk['source'],
                "confidence": 0.6,  # Lower confidence for LLM extraction
                "status": ExtractionStatus.EXTRACTED,
                "extraction_method": "llm_with_rag",
                "rag_context": rag_context
            }
    
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        return {
            "value": None,
            "source": chunk['source'],
            "confidence": 0.0,
            "status": ExtractionStatus.EXTRACTION_FAILED,
            "extraction_method": "llm_with_rag",
            "error": str(e)
        }
```

### Step 2: Modify Extraction Flow

Update `_extract_with_embeddings` method:

```python
def _extract_with_embeddings(
    self,
    spec,
    crif_report,
    document_chunks: List[Dict[str, Any]]
) -> Dict:
    """
    Extract parameter using embedding-guided approach:
    1. Use embeddings to find relevant chunks
    2. (Optional) Retrieve domain knowledge via RAG
    3. Extract programmatically from those chunks
    4. (NEW) If programmatic fails, try LLM with RAG
    """
    # Create query from parameter spec
    query = f"{spec.name}: {spec.description}"

    # Get domain knowledge context if RAG is enabled
    rag_context = ""
    if self.rag_service:
        rag_context = self.rag_service.get_context_for_parameter(
            spec.name,
            spec.description
        )

    # Find relevant chunks using embeddings
    relevant_chunks = self.embedding_service.find_relevant_chunks(
        query=query,
        chunks=document_chunks
    )

    if not relevant_chunks:
        logger.warning(f"No relevant chunks found for {spec.id}")
        return {
            "value": None,
            "source": "No relevant sections found",
            "confidence": 0.0,
            "status": ExtractionStatus.NOT_FOUND,
            "rag_context": rag_context if rag_context else None
        }

    # Get the best matching chunk
    best_chunk = relevant_chunks[0]
    similarity_score = best_chunk.get('score', 0.0)

    # Extract programmatically based on category
    if spec.category == ParameterCategory.DIRECT:
        result = self._extract_direct_from_report(spec, crif_report)
    elif spec.category == ParameterCategory.FLAG:
        result = self._extract_flag_from_report(spec, crif_report)
    elif spec.category == ParameterCategory.DERIVED:
        result = self._extract_derived_from_report(spec, crif_report)
    else:
        result = {
            "value": None,
            "source": "Unknown category",
            "confidence": 0.0,
            "status": ExtractionStatus.EXTRACTION_FAILED
        }

    # ✅ NEW: If programmatic extraction failed, try LLM with RAG
    if result.get('value') is None and rag_context and self.rag_service:
        logger.info(f"Programmatic extraction failed for {spec.id}, trying LLM with RAG")
        
        llm_result = self._extract_with_llm_and_rag(
            spec=spec,
            chunk=best_chunk,
            rag_context=rag_context
        )
        
        if llm_result.get('value') is not None:
            result = llm_result
            # Boost confidence based on similarity score
            result['confidence'] *= self._get_similarity_boost(similarity_score)
            result['similarity_score'] = similarity_score
            return result

    # Boost confidence based on similarity score (for programmatic extraction)
    if result.get('value') is not None:
        original_confidence = result.get('confidence', 0.0)
        similarity_boost = self._get_similarity_boost(similarity_score)
        result['confidence'] = original_confidence * similarity_boost
        result['similarity_score'] = similarity_score
        result['status'] = ExtractionStatus.EXTRACTED
        result['extraction_method'] = 'programmatic'

        # Add RAG context if available (for debugging/transparency)
        if rag_context:
            result['rag_context'] = rag_context

    return result
```

---

## Benefits

1. **Handles edge cases** - New/unusual parameters that aren't in spec
2. **Graceful degradation** - Falls back to LLM instead of failing
3. **RAG improves LLM** - Domain knowledge guides extraction
4. **Transparency** - Results show which method was used

---

## Example Output

### Programmatic Extraction (Current)
```json
{
  "value": 627,
  "confidence": 0.95,
  "extraction_method": "programmatic"
}
```

### LLM Fallback with RAG (New)
```json
{
  "value": "Special Attention: High utilization",
  "confidence": 0.42,
  "extraction_method": "llm_with_rag",
  "rag_context": "Domain Knowledge: Custom remarks usually at bottom..."
}
```

---

## When to Implement

- ✅ When you have parameters not in the spec
- ✅ When programmatic extraction fails frequently
- ✅ When you need to handle free-text fields
- ✅ When you want graceful degradation

---

## Estimated Effort

- **Time**: 2-3 hours
- **Complexity**: Medium
- **Testing**: Add tests for LLM fallback scenarios

