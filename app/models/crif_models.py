from dataclasses import dataclass
from typing import List, Optional
import re


@dataclass
class PaymentHistory:
    month: str
    status: str

    def get_dpd(self) -> int:
        status_lower = self.status.lower().strip()

        if status_lower in ['000', 'std', '000/std']:
            return 0
        elif status_lower == '030':
            return 30
        elif status_lower == '060':
            return 60
        elif status_lower in ['090', 'sub', '090/sub']:
            return 90
        elif status_lower in ['120', 'dbt', '120/dbt']:
            return 120
        elif status_lower in ['150', 'lss', '150/lss', '180']:
            return 180
        elif status_lower == '-':
            return 0
        else:
            match = re.match(r'(\d+)', status_lower)
            if match:
                return int(match.group(1))
            return 0


@dataclass
class Account:
    account_number: str
    account_type: str
    is_active: bool
    is_secured: bool
    current_balance: float
    overdue_amount: float
    sanctioned_amount: float
    payment_history: List[PaymentHistory]
    remarks: str

    def get_worst_dpd(self) -> int:
        if not self.payment_history:
            return 0
        return max(ph.get_dpd() for ph in self.payment_history)

    def has_suit_filed(self) -> bool:
        return "suit filed" in self.remarks.lower()

    def has_wilful_default(self) -> bool:
        return "wilful default" in self.remarks.lower()

    def has_settlement_writeoff(self) -> bool:
        remarks_lower = self.remarks.lower()
        return "settlement" in remarks_lower or "write" in remarks_lower


@dataclass
class CRIFReport:
    accounts: List[Account]
    bureau_score: Optional[int]
    total_current_balance: float
    total_overdue_amount: float
    active_accounts_count: int
    total_accounts_count: int
    total_writeoff_amount: float
    credit_inquiries_count: int

    def count_dpd_accounts(self, threshold: int) -> int:
        count = 0
        for account in self.accounts:
            if account.get_worst_dpd() >= threshold:
                count += 1
        return count

    def has_live_pl_bl(self) -> bool:
        for account in self.accounts:
            if not account.is_active:
                continue
            account_type_lower = account.account_type.lower()
            if "personal loan" in account_type_lower or "business loan" in account_type_lower:
                return True
        return False

    def count_active_loans_by_type(self, loan_types: List[str]) -> int:
        count = 0
        for account in self.accounts:
            if not account.is_active:
                continue
            account_type_lower = account.account_type.lower()
            for loan_type in loan_types:
                if loan_type.lower() in account_type_lower:
                    count += 1
                    break
        return count

    def has_flag_in_any_account(self, flag_checker) -> tuple[bool, int]:
        matched = 0
        for account in self.accounts:
            if flag_checker(account):
                matched += 1
        return matched > 0, matched

