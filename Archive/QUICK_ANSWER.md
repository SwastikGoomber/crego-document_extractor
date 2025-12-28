# Quick Answer: How Embeddings & RAG Work

## Question 1: How does "embeddings locate and programmatic extraction" work?

### Simple Answer

**Embeddings** = Semantic search to find WHERE the data is  
**Programmatic** = Deterministic code to extract WHAT the data is

### The Flow

```
1. You ask: "Find Credit Score"
   ↓
2. System embeds query → [0.8, 0.2, -0.3, ..., 0.1] (1024 numbers)
   ↓
3. System embeds all document chunks:
   - Table 1 (Verification) → [0.79, 0.21, -0.29, ..., 0.09]  ← Very similar!
   - Table 2 (Accounts)    → [0.1, 0.9, 0.5, ..., 0.3]       ← Different
   - Table 3 (History)     → [0.2, 0.8, 0.4, ..., 0.2]       ← Different
   ↓
4. Calculate similarity (cosine):
   - Table 1: 0.78 ← Best match!
   - Table 2: 0.45
   - Table 3: 0.32
   ↓
5. System says: "Credit Score is probably in Table 1 (Verification)"
   ↓
6. Programmatic extraction:
   value = crif_report.bureau_score  # Direct code, no LLM!
   ↓
7. Return: {value: 627, source: "Verification Table", confidence: 0.74}
```

### What Embedding Output Looks Like

```python
# After embedding search, you get:
relevant_chunks = [
    {
        'source': 'Verification Table',
        'score': 0.78,  # ← This tells you how relevant it is
        'content': 'CIBIL Score: 627\nReport Date: 2024-01-15...',
        'data': <DataFrame object>  # ← Structured data for extraction
    },
    {
        'source': 'Account Summary',
        'score': 0.45,
        'content': 'Total Accounts: 12\nActive: 8...',
        'data': <DataFrame object>
    }
]

# Then programmatic extraction uses the structured data:
best_chunk = relevant_chunks[0]  # Verification Table (0.78)
value = best_chunk['data']['CIBIL Score']  # Direct lookup, no LLM!
```

### Key Point

**Embeddings don't extract data!** They just find the right section.  
**Code extracts data** from that section (accurate, fast, no hallucination).

---

## Question 2: How does RAG work? Where's the LLM conversation?

### Simple Answer

**RAG retrieves domain knowledge** but **doesn't use LLM for extraction** (yet).

It's like having a reference manual that you *could* consult, but currently you just keep it in your pocket for transparency.

### The Flow

```
1. RAG Initialization (one-time):
   Load config/domain_knowledge.md
   → Parse into 25 chunks
   → Embed all chunks
   → Store in memory
   
2. For each parameter (e.g., "DPD 30"):
   
   WITH RAG:
   ┌─────────────────────────────────────┐
   │ Retrieve Knowledge (parallel)       │
   │ Query: "DPD 30: Number of accounts" │
   │ → Find similar knowledge chunks     │
   │ → Get "Finding DPD Counts" (0.82)   │
   │ → Get "DPD Definition" (0.76)       │
   │ → Format as context string          │
   └─────────────────────────────────────┘
            ↓
   ┌─────────────────────────────────────┐
   │ Find Document Chunks (same as usual)│
   │ → Embed query                       │
   │ → Find "Account Details" (0.75)     │
   └─────────────────────────────────────┘
            ↓
   ┌─────────────────────────────────────┐
   │ Extract Programmatically (same!)    │
   │ → count_dpd_over_30(crif_report)    │
   │ → value = 3                         │
   └─────────────────────────────────────┘
            ↓
   ┌─────────────────────────────────────┐
   │ Add RAG context to result           │
   │ {                                   │
   │   value: 3,                         │
   │   confidence: 0.85,                 │
   │   rag_context: "Domain Knowledge:   │
   │     Finding DPD Counts (0.82)..."   │
   │ }                                   │
   └─────────────────────────────────────┘
```

### Where's the LLM?

**There is NO LLM conversation!**

RAG context is:
- ✅ Retrieved from knowledge base
- ✅ Stored in results (for transparency)
- ❌ NOT sent to LLM
- ❌ NOT used for extraction (yet)

### What Changes with RAG?

**Without RAG:**
```json
{
  "value": 3,
  "confidence": 0.85
}
```

**With RAG:**
```json
{
  "value": 3,
  "confidence": 0.85,
  "rag_context": "Domain Knowledge:\n[Finding DPD Counts] (0.82)\n1. Look for Account Details..."
}
```

**Only difference**: `rag_context` field added to results.

### Why Have RAG if It's Not Used?

**Current Use**: Transparency & debugging
- Shows what domain knowledge was available
- Helps understand extraction decisions
- Useful for auditing

**Future Use** (not implemented):
- LLM fallback if programmatic extraction fails
- Validation of extracted values
- Disambiguation when multiple values match

**Example Future Use:**
```python
# If programmatic extraction fails
if value is None:
    # THEN use LLM with RAG context
    prompt = f"{rag_context}\n\nDocument: {chunk}\n\nExtract: {param}"
    value = llm.extract(prompt)
```

---

## Visual Summary

### Embedding-Guided Extraction

```
Parameter Query
    ↓
[Embed Query] → Vector [0.8, 0.2, ...]
    ↓
[Embed Chunks] → Vectors [[0.79, ...], [0.1, ...], ...]
    ↓
[Calculate Similarity] → Scores [0.78, 0.45, 0.32]
    ↓
[Get Best Match] → "Verification Table" (0.78)
    ↓
[Extract with Code] → value = crif_report.bureau_score
    ↓
Result: {value: 627, confidence: 0.74}
```

### RAG (When Enabled)

```
Parameter Query
    ↓
[Retrieve Knowledge] → "Finding DPD Counts" (0.82)
    ↓                  "DPD Definition" (0.76)
    ↓
[Format Context] → "Domain Knowledge: ..."
    ↓
[Same Embedding Search] → "Account Details" (0.75)
    ↓
[Same Programmatic Extraction] → value = 3
    ↓
[Add Context to Result] → {value: 3, rag_context: "..."}
```

---

## Test It Yourself

### See Embedding Output
```bash
python tests/test_rag_simple.py
```

This will show you:
- ✅ What embeddings return (similarity scores)
- ✅ What RAG retrieves (knowledge chunks)
- ✅ How context is formatted

### Run Extraction
```bash
# Without RAG
python tests/evaluate.py  # (ENABLE_RAG=False in config.py)

# With RAG
# 1. Edit config.py: ENABLE_RAG = True
# 2. Run:
python tests/evaluate.py
```

Compare the outputs - you'll see RAG just adds `rag_context` field!

---

## Bottom Line

1. **Embeddings** = Smart search (finds relevant sections using semantic similarity)
2. **Programmatic** = Deterministic extraction (no LLM, no hallucination)
3. **RAG** = Domain knowledge retrieval (currently just for transparency, not used in extraction)

**No LLM is involved in the extraction process!** That's why it's fast and accurate.

