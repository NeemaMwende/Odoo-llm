# Knowledge Extraction from ODOO_INVOICE_DATA_ENTRY_AGENT.md

## 🎯 What's VALUABLE (Extract This)

### 1. Partner Identification Logic ✅

**Critical Concept:**

```
Vendor Bill (in_invoice): Partner = SENDER (who is billing us)
Customer Invoice (out_invoice): Partner = RECIPIENT (who we are billing)
```

**Common Mistake Prevention:**

- Users often confuse who the partner should be
- Must emphasize: vendor bill partner is the SENDER, not recipient

**For Instructions:**

> When analyzing invoices, identify the partner correctly:
>
> - **Vendor Bills**: Partner is the sender/vendor (who is billing us)
> - **Customer Invoices**: Partner is the recipient/customer (who we are billing)

### 2. Account Type Mapping ✅

**Concept:**

```
in_invoice (vendor bill) → expense/expense_direct_cost accounts
out_invoice (customer invoice) → income/income_other accounts
```

**For Instructions:**

> Use correct account types:
>
> - Vendor bills: expense accounts
> - Customer invoices: income accounts

### 3. Invoice Types Reference ✅

**Concept:**

```python
move_types = {
    "in_invoice": "Vendor Bill (incoming)",
    "in_refund": "Vendor Credit Note",
    "out_invoice": "Customer Invoice (outgoing)",
    "out_refund": "Customer Credit Note"
}
```

**For Instructions:**

> Understand invoice types in Odoo:
>
> - `in_invoice`: Vendor Bill (money we owe)
> - `out_invoice`: Customer Invoice (money owed to us)
> - `in_refund`: Vendor Credit Note
> - `out_refund`: Customer Credit Note

### 4. Historical Pattern Analysis ✅

**Concept:**
Check previous invoices from same partner to:

- Detect duplicates
- Learn typical tax rates
- Learn typical accounts used
- Learn payment terms

**Domain Examples:**

```python
# Find duplicates
[["partner_id", "=", partner_id], ["ref", "=", invoice_ref], ["invoice_date", "=", date]]

# Find historical invoices
[["partner_id", "=", partner_id], ["move_type", "=", move_type], ["state", "=", "posted"]]
```

**For Instructions:**

> Check historical patterns:
>
> 1. Search for duplicate invoices (same partner, ref, date)
> 2. Analyze previous invoices from same partner for typical patterns
> 3. Use historical data to inform tax rates, accounts, payment terms

### 5. Field Validation Checklist ✅

**Concept:**
Always verify these before suggesting updates:

- No duplicate exists
- Partner is correct
- Amount matches parsed document
- Tax configuration is appropriate
- Accounts match patterns
- Dates are logical

**For Instructions:**

> Before suggesting updates, verify:
>
> - No duplicate invoice exists
> - Partner identification is correct
> - Amounts match extracted data
> - Tax rates are appropriate for jurisdiction/partner
> - Account selection follows patterns
> - Dates are logical (invoice date before due date)

### 6. Invoice Line Structure ✅

**Odoo Fields Reference:**

```python
account.move.line fields:
- move_id: Parent invoice ID
- name: Line description
- account_id: Expense or income account
- product_id: Optional product reference
- quantity: Quantity
- price_unit: Unit price
- tax_ids: Many2many [[6, 0, [tax_ids]]]
- display_type: 'product' (not 'line_section' or 'line_note')

Auto-computed (don't set):
- price_subtotal
- price_total
- debit/credit
```

**For Instructions:**

> Invoice line fields:
>
> - `move_id`: Links to parent invoice
> - `name`: Line description text
> - `account_id`: Expense (vendor) or income (customer) account
> - `product_id`: Optional product
> - `quantity`, `price_unit`: Line amounts
> - `tax_ids`: Use format [[6, 0, [list of tax IDs]]]
> - `display_type`: Should be 'product' for normal lines

### 7. Tax Application Rules ✅

**Concept:**
Tax determination priority:

1. Historical pattern (if consistent)
2. Partner fiscal position rules
3. Jurisdiction rules
4. Service-specific rules (withholding)

**Edge Cases:**

- Tax-inclusive prices (set price_include=True on tax)
- Multiple tax rates per invoice
- Withholding taxes (negative percentages)
- Reverse charge scenarios

**For Instructions:**

> Tax application logic:
>
> 1. Check historical invoices from same partner
> 2. Respect partner's fiscal position if set
> 3. Consider jurisdiction (state, country)
> 4. Watch for tax-inclusive prices
> 5. Handle withholding taxes for services

### 8. Edge Cases Awareness ✅

**Multi-Currency:**

- Check invoice currency_id
- Verify exchange rates configured
- Amounts auto-convert

**Partial Invoices:**

- Check invoice_origin for PO reference
- Look for related invoices
- Check for down payments

**Missing Information:**

- Partner: Prompt user to select/create
- Date: Default to today, ask confirmation
- Amount: Require manual entry

**For Instructions:**

> Handle edge cases:
>
> - **Multi-currency**: Check currency_id, verify exchange rates
> - **Partial invoices**: Look for PO references in invoice_origin
> - **Missing data**: Prompt user instead of guessing

### 9. Best Practices ✅

**Audit Trail:**

- Always populate `ref` field (original invoice number)
- Use `narration` for processing notes
- Set `invoice_origin` for PO/SO references

**State Management:**

- NEVER auto-post invoices
- Keep in 'draft' for user review
- Let user trigger posting

**For Instructions:**

> Best practices:
>
> - Populate `ref` with original invoice number
> - Add processing notes to `narration`
> - NEVER auto-post - keep in 'draft' state
> - Let user review before posting

---

## ❌ What's GARBAGE (Ignore This)

### 1. Fake Method Names ❌

```python
check_attachments(invoice_id)
identify_or_create_partner()
analyze_historical_patterns()
prepare_invoice_lines()
get_user_confirmation()
```

**These don't exist!** They're conceptual pseudocode.

### 2. Wrong Tool References ❌

```python
mcp__odoo-llm-mcp-server__odoo_record_retriever
mcp__odoo-llm-mcp-server__odoo_model_inspector
```

**Wrong!** We use: `odoo_record_retriever`, `odoo_model_inspector`

### 3. LLM Resource Workflow ❌

```python
llm_resource_domain = [["res_model", "=", "ir.attachment"], ...]
if llm_resource.state == 'parsed':
    parsed_data = llm_resource.content
```

**Outdated!** We use `llm_mistral_attachment_parser` tool instead.

### 4. Async/Await Patterns ❌

```python
async def process_invoice(invoice_id):
    invoice = await odoo_record_retriever(...)
```

**Not applicable!** Tools are not async in our context.

### 5. Step-by-Step Workflow ❌

The rigid 9-step workflow is too prescriptive. Our assistant should be flexible and conversational.

### 6. Fake Functions in Examples ❌

```python
average(previous_amounts)
most_common(tax_configurations)
frequency_map(account_ids)
apply_fiscal_position_rules()
check_withholding_requirements()
```

**These are conceptual!** Not real functions available to the LLM.

---

## 📝 Extracted Instructions (Clean Version)

Use these concepts to enhance our assistant instructions:

```markdown
**Invoice Type & Partner Identification:**

- Vendor bills (in_invoice): Partner is the SENDER (who is billing us)
- Customer invoices (out_invoice): Partner is the RECIPIENT (who we are billing)
- in_refund: Vendor credit note | out_refund: Customer credit note

**Account Selection:**

- Vendor bills → Use expense accounts (expense, expense_direct_cost)
- Customer invoices → Use income accounts (income, income_other)

**Historical Pattern Analysis:**
Use odoo_record_retriever to:

- Check for duplicates: [['partner_id', '=', id], ['ref', '=', ref], ['invoice_date', '=', date]]
- Find previous invoices: [['partner_id', '=', id], ['move_type', '=', type], ['state', '=', 'posted']]
- Learn typical tax rates, accounts, payment terms from history

**Invoice Line Structure:**
When creating/updating lines (account.move.line):

- move_id: Parent invoice ID
- name: Line description
- account_id: Expense or income account
- product_id: Optional
- quantity, price_unit: Amounts
- tax_ids: Format [[6, 0, [tax_id_list]]]
- display_type: 'product' for normal lines
- Do NOT set: price_subtotal, price_total, debit, credit (auto-computed)

**Tax Application:**
Priority order:

1. Check historical pattern from previous invoices
2. Respect partner fiscal position if configured
3. Consider jurisdiction/state rules
4. Watch for tax-inclusive prices
5. Handle withholding taxes (negative rates)

**Validation Checklist:**
Before suggesting updates:

1. No duplicate invoice exists
2. Partner correctly identified
3. Amounts match extracted data
4. Tax rates appropriate
5. Accounts follow historical patterns
6. Dates are logical

**Edge Cases:**

- Multi-currency: Check currency_id field
- Partial invoices: Look for invoice_origin (PO reference)
- Missing data: Prompt user, don't guess

**Best Practices:**

- Populate ref field with original invoice number
- Add notes to narration field
- NEVER auto-post invoices (keep draft)
- Let user review and post manually
```

---

## 🎯 Summary

**Keep:**

- Partner identification rules
- Account type mappings
- Historical analysis concepts
- Field structure knowledge
- Tax application logic
- Validation checklist
- Edge case awareness
- Best practices

**Remove:**

- Fake method names
- Wrong tool references
- LLM resource workflow
- Async patterns
- Prescriptive workflow steps
- Conceptual pseudocode

The document has **excellent domain knowledge** buried in **bad implementation examples**. Extract the concepts, discard the code!
