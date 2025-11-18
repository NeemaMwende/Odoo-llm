# LLM Invoice Assistant Module - Design Document

## Overview

The `llm_invoice_assistant` module provides AI-powered invoice analysis capabilities by integrating Odoo's accounting system with the LLM infrastructure. It demonstrates how to build application-level modules on top of the LLM framework without requiring heavy dependencies like vector stores.

## Module Information

- **Name**: llm_invoice_assistant
- **Version**: 18.0.1.0.0
- **Category**: Accounting/AI
- **License**: LGPL-3

## Dependencies

```python
"depends": [
    "account",              # Invoice model (account.move)
    "llm_assistant",        # Includes llm, llm_thread, llm_tool
]
```

**Optional Enhancement Dependencies** (not required for basic functionality):
- `llm_knowledge_mistral` - If generic OCR tool is available there

## Module Structure (MINIMAL)

```
llm_invoice_assistant/
├── __manifest__.py
├── __init__.py                  # Empty - no Python code needed!
├── data/
│   ├── llm_prompt_invoice_analyzer.xml
│   └── llm_assistant_invoice.xml
├── views/
│   └── account_move_views.xml   # Optional: Add "Ask AI" button with server action
├── static/
│   └── description/
│       └── index.html
└── security/
    └── ir.model.access.csv      # Inherits from account module groups
```

**Note**: No Python models needed! Everything is configuration.

## Core Features

### 1. Invoice-Thread Linking

**Pattern**: Use llm_thread's existing record linking (model + res_id) via UI

**User Workflow** (no code needed):
1. User opens invoice form
2. User clicks "Ask AI" button (optional enhancement)
3. System opens llm.thread form in "create" mode
4. User manually links to invoice using the record picker (already exists in llm_thread)
5. User selects "Invoice Analysis Assistant" from dropdown
6. Context is automatically injected via related_record proxy

**Optional Button** (simple server action in XML):
```xml
<record id="action_invoice_open_assistant" model="ir.actions.server">
    <field name="name">Ask AI Assistant</field>
    <field name="model_id" ref="account.model_account_move"/>
    <field name="binding_model_id" ref="account.model_account_move"/>
    <field name="binding_view_types">form</field>
    <field name="state">code</field>
    <field name="code"><![CDATA[
action = {
    'type': 'ir.actions.act_window',
    'res_model': 'llm.thread',
    'view_mode': 'form',
    'context': {
        'default_model': 'account.move',
        'default_res_id': record.id,
        'default_name': f'Invoice {record.name or "Draft"}',
        'default_assistant_id': env.ref('llm_invoice_assistant.llm_assistant_invoice_analyzer').id,
    },
    'target': 'current',
}
    ]]></field>
</record>
```

That's it! No Python model code needed.

### 2. Invoice Context in Prompts

**Pattern**: Use RelatedRecordProxy for safe field access in Jinja2 templates

**Example Prompt Template**:
```xml
<record id="llm_prompt_invoice_analyzer" model="llm.prompt">
    <field name="name">Invoice Analysis Assistant</field>
    <field name="template"><![CDATA[
You are an Invoice Analysis Assistant specialized in reviewing vendor invoices.

# Invoice Context

**Invoice Number**: {{ related_record.get_field('name', 'Draft') }}
**Vendor**: {{ related_record.get_field('partner_id.name', 'Unknown') }}
**Invoice Date**: {{ related_record.get_field('invoice_date', 'Not set') }}
**Due Date**: {{ related_record.get_field('invoice_date_due', 'Not set') }}
**Amount Total**: {{ related_record.get_field('amount_total', '0.00') }}
**Status**: {{ related_record.get_field('state', 'draft') }}
**Line Items**: {{ related_record.get_field('invoice_line_ids', []) | length }}

# Your Capabilities

1. **Answer Questions**: Provide information about this invoice
2. **Validate Invoice**: Check for common errors using validate_invoice tool
3. **Extract from Document**: Use extract_invoice_ocr tool to parse uploaded PDFs/images
4. **Financial Analysis**: Analyze amounts, taxes, discounts

# Guidelines

- Be concise and professional
- Cite specific line items when relevant
- Flag potential issues (missing VAT, unusual amounts, etc.)
- Suggest corrections when appropriate
    ]]></field>
    <field name="format">text</field>
    <field name="category_id" ref="llm_assistant.llm_prompt_category_business"/>
</record>
```

### 3. Tools (Leverage Existing + One Generic OCR Tool)

#### Built-in Tools (Already Available)

The assistant will use existing generic tools from `llm_tool`:
- `odoo_record_retriever` - Query invoice data
- `odoo_model_inspector` - Inspect account.move structure
- `odoo_record_updater` - Update invoice fields (with consent)

**No custom tools needed in this module!**

#### Generic OCR Tool (In llm_knowledge_mistral)

**Purpose**: Extract text from ANY attachment (not invoice-specific)

**Implementation**: Delegated to `mistral_tool_dev` agent to add to `llm_knowledge_mistral`

**Expected Tool** (generic, reusable):
```python
# In llm_knowledge_mistral/models/ir_attachment.py
from odoo.addons.llm_tool.decorators import llm_tool

class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    @llm_tool(
        name="parse_document_ocr",
        description="Extract text and structured data from PDF or image attachment using Mistral OCR vision models"
    )
    def llm_parse_document_ocr(self, attachment_id):
        """
        Generic OCR parser for any attachment.

        Args:
            attachment_id (int): ID of the attachment to parse

        Returns:
            dict: {
                "extracted_text": str,  # Full text content
                "pages": int,           # Number of pages
                "mimetype": str,        # Original file type
            }
        """
        # Uses existing llm_knowledge_mistral OCR infrastructure
        pass
```

**Usage in Invoice Context**:
```
User: "Parse the uploaded invoice PDF attachment 123"
Assistant: [calls parse_document_ocr(attachment_id=123)]
Assistant: "I found an invoice from Acme Corp for $5,420.00..."
```

The assistant's prompt tells it how to interpret OCR results for invoices.

### 4. Assistant Configuration

**Pre-built Assistant** (simple XML data file):
```xml
<record id="llm_assistant_invoice_analyzer" model="llm.assistant">
    <field name="name">Invoice Analysis Assistant</field>
    <field name="code">invoice_analyzer</field>
    <field name="res_model">account.move</field>
    <field name="is_default" eval="True"/>
    <field name="is_public" eval="True"/>

    <!-- Link to prompt (context injection happens here) -->
    <field name="prompt_id" ref="llm_prompt_invoice_analyzer"/>

    <!-- Use existing generic tools -->
    <field name="tool_ids" eval="[(6, 0, [
        ref('llm_tool.llm_tool_odoo_record_retriever'),
        ref('llm_tool.llm_tool_odoo_model_inspector'),
        ref('llm_tool.llm_tool_odoo_record_updater'),
    ])]"/>

    <field name="tool_calls_max">5</field>
</record>
```

**Note**:
- No provider/model specified → User chooses at runtime
- Tools are all generic → No invoice-specific code
- OCR tool reference will be added once available in llm_knowledge_mistral

### 5. UI Integration (Optional)

**Add Button to Invoice Form** (optional convenience feature):
```xml
<!-- Button in buttonbox -->
<record id="view_account_move_form_llm" model="ir.ui.view">
    <field name="name">account.move.form.llm</field>
    <field name="model">account.move</field>
    <field name="inherit_id" ref="account.view_move_form"/>
    <field name="arch" type="xml">
        <div name="button_box" position="inside">
            <button name="%(action_invoice_open_assistant)d"
                    type="action"
                    class="oe_stat_button"
                    icon="fa-comments"
                    string="Ask AI"
                    groups="account.group_account_user"/>
        </div>
    </field>
</record>
```

**Without button**: Users can manually create thread and link to invoice via record picker.

## Data Flow

### Typical User Interaction

1. **User opens invoice** → Clicks "Ask AI" button (or creates thread manually)
2. **System creates thread** → Links to invoice (model="account.move", res_id=invoice.id)
3. **System loads assistant** → Invoice Analysis Assistant with prompt
4. **System injects context** → Prompt template rendered with invoice fields via `related_record.get_field()`
5. **User asks question** → "What is the total amount?"
6. **Assistant responds** → Uses context: "The total is $5,420.00"

### Using Generic Tools

**Example: Query invoice lines**
```
User: "Show me all line items"
Assistant: [calls odoo_record_retriever with model="account.move.line", domain=[('move_id', '=', invoice_id)]]
Assistant: "Here are the 3 line items: ..."
```

**Example: OCR extraction** (once tool available)
```
User: "Parse attachment 123"
Assistant: [calls parse_document_ocr(attachment_id=123)]
Assistant: "I extracted: Vendor: Acme Corp, Amount: $5,420.00..."
User: "Update the invoice with that data"
Assistant: [calls odoo_record_updater to fill fields]
```

## Security & Access Control

**Inherits from existing modules** - No custom access rights needed!

- Thread creation: Controlled by `llm_thread` module
- Tool usage: Controlled by `llm_tool` consent system
- Invoice access: Controlled by `account` module groups

## Testing Strategy

### Manual Testing Checklist

1. **Install module**: `odoo-bin -d mydb -u llm_invoice_assistant`
2. **Create test invoice**: Accounting → Vendors → Bills → Create
3. **Open assistant**: Click "Ask AI" button (if view installed) or create thread manually
4. **Link to invoice**: Select invoice from record picker if created manually
5. **Select assistant**: Choose "Invoice Analysis Assistant" from dropdown
6. **Test context**: Ask "What is the vendor name?" → Should respond from context
7. **Test tools**: Ask "Find other invoices from this vendor" → Should use odoo_record_retriever

## Installation & Configuration

### Installation Steps

1. Install module: `odoo-bin -d mydb -u llm_invoice_assistant`
2. Ensure Mistral provider is configured with API key
3. Verify OCR models are available (check llm.model list)

### Configuration

1. **Provider Setup**: Settings → LLM → Providers → Mistral AI
   - Enter API key
   - Click "Sync Models"
   - Verify OCR models appear (e.g., "pixtral-12b-2409")

2. **Assistant Configuration**: Settings → LLM → Assistants
   - Find "Invoice Analysis Assistant"
   - Optionally customize prompt or tools
   - Set default model if needed

## Extensibility Points

### Adding More Assistants

```xml
<record id="llm_assistant_invoice_approver" model="llm.assistant">
    <field name="name">Invoice Approval Assistant</field>
    <field name="code">invoice_approver</field>
    <field name="res_model">account.move</field>
    <field name="prompt_id" ref="llm_prompt_invoice_approver"/>
    <!-- Different tools for approval workflow -->
</record>
```

### Adding Custom Tools

```python
@llm_tool(
    name="match_purchase_order",
    description="Find matching purchase order for invoice line items"
)
def llm_match_purchase_order(self):
    # Custom logic to match PO
    pass
```

### Multi-language Support

Use prompt variables and translations:
```xml
<field name="template"><![CDATA[
{{ _("You are an Invoice Analysis Assistant") }}
...
]]></field>
```

## Known Limitations

1. **No Vector Store**: This module doesn't use embeddings/RAG - all context from direct record access
2. **Single Invoice Focus**: Each thread links to one invoice (intentional design)
3. **OCR Accuracy**: Depends on Mistral OCR quality and document clarity
4. **Tool Execution**: Limited to 5 tool calls per response (configurable)

## Future Enhancements

1. **Batch Processing**: Analyze multiple invoices in one conversation
2. **Approval Workflow**: Tools to approve/reject invoices
3. **Learning from Corrections**: Store user feedback for future improvements
4. **Custom Validations**: Configurable validation rules per company
5. **Integration with Purchase Orders**: Automatic 3-way matching

## References

- [llm_thread Pattern](../llm_thread/README.md)
- [llm_assistant Configuration](../llm_assistant/README.md)
- [llm_tool Decorator Guide](../llm_tool/README.md)
- [Odoo 18.0 Accounting](https://www.odoo.com/documentation/18.0/applications/finance/accounting.html)

---

**Document Version**: 1.0
**Last Updated**: 2025-11-18
**Author**: Lead Architect (AI)
