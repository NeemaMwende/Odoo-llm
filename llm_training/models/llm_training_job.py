import io
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LLMTrainingJob(models.Model):
    _name = "llm.training.job"
    _description = "LLM Fine-tuning Job"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(required=True, tracking=True)
    description = fields.Text(tracking=True)
    active = fields.Boolean(default=True)
    
    # Provider information
    provider_id = fields.Many2one(
        'llm.provider',
        string='LLM Provider',
        required=True,
        tracking=True
    )
    base_model_id = fields.Many2one(
        'llm.model',
        string='Base Model',
        required=True,
        domain="[('provider_id', '=', provider_id)]",
        tracking=True
    )
    trained_model_name = fields.Char(
        string='Trained Model Name',
        tracking=True,
        help="Name of the fine-tuned model"
    )
    
    # Job details and tracking
    state = fields.Selection([
        ('draft', 'Draft'),
        ('validating', 'Validating'),
        ('preparing', 'Preparing'),
        ('queued', 'Queued'),
        ('training', 'Training'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled')
    ], default='draft', string='Status', tracking=True)
    
    # Job configuration
    hyperparameters = fields.Json(
        string='Hyperparameters',
        default={},
        help="Training hyperparameters (epochs, batch size, etc.)"
    )
    
    # Dataset relation
    dataset_ids = fields.Many2many(
        'llm.training.dataset',
        'llm_training_job_dataset_rel',
        'job_id',
        'dataset_id',
        string='Datasets',
        required=True
    )
    
    # Results and metrics
    external_job_id = fields.Char(
        string='External Job ID',
        tracking=True,
        help="ID of the job on the provider's system"
    )
    training_metrics = fields.Json(
        string='Training Metrics',
        help="Metrics from the training job (loss, accuracy, etc.)"
    )
    training_logs = fields.Text(
        string='Training Logs',
        help="Logs from the training process"
    )
    
    # Costs
    estimated_cost = fields.Float(
        string='Estimated Cost',
        compute='_compute_estimated_cost',
        store=False,
        help="Estimated cost of the training job in USD"
    )
    final_cost = fields.Float(
        string='Final Cost',
        tracking=True,
        help="Final cost of the training job in USD"
    )
    
    # Result model details
    result_model_id = fields.Many2one(
        'llm.model',
        string='Resulting Model',
        help="The fine-tuned model created by this job"
    )
    
    # Provider-specific identifiers
    training_file_id = fields.Char(
        string="Training File ID", 
        readonly=True, 
        copy=False, 
        tracking=True,
        help="The File ID returned by the provider after dataset upload."
    )

    @api.depends('dataset_ids', 'base_model_id')
    def _compute_estimated_cost(self):
        """Calculate estimated cost based on dataset size and model"""
        for record in self:
            # This would use provider-specific pricing information
            # For demonstration, using a simplified calculation
            example_count = sum(dataset.example_count for dataset in record.dataset_ids)
            base_cost = 0.0
            
            # Different providers have different pricing structures
            if record.provider_id and record.provider_id.service:
                if record.provider_id.service == 'openai':
                    # Example OpenAI pricing
                    if record.base_model_id and 'gpt-4' in record.base_model_id.name:
                        base_cost = 0.03 * example_count  # $0.03 per 1K tokens
                    else:
                        base_cost = 0.008 * example_count  # $0.008 per 1K tokens
            
            record.estimated_cost = base_cost
    
    def action_validate(self):
        """Validate associated datasets. Set state to 'validating' if all pass.
        
        Raises:
            UserError: If no datasets are selected or if the first invalid dataset is found.
        """
        for job in self:
            if not job.dataset_ids:
                raise UserError(f"Job '{job.name}': Please select at least one dataset before validating.")

            for dataset in job.dataset_ids:
                result = dataset.validate_dataset()
                if not result['valid']:
                     raise UserError(f"Validation failed for job '{job.name}':\nDataset '{dataset.name}': {result['message']}")
            job.write({'state': 'validating'})

        return True
    
    def action_prepare(self):
        """Prepare datasets for training"""
        self.ensure_one()
        if self.provider_id.service != 'openai':
            raise UserError(f"Job '{self.name}': Preparation currently only supported for OpenAI.")

        if not self.dataset_ids:
            raise UserError(f"Job '{self.name}': No datasets linked for preparation.")
        
        all_datasets_bytes = []
        dataset_names = []
        for dataset in self.dataset_ids:
            content_bytes = dataset._get_combined_content_bytes()
            if content_bytes:
                all_datasets_bytes.append(content_bytes)
                dataset_names.append(dataset.name)
            else:
                _logger.warning(f"Dataset '{dataset.name}' for job '{self.name}' resulted in empty content, skipping.")
            
 
        if not all_datasets_bytes:
            raise UserError(f"Job '{self.name}': No valid content found in any linked dataset.")
        
        final_combined_bytes = b''.join(all_datasets_bytes)
        
        if not final_combined_bytes:
             raise UserError(f"Job '{self.name}': Combined content from all datasets is empty after processing.")
         
         # Create a filename for the upload (e.g., based on job name or dataset name)
        upload_filename = f"{self.name or 'job'}_combined_datasets.jsonl"
         
        file_obj = io.BytesIO(final_combined_bytes)
        file_tuple = (upload_filename, file_obj)

        response = self.provider_id.upload_file(
            file_tuple,
            purpose='fine-tune'
        )
        
        self.write({
            'state': 'preparing', 
            'training_file_id': response.id
        })

        return True
    
    def action_submit(self):
        """Submit job to the provider"""
        self.ensure_one()
        self.write({'state': 'queued'})
        # Submission logic would call the provider's API
        # This would be provider-specific
        return True
    
    def action_cancel(self):
        """Cancel the training job"""
        self.ensure_one()
        self.write({'state': 'cancelled'})
        # Cancellation logic would call the provider's API
        return True
    
    def action_check_status(self):
        """Check the status of the job with the provider"""
        self.ensure_one()
        # This would call the provider's API to check status
        # and update the record accordingly
        return True
    
    def update_training_metrics(self, metrics):
        """Update training metrics from the provider"""
        self.ensure_one()
        self.write({
            'training_metrics': metrics
        })
        return True
