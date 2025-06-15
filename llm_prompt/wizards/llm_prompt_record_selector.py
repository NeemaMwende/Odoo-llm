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

    # Model selection
    model_id = fields.Many2one(
        "ir.model",
        string="Model Type",
        domain=[('transient', '=', False)],
        help="Select the model type for the related record",
        required=True,
    )

    model_name = fields.Char(
        related="model_id.model",
        string="Model Name",
        readonly=True,
    )

    # Record selection - dynamically populated based on model
    record_selection = fields.Selection(
        string="Record",
        selection="_get_record_selection",
        help="Select a specific record from the chosen model",
    )

    # Store the selected record info
    selected_record_id = fields.Integer(
        string="Selected Record ID",
    )

    selected_record_name = fields.Char(
        string="Selected Record Name",
        compute="_compute_selected_record_name",
    )

    @api.depends('record_selection')
    def _compute_selected_record_name(self):
        """Compute the display name of the selected record"""
        for wizard in self:
            if wizard.record_selection and wizard.model_name:
                try:
                    record_id = int(wizard.record_selection)
                    record = self.env[wizard.model_name].browse(record_id)
                    if record.exists():
                        wizard.selected_record_name = record.display_name
                        wizard.selected_record_id = record_id
                    else:
                        wizard.selected_record_name = "Record not found"
                        wizard.selected_record_id = 0
                except (ValueError, KeyError):
                    wizard.selected_record_name = ""
                    wizard.selected_record_id = 0
            else:
                wizard.selected_record_name = ""
                wizard.selected_record_id = 0

    def _get_record_selection(self):
        """Generate selection options for records based on the selected model"""
        if not self.model_id or not self.model_name:
            return []

        try:
            # Get records from the selected model (limit for performance)
            model = self.env[self.model_name]
            records = model.search([], limit=50, order='id desc')

            # Create selection tuples (value, label)
            selection = []
            for record in records:
                selection.append((str(record.id), record.display_name))

            return selection

        except Exception:
            # Return empty list if there's any error accessing the model
            return []

    @api.onchange('model_id')
    def _onchange_model_id(self):
        """Clear record selection when model changes"""
        if self.model_id:
            self.record_selection = False
        else:
            self.record_selection = False

    def action_confirm_selection(self):
        """Confirm the record selection and return to test wizard"""
        self.ensure_one()

        if not self.model_id:
            raise models.ValidationError(_("Please select a model type."))

        if not self.record_selection:
            raise models.ValidationError(_("Please select a record."))

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

