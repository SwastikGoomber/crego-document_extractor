# CRIF Bureau & GSTR-3B Extraction Pipeline - Refactoring Plan

**Date:** 2025-12-27  
**Status:** PENDING APPROVAL  
**Scope:** Fix extraction logic and architecture without replacing Docling or adding more LLM calls

---

## Executive Summary

The current pipeline has **fundamental architectural flaws** in how it interprets Excel parameters and extracts values from CRIF Bureau Reports. The problem is NOT PDF parsing (Docling works correctly), but rather:

1. **Misunderstanding parameter intent** - Excel defines WHAT to look for, not WHERE or HOW
2. **LLMs extracting final values** - Violates the core principle that LLMs locate, code extracts
3. **Wrong DPD calculation logic** - Counting cells instead of accounts with delinquency status
4. **Extracting numbers from markdown text** - Ignoring Docling's authoritative table DataFrames
5. **Attempting to extract non-existent thresholds** - Policy parameters don't exist in CRIF PDFs

---

## Current State Analysis

### What Docling Provides (CORRECT ✅)

Docling successfully parses PDFs into three representations:

1. **Tables as pandas DataFrames** - AUTHORITATIVE source for numeric data

   - Example: Account Summary table with columns: `Number of Accounts`, `Active Accounts`, `Total Current Balance`, `Total Amount Overdue`
   - Example: Payment History with status codes: `000/STD`, `SUB`, `DBT`, `LSS`

2. **Structured chunks with headers** - For navigation and context

   - Example: `"Account Information"` sections (repeated for each account)
   - Example: `"Account Summary"`, `"Personal Info Variations"`

3. **Markdown text** - LOSSY representation, should NOT be used for numeric extraction
   - Contains formatting artifacts, spacing issues, OCR errors
   - Only suitable for: flag detection (Yes/No), context logging, debugging

### What Excel Parameters Define (MISUNDERSTOOD ❌)

The Excel file `Bureau parameters - Report.xlsx` contains **parameter definitions**, NOT data locations:

| Parameter ID               | Parameter Name    | Description                                    | Category            |
| -------------------------- | ----------------- | ---------------------------------------------- | ------------------- |
| `bureau_credit_score`      | CIBIL Score       | Credit bureau score (300–900 range)            | DIRECT NUMERIC      |
| `bureau_suit_filed`        | Suit Filed        | Indicates whether any suit filed status exists | BOOLEAN FLAG        |
| `bureau_dpd_30`            | 30+ DPD           | Count of accounts with 30+ days past due       | DERIVED METRIC      |
| `bureau_overdue_threshold` | Overdue Threshold | Maximum allowable overdue amount               | POLICY (NOT IN PDF) |

**Critical insight:** Excel parameters fall into 4 categories:

1. **DIRECT NUMERIC** - Map directly to table columns (e.g., Bureau Score, Total Current Balance)
2. **BOOLEAN FLAGS** - Textual indicators in remarks/status fields (e.g., Suit Filed: Yes/No)
3. **DERIVED METRICS** - Computed from account-level data (e.g., 30+ DPD count, Max Active Loans)
4. **POLICY PARAMETERS** - Thresholds/rules NOT present in CRIF (e.g., overdue_threshold, loan_amount_threshold)

---

## Critical Problems

### 🔴 PROBLEM 1: Wrong Interpretation of Excel Parameters

**Current (incorrect) assumption:**

- Excel tells us where to find values in the PDF
- Parameter names map directly to PDF text

**Reality:**

- Excel defines WHAT we need to extract (intent)
- Excel does NOT tell WHERE the value is
- Excel does NOT guarantee the value exists verbatim
- Parameter names may not match PDF column names

**Example:**

```csv
Parameter ID: bureau_overdue_threshold
Parameter Name: Overdue Threshold
Description: Maximum allowable overdue amount
```

This is a **POLICY PARAMETER** - it's a threshold for decision-making, NOT a value in the CRIF PDF.  
CRIF provides: `Total Amount Overdue` (observed value)  
CRIF does NOT provide: `Overdue Threshold` (policy cutoff)

**Fix Required:**

- Classify each parameter by category (DIRECT/FLAG/DERIVED/POLICY)
- Route extraction based on category
- Return `null` for POLICY parameters with status `"not_applicable"`

---

### 🔴 PROBLEM 2: Confusing Policy Thresholds with Observed Values

**Current behavior:**

```python
# In _extract_via_rag() - tries to extract "Overdue Threshold" from PDF
result = self._extract_via_rag(param, text_chunks)
# Returns: {"value": 3528476, "source": "...", "confidence": 0.75}
```

**Why this is wrong:**

- CRIF PDFs contain OBSERVATIONS (what happened), not POLICIES (what's allowed)
- Parameters like `overdue_threshold`, `loan_amount_threshold` are business rules
- These thresholds are defined by the lender, NOT reported by CRIF

**What CRIF provides:**

- `Total Amount Overdue`: 53,27,046 (observed overdue amount)
- `Total Current Balance`: 14,04,02,768 (observed balance)
- `Active Accounts`: 25 (observed count)

**What CRIF does NOT provide:**

- Overdue threshold (policy)
- Loan amount threshold (policy)
- Eligibility rules (policy)

**Fix Required:**

- Identify policy parameters in parameter classification
- Always return: `{"value": null, "status": "not_applicable", "confidence": 0.0}`
- Do NOT attempt extraction from text

---

### 🔴 PROBLEM 3: DPD Logic is Fundamentally Wrong

**Current (incorrect) logic in `_calculate_dpd()`:**

```python
# Lines 173-186 in crif.py
for col in df.columns:
    for val in df[col].values:
        val_str = str(val)
        if val_str.isdigit():
            if int(val_str) > threshold:  # ❌ WRONG: Counting cells
                count += 1
```

**Why this is wrong:**

1. Payment history cells are NOT numbers - they are STATUS CODES
2. Status codes: `000/STD` (Standard), `SUB` (Substandard), `DBT` (Doubtful), `LSS` (Loss)
3. DPD is about ACCOUNTS with delinquency, not individual payment cells
4. Current logic counts cells > 30, but cells contain codes like "000/STD"

**What DPD actually means:**

- **30+ DPD**: Count of ACCOUNTS where worst delinquency status >= 30 days
- **60+ DPD**: Count of ACCOUNTS where worst delinquency status >= 60 days
- **90+ DPD**: Count of ACCOUNTS where worst delinquency status >= 90 days

**Correct DPD logic:**

```python
# For each account:
#   1. Parse payment history (12-24 months of status codes)
#   2. Determine WORST status across history
#   3. Map status to DPD bucket:
#      - 000/STD → 0 DPD
#      - 030 → 30 DPD
#      - 060 → 60 DPD
#      - 090/SUB → 90 DPD
#      - 120/DBT → 120 DPD
#      - 180+/LSS → 180+ DPD
#   4. If worst DPD >= threshold, increment account count
```

**Fix Required:**

- Parse CRIF into account-level objects (see Problem 5)
- For each account, extract payment history status codes
- Determine worst delinquency status per account
- Count accounts exceeding threshold
- This is a BUSINESS LOGIC fix, not a parsing fix

---

### 🔴 PROBLEM 4: Unconstrained RAG Extraction

**Current behavior in `_extract_via_rag()`:**

```python
# Lines 247-260 in crif.py
llm_location_response = self.llm_service.generate(prompt, system_instruction)
location_context = llm_location_response.strip()

# Then extracts value from LLM response
extracted_value = self._extract_value_from_context(location_context, param)
# Problem: LLM can return ANY number from the chunk
```

**The issue:**

- Embeddings correctly find relevant chunk
- LLM is asked to "locate" the value
- But LLM returns context like: `"Written-off Amount: Rs. 3,528,476"`
- Code then extracts `3528476` using regex
- This number might be WRONG (e.g., it's a written-off amount, not overdue threshold)

**Why this happens:**

- LLM has no constraint on WHICH number to return
- Regex extracts the largest number found
- No validation that the number matches the parameter intent

**Fix Required:**

- LLMs may ONLY identify section relevance and provide location
- LLMs must NEVER extract numeric values
- All numeric extraction must come from Docling DataFrames
- Add strict validation: if value doesn't match expected type/range, return null

---

### 🔴 PROBLEM 5: Extracting Numbers from Markdown Text

**Current behavior:**

```python
# Lines 148-156 in crif.py - Score extraction from text
for chunk in chunks:
    if "score" in chunk["text"].lower():
        match = re.search(r"\b([3-8]\d{2})\b", chunk["text"])  # ❌ WRONG
        if match:
            return {"value": int(match.group(1)), ...}
```

**Why this is wrong:**

- Markdown text is LOSSY and NOISY
- Contains formatting artifacts, OCR errors, spacing issues
- Regex on markdown will produce incorrect values

**Example from Docling output:**

```markdown
## CRIF HM Score(S):

SCORE NAME PERFORM CONSUMER 2.2
RANGE 300-900
SCORE 627
```

Regex might match: `300`, `900`, `627`, or even page numbers like `480001`

**What should be used instead:**
Docling provides a **Verification table** (Table ID 1):

```python
{
  "Requested Service": "CB SCORE",
  "Description": "Enquired Entity exists in bureau",
  "Score": "627",  # ✅ AUTHORITATIVE
  "Remarks": ""
}
```

**Fix Required:**

- ❌ FORBID numeric extraction from markdown text
- ✅ ALL numeric values MUST come from Docling DataFrames
- Markdown text may ONLY be used for: flag detection (Yes/No), context logging, debugging

---

## Mandatory Fixes

### 🔧 FIX 1: Introduce Parameter Contract Layer

**Create a parameter specification system:**

```python
from enum import Enum
from typing import Callable, Any, List, Optional
from pydantic import BaseModel

class ParameterCategory(Enum):
    DIRECT = "direct"           # Maps directly to table column
    FLAG = "flag"               # Boolean/categorical from text
    DERIVED = "derived"         # Computed from other fields
    NOT_APPLICABLE = "not_applicable"  # Policy parameter, not in PDF

class ParameterSpec(BaseModel):
    id: str
    name: str
    description: str
    expected_type: type  # int, float, bool, str, None
    category: ParameterCategory
    allowed_sources: List[str]  # e.g., ["Account Summary", "Verification"]
    validator: Optional[Callable[[Any], bool]] = None

    def validate(self, value: Any) -> bool:
        """Validate extracted value against expected type and custom validator."""
        if value is None:
            return True  # null is always valid

        # Type check
        if not isinstance(value, self.expected_type):
            return False

        # Custom validation
        if self.validator and not self.validator(value):
            return False

        return True
```

**Parameter definitions:**

```python
PARAMETER_SPECS = {
    "bureau_credit_score": ParameterSpec(
        id="bureau_credit_score",
        name="CIBIL Score",
        description="Credit bureau score (300–900 range)",
        expected_type=int,
        category=ParameterCategory.DIRECT,
        allowed_sources=["Verification"],
        validator=lambda v: 300 <= v <= 900
    ),
    "bureau_suit_filed": ParameterSpec(
        id="bureau_suit_filed",
        name="Suit Filed",
        description="Indicates whether any suit filed status exists",
        expected_type=bool,
        category=ParameterCategory.FLAG,
        allowed_sources=["Account Remarks"],
        validator=None
    ),
    "bureau_dpd_30": ParameterSpec(
        id="bureau_dpd_30",
        name="30+ DPD",
        description="Count of accounts with 30+ days past due",
        expected_type=int,
        category=ParameterCategory.DERIVED,
        allowed_sources=["Payment History"],
        validator=lambda v: v >= 0
    ),
    "bureau_overdue_threshold": ParameterSpec(
        id="bureau_overdue_threshold",
        name="Overdue Threshold",
        description="Maximum allowable overdue amount",
        expected_type=type(None),
        category=ParameterCategory.NOT_APPLICABLE,
        allowed_sources=[],
        validator=None
    ),
    # ... more specs
}
```

**Validation enforcement:**

```python
def extract_parameter(param_id: str, raw_value: Any) -> Dict:
    spec = PARAMETER_SPECS[param_id]

    if not spec.validate(raw_value):
        return {
            "value": None,
            "source": "Validation failed",
            "confidence": 0.0,
            "validation_error": f"Expected {spec.expected_type}, got {type(raw_value)}"
        }

    return {
        "value": raw_value,
        "source": "...",
        "confidence": calculate_confidence(spec, raw_value)
    }
```

---

### 🔧 FIX 2: Strict Extraction Routing

**Implement category-based routing:**

```python
def extract(self, parsed_doc: Dict, parameters: List[Dict]) -> Dict:
    results = {}

    for param in parameters:
        spec = PARAMETER_SPECS[param['id']]

        # Route based on category
        if spec.category == ParameterCategory.NOT_APPLICABLE:
            result = self._return_not_applicable(spec)

        elif spec.category == ParameterCategory.DIRECT:
            result = self._extract_direct_from_tables(spec, parsed_doc['tables'])

        elif spec.category == ParameterCategory.FLAG:
            result = self._extract_flag_from_chunks(spec, parsed_doc['chunks'])

        elif spec.category == ParameterCategory.DERIVED:
            result = self._compute_derived_metric(spec, parsed_doc)

        else:
            result = {"value": None, "source": "Unknown category", "confidence": 0.0}

        results[param['id']] = result

    return results
```

**No fallbacks allowed:**

- If DIRECT extraction fails → return null (don't try RAG)
- If FLAG extraction fails → return null (don't try tables)
- If DERIVED computation fails → return null (don't try extraction)
- Any deviation is a bug

---

### 🔧 FIX 3: Account-Level Modeling (Required for Derived Metrics)

**Problem:**
Current code treats CRIF as flat tables. But CRIF has REPEATED "Account Information" blocks.

**Example from CRIF PDF:**

```
## Account Information 1
Account Type: BUSINESS LOAN
Active: Yes
Current Balance: 50,00,000
Overdue Amt: 0
Payment History: Jan: -, Feb: -, ..., Oct: 000/STD, Nov: 000/STD

## Account Information 2
Account Type: BUSINESS LOAN UNSECURED
Active: Yes
Current Balance: 13,59,144
Overdue Amt: 0
Payment History: Oct: 000/STD, Nov: 000/STD

... (25 active accounts total)
```

**Required data model:**

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class PaymentHistory:
    month: str
    status: str  # "000/STD", "030", "060", "090/SUB", "DBT", "LSS", etc.

    def get_dpd(self) -> int:
        """Convert status code to DPD days."""
        if "STD" in self.status or "000" in self.status:
            return 0
        elif "030" in self.status:
            return 30
        elif "060" in self.status:
            return 60
        elif "SUB" in self.status or "090" in self.status:
            return 90
        elif "DBT" in self.status or "120" in self.status:
            return 120
        elif "LSS" in self.status or "180" in self.status:
            return 180
        else:
            # Try to extract number
            import re
            match = re.search(r'(\d+)', self.status)
            return int(match.group(1)) if match else 0

@dataclass
class Account:
    account_number: str
    account_type: str  # "BUSINESS LOAN", "PERSONAL LOAN", "OVERDRAFT"
    is_active: bool
    is_secured: bool
    current_balance: float
    overdue_amount: float
    sanctioned_amount: float
    payment_history: List[PaymentHistory]
    remarks: str  # For flags like "Suit Filed", "Settlement"

    def get_worst_dpd(self) -> int:
        """Get the worst (highest) DPD from payment history."""
        if not self.payment_history:
            return 0
        return max(ph.get_dpd() for ph in self.payment_history)

    def has_suit_filed(self) -> bool:
        """Check if 'Suit Filed' appears in remarks."""
        return "suit filed" in self.remarks.lower()

    def has_settlement_writeoff(self) -> bool:
        """Check if settlement or write-off appears in remarks."""
        remarks_lower = self.remarks.lower()
        return "settlement" in remarks_lower or "write" in remarks_lower

@dataclass
class CRIFReport:
    accounts: List[Account]
    bureau_score: Optional[int]
    total_current_balance: float
    total_overdue_amount: float
    active_accounts_count: int

    def count_dpd_accounts(self, threshold: int) -> int:
        """Count accounts with worst DPD >= threshold."""
        return sum(1 for acc in self.accounts if acc.get_worst_dpd() >= threshold)

    def count_active_loans_by_type(self, loan_types: List[str]) -> int:
        """Count active loans of specific types."""
        return sum(
            1 for acc in self.accounts
            if acc.is_active and any(lt.lower() in acc.account_type.lower() for lt in loan_types)
        )

    def has_live_pl_bl(self) -> bool:
        """Check if there are live Personal Loan or Business Loan accounts."""
        return self.count_active_loans_by_type(["personal loan", "business loan"]) > 0
```

**Parsing strategy (Source Hierarchy):**

**CRITICAL: Data Source Priority Rules**

1. **Tables are the authoritative source for numeric fields** (when available)
2. **Chunks define account structure and boundaries** (which accounts exist)
3. **Text fills gaps** (only for fields not in tables)

**Example:**

- Account balance: Extract from table (if present), NOT from chunk text
- Account type: Extract from chunk text (not in tables)
- Payment history: Extract from chunk text (not in tables)

```python
def parse_crif_report(parsed_doc: Dict) -> CRIFReport:
    """
    Parse Docling output into structured CRIFReport object.

    Source hierarchy:
    1. Tables → Numeric fields (balance, overdue, sanctioned amount)
    2. Chunks → Structure (account boundaries, type, remarks)
    3. Text → Gaps only (fields not in tables or chunks)
    """

    # 1. Extract summary data from Account Summary table (AUTHORITATIVE)
    summary_table = find_table_by_columns(
        parsed_doc['tables'],
        ["Number of Accounts", "Active Accounts", "Total Current Balance"]
    )

    # 2. Parse individual account blocks from chunks
    # Chunks define STRUCTURE, tables provide NUMERIC AUTHORITY
    accounts = []
    for chunk in parsed_doc['chunks']:
        if chunk['header'].startswith("Account Information"):
            # Parse account structure from chunk
            account = parse_account_chunk(
                chunk,
                tables=parsed_doc['tables']  # Pass tables for numeric fields
            )
            accounts.append(account)

    # 3. Extract bureau score from Verification table (AUTHORITATIVE)
    verification_table = find_table_by_columns(
        parsed_doc['tables'],
        ["Requested Service", "Score"]
    )
    bureau_score = extract_score_from_verification(verification_table)

    return CRIFReport(
        accounts=accounts,
        bureau_score=bureau_score,
        total_current_balance=summary_table['Total Current Balance'],
        total_overdue_amount=summary_table['Total Amount Overdue'],
        active_accounts_count=summary_table['Active Accounts']
    )


def parse_account_chunk(chunk: Dict, tables: List[pd.DataFrame]) -> Account:
    """
    Parse a single account block.

    Source priority:
    1. Account-level table (if exists) → numeric fields
    2. Chunk text → account type, remarks, payment history
    """
    text = chunk['text']

    # Extract from text (structure)
    account_type = extract_account_type(text)  # e.g., "BUSINESS LOAN"
    remarks = extract_remarks(text)  # e.g., "Suit Filed: Yes"
    payment_history = extract_payment_history(text)  # e.g., "Oct: 000/STD"

    # Extract from tables (numeric authority)
    # Check if there's an account-specific table in this chunk
    account_table = find_account_table_in_chunk(chunk, tables)
    if account_table:
        current_balance = account_table.get('Current Balance', 0)
        overdue_amount = account_table.get('Overdue Amt', 0)
        sanctioned_amount = account_table.get('Disbd Amt/High Credit', 0)
    else:
        # Fallback to text parsing ONLY if table not available
        current_balance = extract_balance_from_text(text)
        overdue_amount = extract_overdue_from_text(text)
        sanctioned_amount = extract_sanctioned_from_text(text)

    return Account(
        account_type=account_type,
        current_balance=current_balance,  # From table (preferred)
        overdue_amount=overdue_amount,    # From table (preferred)
        sanctioned_amount=sanctioned_amount,  # From table (preferred)
        remarks=remarks,  # From text (only source)
        payment_history=payment_history  # From text (only source)
    )
```

**Then derived metrics become simple:**

```python
def _compute_derived_metric(self, spec: ParameterSpec, parsed_doc: Dict) -> Dict:
    # Parse once
    crif_report = parse_crif_report(parsed_doc)

    if spec.id == "bureau_dpd_30":
        value = crif_report.count_dpd_accounts(threshold=30)
    elif spec.id == "bureau_dpd_60":
        value = crif_report.count_dpd_accounts(threshold=60)
    elif spec.id == "bureau_dpd_90":
        value = crif_report.count_dpd_accounts(threshold=90)
    elif spec.id == "bureau_no_live_pl_bl":
        value = not crif_report.has_live_pl_bl()
    elif spec.id == "bureau_max_active_loans":
        value = crif_report.active_accounts_count
    else:
        return {"value": None, "source": "Unknown derived metric", "confidence": 0.0}

    return {
        "value": value,
        "source": f"Computed from {len(crif_report.accounts)} accounts",
        "confidence": 1.0
    }
```

---

### 🔧 FIX 4: Confidence Calculation Based on Validation

**Current problem:**
Confidence is assigned arbitrarily (0.75, 0.85, 0.95) based on extraction method, not validation.

**New approach:**

```python
def calculate_confidence(
    spec: ParameterSpec,
    value: Any,
    extraction_method: str,
    extraction_context: Optional[Dict] = None
) -> float:
    """
    Confidence = method_confidence × type_certainty × coverage_ratio

    Args:
        spec: Parameter specification
        value: Extracted value
        extraction_method: Method used for extraction
        extraction_context: Additional context (e.g., matched_accounts, total_accounts)
    """

    # Base confidence by extraction method
    method_confidence = {
        "direct_table": 0.95,
        "computed": 1.0,
        "flag_detection": 0.85,
        "rag_assisted": 0.70
    }.get(extraction_method, 0.5)

    # Validation multiplier
    if not spec.validate(value):
        return 0.0  # Failed validation → zero confidence

    # Type certainty
    if value is None:
        type_certainty = 0.0
    elif isinstance(value, spec.expected_type):
        type_certainty = 1.0
    else:
        type_certainty = 0.5

    # Coverage ratio (for FLAG and DERIVED parameters only)
    coverage_ratio = 1.0
    if spec.category in [ParameterCategory.FLAG, ParameterCategory.DERIVED]:
        if extraction_context:
            matched = extraction_context.get("matched_accounts", 0)
            total = extraction_context.get("total_accounts", 1)
            if total > 0:
                # Penalize low coverage
                # Example: 1/25 accounts → 0.04, 20/25 accounts → 0.80
                coverage_ratio = min(1.0, matched / total + 0.2)  # Add 0.2 baseline
                # Alternative: Use sqrt for less aggressive penalty
                # coverage_ratio = min(1.0, (matched / total) ** 0.5)

    return method_confidence * type_certainty * coverage_ratio
```

**Example scenarios:**

| Scenario                       | Method         | Type | Matched/Total | Coverage | Final Confidence |
| ------------------------------ | -------------- | ---- | ------------- | -------- | ---------------- |
| Direct table extraction        | direct_table   | ✅   | N/A           | 1.0      | 0.95             |
| Flag found in 1/25 accounts    | flag_detection | ✅   | 1/25          | 0.24     | 0.20             |
| Flag found in 20/25 accounts   | flag_detection | ✅   | 20/25         | 1.0      | 0.85             |
| DPD computed from all accounts | computed       | ✅   | 25/25         | 1.0      | 1.0              |
| Failed validation              | any            | ❌   | any           | any      | 0.0              |

---

## What to Keep ✅

1. **Docling** - PDF parsing works correctly, provides excellent table extraction
2. **Caching** - Disk cache for Docling outputs is efficient
3. **Embeddings for section location** - Using embeddings to find relevant chunks is good
4. **Deterministic-first approach** - Philosophy is correct, just needs better implementation

---

## What NOT to Do ❌

1. ❌ Do NOT replace Docling with another PDF parser
2. ❌ Do NOT add more LLM calls
3. ❌ Do NOT extract numbers from markdown text
4. ❌ Do NOT let LLMs output final values
5. ❌ Do NOT infer values from nearby numbers
6. ❌ Do NOT create new files for documentation (unless explicitly requested)

---

## Implementation Plan

### Phase 1: Parameter Classification & Contracts

1. Create `ParameterCategory` enum
2. Create `ParameterSpec` class with validation
3. Define all 16 bureau parameters with specs
4. Add validation enforcement to extraction pipeline

### Phase 2: Account-Level Modeling

1. Create `Account`, `PaymentHistory`, `CRIFReport` dataclasses
2. Implement `parse_crif_report()` to convert Docling output to structured objects
3. Add helper methods for DPD calculation, loan type counting, flag detection

### Phase 3: Extraction Routing

1. Implement `_extract_direct_from_tables()` - only uses DataFrames
2. Implement `_extract_flag_from_chunks()` - boolean detection from text
3. Implement `_compute_derived_metric()` - uses CRIFReport object
4. Implement `_return_not_applicable()` - for policy parameters
5. Remove fallback logic (no RAG for failed table extraction)

### Phase 4: Fix DPD Logic

1. Parse payment history status codes from account chunks
2. Map status codes to DPD buckets
3. Count accounts (not cells) exceeding threshold
4. Test against sample PDFs

### Phase 5: Confidence & Validation

1. Implement validation-based confidence calculation
2. Add type checking and range validation
3. Return null for failed validations
4. Add detailed error messages

### Phase 6: Testing & Validation

1. Test all 16 parameters against 6 sample CRIF PDFs
2. Verify no numbers extracted from markdown
3. Verify policy parameters return null
4. Verify DPD counts match manual calculation
5. Verify confidence scores reflect validation status

---

## Expected Outcomes

After refactoring:

1. **Type Safety**: All extracted values match expected types or are null
2. **Explainability**: Every value traces to a specific DataFrame row/column or computation
3. **Correctness**: DPD counts reflect account-level delinquency, not cell counts
4. **Clarity**: Policy parameters clearly marked as not_applicable
5. **Confidence**: Confidence scores reflect validation, not extraction method
6. **Maintainability**: Adding new parameters requires defining a ParameterSpec

---

## Files to Modify

1. `app/services/extractors/crif.py` - Main extraction logic (major refactor)
2. `app/models/schemas.py` - Add ParameterSpec, Account, CRIFReport models
3. `tests/evaluate.py` - Update tests to verify new behavior

## Files to Create

1. `app/models/parameter_specs.py` - Parameter definitions and validators
2. `app/models/crif_models.py` - Account, PaymentHistory, CRIFReport dataclasses
3. `app/services/extractors/crif_parser.py` - Parse Docling output to CRIFReport

---

## Risk Assessment

**Low Risk:**

- Parameter classification (additive change)
- Account modeling (new code, doesn't break existing)
- Validation layer (improves correctness)

**Medium Risk:**

- Extraction routing refactor (changes core logic)
- DPD calculation fix (business logic change)

**High Risk:**

- Removing RAG fallbacks (might reduce coverage temporarily)

**Mitigation:**

- Implement in phases with testing after each phase
- Keep old code commented out until new code is validated
- Test against all 6 sample PDFs after each phase

---

## Success Criteria

1. ✅ All 16 parameters extracted with correct types or null
2. ✅ No numeric values extracted from markdown text
3. ✅ DPD counts match manual calculation from payment history
4. ✅ Policy parameters return null with not_applicable status
5. ✅ Confidence = 0.0 for failed validations
6. ✅ All values traceable to DataFrame or computation
7. ✅ No LLM calls for final value extraction

---

## Appendix: Actual Data Observations

### CRIF PDF Structure (from sample analysis)

**Tables provided by Docling:**

1. **Score Trend Table** (Table 0)

   - Columns: Retro dates and scores
   - Example: `{"30-09-2025": "609", "30-06-2025": "662", ...}`

2. **Verification Table** (Table 1)

   - Columns: `Requested Service`, `Description`, `Score`, `Remarks`
   - Contains: Bureau score (627), Income imputation, DOB verification
   - **This is the authoritative source for bureau_credit_score**

3. **Account Summary Table** (Table 2)

   - Columns: `Number of Accounts`, `Active Accounts`, `Overdue Accounts`, `Total Current Balance`, `Total Amount Overdue`, etc.
   - Example values: 54 accounts, 25 active, 1 overdue, ₹14,04,02,768 current balance
   - **This is the authoritative source for direct numeric parameters**

4. **Account Information blocks** (repeated in chunks)
   - Each account has: Type, Ownership, Balance, Overdue, Payment History
   - Payment History format: `Jan: -, Feb: -, ..., Oct: 000/STD, Nov: 000/STD`
   - **These must be parsed into Account objects for derived metrics**

### Parameter Classification (All 16 Parameters)

| #   | Parameter ID                     | Parameter Name          | Category | Expected Type | Source Location                       | Extraction Method                      |
| --- | -------------------------------- | ----------------------- | -------- | ------------- | ------------------------------------- | -------------------------------------- |
| 1   | `bureau_credit_score`            | CIBIL Score             | DIRECT   | int           | Verification Table, "CB SCORE" row    | DataFrame lookup                       |
| 2   | `bureau_ntc_accepted`            | NTC Accepted            | FLAG     | bool          | Verification Table or Account Remarks | Text search for NTC status             |
| 3   | `bureau_overdue_threshold`       | Overdue Threshold       | POLICY   | None          | N/A - Not in CRIF                     | Return null                            |
| 4   | `bureau_dpd_30`                  | 30+ DPD                 | DERIVED  | int           | Payment History across accounts       | Count accounts with worst DPD >= 30    |
| 5   | `bureau_dpd_60`                  | 60+ DPD                 | DERIVED  | int           | Payment History across accounts       | Count accounts with worst DPD >= 60    |
| 6   | `bureau_dpd_90`                  | 90+ DPD                 | DERIVED  | int           | Payment History across accounts       | Count accounts with worst DPD >= 90    |
| 7   | `bureau_settlement_writeoff`     | Settlement/Write-off    | FLAG     | bool          | Account Remarks                       | Search for "Settlement" or "Write-off" |
| 8   | `bureau_no_live_pl_bl`           | No Live PL/BL           | DERIVED  | bool          | Account objects                       | Check if any active PL/BL exists       |
| 9   | `bureau_suit_filed`              | Suit Filed              | FLAG     | bool          | Account Remarks                       | Search for "Suit Filed"                |
| 10  | `bureau_wilful_default`          | Wilful Default          | FLAG     | bool          | Account Remarks                       | Search for "Wilful Default"            |
| 11  | `bureau_written_off_debt_amount` | Written-off Debt Amount | DIRECT   | float         | Account Summary Table                 | "Total Writeoff Amt" column            |
| 12  | `bureau_max_loans`               | Max Loans               | DIRECT   | int           | Account Summary Table                 | "Number of Accounts" column            |
| 13  | `bureau_loan_amount_threshold`   | Loan Amount Threshold   | POLICY   | None          | N/A - Not in CRIF                     | Return null                            |
| 14  | `bureau_credit_inquiries`        | Credit Inquiries        | DIRECT   | int           | Additional Summary or separate table  | Needs investigation                    |
| 15  | `bureau_max_active_loans`        | Max Active Loans        | DIRECT   | int           | Account Summary Table                 | "Active Accounts" column               |
| 16  | _(reserved)_                     | _(if 16th exists)_      | -        | -             | -                                     | -                                      |

**Summary by Category:**

- **DIRECT**: 5 parameters (extract from DataFrames)
- **FLAG**: 4 parameters (boolean detection from text)
- **DERIVED**: 4 parameters (compute from account objects)
- **POLICY**: 2 parameters (return null, not in PDF)
- **UNCLEAR**: 1 parameter (needs investigation)

**Clarification on `bureau_max_loans`:**

The requirements state "Maximum number of loans in selected months" which is ambiguous. After analyzing the CRIF structure:

- **Account Summary Table** contains: `Number of Accounts` (54 in sample)
- This represents the **total count of all accounts** (active + closed) in the report
- **Decision**: Classify as **DIRECT** and extract from "Number of Accounts" column
- **Rationale**: CRIF does not provide temporal loan counts per month; the only deterministic value is the total account count in the report
- **Alternative interpretation** (if requirements clarify): Could be computed as max(active accounts across reporting periods), but this requires parsing all account blocks and is not currently defined

### Key Insights from Sample Data

1. **Bureau Score Location:**

   - ✅ Found in Verification Table: `{"Requested Service": "CB SCORE", "Score": "627"}`
   - ❌ NOT reliably extractable from markdown text (contains multiple numbers: 300, 900, 627)

2. **Account Summary Values:**

   - All numeric parameters available in structured DataFrame
   - Example: `Total Amount Overdue: 53,27,046` (formatted with commas)
   - Must clean numbers: remove commas, convert to int/float

3. **Payment History Format:**

   - Status codes: `000/STD`, `030`, `060`, `090/SUB`, `DBT`, `LSS`, `-` (no data)
   - Located in Account Information chunks, NOT in a single table
   - Requires parsing each account block separately

4. **Account Information Blocks:**

   - Repeated sections with header "Account Information" (numbered 1, 2, 3, ...)
   - Each contains: Account Type, Ownership, Balance, Overdue, Payment History
   - Total of 25 active accounts in sample PDF (matches Account Summary)

5. **Flags in Remarks:**
   - Account Remarks field contains textual indicators
   - Example: "Suit Filed: Yes", "Settlement Amt: ..."
   - Must search across all account remarks, not just one

---

---

## 🔧 Critical Issues Addressed (Post-Review)

### Issue 1: `bureau_max_loans` Classification Ambiguity ✅ FIXED

**Problem:** Parameter was marked as DERIVED with "TBD" logic, creating implementation uncertainty.

**Root Cause:** Requirements state "Maximum number of loans in selected months" which is ambiguous without temporal data.

**Resolution:**

- **Reclassified as DIRECT** (from DERIVED)
- **Source:** Account Summary Table, "Number of Accounts" column
- **Rationale:** CRIF provides total account count (54 in sample), not temporal loan counts per month
- **Value:** Total accounts in report (active + closed)

**Alternative (if requirements clarify):** Could be computed as max(active accounts across reporting periods), but this requires parsing all account blocks and is not currently defined in requirements.

---

### Issue 2: Confidence Formula Enhancement ✅ FIXED

**Problem:** Original formula over-trusted FLAG and DERIVED parameters regardless of coverage.

**Example:**

- Flag found in 1/25 accounts → Same confidence as 20/25 accounts ❌

**Original Formula:**

```python
confidence = method_confidence × type_certainty
```

**Enhanced Formula:**

```python
confidence = method_confidence × type_certainty × coverage_ratio
```

**Coverage Ratio (for FLAG and DERIVED only):**

```python
coverage_ratio = min(1.0, matched_accounts / total_accounts + 0.2)
```

**Impact:**
| Scenario | Old Confidence | New Confidence | Improvement |
|----------|----------------|----------------|-------------|
| Flag in 1/25 accounts | 0.85 | 0.20 | More realistic |
| Flag in 20/25 accounts | 0.85 | 0.85 | Unchanged (correct) |
| Direct table extraction | 0.95 | 0.95 | Unchanged (N/A) |

---

### Issue 3: Account Parsing Source Hierarchy ✅ CLARIFIED

**Problem:** Original plan said "parse accounts from chunks" without specifying numeric field authority.

**Risk:** Could lead to extracting numeric values from chunk text instead of tables (regression).

**Clarification Added:**

**Source Priority Rules:**

1. **Tables** → Authoritative source for numeric fields (balance, overdue, sanctioned amount)
2. **Chunks** → Define account structure and boundaries (which accounts exist, account type, remarks)
3. **Text** → Fill gaps only (fields not available in tables)

**Example:**

- ✅ Account balance: Extract from table (if present)
- ❌ Account balance: Extract from chunk text (only if table missing)
- ✅ Account type: Extract from chunk text (not in tables)
- ✅ Payment history: Extract from chunk text (not in tables)

**Implementation:**

```python
def parse_account_chunk(chunk: Dict, tables: List[pd.DataFrame]) -> Account:
    # 1. Extract structure from text
    account_type = extract_account_type(text)
    remarks = extract_remarks(text)

    # 2. Extract numeric fields from tables (PREFERRED)
    account_table = find_account_table_in_chunk(chunk, tables)
    if account_table:
        current_balance = account_table.get('Current Balance', 0)
    else:
        # Fallback to text ONLY if table not available
        current_balance = extract_balance_from_text(text)
```

---

**END OF REFACTORING PLAN**

**Next Step:** Await approval before proceeding with implementation.

**Diagrams:** Three Mermaid diagrams have been rendered to visualize:

1. Before vs After architecture
2. Parameter classification and routing
3. DPD calculation fix (wrong vs correct)

**Document Version:** 1.1 (Post-Review)
**Last Updated:** 2025-12-27
**Status:** Ready for implementation approval
