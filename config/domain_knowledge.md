# Domain Knowledge Base for Credit Bureau & GST Extraction

## Credit Bureau Terms

### Credit Score (CIBIL Score)
- **Definition**: A 3-digit number ranging from 300 to 900 that represents creditworthiness
- **Location**: Usually found in "Score Section" or "Verification Table" of CRIF reports
- **Good Score**: 750 and above
- **Poor Score**: Below 650
- **Synonyms**: Bureau Score, CIBIL Score, Credit Rating

### DPD (Days Past Due)
- **Definition**: Number of days a payment is overdue from the due date
- **Categories**:
  - 30+ DPD: Payments overdue by 30 or more days
  - 60+ DPD: Payments overdue by 60 or more days
  - 90+ DPD: Payments overdue by 90 or more days (serious delinquency)
- **Location**: Account-level payment history in CRIF reports
- **Calculation**: Count of accounts with DPD exceeding threshold in a given period

### Suit Filed
- **Definition**: Legal action initiated by a lender against the borrower for non-payment
- **Indicator**: Usually marked as "Suit Filed" or "Legal Action" in account remarks
- **Severity**: Very serious negative indicator
- **Impact**: Significantly reduces creditworthiness

### Wilful Default
- **Definition**: Intentional non-payment of debt despite having the ability to pay
- **Indicator**: Marked as "Wilful Default" or "WD" in account status
- **Severity**: Most serious negative indicator
- **Legal**: Can lead to criminal proceedings in some cases

### Settlement / Write-off
- **Settlement**: Partial payment accepted by lender as full settlement of debt
- **Write-off**: Lender has given up on recovering the debt
- **Indicators**: "Settled", "Written Off", "WO", "Settlement"
- **Impact**: Negative indicator, though better than default
- **Location**: Account status or remarks section

### NTC (No Track Case)
- **Definition**: Cases where the borrower cannot be tracked or located
- **Indicator**: Marked as "NTC" in account status
- **Reason**: Usually due to incorrect contact information or borrower absconding

### Account Types
- **Personal Loan (PL)**: Unsecured loan for personal use
- **Business Loan (BL)**: Loan for business purposes
- **Credit Card (CC)**: Revolving credit facility
- **Home Loan (HL)**: Secured loan for property purchase
- **Auto Loan (AL)**: Secured loan for vehicle purchase
- **Gold Loan (GL)**: Loan against gold collateral

### Account Status
- **Active**: Currently operational account with outstanding balance
- **Closed**: Account that has been closed (paid off or otherwise)
- **Live**: Active account with current transactions
- **Inactive**: Account with no recent activity

### Credit Inquiries
- **Definition**: Number of times credit report was accessed by lenders
- **Types**:
  - Hard Inquiry: For loan/credit applications (impacts score)
  - Soft Inquiry: For background checks (doesn't impact score)
- **Location**: "Inquiry Section" or "Enquiry Table" in CRIF reports
- **Impact**: Too many inquiries in short time = negative signal

### Exposure
- **Secured Exposure**: Loans backed by collateral (home, vehicle, gold)
- **Unsecured Exposure**: Loans without collateral (personal loans, credit cards)
- **Total Exposure**: Sum of all outstanding balances

### Amounts
- **Sanctioned Amount**: Total loan amount approved by lender
- **Current Balance**: Outstanding amount to be repaid
- **Overdue Amount**: Amount past the due date
- **Written-off Amount**: Amount that lender has written off as bad debt

## GST Terms

### GSTR-3B
- **Definition**: Monthly summary return for GST taxpayers
- **Filing**: Due by 20th of following month
- **Contents**: Summary of sales, purchases, and tax liability

### Table 3.1 - Outward Supplies
- **Definition**: Details of sales/supplies made by the taxpayer
- **Table 3.1(a)**: Outward taxable supplies (excluding zero-rated, nil-rated, exempted)
- **Columns**:
  - Total Taxable Value: Total sales amount (excluding tax)
  - Integrated Tax (IGST): Tax on inter-state supplies
  - Central Tax (CGST): Tax on intra-state supplies (central portion)
  - State Tax (SGST): Tax on intra-state supplies (state portion)
  - Cess: Additional tax on certain goods

### Filing Period
- **Format**: Month Year (e.g., "April 2024")
- **Financial Year**: April to March (e.g., "2024-25" means April 2024 to March 2025)
- **Representation**: Use starting year for financial year (2024-25 → 2024)

## Common Extraction Patterns

### Finding Credit Score
1. Look for "Score Section", "Verification Table", or "Summary"
2. Search for keywords: "Score", "CIBIL", "Credit Rating"
3. Value is typically 3 digits between 300-900

### Finding DPD Counts
1. Look for "Account Details" or "Payment History"
2. Check each account's payment history
3. Count accounts where DPD exceeds threshold (30/60/90)
4. May be in columns like "DPD", "Days Past Due", "Overdue Days"

### Finding Flags (Suit Filed, Wilful Default, etc.)
1. Look in "Account Status" or "Remarks" columns
2. Search for exact keywords or abbreviations
3. Check across all accounts (any account with flag = True)

### Finding Account Counts
1. Look for "Account Summary" table
2. Keywords: "Total Accounts", "Active Accounts", "Closed Accounts"
3. May need to count rows in account details table

### Finding GST Sales
1. Locate Table 3.1 in GSTR-3B
2. Find row "(a) Outward taxable supplies"
3. Extract value from "Total Taxable Value" column
4. Remove currency symbols and commas

## Validation Rules

### Credit Score
- Must be between 300 and 900
- If outside range, likely extraction error

### DPD Counts
- Must be non-negative integer
- Cannot exceed total number of accounts

### Amounts
- Must be non-negative
- Remove all currency symbols (₹, Rs., etc.)
- Remove commas and spaces
- Keep only digits and decimal point

### Dates
- Financial year format: YYYY-YY (e.g., 2024-25)
- Month format: Full month name + Year (e.g., April 2024)

### Boolean Flags
- True if any account shows the indicator
- False if no accounts show the indicator
- Check all accounts, not just active ones

