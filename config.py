"""
Configuration file for the Document Intelligence system.
All configurable parameters are centralized here.
"""

# ============================================================================
# MODEL CONFIGURATION
# ============================================================================

# Embedding Model (Ollama)
EMBEDDING_MODEL = "mxbai-embed-large"  # Options: "mxbai-embed-large", "nomic-embed-text"

# LLM Models
LLM_PRIMARY_MODEL = "gemma3:1b"  # Primary Ollama model
LLM_BACKUP_MODEL = "gemini-2.5-flash-lite"  # Google AI Studio backup

# ============================================================================
# EMBEDDING & RETRIEVAL SETTINGS
# ============================================================================

# Similarity threshold for embedding-based retrieval (0.0 - 1.0)
SIMILARITY_THRESHOLD = 0.5

# Number of top chunks to retrieve for each parameter
TOP_K_CHUNKS = 3

# Similarity boost thresholds for confidence calculation
# Format: (min_similarity, boost_multiplier)
SIMILARITY_BOOST_THRESHOLDS = {
    "high": (0.85, 1.0),      # similarity >= 0.85 → boost = 1.0
    "medium": (0.70, 0.9),    # similarity >= 0.70 → boost = 0.9
    "low": (0.50, 0.7),       # similarity >= 0.50 → boost = 0.7
    "very_low": (0.0, 0.5)    # similarity < 0.50 → boost = 0.5
}

# ============================================================================
# CONFIDENCE CALCULATION
# ============================================================================

# Base confidence scores for different extraction methods
CONFIDENCE_METHOD_WEIGHTS = {
    "direct_table": 0.95,        # Direct extraction from tables
    "computed": 1.0,             # Computed/derived values
    "flag_detection": 0.85,      # Boolean flag detection
    "embedding_guided": 0.90,    # Embedding-guided extraction
    "rag_assisted": 0.70         # RAG-assisted extraction (if used)
}

# Overall confidence calculation method
# Options: "average", "weighted_average", "minimum"
OVERALL_CONFIDENCE_METHOD = "average"

# ============================================================================
# EXTRACTION SETTINGS
# ============================================================================

# Use embedding-guided extraction (set to False to use legacy direct parsing)
USE_EMBEDDING_GUIDED_EXTRACTION = True

# Enable RAG (Retrieval-Augmented Generation) for extraction
# When enabled:
#   1. Tries programmatic extraction first (fast, accurate)
#   2. If programmatic fails, uses LLM with domain knowledge context (slower, handles edge cases)
# When disabled:
#   - Only uses programmatic extraction (fails if value not found)
# Use case: Enable when PDF structure changes or new parameters appear
ENABLE_RAG = False  # Toggle: True to enable RAG+LLM fallback, False to use programmatic only

# Fallback to direct parsing if embedding-guided extraction fails
ENABLE_DIRECT_PARSING_FALLBACK = False

# ============================================================================
# PARSING & CACHING
# ============================================================================

# Cache directory for parsed documents
CACHE_DIR = "docling_cache"

# Maximum number of chunks to process per table
MAX_CHUNKS_PER_TABLE = 100

# Maximum text length for embedding (characters)
MAX_EMBEDDING_TEXT_LENGTH = 2000

# ============================================================================
# API SETTINGS (if running as API)
# ============================================================================

# API host and port
API_HOST = "0.0.0.0"
API_PORT = 8000

# Enable CORS
ENABLE_CORS = True

# ============================================================================
# LOGGING
# ============================================================================

# Log level: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
LOG_LEVEL = "INFO"

# Enable detailed extraction logging
ENABLE_EXTRACTION_LOGGING = True

# ============================================================================
# FILE PATHS (for testing/evaluation)
# ============================================================================

# Default paths for sample documents
DEFAULT_CRIF_PATHS = [
    "CRIF_Bureau_Report/JEET  ARORA_PARK251217CR671901414.pdf",
    "CRIF_Bureau_Report/SHATNAM ARORA_PARK251217CR671898385.pdf"
]

DEFAULT_GSTR_PATH = "GSTR-3B_GST_Return/GSTR3B_06AAICK4577H1Z8_012025.pdf"

DEFAULT_PARAM_PATH = "Parameter Definition/Bureau parameters - Report.xlsx"

