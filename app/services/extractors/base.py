from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseExtractor(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def extract(self, parsed_doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Abstract method to extract data from a parsed document.
        parsed_doc is the output from DoclingParser.parse_pdf
        """
        pass

