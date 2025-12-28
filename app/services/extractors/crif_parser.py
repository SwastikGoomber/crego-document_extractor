from typing import Dict, Any, List, Optional
import pandas as pd
import re
from app.models.crif_models import Account, PaymentHistory, CRIFReport


def parse_crif_report(parsed_doc: Dict[str, Any]) -> CRIFReport:
    tables = parsed_doc.get('tables', [])
    chunks = parsed_doc.get('chunks', [])

    summary_data = extract_account_summary(tables)
    bureau_score = extract_bureau_score(tables)
    credit_inquiries = extract_credit_inquiries(tables)
    accounts = parse_accounts_from_chunks(chunks)

    return CRIFReport(
        accounts=accounts,
        bureau_score=bureau_score,
        total_current_balance=summary_data.get('total_current_balance', 0.0),
        total_overdue_amount=summary_data.get('total_overdue_amount', 0.0),
        active_accounts_count=summary_data.get('active_accounts', 0),
        total_accounts_count=summary_data.get('total_accounts', 0),
        total_writeoff_amount=summary_data.get('total_writeoff_amount', 0.0),
        credit_inquiries_count=credit_inquiries
    )


def extract_account_summary_from_df(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Extract account summary from a single DataFrame."""
    if df is None or df.empty:
        return None

    columns_lower = [str(col).lower() for col in df.columns]

    if 'number of accounts' in columns_lower or 'active accounts' in columns_lower:
        row = df.iloc[0] if len(df) > 0 else {}

        return {
            'total_accounts': int(clean_number(row.get('Number of Accounts', 0))),
            'active_accounts': int(clean_number(row.get('Active Accounts', 0))),
            'total_current_balance': clean_number(row.get('Total Current Balance', 0)),
            'total_overdue_amount': clean_number(row.get('Total Amount Overdue', 0)),
            'total_writeoff_amount': clean_number(row.get('Total Writeoff Amt', 0))
        }

    return None


def extract_account_summary(tables: List[Dict]) -> Dict[str, Any]:
    """Extract account summary from all tables (fallback method)."""
    for table in tables:
        df = table.get('dataframe')
        result = extract_account_summary_from_df(df)
        if result:
            return result

    return {
        'total_accounts': 0,
        'active_accounts': 0,
        'total_current_balance': 0.0,
        'total_overdue_amount': 0.0,
        'total_writeoff_amount': 0.0
    }


def extract_bureau_score_from_df(df: pd.DataFrame) -> Optional[int]:
    """Extract bureau score from a single DataFrame."""
    if df is None or df.empty:
        return None

    columns_lower = [str(col).lower() for col in df.columns]

    if 'requested service' in columns_lower and 'score' in columns_lower:
        for _, row in df.iterrows():
            service = str(row.get('Requested Service', '')).upper()
            if 'CB SCORE' in service or 'SCORE' in service:
                score_val = row.get('Score', None)
                if score_val:
                    try:
                        score = int(clean_number(score_val))
                        if 300 <= score <= 900:
                            return score
                    except (ValueError, TypeError):
                        pass

    return None


def extract_bureau_score(tables: List[Dict]) -> Optional[int]:
    """Extract bureau score from all tables (fallback method)."""
    for table in tables:
        df = table.get('dataframe')
        result = extract_bureau_score_from_df(df)
        if result is not None:
            return result

    return None


def extract_credit_inquiries_from_df(df: pd.DataFrame) -> Optional[int]:
    """Extract credit inquiries count from a single DataFrame."""
    if df is None or df.empty:
        return None

    columns_lower = [str(col).lower() for col in df.columns]

    if 'enquiry purpose' in columns_lower or 'inquiry' in ' '.join(columns_lower):
        return len(df)

    if 'number of enquiries' in columns_lower:
        for _, row in df.iterrows():
            val = row.get('Number of Enquiries', row.get('Number of enquiries', 0))
            if val:
                return int(clean_number(val))

    return None


def extract_credit_inquiries(tables: List[Dict]) -> int:
    """Extract credit inquiries from all tables (fallback method)."""
    for table in tables:
        df = table.get('dataframe')
        result = extract_credit_inquiries_from_df(df)
        if result is not None:
            return result

    return 0


def parse_accounts_from_chunks(chunks: List[Dict]) -> List[Account]:
    accounts = []

    for chunk in chunks:
        header = chunk.get('header', '')
        if not header.startswith('Account Information'):
            continue

        text = chunk.get('text', '')
        account = parse_account_from_text(text)
        if account:
            accounts.append(account)

    return accounts


def parse_account_from_text(text: str) -> Optional[Account]:
    lines = text.split('\n')

    account_type = extract_field(lines, 'Account Type')
    ownership = extract_field(lines, 'Ownership')
    current_balance = extract_numeric_field(lines, 'Current Balance')
    overdue_amount = extract_numeric_field(lines, 'Overdue Amt')
    sanctioned_amount = extract_numeric_field(lines, 'Disbd Amt')
    remarks = extract_field(lines, 'Account Remarks')

    is_active = 'active' in text.lower() or 'Active' in text
    is_secured = 'secured' in account_type.lower() if account_type else False

    payment_history = extract_payment_history(text)

    if not account_type:
        return None

    return Account(
        account_number='',
        account_type=account_type,
        is_active=is_active,
        is_secured=is_secured,
        current_balance=current_balance,
        overdue_amount=overdue_amount,
        sanctioned_amount=sanctioned_amount,
        payment_history=payment_history,
        remarks=remarks or ''
    )


def extract_field(lines: List[str], field_name: str) -> str:
    for line in lines:
        if field_name in line:
            parts = line.split(':', 1)
            if len(parts) > 1:
                return parts[1].strip()
    return ''


def extract_numeric_field(lines: List[str], field_name: str) -> float:
    value_str = extract_field(lines, field_name)
    if value_str:
        return clean_number(value_str)
    return 0.0


def extract_payment_history(text: str) -> List[PaymentHistory]:
    history = []
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    for month in months:
        pattern = rf'{month}\s*[:\-]?\s*([A-Z0-9\-/]+)'
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            status = match.group(1).strip()
            history.append(PaymentHistory(month=month, status=status))

    return history


def clean_number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)

    value_str = str(value).replace(',', '').replace('₹', '').replace('Rs', '').strip()

    try:
        return float(value_str)
    except (ValueError, TypeError):
        return 0.0


