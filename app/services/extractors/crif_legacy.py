"""
Legacy CRIF Extractor - Direct Table Parsing Approach
This file contains the original direct parsing logic as a backup.
Use this if embedding-guided extraction fails or for comparison.
"""

import logging
from typing import Dict, Any, List
from app.services.extractors.base import BaseExtractor
from app.services.embeddings import EmbeddingService
from app.services.llm import LLMService
from app.models.parameter_specs import PARAMETER_SPECS, ParameterCategory
from app.services.extractors.crif_parser import parse_crif_report

logger = logging.getLogger(__name__)

class CRIFExtractorLegacy(BaseExtractor):
    def __init__(self, embedding_service: EmbeddingService, llm_service: LLMService):
        self.embedding_service = embedding_service
        self.llm_service = llm_service

    def extract(self, parsed_doc: Dict[str, Any], parameters: List[Dict]) -> Dict[str, Any]:
        extracted_results = {}

        crif_report = parse_crif_report(parsed_doc)

        for param in parameters:
            param_id = param['id']
            param_name = param['name']

            logger.info(f"[LEGACY] Extracting parameter: {param_name} ({param_id})")

            spec = PARAMETER_SPECS.get(param_id)
            if not spec:
                logger.warning(f"No spec found for {param_id}, skipping")
                extracted_results[param_id] = {
                    "value": None,
                    "source": "Parameter spec not found",
                    "confidence": 0.0
                }
                continue

            if spec.category == ParameterCategory.DIRECT:
                result = self._extract_direct(spec, crif_report, parsed_doc)
            elif spec.category == ParameterCategory.FLAG:
                result = self._extract_flag(spec, crif_report)
            elif spec.category == ParameterCategory.DERIVED:
                result = self._extract_derived(spec, crif_report)
            elif spec.category == ParameterCategory.POLICY:
                result = self._extract_policy(spec)
            else:
                result = {"value": None, "source": "Unknown category", "confidence": 0.0}

            extracted_results[param_id] = result

        return extracted_results

    def _extract_direct(self, spec, crif_report, parsed_doc) -> Dict:
        if spec.id == "bureau_credit_score":
            value = crif_report.bureau_score
            source = "Verification Table"
        elif spec.id == "bureau_written_off_debt_amount":
            value = crif_report.total_writeoff_amount
            source = "Account Summary Table"
        elif spec.id == "bureau_max_loans":
            value = int(crif_report.total_accounts_count)
            source = "Account Summary Table"
        elif spec.id == "bureau_max_active_loans":
            value = int(crif_report.active_accounts_count)
            source = "Account Summary Table"
        elif spec.id == "bureau_credit_inquiries":
            value = crif_report.credit_inquiries_count
            source = "Inquiry Table"
        else:
            value = None
            source = "Unknown direct parameter"

        confidence = self._calculate_confidence(spec, value, "direct_table")

        return {
            "value": value,
            "source": source,
            "confidence": confidence
        }

    def _extract_flag(self, spec, crif_report) -> Dict:
        if spec.id == "bureau_suit_filed":
            checker = lambda acc: acc.has_suit_filed()
            has_flag, matched = crif_report.has_flag_in_any_account(checker)
        elif spec.id == "bureau_wilful_default":
            checker = lambda acc: acc.has_wilful_default()
            has_flag, matched = crif_report.has_flag_in_any_account(checker)
        elif spec.id == "bureau_settlement_writeoff":
            checker = lambda acc: acc.has_settlement_writeoff()
            has_flag, matched = crif_report.has_flag_in_any_account(checker)
        elif spec.id == "bureau_ntc_accepted":
            has_flag, matched = False, 0
        else:
            has_flag, matched = False, 0

        value = has_flag
        total_accounts = len(crif_report.accounts)

        confidence = self._calculate_confidence(spec, value, "flag_detection")

        return {
            "value": value,
            "source": f"Account Remarks ({matched}/{total_accounts} accounts)",
            "confidence": confidence
        }

    def _extract_derived(self, spec, crif_report) -> Dict:
        if spec.id == "bureau_dpd_30":
            value = crif_report.count_dpd_accounts(30)
        elif spec.id == "bureau_dpd_60":
            value = crif_report.count_dpd_accounts(60)
        elif spec.id == "bureau_dpd_90":
            value = crif_report.count_dpd_accounts(90)
        elif spec.id == "bureau_no_live_pl_bl":
            value = not crif_report.has_live_pl_bl()
        else:
            value = None

        total_accounts = len(crif_report.accounts)

        confidence = self._calculate_confidence(spec, value, "computed")

        return {
            "value": value,
            "source": f"Computed from {total_accounts} accounts",
            "confidence": confidence
        }

    def _extract_policy(self, spec) -> Dict:
        return {
            "value": None,
            "source": "Not applicable (policy parameter)",
            "confidence": 0.0
        }

    def _calculate_confidence(self, spec, value, method) -> float:
        method_confidence = {
            "direct_table": 0.95,
            "computed": 1.0,
            "flag_detection": 0.85,
            "rag_assisted": 0.70
        }.get(method, 0.5)

        if not spec.validate(value):
            return 0.0

        if value is None:
            type_certainty = 0.0
        elif isinstance(value, spec.expected_type):
            type_certainty = 1.0
        else:
            type_certainty = 0.5

        return method_confidence * type_certainty

