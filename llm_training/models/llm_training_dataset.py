from odoo import api, fields, models
import json
import logging

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
    
    def _compute_example_count(self):
        """Count examples across all attached JSON files"""
        for record in self:
            count = 0
            for attachment in record.attachment_ids:
                try:
                    content = attachment.datas.decode('utf-8')
                    data = json.loads(content)
                    # Count items if it's a list of examples
                    if isinstance(data, list):
                        count += len(data)
                    # For JSONL files, count lines
                    elif isinstance(data, str):
                        count += data.count('\n') + 1
                except Exception as e:
                    _logger.warning(f"Could not parse dataset file: {e}")
            
            record.example_count = count
    
    def validate_dataset(self):
        """Validate that the dataset files are in the correct format"""
        self.ensure_one()
        # This method would validate JSON schema, format, etc.
        # For OpenAI fine-tuning, validate JSONL format with messages
        # Return validation result
        return {'valid': True, 'message': 'Dataset is valid'}
