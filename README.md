# Document Intelligence Extraction System

A production-grade system to extract structured financial data from CRIF Bureau Reports and GSTR-3B Returns using a hybrid approach of **Docling**, **Embeddings**, and **Deterministic Logic**.

## Features

- **Robust PDF Parsing:** Uses `Docling` to convert PDFs into structured Markdown and Tables (no fragile text-scraping).
- **Disk-Based Caching:** SHA256-hashed cache system eliminates re-parsing identical PDFs (30-400s → ~100ms).
- **Hybrid Extraction Engine:**
  - **Embedding-Guided Extraction:** Uses semantic search to find relevant document sections, then applies programmatic extraction to extract the actual values from the identified sources.
  - **Deterministic:** Uses programmatic lookups to extract the numeric values to avoid LLM hallucination.
  - **Logic-Based:** Calculates derived fields (e.g., DPD counts) using Python logic, avoiding LLM math errors.
  - **Optional RAG (Retrieval-Augmented Generation):** Toggle-able for cases with ambiguous data (Off by default).
  - **Optional Fallback:** LLM (Gemini/Ollama) only for ambibuous fields where deterministic extraction fails.
- **Explainability:** Every extracted value comes with a `source` (Section/Table Name) and a `confidence` score.
- **GPU Acceleration:** Automatically detects and uses CUDA (NVIDIA) or MPS (Mac Metal) for faster parsing.

## Tech Stack

- **Framework:** FastAPI
- **Parser:** Docling
- **Embeddings:** Ollama (mxbai-embed-large)
- **LLM:** Google Gemini 2.5 Flash Lite / Ollama Gemma3:1b
- **Vector Search:** Cosine Similarity (NumPy)

## Setup & Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/SwastikGoomber/crego-document_extractor.git
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3A. **Install Local Models (Ollama):**
   Ensure [Ollama](https://ollama.com/) is installed and running.

   ```bash
   ollama pull mxbai-embed-large
   ollama pull gemma3:1b
   ollama serve
   ```
  **OR**

3B. **Set API Keys:**
   Obtain an API Key from Google AI Studio
   Create a `.env` file or export variables:
   ```bash
   export GOOGLE_API_KEY="your_gemini_key"
   ```

## Usage

### Run the API Server

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000/docs`.

### Run Extraction via API

Use the Swagger UI or `curl`:

```bash
curl -X POST "http://localhost:8000/extract" \
  -F "bureau_file=@path/to/crif.pdf" \
  -F "gst_file=@path/to/gstr.pdf" \
  -F "parameter_file=@path/to/params.xlsx"
```

### Run Evaluation Script (CLI)

To test the extraction system without starting the server:

```bash
python tests/evaluate.py
```

This will:

1. Parse CRIF and GSTR-3B documents
2. Extract all parameters using embedding-guided approach
3. Display a summary with extraction status
4. Save results to `extraction_output.json`

**Sample JSON Output**:

```json
{
  "bureau_parameters": {
    "bureau_credit_score": {
      "value": 627,
      "source": "Verification Table",
      "confidence": 0.63,
      "status": "extracted",
      "similarity_score": 0.643
    },
    "bureau_ntc_accepted": {
      "value": false,
      "source": "Account Remarks (0/36 accounts)",
      "confidence": 0.63,
      "status": "extracted",
      "similarity_score": 0.564
    },
    "bureau_overdue_threshold": {
      "value": null,
      "source": "Not applicable (policy parameter)",
      "confidence": 0.0,
      "status": "not_applicable"
    },
    "bureau_dpd_30": {
      "value": 0,
      "source": "Computed from 36 accounts",
      "confidence": 0.81,
      "status": "extracted",
      "similarity_score": 0.725
    },
    "bureau_dpd_60": {
      "value": 0,
      "source": "Computed from 36 accounts",
      "confidence": 0.81,
      "status": "extracted",
      "similarity_score": 0.725
    },
    "bureau_dpd_90": {
      "value": 0,
      "source": "Computed from 36 accounts",
      "confidence": 0.81,
      "status": "extracted",
      "similarity_score": 0.736
    },
    "bureau_settlement_writeoff": {
      "value": true,
      "source": "Account Remarks (34/36 accounts)",
      "confidence": 0.63,
      "status": "extracted",
      "similarity_score": 0.689
    },
    "bureau_no_live_pl_bl": {
      "value": false,
      "source": "Computed from 36 accounts",
      "confidence": 0.63,
      "status": "extracted",
      "similarity_score": 0.694
    },
    "bureau_suit_filed": {
      "value": true,
      "source": "Account Remarks (2/36 accounts)",
      "confidence": 0.63,
      "status": "extracted",
      "similarity_score": 0.576
    },
    "bureau_wilful_default": {
      "value": false,
      "source": "Account Remarks (0/36 accounts)",
      "confidence": 0.63,
      "status": "extracted",
      "similarity_score": 0.672
    },
    "bureau_written_off_debt_amount": {
      "value": 0.0,
      "source": "Account Summary Table",
      "confidence": 0.63,
      "status": "extracted",
      "similarity_score": 0.654
    },
    "bureau_max_loans": {
      "value": 54,
      "source": "Account Summary Table",
      "confidence": 0.63,
      "status": "extracted",
      "similarity_score": 0.694
    },
    "bureau_loan_amount_threshold": {
      "value": null,
      "source": "Not applicable (policy parameter)",
      "confidence": 0.0,
      "status": "not_applicable"
    },
    "bureau_credit_inquiries": {
      "value": 0,
      "source": "Inquiry Table",
      "confidence": 0.63,
      "status": "extracted",
      "similarity_score": 0.699
    },
    "bureau_max_active_loans": {
      "value": 25,
      "source": "Account Summary Table",
      "confidence": 0.63,
      "status": "extracted",
      "similarity_score": 0.673
    }
  },
  "gst_sales": [
    {
      "month": "January 2024",
      "sales": 951381.0,
      "source": "GSTR-3B Table 3.1 (Page 1)",
      "confidence": 1.0,
      "status": "extracted"
    }
  ],
  "overall_confidence_score": 0.695
}
```

**Output Summary**:

- **CRIF Parameters Extracted**: 13/15 (2 policy parameters not applicable)
- **GSTR Sales Extracted**: 1/1
- **Overall Confidence**: 0.695
- **Output File**: `extraction_output.json`

**Key Extracted Values**:
- `bureau_credit_score`: 627 (from Verification Table, similarity: 0.643)
- `bureau_max_loans`: 54 (from Account Summary Table, similarity: 0.694)
- `bureau_max_active_loans`: 25 (from Account Summary Table, similarity: 0.673)
- `bureau_dpd_30/60/90`: 0 (computed from 36 accounts, similarity: 0.72-0.74)
- `bureau_suit_filed`: True (found in 2/36 accounts, similarity: 0.576)
- `bureau_settlement_writeoff`: True (found in 34/36 accounts, similarity: 0.689)
- `gst_sales`: 951381.0 (from GSTR-3B Table 3.1, confidence: 1.0)

**Note**: The full JSON is saved to `extraction_output.json`.

### Run Comprehensive Testing & Accuracy Evaluation

To run the full test suite (as required by project specifications):

```bash
# Quick test (10 runs)
python tests/test_accuracy.py

# Full test (100 runs)
python tests/test_accuracy.py --runs 100
```

This comprehensive test will:

1. **Run extraction multiple times** to measure consistency
2. **Measure consistency** - Check if all runs produce identical values
3. **Measure accuracy** - Compare against ground truth values
4. **Generate detailed reports**:
   - Per-parameter consistency (✓/✗)
   - Per-parameter accuracy (expected vs actual)
   - Overall consistency rate
   - Overall accuracy percentage
5. **Save results** to `test_results.json`

**Sample Output:**

```
CONSISTENCY REPORT (100 Runs)
================================================================================
bureau_credit_score:
  Status: [OK] CONSISTENT

Overall Consistency: 100.0% (15/15 parameters)

ACCURACY REPORT (vs Ground Truth)
================================================================================
[OK] bureau_credit_score:
  Expected: 627
  Actual:   627

Overall Accuracy: 100.0% (15/15 parameters)
```

---

## Test Results

### Latest Test Run (100 runs)

**Test Date**: 2025-12-28 20:41:22

**Consistency Report**:
- **Overall Consistency**: 100.0% (16/16 parameters)
- All parameters produced identical values across all 100 runs
- No variance detected - fully deterministic extraction
- Example: `bureau_credit_score` = 627 in all 100 runs
- Example: `gst_sales` = 951381.0 in all 100 runs

**Accuracy Report**:
- **Overall Accuracy**: 100.0% (16/16 parameters)
- All CRIF parameters match ground truth exactly
- GSTR sales match ground truth exactly

**Performance Metrics**:
- **Setup Time**: 12.23s (one-time: parsing + embedding)
- **Extraction Time**: 0.786s per run (average)
- **Total Test Time**: 78.57s for 100 runs
- **Cache Hit Rate**: 100% (documents cached after first parse)

**Detailed Results**:

| Parameter | Expected | Actual | Status | Consistency (100 runs) |
|-----------|----------|--------|--------|------------------------|
| bureau_credit_score | 627 | 627 | ✅ | 100/100 |
| bureau_max_loans | 54 | 54 | ✅ | 100/100 |
| bureau_max_active_loans | 25 | 25 | ✅ | 100/100 |
| bureau_dpd_30 | 0 | 0 | ✅ | 100/100 |
| bureau_dpd_60 | 0 | 0 | ✅ | 100/100 |
| bureau_dpd_90 | 0 | 0 | ✅ | 100/100 |
| bureau_suit_filed | True | True | ✅ | 100/100 |
| bureau_wilful_default | False | False | ✅ | 100/100 |
| bureau_settlement_writeoff | True | True | ✅ | 100/100 |
| bureau_no_live_pl_bl | False | False | ✅ | 100/100 |
| bureau_written_off_debt_amount | 0.0 | 0.0 | ✅ | 100/100 |
| bureau_credit_inquiries | 0 | 0 | ✅ | 100/100 |
| bureau_ntc_accepted | False | False | ✅ | 100/100 |
| bureau_overdue_threshold | None | None | ✅ | 100/100 |
| bureau_loan_amount_threshold | None | None | ✅ | 100/100 |
| gst_sales | 951381.0 | 951381.0 | ✅ | 100/100 |

**Full Test Results**: See `test_results.json` for complete data including:
- Per-parameter consistency across all 100 runs
- Per-parameter accuracy vs ground truth
- Performance metrics (setup time, extraction time)
- Test metadata

**Key Metrics Summary**:
- ✅ **Consistency**: 100% (all parameters consistent across 100 runs)
- ✅ **Accuracy**: 100% (16/16 parameters match ground truth)
- ✅ **Performance**: 0.786s average extraction time per run
- ✅ **Cache Performance**: 100% cache hit rate (documents cached after first parse)
- ✅ **All Tests Passed**: true
- ✅ **Deterministic**: No variance detected across 100 runs

### Enable/Disable RAG (Retrieval-Augmented Generation)

The system includes an optional **RAG + LLM Fallback** feature that provides resilience when programmatic extraction fails.

#### How It Works:

**When `ENABLE_RAG = True`:**

1.**Try embedding + programmatic extraction first**
2.**If programmatic fails**
3.**Fall back to LLM with RAG context**

**When `ENABLE_RAG = False` (Default):**

- Only uses programmatic extraction
- Faster initialization (~5-10s saved)
- Returns `NOT_FOUND` if extraction fails


#### To Enable RAG:

1. **Edit `config.py`:**

   ```python
   # Line 67 in config.py
   ENABLE_RAG = True  # Enable RAG + LLM fallback
   ```

2. **Run extraction:**
   ```bash
   python tests/evaluate.py
   ```

**Sample Output:**

```json
{
  "bureau_parameters": {
    "bureau_credit_score": {
      "value": 627,
      "source": "Verification Table",
      "confidence": 0.63,
      "status": "extracted",
      "similarity_score": 0.643
    }
  },
  "gst_sales": [
    {
      "month": "January 2025",
      "sales": 951381.0,
      "source": "GSTR-3B Table 3.1 (Page 1)",
      "confidence": 1.0,
      "status": "extracted"
    }
  ],
  "overall_confidence_score": 0.695
}
```

### Cache Management

The system automatically caches parsed PDFs in `docling_cache/` directory. Cache is keyed by SHA256 hash of file content, ensuring:

- **No false cache hits** (different files won't collide)
- **Automatic invalidation** (file changes detected via hash mismatch)
- **Fast retrieval** (~100ms vs 30-400s parsing time)

To clear cache programmatically:

```python
from app.services.cache import DoclingCache
cache = DoclingCache()
cache.clear()  # Clears all cached files
```

Cache statistics:

```python
stats = cache.get_cache_stats()
print(f"Cache size: {stats['total_size_mb']} MB, Files: {stats['total_files']}")
```

## Project Structure

```
app/
├── services/
│   ├── parser.py        # Docling PDF to Markdown/Table conversion
│   ├── embeddings.py    # Vector generation and similarity search
│   ├── llm.py           # Gemini/Ollama wrapper
│   └── extractors/
│       ├── gstr.py      # GSTR-3B Table 3.1 logic
│       └── crif.py      # CRIF Account Summary + DPD logic
├── models/
│   └── schemas.py       # Pydantic response models
└── main.py              # FastAPI entrypoint
```
