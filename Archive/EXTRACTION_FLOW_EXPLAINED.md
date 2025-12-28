# Extraction Flow Explained

This document explains how the embedding-guided extraction and RAG work in detail.

---

## 🔍 Part 1: How Embedding-Guided Extraction Works

### The Problem

You have a PDF with 50+ pages and need to find where "Credit Score" is mentioned. Traditional approaches:

- ❌ **Regex/Text Search**: Brittle, misses variations like "CIBIL Score", "Bureau Score"
- ❌ **LLM on Full Document**: Too slow, expensive, unreliable for structured data

### The Solution: Embedding-Guided + Programmatic Extraction

**Key Insight**: Use embeddings to **locate** the right section, then use **deterministic code** to extract the value.

---

### Step-by-Step Flow

#### **Step 1: Prepare Document Chunks**

The parsed PDF is split into chunks:

```python
# From app/services/extractors/crif.py:76-117
chunks = [
    {
        'type': 'table',
        'index': 0,
        'content': 'Verification Table\nCIBIL Score: 627\nReport Date: 2024-01-15',
        'source': 'Table 1',
        'data': <DataFrame object>
    },
    {
        'type': 'table',
        'index': 1,
        'content': 'Account Summary\nTotal Accounts: 12\nActive: 8',
        'source': 'Table 2',
        'data': <DataFrame object>
    },
    # ... more chunks
]
```

**Why chunks?** Embedding models have token limits (512 tokens for mxbai-embed-large). We split the document into digestible pieces.

---

#### **Step 2: Embed Query and Chunks**

```python
# From app/services/embeddings.py:93-145

# 1. Create query from parameter
query = "Credit Score: Bureau credit score from CIBIL report"

# 2. Embed query → vector of 1024 numbers
query_embedding = embed_text(query)
# Result: [0.123, -0.456, 0.789, ..., 0.234]  (1024 dimensions)

# 3. Embed each chunk → vectors of 1024 numbers
chunk_embeddings = []
for chunk in chunks:
    chunk_embedding = embed_text(chunk['content'])
    chunk_embeddings.append(chunk_embedding)
```

**What are embeddings?** Vectors that capture semantic meaning. Similar concepts have similar vectors.

Example:

- "Credit Score" → `[0.8, 0.2, -0.3, ...]`
- "CIBIL Score" → `[0.79, 0.21, -0.29, ...]` (very similar!)
- "Payment History" → `[0.1, 0.9, 0.5, ...]` (different)

---

#### **Step 3: Calculate Similarity**

```python
# From app/services/embeddings.py:59-73

# Cosine similarity: measures angle between vectors
# Range: -1 (opposite) to 1 (identical)

similarities = []
for chunk_embedding in chunk_embeddings:
    similarity = cosine_similarity(query_embedding, chunk_embedding)
    similarities.append(similarity)

# Results:
# Chunk 0 (Verification Table): 0.78  ← Best match!
# Chunk 1 (Account Summary): 0.45
# Chunk 2 (Payment History): 0.32
```

**Embedding Output Example:**

```json
[
    {
        "chunk": "Verification Table\nCIBIL Score: 627...",
        "source": "Table 1",
        "score": 0.78,
        "data": <DataFrame>
    },
    {
        "chunk": "Account Summary\nTotal Accounts: 12...",
        "source": "Table 2",
        "score": 0.45,
        "data": <DataFrame>
    },
    {
        "chunk": "Payment History\nDPD: 30, 60, 90...",
        "source": "Table 3",
        "score": 0.32,
        "data": <DataFrame>
    }
]
```

---

#### **Step 4: Filter by Threshold**

```python
# From config.py
SIMILARITY_THRESHOLD = 0.3
TOP_K_CHUNKS = 3

# Keep only chunks with similarity >= 0.3
relevant_chunks = [chunk for chunk in chunks if chunk['score'] >= 0.3]

# Get top 3
top_chunks = relevant_chunks[:3]
```

**Result**: We now know "Verification Table" (score 0.78) is the most relevant section!

---

#### **Step 5: Programmatic Extraction**

**This is the key difference from pure LLM approaches!**

```python
# From app/services/extractors/crif.py:197-220

# We DON'T ask LLM to extract from text
# We use deterministic code on structured data

best_chunk = relevant_chunks[0]  # Verification Table
similarity_score = 0.78

# Extract programmatically from parsed CRIF report
if spec.id == "bureau_credit_score":
    value = crif_report.bureau_score  # Direct attribute access
    source = "Verification Table"
    confidence = 0.95  # High confidence (deterministic)

# Boost confidence based on similarity
final_confidence = confidence * similarity_score
# 0.95 × 0.78 = 0.74

return {
    "value": 627,
    "source": "Verification Table",
    "confidence": 0.74,
    "similarity_score": 0.78,
    "status": "extracted"
}
```

**Why programmatic?**

- ✅ **Accurate**: No LLM hallucination
- ✅ **Fast**: Direct data access
- ✅ **Reliable**: Deterministic logic
- ✅ **Explainable**: Clear source attribution

---

### Summary: Embedding-Guided Flow

```
Parameter Query
    ↓
Embed Query → [0.8, 0.2, -0.3, ...]
    ↓
Embed All Chunks → [[0.79, 0.21, ...], [0.1, 0.9, ...], ...]
    ↓
Calculate Similarities → [0.78, 0.45, 0.32, ...]
    ↓
Get Top Chunks → [Verification Table (0.78), Account Summary (0.45), ...]
    ↓
Extract Programmatically → value = crif_report.bureau_score
    ↓
Return Result → {value: 627, confidence: 0.74}
```

**Key Point**: Embeddings tell us **WHERE** to look, code tells us **WHAT** to extract.

---

## 🧠 Part 2: How RAG Works (When ENABLE_RAG=True)

### The Problem

Sometimes the parameter description is ambiguous:

- "DPD 30" - What does this mean? 30 days? 30 accounts?
- "Suit Filed" - Where to look? What format?

### The Solution: Domain Knowledge Base

RAG adds a **knowledge base** that explains domain-specific terms.

---

### RAG Flow

#### **Step 1: Initialization (One-time)**

```python
# From app/services/rag_service.py:36-70

# 1. Load domain knowledge
with open('config/domain_knowledge.md') as f:
    content = f.read()

# 2. Parse into chunks (by ### sections)
knowledge_chunks = [
    {
        'title': 'Credit Bureau Terms - DPD (Days Past Due)',
        'text': '- Definition: Number of days a payment is overdue\n- Categories: 30+, 60+, 90+...'
    },
    {
        'title': 'Common Extraction Patterns - Finding DPD Counts',
        'text': '1. Look for Account Details\n2. Check payment history\n3. Count accounts...'
    },
    # ... 25 total chunks
]

# 3. Embed all knowledge chunks
knowledge_embeddings = embed_text([chunk['text'] for chunk in knowledge_chunks])
# Result: 25 vectors stored in memory
```

---

#### **Step 2: Retrieve Knowledge (Per Parameter)**

```python
# From app/services/rag_service.py:191-226

# For parameter "DPD 30"
query = "DPD 30: Number of accounts with 30+ days past due"

# 1. Embed query
query_embedding = embed_text(query)

# 2. Compare with all 25 knowledge embeddings
similarities = []
for knowledge_embedding in knowledge_embeddings:
    similarity = cosine_similarity(query_embedding, knowledge_embedding)
    similarities.append(similarity)

# Results:
# Chunk 16 (Finding DPD Counts): 0.82  ← Best match!
# Chunk 2 (DPD Definition): 0.76
# Chunk 17 (Finding Flags): 0.58
# ... (22 more chunks with lower scores)

# 3. Get top 2 chunks above 0.5 threshold
top_knowledge = [
    (knowledge_chunks[16], 0.82),
    (knowledge_chunks[2], 0.76)
]
```

---

#### **Step 3: Format Context**

```python
# From app/services/rag_service.py:220-226

# Format knowledge into context string
context = """
Domain Knowledge Context:

[Common Extraction Patterns - Finding DPD Counts] (similarity: 0.82)
1. Look for "Account Details" or "Payment History"
2. Check each account's payment history
3. Count accounts where DPD exceeds threshold (30/60/90)
4. May be in columns like "DPD", "Days Past Due", "Overdue Days"

[Credit Bureau Terms - DPD (Days Past Due)] (similarity: 0.76)
- Definition: Number of days a payment is overdue from the due date
- Categories:
  - 30+ DPD: Payments overdue by 30 or more days
  - 60+ DPD: Payments overdue by 60 or more days
  - 90+ DPD: Payments overdue by 90 or more days (serious delinquency)
- Location: Account-level payment history in CRIF reports
- Calculation: Count of accounts with DPD exceeding threshold in a given period
"""
```

---

#### **Step 4: Use Context (Optional)**

**Important**: RAG context is **NOT** sent to an LLM for extraction!

Instead, it's:

1. **Stored in the result** for transparency/debugging
2. **Available for future LLM fallback** (if needed)
3. **Used for logging/auditing**

```python
# From app/services/extractors/crif.py:134-194

# Get RAG context
rag_context = rag_service.get_context_for_parameter(
    "DPD 30",
    "Number of accounts with 30+ days past due"
)

# Find relevant chunks using embeddings (same as before)
relevant_chunks = embedding_service.find_relevant_chunks(query, document_chunks)

# Extract programmatically (same as before)
value = count_accounts_with_dpd_over_30(crif_report)

# Add RAG context to result
result = {
    "value": 3,
    "source": "Account Details Table",
    "confidence": 0.85,
    "status": "extracted",
    "rag_context": rag_context  # ← Added for transparency
}
```

---

### What RAG Does NOT Do

❌ **RAG does NOT**:

- Send context to LLM for extraction
- Replace programmatic extraction
- Change the extraction logic
- Slow down extraction (context retrieval is fast)

✅ **RAG DOES**:

- Provide domain knowledge for transparency
- Enable future LLM fallback (if programmatic extraction fails)
- Help with debugging (shows what knowledge was available)
- Support edge cases (if we add LLM fallback later)

---

### When is RAG Context Actually Used?

**Currently**: Only stored in results for transparency.

**Future Use Cases** (not implemented yet):

1. **LLM Fallback**: If programmatic extraction fails, send context + document to LLM
2. **Validation**: Use knowledge to validate extracted values
3. **Disambiguation**: When multiple values match, use knowledge to pick the right one

**Example Future LLM Fallback**:

```python
# If programmatic extraction fails
if value is None:
    # Send to LLM with RAG context
    prompt = f"""
    {rag_context}

    Document:
    {relevant_chunk['content']}

    Extract: {param_name}
    """
    value = llm.extract(prompt)
```

---

## 🔄 Complete Flow Comparison

### Without RAG (ENABLE_RAG=False)

```
Parameter: DPD 30
    ↓
Embed Query → [0.8, 0.2, ...]
    ↓
Find Relevant Chunks → Account Details Table (0.75)
    ↓
Extract Programmatically → count_dpd_over_30()
    ↓
Result: {value: 3, confidence: 0.85}
```

### With RAG (ENABLE_RAG=True)

```
Parameter: DPD 30
    ↓
Embed Query → [0.8, 0.2, ...]
    ↓
Retrieve Knowledge → "Finding DPD Counts" (0.82), "DPD Definition" (0.76)
    ↓
Format Context → "Domain Knowledge Context: ..."
    ↓
Find Relevant Chunks → Account Details Table (0.75)
    ↓
Extract Programmatically → count_dpd_over_30()
    ↓
Result: {value: 3, confidence: 0.85, rag_context: "..."}
                                        ↑
                                   Added for transparency
```

**Difference**: RAG adds `rag_context` field to results. Extraction logic is **identical**.

---

## 📊 Real Example Output

### Without RAG

```json
{
  "bureau_dpd_30": {
    "value": 3,
    "source": "Account Details Table",
    "confidence": 0.85,
    "similarity_score": 0.75,
    "status": "extracted"
  }
}
```

### With RAG

```json
{
  "bureau_dpd_30": {
    "value": 3,
    "source": "Account Details Table",
    "confidence": 0.85,
    "similarity_score": 0.75,
    "status": "extracted",
    "rag_context": "Domain Knowledge Context:\n\n[Common Extraction Patterns - Finding DPD Counts] (similarity: 0.82)\n1. Look for \"Account Details\" or \"Payment History\"\n2. Check each account's payment history\n3. Count accounts where DPD exceeds threshold (30/60/90)\n..."
  }
}
```

**Only difference**: `rag_context` field added.

---

## 💡 Key Takeaways

### Embedding-Guided Extraction

1. **Embeddings locate** the relevant section (semantic search)
2. **Code extracts** the value (deterministic, accurate)
3. **No LLM** involved in extraction (fast, reliable)
4. **Similarity score** boosts confidence

### RAG (Retrieval-Augmented Generation)

1. **Loads domain knowledge** from markdown file
2. **Retrieves relevant knowledge** for each parameter
3. **Stores context** in results (transparency)
4. **Does NOT change** extraction logic (yet)
5. **Enables future** LLM fallback (if needed)

### Why This Approach Works

- ✅ **Fast**: Embeddings are quick, no LLM calls
- ✅ **Accurate**: Programmatic extraction, no hallucination
- ✅ **Flexible**: Embeddings handle variations ("Credit Score" vs "CIBIL Score")
- ✅ **Explainable**: Clear source attribution + similarity scores
- ✅ **Extensible**: RAG enables future enhancements

---

## 🧪 Test It Yourself

### See Embedding Output

```bash
python -c "
from app.services.embeddings import EmbeddingService
from app.services.parser import DoclingParser

# Parse a PDF
parser = DoclingParser()
with open('data/crif/sample.pdf', 'rb') as f:
    doc = parser.parse_pdf(f.read())

# Prepare chunks
chunks = []
for i, table in enumerate(doc['tables']):
    chunks.append({'content': str(table['dataframe']), 'source': f'Table {i+1}'})

# Find relevant chunks
embedding = EmbeddingService()
results = embedding.find_relevant_chunks('Credit Score', chunks)

# Print results
for r in results:
    print(f\"Source: {r['source']}, Score: {r['score']:.3f}\")
    print(f\"Content: {r['content'][:200]}...\n\")
"
```

### See RAG Output

```bash
python tests/test_rag_simple.py
```

This will show you exactly what knowledge is retrieved for each parameter!

---
