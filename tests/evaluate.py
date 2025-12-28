import asyncio
import os
import logging
import sys
import json
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app.services.parser import DoclingParser
from app.services.embeddings import EmbeddingService
from app.services.llm import LLMService
from app.services.extractors.gstr import GSTR3BExtractor
from app.services.extractors.crif import CRIFExtractor
from app.utils.output_formatter import format_extraction_output, print_summary, print_formatted_output
import pandas as pd
from config import DEFAULT_CRIF_PATHS, DEFAULT_GSTR_PATH, DEFAULT_PARAM_PATH

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sample File Paths (from config)
CRIF_PATHS = DEFAULT_CRIF_PATHS
GSTR_PATH = DEFAULT_GSTR_PATH
PARAM_PATH = DEFAULT_PARAM_PATH

async def run_evaluation():
    logger.info("Starting Evaluation Run...")

    # 1. Initialize Services
    parser = DoclingParser()
    embedding = EmbeddingService()
    llm = LLMService()
    gstr_extractor = GSTR3BExtractor()
    crif_extractor = CRIFExtractor(embedding, llm)

    # 2. Load Parameters
    logger.info("Loading Parameters...")
    df = pd.read_excel(PARAM_PATH)
    # Normalize keys
    df.columns = [c.lower().strip() for c in df.columns]
    params = []
    for _, row in df.iterrows():
        params.append({
            "id": row.get("parameter id", ""),
            "name": row.get("parameter name", ""),
            "description": row.get("description", "")
        })

    # 3. Process GSTR
    gst_data = []
    if os.path.exists(GSTR_PATH):
        logger.info(f"Processing GSTR: {GSTR_PATH}")
        with open(GSTR_PATH, "rb") as f:
            gst_doc = parser.parse_pdf(f.read(), source_name="gstr.pdf")
            gst_data = gstr_extractor.extract(gst_doc)
    else:
        logger.warning(f"GSTR file not found at {GSTR_PATH}")

    # 4. Process CRIF (process first PDF only for now)
    bureau_data = {}
    if CRIF_PATHS and os.path.exists(CRIF_PATHS[0]):
        crif_path = CRIF_PATHS[0]
        logger.info(f"Processing CRIF: {crif_path}")
        with open(crif_path, "rb") as f:
            crif_doc = parser.parse_pdf(f.read(), source_name=os.path.basename(crif_path))
            bureau_data = crif_extractor.extract(crif_doc, params)
    else:
        logger.warning("No CRIF files found")

    # 5. Format and display output
    output = format_extraction_output(bureau_data, gst_data)

    # Print summary
    print_summary(output)

    # Print full JSON
    print("\n" + "="*80)
    print("FULL JSON OUTPUT")
    print("="*80)
    print_formatted_output(output)

    # Save to file
    output_file = "extraction_output.json"
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)
    logger.info(f"Output saved to {output_file}")

if __name__ == "__main__":
    asyncio.run(run_evaluation())

