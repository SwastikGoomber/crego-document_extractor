from enum import Enum
from typing import Any, Callable, Optional, List
from dataclasses import dataclass


class ExtractionStatus(str, Enum):
    """Status of parameter extraction"""
    EXTRACTED = "extracted"                   # Successfully extracted from document
    NOT_FOUND = "not_found"                   # Searched but couldn't find in document
    NOT_APPLICABLE = "not_applicable"         # Policy parameter (not in document)
    EXTRACTION_FAILED = "extraction_failed"   # Found but failed to parse


class ParameterCategory(Enum):
    DIRECT = "direct"
    FLAG = "flag"
    DERIVED = "derived"
    POLICY = "policy"


@dataclass
class ParameterSpec:
    id: str
    name: str
    description: str
    expected_type: type
    category: ParameterCategory
    allowed_sources: List[str]
    validator: Optional[Callable[[Any], bool]] = None

    def validate(self, value: Any) -> bool:
        if value is None:
            return self.category == ParameterCategory.POLICY
        
        if not isinstance(value, self.expected_type):
            return False
        
        if self.validator and not self.validator(value):
            return False
        
        return True


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
    "bureau_ntc_accepted": ParameterSpec(
        id="bureau_ntc_accepted",
        name="NTC Accepted",
        description="Whether No-Track-Case (NTC) applicants are acceptable",
        expected_type=bool,
        category=ParameterCategory.FLAG,
        allowed_sources=["Verification", "Account Remarks"],
        validator=None
    ),
    "bureau_overdue_threshold": ParameterSpec(
        id="bureau_overdue_threshold",
        name="Overdue Threshold",
        description="Maximum allowable overdue amount",
        expected_type=type(None),
        category=ParameterCategory.POLICY,
        allowed_sources=[],
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
    "bureau_dpd_60": ParameterSpec(
        id="bureau_dpd_60",
        name="60+ DPD",
        description="Count of accounts with 60+ days past due",
        expected_type=int,
        category=ParameterCategory.DERIVED,
        allowed_sources=["Payment History"],
        validator=lambda v: v >= 0
    ),
    "bureau_dpd_90": ParameterSpec(
        id="bureau_dpd_90",
        name="90+ DPD",
        description="Count of accounts with 90+ days past due",
        expected_type=int,
        category=ParameterCategory.DERIVED,
        allowed_sources=["Payment History"],
        validator=lambda v: v >= 0
    ),
    "bureau_settlement_writeoff": ParameterSpec(
        id="bureau_settlement_writeoff",
        name="Settlement / Write-off",
        description="Presence of settlement or write-off",
        expected_type=bool,
        category=ParameterCategory.FLAG,
        allowed_sources=["Account Remarks"],
        validator=None
    ),
    "bureau_no_live_pl_bl": ParameterSpec(
        id="bureau_no_live_pl_bl",
        name="No Live PL/BL",
        description="Check for no live Personal Loan or Business Loan",
        expected_type=bool,
        category=ParameterCategory.DERIVED,
        allowed_sources=["Account Information"],
        validator=None
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
    "bureau_wilful_default": ParameterSpec(
        id="bureau_wilful_default",
        name="Wilful Default",
        description="Indicates wilful default status",
        expected_type=bool,
        category=ParameterCategory.FLAG,
        allowed_sources=["Account Remarks"],
        validator=None
    ),
    "bureau_written_off_debt_amount": ParameterSpec(
        id="bureau_written_off_debt_amount",
        name="Written-off Debt Amount",
        description="Total written-off debt exposure",
        expected_type=float,
        category=ParameterCategory.DIRECT,
        allowed_sources=["Account Summary"],
        validator=lambda v: v >= 0
    ),
    "bureau_max_loans": ParameterSpec(
        id="bureau_max_loans",
        name="Max Loans",
        description="Maximum number of loans in selected months",
        expected_type=int,
        category=ParameterCategory.DIRECT,
        allowed_sources=["Account Summary"],
        validator=lambda v: v >= 0
    ),
    "bureau_loan_amount_threshold": ParameterSpec(
        id="bureau_loan_amount_threshold",
        name="Loan Amount Threshold",
        description="Maximum cumulative loan amount exposure",
        expected_type=type(None),
        category=ParameterCategory.POLICY,
        allowed_sources=[],
        validator=None
    ),
    "bureau_credit_inquiries": ParameterSpec(
        id="bureau_credit_inquiries",
        name="Credit Inquiries",
        description="Number of bureau credit inquiries",
        expected_type=int,
        category=ParameterCategory.DIRECT,
        allowed_sources=["Additional Summary", "Inquiry"],
        validator=lambda v: v >= 0
    ),
    "bureau_max_active_loans": ParameterSpec(
        id="bureau_max_active_loans",
        name="Max Active Loans",
        description="Maximum active loans",
        expected_type=int,
        category=ParameterCategory.DIRECT,
        allowed_sources=["Account Summary"],
        validator=lambda v: v >= 0
    ),
}


