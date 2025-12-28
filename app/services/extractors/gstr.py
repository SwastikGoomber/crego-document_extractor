import re
import logging
import pandas as pd
from typing import Dict, Any, List, Optional
from app.services.extractors.base import BaseExtractor
from app.models.parameter_specs import ExtractionStatus

logger = logging.getLogger(__name__)

class GSTR3BExtractor(BaseExtractor):
    def extract(self, parsed_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extracts sales data from GSTR-3B.
        Returns a list of dicts: [{"month": "April 2025", "sales": 12345, "source": "..."}]
        """
        text = parsed_doc["text"]
        tables = parsed_doc["tables"]

        month = self._extract_month(text)
        sales_data = self._extract_sales_from_table(tables)

        if not sales_data:
            return [{
                "month": month,
                "sales": None,
                "source": "GSTR-3B Table 3.1 not found",
                "confidence": 0.0,
                "status": ExtractionStatus.NOT_FOUND
            }]

        return [{
            "month": month,
            "sales": sales_data["value"],
            "source": sales_data["source"],
            "confidence": sales_data["confidence"],
            "status": ExtractionStatus.EXTRACTED
        }]

    def _extract_month(self, text: str) -> str:
        """
        Extracts the filing period (Month Year) from the text.
        Common formats: "Period: MM/YYYY", "Year: 2024-25 Month: April"
        """
        # Look for patterns near the top of the document
        lines = text.split('\n')[:20] # Only check header
        header_text = "\n".join(lines)

        # Pattern 1: explicit "Month: April" and "Year: 2025"
        month_match = re.search(r"(?:Month|Period)\s*[:\-]?\s*([A-Za-z]+)", header_text, re.IGNORECASE)
        year_match = re.search(r"(?:Year|Financial Year)\s*[:\-]?\s*(\d{4}(?:-\d{2,4})?)", header_text, re.IGNORECASE)

        if month_match and year_match:
            year_str = year_match.group(1)
            # Convert "2024-25" to "2024" (use the starting year)
            if '-' in year_str:
                year_str = year_str.split('-')[0]
            return f"{month_match.group(1)} {year_str}"
        
        # Pattern 2: "042025" or "04/2025" in filename or text headers
        # Fallback to simple scan
        date_match = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s*20\d{2}\b", header_text)
        if date_match:
            return date_match.group(0)

        return "Unknown Month"

    def _extract_sales_from_table(self, tables: List[Dict]) -> Optional[Dict]:
        """
        Locates Table 3.1 and extracts "Total Taxable Value".
        """
        target_table_ids = []
        
        # 1. Identify the table
        for table in tables:
            # Check headers or content for "3.1" and "Outward"
            df = table["dataframe"]
            # Convert full dataframe to string to search for keywords (normalize spaces)
            table_str = re.sub(r'\s+', ' ', df.to_string().lower())
            
            # Signature Check: Look for column patterns specific to Table 3.1
            cols = [str(c).lower() for c in df.columns]
            has_tax_cols = any("integrated" in c for c in cols) and any("central" in c for c in cols)
            has_taxable = any("taxable" in c for c in cols)
            
            # Strong Match: Has explicit Tax columns AND (Header mention or content mention)
            if has_tax_cols and has_taxable:
                target_table_ids.append(table)
            # Weak Match: Just keywords
            elif "3.1" in table_str and ("outward" in table_str or "supplies" in table_str):
                target_table_ids.append(table)
        
        if not target_table_ids:
            logger.warning("Table 3.1 not found in GSTR tables.")
            return None

        # 2. Extract Value from the best candidate
        best_table = target_table_ids[0] # Assume first match is correct
        df = best_table["dataframe"]
        
        # Logic: Look for row containing "taxable value" (usually row 1 or sum)
        # and column "Total Taxable Value" or column index 1/2.
        
        try:
            # GSTR Table 3.1 usually has columns: 
            # Description | Total Taxable Value | Integrated Tax | Central Tax | State Tax | Cess
            
            # Find the column index for "Taxable Value"
            taxable_col_idx = -1
            for i, col in enumerate(df.columns):
                if "taxable" in str(col).lower() and "value" in str(col).lower():
                    taxable_col_idx = i
                    break
            
            # If explicit column not found, assume it's the 2nd column (Index 1) as per standard GSTR format
            if taxable_col_idx == -1 and len(df.columns) > 1:
                taxable_col_idx = 1
            
            # Find the row for "(a) Outward taxable supplies"
            sales_value = 0.0
            found_row = False
            
            for index, row in df.iterrows():
                row_str = " ".join([str(x) for x in row.values]).lower()
                if "(a)" in row_str or "outward taxable supplies" in row_str:
                    # Extract the value from the identified column
                    raw_val = str(row.iloc[taxable_col_idx])
                    clean_val = self._clean_currency(raw_val)
                    sales_value = clean_val
                    found_row = True
                    break
            
            if found_row:
                return {
                    "value": sales_value,
                    "source": f"GSTR-3B Table 3.1 (Page {best_table['page']})",
                    "confidence": 1.0
                }
                
        except Exception as e:
            logger.error(f"Error extracting from GSTR table: {e}")
            
        return None

    def _clean_currency(self, val: str) -> float:
        """
        Removes symbols and returns float.
        """
        if not val:
            return 0.0
        # Remove chars that aren't digits or dots
        clean = re.sub(r"[^\d\.]", "", val)
        try:
            return float(clean)
        except:
            return 0.0

