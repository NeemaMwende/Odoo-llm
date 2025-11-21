# Verified Odoo 18.0 Invoice Models

## ✅ account.move (Invoice Header)

**Source**: `/src/odoo/addons/account/models/account_move.py`

### Verified Fields

**Invoice Type:**

```python
move_type = fields.Selection([
    ('entry', 'Journal Entry'),
    ('out_invoice', 'Customer Invoice'),
    ('out_refund', 'Customer Credit Note'),
    ('in_invoice', 'Vendor Bill'),
    ('in_refund', 'Vendor Credit Note'),
    ('out_receipt', 'Sales Receipt'),
    ('in_receipt', 'Purchase Receipt'),
])
```

**Key Fields (Verified):**

- `partner_id` = Many2one → Vendor (for in_invoice) or Customer (for out_invoice)
- `invoice_date` = Date → Invoice date
- `invoice_date_due` = Date → Payment due date
- `ref` = Char → External reference (original invoice number)
- `state` = Selection → draft, posted, cancel
- `amount_untaxed` = Monetary (computed) → Subtotal
- `amount_total` = Monetary (computed) → Total with tax
- `invoice_origin` = Char → Source document (PO/SO number)

## ✅ account.move.line (Invoice Lines)

**Source**: `/src/odoo/addons/account/models/account_move_line.py`

### Verified Fields

**Key Fields (Verified):**

- `move_id` = Many2one('account.move') → Parent invoice
- `name` = Char → Line description
- `account_id` = Many2one('account.account') → Expense/Income account
- `product_id` = Many2one('product.product') → Optional product
- `quantity` = Float → Quantity
- `price_unit` = Float → Unit price
- `tax_ids` = Many2many('account.tax') → Applied taxes
- `display_type` = Selection → 'product', 'line_section', 'line_note'

**Computed Fields (Don't Set):**

- `price_subtotal` → Auto-calculated
- `price_total` → Auto-calculated with tax
- `debit`/`credit` → Auto-calculated accounting entries

## ✅ Verified Domain Knowledge

### Invoice Types (CONFIRMED)

```
in_invoice: Vendor Bill (money we owe)
out_invoice: Customer Invoice (money owed to us)
in_refund: Vendor Credit Note
out_refund: Customer Credit Note
```

### Partner Logic (CONFIRMED)

```
in_invoice → partner_id = SENDER (vendor billing us)
out_invoice → partner_id = RECIPIENT (customer we're billing)
```

### Account Types (Need to verify)

```
in_invoice → expense accounts (expense, expense_direct_cost)
out_invoice → income accounts (income, income_other)
```

Let me verify account types...
