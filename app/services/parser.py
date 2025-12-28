import logging
import io
import pandas as pd
try:
    import torch
except ImportError:
    torch = None

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat, DocumentStream
from docling.datamodel.document import ConversionResult
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
from app.services.cache import DoclingCache

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DoclingParser:
    def __init__(self, use_cache: bool = True, cache_dir: str = "docling_cache"):
        """
        Initialize the Docling converter with GPU acceleration if available.
        
        Args:
            use_cache: Enable disk-based caching for parsed results
            cache_dir: Directory to store cache files
        """
        self.use_cache = use_cache
        self.cache = DoclingCache(cache_dir) if use_cache else None
        # Configure acceleration
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options.do_cell_matching = True
        device = AcceleratorDevice.CPU
        if torch:
            if torch.cuda.is_available():
                device = AcceleratorDevice.CUDA
                logger.info(f"CUDA detected. Using GPU for Docling (Device: {torch.cuda.get_device_name(0)}).")
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                device = AcceleratorDevice.MPS
                logger.info("MPS detected. Using Metal for Docling (Mac).")
            else:
                logger.info("No GPU detected. Using CPU for Docling.")
        else:
            logger.info("PyTorch not available. Using CPU for Docling.")

        # Enable Acceleration
        pipeline_options.accelerator_options = AcceleratorOptions(
            num_threads=8, device=device
        )

        self.converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )

    def parse_pdf(self, pdf_bytes: bytes, source_name: str = "document.pdf") -> dict:
        """
        Parses a PDF from bytes and returns a structured dictionary containing:
        - text: The full markdown text.
        - tables: A list of pandas DataFrames (converted to dicts).
        - chunks: Logical sections of the document (headers + content).
        
        Uses disk cache to avoid re-parsing identical files.
        """
        # Check cache first
        if self.use_cache and self.cache:
            cached_result = self.cache.get(pdf_bytes, source_name)
            if cached_result:
                # Reconstruct DataFrames from cached content
                return self._reconstruct_dataframes(cached_result)
        
        # Cache miss - parse with Docling
        try:
            logger.info(f"Starting Docling parse for {source_name}...")
            
            # Docling expects a DocumentStream wrapper for bytes
            input_stream = DocumentStream(name=source_name, stream=io.BytesIO(pdf_bytes))
            
            result: ConversionResult = self.converter.convert(input_stream)
            doc = result.document


            full_markdown = doc.export_to_markdown()


            tables_data = []
            for i, table in enumerate(doc.tables):
                df: pd.DataFrame = table.export_to_dataframe()
                
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [' '.join(col).strip() for col in df.columns.values]
                
                df = df.fillna("")
                df = df.astype(str)

                tables_data.append({
                    "id": i,
                    "page": table.prov[0].page_no if table.prov else -1,
                    "content": df.to_dict(orient="records"),
                    "columns": list(df.columns),
                    "dataframe": df
                })
            chunks = []
            current_chunk = {"header": "Start", "text": "", "page": 1}
            
            for line in full_markdown.split('\n'):
                if line.startswith('#'):
                    if current_chunk["text"].strip():
                        chunks.append(current_chunk)
                    
                    current_chunk = {
                        "header": line.strip('# '),
                        "text": line + "\n",
                        "page": -1
                    }
                else:
                    current_chunk["text"] += line + "\n"
            
            if current_chunk["text"].strip():
                chunks.append(current_chunk)

            logger.info(f"Parsed {len(tables_data)} tables and {len(chunks)} text chunks.")

            parsed_data = {
                "text": full_markdown,
                "tables": tables_data,
                "chunks": chunks
            }
            
            # Store in cache
            if self.use_cache and self.cache:
                self.cache.set(pdf_bytes, parsed_data, source_name)
            
            return parsed_data

        except Exception as e:
            logger.error(f"Error parsing PDF: {str(e)}")
            raise e
    
    def _reconstruct_dataframes(self, cached_data: dict) -> dict:
        """Reconstruct DataFrames from cached table content."""
        tables = []
        for table in cached_data.get("tables", []):
            df = pd.DataFrame(table["content"])
            if table["columns"]:
                df = df.reindex(columns=table["columns"], fill_value="")
            
            tables.append({
                "id": table.get("id"),
                "page": table.get("page", -1),
                "content": table["content"],
                "columns": table["columns"],
                "dataframe": df
            })
        
        return {
            "text": cached_data.get("text", ""),
            "tables": tables,
            "chunks": cached_data.get("chunks", [])
        }

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        print(f"Testing with file: {file_path}")
        with open(file_path, "rb") as f:
            parser = DoclingParser()
            result = parser.parse_pdf(f.read(), source_name=file_path)
            
            print("\n--- Extracted Tables ---")
            for t in result['tables']:
                print(f"Table {t['id']} (Page {t['page']}): Columns: {t['columns']}")
                print(t['dataframe'].head(2))
            
            print("\n--- First 2 Chunks ---")
            for c in result['chunks'][:2]:
                print(f"Header: {c['header']}")
                print(f"Text Preview: {c['text'][:100]}...")

