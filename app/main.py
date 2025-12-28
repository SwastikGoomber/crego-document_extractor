import logging
import pandas as pd
import io
from fastapi import FastAPI, UploadFile, File, HTTPException
from contextlib import asynccontextmanager
from typing import List

# Import Services
from app.services.parser import DoclingParser
from app.services.embeddings import EmbeddingService
from app.services.llm import LLMService
from app.services.extractors.gstr import GSTR3BExtractor
from app.services.extractors.crif import CRIFExtractor
from app.models.schemas import ExtractionResponse, ParameterSource, GSTSale

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global Services (Lazy loaded)
services = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialize services on startup.
    """
    logger.info("Initializing services...")
    services["parser"] = DoclingParser()
    services["embedding"] = EmbeddingService() # Defaults to Ollama nomic
    services["llm"] = LLMService() # Defaults to Gemini/Ollama
    
    services["gstr_extractor"] = GSTR3BExtractor()
    services["crif_extractor"] = CRIFExtractor(
        embedding_service=services["embedding"],
        llm_service=services["llm"]
    )
    logger.info("Services ready.")
    yield
    # Cleanup if needed
    services.clear()

app = FastAPI(title="Document Intelligence API", lifespan=lifespan)

@app.post("/extract", response_model=ExtractionResponse)
async def extract_data(
    bureau_file: UploadFile = File(...),
    gst_file: UploadFile = File(...),
    parameter_file: UploadFile = File(...)
):
    """
    Main extraction endpoint.
    Uploads: CRIF PDF, GSTR PDF, and Parameter Excel/CSV.
    """
    try:
        params = _parse_parameters(await parameter_file.read(), parameter_file.filename)
        parser = services["parser"]
        
        logger.info(f"Parsing CRIF: {bureau_file.filename}")
        crif_doc = parser.parse_pdf(await bureau_file.read(), source_name=bureau_file.filename)
        
        logger.info(f"Parsing GSTR: {gst_file.filename}")
        gst_doc = parser.parse_pdf(await gst_file.read(), source_name=gst_file.filename)

        logger.info("Running CRIF Extraction...")
        bureau_data = services["crif_extractor"].extract(crif_doc, params)
        
        logger.info("Running GSTR Extraction...")
        gst_data = services["gstr_extractor"].extract(gst_doc)
        all_confs = [item['confidence'] for item in bureau_data.values()]
        all_confs.extend([item['confidence'] for item in gst_data])
        
        avg_confidence = sum(all_confs) / len(all_confs) if all_confs else 0.0

        return ExtractionResponse(
            bureau_parameters=bureau_data,
            gst_sales=gst_data,
            overall_confidence_score=round(avg_confidence, 2)
        )

    except Exception as e:
        logger.error(f"Extraction failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-rule", response_model=ExtractionResponse)
async def generate_rule(
    bureau_file: UploadFile = File(...),
    gst_file: UploadFile = File(...),
    parameter_file: UploadFile = File(...)
):
    """Alias endpoint for /extract (same functionality)."""
    return await extract_data(bureau_file, gst_file, parameter_file)

def _parse_parameters(file_bytes: bytes, filename: str) -> List[dict]:
    """
    Helper to parse the Excel/CSV parameter file.
    Expects columns: Parameter ID, Parameter Name, Description
    """
    try:
        stream = io.BytesIO(file_bytes)
        if filename.endswith('.csv'):
            df = pd.read_csv(stream)
        else:
            df = pd.read_excel(stream)
        
        df.columns = [c.lower().strip() for c in df.columns]
        
        required = ['parameter id', 'parameter name', 'description']
        for req in required:
            if req not in df.columns:
                pass 
        
        parameters = []
        for _, row in df.iterrows():
            parameters.append({
                "id": row.get("parameter id", ""),
                "name": row.get("parameter name", ""),
                "description": row.get("description", "")
            })
        return parameters
    except Exception as e:
        raise ValueError(f"Invalid parameter file: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

