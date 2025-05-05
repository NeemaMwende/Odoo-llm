import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LLMTrainingDataset(models.Model):
    _name = "llm.training.dataset"
    _description = "LLM Training Dataset"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(required=True, tracking=True)
    description = fields.Text(tracking=True)
    active = fields.Boolean(default=True)
    
    # Dataset files
    attachment_ids = fields.Many2many(
        'ir.attachment',
        string='Dataset Files',
        help="JSON files containing training examples"
    )
    
    # Relationships
    job_ids = fields.Many2many(
        'llm.training.job',
        'llm_training_job_dataset_rel',
        'dataset_id',
        'job_id',
        string='Training Jobs'
    )
    
    # Metrics
    example_count = fields.Integer(
        string="Number of Examples",
        compute="_compute_example_count",
        store=False
    )
    file_count = fields.Integer(
        compute="_compute_file_count",
        string="Number of Files"
    )
    
    @api.depends('attachment_ids')
    def _compute_file_count(self):
        for record in self:
            record.file_count = len(record.attachment_ids)

    @api.depends('attachment_ids')
    def _compute_example_count(self):
        """Count examples across all attached JSON files"""
        for record in self:
            result = record.validate_dataset()
            record.example_count = result['example_count'] if result['valid'] else 0
    
    def action_validate_dataset(self):
        """Validate the dataset"""
        self.ensure_one()
        result = self.validate_dataset()
        if not result['valid']:
            raise UserError(result['message'])
        else:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Dataset Validated",
                    "message": result['message'],
                    "type": "success",
                    "sticky": False,
                },
            }

    def validate_dataset(self):
        """Validate that the dataset files contain valid JSON objects on each line (JSONL).

        Checks:
        - Each non-empty line is valid JSON.
        Returns:
        - dict: {'valid': bool, 'message': str, 'example_count': int (optional)}
        """
        self.ensure_one()
        errors = []
        total_valid_lines = 0

        if not self.attachment_ids:
            return {'valid': False, 'message': 'No dataset files attached.'}

        for attachment in self.attachment_ids:
            try:
                _logger.info(f"Validating file: {attachment.name} {attachment.mimetype}")
                content = attachment.raw.decode('utf-8')
                _logger.info(f"File content: {content}")
                lines = [line for line in content.splitlines() if line.strip()]
                if not lines:
                    _logger.info(f"Dataset validation: File '{attachment.name}' is empty or contains only whitespace.")
                    continue

                for i, line in enumerate(lines):
                    line_num = i + 1
                    try:
                        json.loads(line)
                        total_valid_lines += 1
                    except json.JSONDecodeError as json_error:
                        errors.append(f"File '{attachment.name}', Line {line_num}: Invalid JSON - {json_error}")

            except UnicodeDecodeError:
                errors.append(f"File '{attachment.name}': Could not decode as UTF-8.")
            except Exception as e:
                _logger.error(f"Unexpected error validating file {attachment.name}: {e}", exc_info=True)
                errors.append(f"File '{attachment.name}': Unexpected error during validation - {e}")

        if errors:
            error_message = "Dataset validation failed (JSON format errors):\n" + "\n".join(errors)
            max_len = 1000
            if len(error_message) > max_len:
                 error_message = error_message[:max_len] + "... (more errors exist)"
            return {'valid': False, 'message': error_message, 'example_count': total_valid_lines}
        else:
            return {
                'valid': True, 
                'message': f'All {total_valid_lines} non-empty lines in attached files are valid JSON.',
                'example_count': total_valid_lines
            }
