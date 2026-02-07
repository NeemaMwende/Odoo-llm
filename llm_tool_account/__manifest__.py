{
    "name": "LLM Tool Account",
    "version": "18.0.1.0.0",
    "category": "Productivity/LLM",
    "summary": "LLM tools for accounting: data entry, balances, reconciliation, and reporting",
    "description": """
LLM Tool Account
=================

This module provides LLM tools for interacting with Odoo accounting through
AI assistants and MCP servers.

Features
--------

**Data Entry:**
- Create journal entries, invoices, and bills
- Post and unpost moves
- Reverse entries with reason tracking

**Lookups:**
- Find moves by reference, partner, type, date range
- Find accounts by code pattern, name, or type
- Find journals by code, name, or type

**Payments:**
- Register payments against invoices/bills
- Support for partial and group payments

**Balances & Reports:**
- Trial balance with flexible grouping
- Tax balance summaries
- General ledger with running balances
- Profit & Loss with period comparison
- Cash position snapshot

**Reconciliation:**
- List unreconciled items by type
- Reconcile journal items with optional write-off
- Suggest matching entries

**Period Close:**
- Pre-close checklist (draft moves, unreconciled items)
- Set lock dates (fiscal year, tax, period)

All tools follow proper consent requirements for data modification operations.
    """,
    "author": "Apexive",
    "website": "https://github.com/apexive/odoo-llm",
    "license": "LGPL-3",
    "depends": [
        "llm_tool",
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
    ],
    "demo": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
