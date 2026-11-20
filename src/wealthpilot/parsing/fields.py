"""The financial-statement vocabulary: canonical field names and the labels they appear under in real documents."""

IS_FIELDS = ["revenue", "cogs", "operating_expenses", "depreciation", "interest_expense", "income_tax", "net_income"]
BS_FIELDS = ["cash", "accounts_receivable", "inventory", "total_current_assets", "net_fixed_assets", "total_assets",
             "accounts_payable", "current_portion_ltd", "total_current_liabilities", "long_term_debt",
             "total_liabilities", "total_equity"]
ALL_FIELDS = IS_FIELDS + BS_FIELDS

LABELS = {  # canonical: (clean label, noisy synonyms)
    "revenue": ("Revenue", ["Net Sales", "Total Revenues", "Sales"]),
    "cogs": ("Cost of Goods Sold", ["Cost of Sales", "Direct Costs"]),
    "operating_expenses": ("Operating Expenses", ["SG&A and Other Operating Costs", "Overheads"]),
    "depreciation": ("Depreciation", ["Depreciation & Amortization", "D&A"]),
    "interest_expense": ("Interest Expense", ["Finance Costs", "Interest Paid"]),
    "income_tax": ("Income Tax", ["Provision for Taxes", "Taxes"]),
    "net_income": ("Net Income", ["Net Profit", "Profit After Tax"]),
    "cash": ("Cash", ["Cash and Cash Equivalents", "Cash at Bank"]),
    "accounts_receivable": ("Accounts Receivable", ["Trade Receivables", "Debtors"]),
    "inventory": ("Inventory", ["Stock", "Inventories"]),
    "total_current_assets": ("Total Current Assets", ["Current Assets, Total"]),
    "net_fixed_assets": ("Net Fixed Assets", ["Property, Plant & Equipment (net)", "Fixed Assets, Net"]),
    "total_assets": ("Total Assets", ["Assets, Total"]),
    "accounts_payable": ("Accounts Payable", ["Trade Payables", "Creditors"]),
    "current_portion_ltd": ("Current Portion of Long-Term Debt", ["Current Maturities of Debt", "LTD Due Within One Year"]),
    "total_current_liabilities": ("Total Current Liabilities", ["Current Liabilities, Total"]),
    "long_term_debt": ("Long-Term Debt", ["Non-current Borrowings", "Term Loans (non-current)"]),
    "total_liabilities": ("Total Liabilities", ["Liabilities, Total"]),
    "total_equity": ("Total Equity", ["Shareholders' Equity", "Owner's Equity", "Net Worth"]),
}
