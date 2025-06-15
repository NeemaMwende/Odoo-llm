from odoo import _, api, fields, models


class LLMPromptRecordSelector(models.TransientModel):
    _name = "llm.prompt.record.selector"
    _description = "Related Record Selector for Prompt Testing"

    test_wizard_id = fields.Many2one(
        "llm.prompt.test",
        string="Test Wizard",
        required=True,
        ondelete="cascade",
    )

    # Step 1: Model selection
    model_id = fields.Many2one(
        "ir.model",
        string="Model",
        domain=[('transient', '=', False)],
        help="Select the model type for the related record",
    )

    model_name = fields.Char(
        related="model_id.model",
        string="Model Name",
        readonly=True,
    )

    # Step 2: Record selection
    record_ids = fields.One2many(
        "llm.prompt.record.selector.line",
        "selector_id",
        string="Available Records",
    )

    selected_record_id = fields.Integer(
        string="Selected Record ID",
    )

    # UI State
    step = fields.Selection([
        ('model', 'Select Model'),
        ('record', 'Select Record'),
    ], default='model', string="Current Step")

    def action_next_step(self):
        """Move to record selection step"""
        self.ensure_one()
        if self.step == 'model' and self.model_id:
            self.step = 'record'
            self._load_records()
        return self._return_form_view()

    def action_previous_step(self):
        """Go back to model selection"""
        self.ensure_one()
        self.step = 'model'
        self.record_ids.unlink()  # Clear loaded records
        return self._return_form_view()

    def _load_records(self):
        """Load records for the selected model"""
        self.ensure_one()
        if not self.model_id:
            return

        # Clear existing records
        self.record_ids.unlink()

        try:
            # Get records from the selected model
            model = self.env[self.model_name]
            records = model.search([], limit=100, order='id desc')

            # Create selector lines
            lines = []
            for record in records:
                lines.append((0, 0, {
                    'record_id': record.id,
                    'display_name': record.display_name,
                    'model_name': self.model_name,
                }))

            self.record_ids = lines

        except Exception as e:
            # If there's an error, go back to model selection
            self.step = 'model'
            raise models.ValidationError(_("Error loading records: %s") % str(e))

    def action_select_record(self, record_id):
        """Select a specific record"""
        self.ensure_one()
        self.selected_record_id = record_id
        return self.action_confirm_selection()

    def action_confirm_selection(self):
        """Confirm the record selection and return to test wizard"""
        self.ensure_one()

        if self.selected_record_id and self.model_name:
            # Update the test wizard with the selected record
            self.test_wizard_id.write({
                'related_record_model': self.model_name,
                'related_record_id': self.selected_record_id,
            })

            # Trigger the onchange to update context
            self.test_wizard_id._onchange_related_record()

        # Return to the test wizard
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'llm.prompt.test',
            'view_mode': 'form',
            'res_id': self.test_wizard_id.id,
            'target': 'new',
        }

    def _return_form_view(self):
        """Return the form view for this wizard"""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'llm.prompt.record.selector',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }


class LLMPromptRecordSelectorLine(models.TransientModel):
    _name = "llm.prompt.record.selector.line"
    _description = "Record Selector Line"

    selector_id = fields.Many2one(
        "llm.prompt.record.selector",
        string="Selector",
        required=True,
        ondelete="cascade",
    )

    record_id = fields.Integer(
        string="Record ID",
        required=True,
    )

    display_name = fields.Char(
        string="Display Name",
        required=True,
    )

    model_name = fields.Char(
        string="Model Name",
        required=True,
    )

    def action_select_this_record(self):
        """Select this specific record"""
        self.ensure_one()
        return self.selector_id.action_select_record(self.record_id)