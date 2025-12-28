from pydantic import BaseModel, ConfigDict
from typing import Dict, List, Any, Optional

class ParameterSource(BaseModel):
    model_config = ConfigDict(extra='allow')  # Allow extra fields like status, similarity_score
    
    value: Any
    source: str
    confidence: float
    status: Optional[str] = "extracted"  # extracted, not_found, not_applicable, extraction_failed
    similarity_score: Optional[float] = None  # For transparency/debugging

class GSTSale(BaseModel):
    model_config = ConfigDict(extra='allow')
    
    month: str
    sales: Optional[float]
    source: str
    confidence: float
    status: Optional[str] = "extracted"  # extracted, not_found, etc.

class ExtractionResponse(BaseModel):
    model_config = ConfigDict(extra='allow')
    
    bureau_parameters: Dict[str, ParameterSource]
    gst_sales: List[GSTSale]
    overall_confidence_score: float

