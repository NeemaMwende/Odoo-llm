{
    "name": "LLM Tool MIS Builder",
    "version": "18.0.1.0.0",
    "category": "Productivity/LLM",
    "summary": "MCP tools for MIS Builder report management and exploration",
    "description": """
LLM Tool MIS Builder
====================

This module provides MCP tools for managing and exploring MIS Builder reports
through LLM interactions.

Features
--------

**Template Management:**
- List, create, update, delete, and duplicate MIS report templates
- Manage KPIs (Key Performance Indicators) with expressions
- Configure custom data queries

**Instance Management:**
- Create and configure report instances with periods
- Support for fixed dates, relative periods, and comparisons
- Multi-company support

**Report Execution:**
- Compute reports and retrieve results
- Quick preview with ad-hoc parameters
- Drill-down into cell details
- Export to JSON format

**Analysis Tools:**
- Period comparisons (YoY, MoM, QoQ)
- KPI trend analysis
- Account-level breakdown
- Variance analysis

**Annotations:**
- List, create, update, and delete cell annotations

All tools follow proper consent requirements for data modification operations.
    """,
    "author": "Apexive",
    "website": "https://github.com/apexive/odoo-llm",
    "license": "LGPL-3",
    "depends": [
        "llm_tool",
        "mis_builder",
    ],
    "data": [
        "security/ir.model.access.csv",
    ],
    "demo": [],
    "images": ["static/description/banner.jpeg"],
    "installable": True,
    "application": False,
    "auto_install": False,
}
