import io
import json
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
        "llm.provider", string="LLM Provider", required=True, tracking=True
    )
    base_model_id = fields.Many2one(
        "llm.model",
        string="Base Model",
        required=True,
        domain="[('provider_id', '=', provider_id)]",
        tracking=True,
    )
    trained_model_name = fields.Char(
        string="Trained Model Name", tracking=True, help="Name of the fine-tuned model"
    )

    # Job details and tracking
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("validating", "Validating"),
            ("preparing", "Preparing"),
            ("queued", "Queued"),
            ("training", "Training"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        string="Status",
        tracking=True,
    )

    # Job configuration
    hyperparameters = fields.Json(
        string="Hyperparameters",
        default={},
        help="Training hyperparameters (epochs, batch size, etc.)",
    )

    # Dataset relation
    dataset_ids = fields.Many2many(
        "llm.training.dataset",
        "llm_training_job_dataset_rel",
        "job_id",
        "dataset_id",
        string="Datasets",
        required=True,
    )

    # Results and metrics
    external_job_id = fields.Char(
        string="External Job ID",
        tracking=True,
        help="ID of the job on the provider's system",
    )
    training_metrics = fields.Json(
        string="Training Metrics",
        help="Metrics from the training job (loss, accuracy, etc.)",
    )
    training_logs = fields.Text(
        string="Training Logs", help="Logs from the training process"
    )

    # Costs
    estimated_cost = fields.Float(
        string="Estimated Cost",
        compute="_compute_estimated_cost",
        store=False,
        help="Estimated cost of the training job in USD",
    )
    final_cost = fields.Float(
        string="Final Cost", tracking=True, help="Final cost of the training job in USD"
    )

    # Result model details
    result_model_id = fields.Many2one(
        "llm.model",
        string="Resulting Model",
        help="The fine-tuned model created by this job",
    )

    # Provider-specific identifiers
    training_file_id = fields.Char(
        string="Training File ID",
        readonly=True,
        copy=False,
        tracking=True,
        help="The File ID returned by the provider after dataset upload.",
    )

    @api.depends("dataset_ids", "base_model_id")
    def _compute_estimated_cost(self):
        """Calculate estimated cost based on dataset size and model"""
        # TODO: Think about it later
        for record in self:
            # This would use provider-specific pricing information
            # For demonstration, using a simplified calculation
            example_count = sum(dataset.example_count for dataset in record.dataset_ids)
            base_cost = 0.0

            # Different providers have different pricing structures
            if record.provider_id and record.provider_id.service:
                if record.provider_id.service == "openai":
                    # Example OpenAI pricing
                    if record.base_model_id and "gpt-4" in record.base_model_id.name:
                        base_cost = 0.03 * example_count  # $0.03 per 1K tokens
                    else:
                        base_cost = 0.008 * example_count  # $0.008 per 1K tokens

            record.estimated_cost = base_cost

    def _validate(self):
        """Initial validation of associated datasets.

        Raises:
            UserError: If no datasets are selected or if the first invalid dataset is found.
        """
        for job in self:
            if not job.dataset_ids:
                raise UserError(
                    f"Job '{job.name}': Please select at least one dataset before validating."
                )

            for dataset in job.dataset_ids:
                result = dataset.validate_dataset()
                if not result["valid"]:
                    raise UserError(
                        f"Validation failed for job '{job.name}':\nDataset '{dataset.name}': {result['message']}"
                    )

        return True

    def _prepare(self):
        """Prepare datasets for training"""
        self.ensure_one()
        if self.training_file_id:
            return True
        if self.provider_id.service != "openai":
            raise UserError(
                f"Job '{self.name}': Preparation currently only supported for OpenAI."
            )

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
                _logger.warning(
                    f"Dataset '{dataset.name}' for job '{self.name}' resulted in empty content, skipping."
                )

        if not all_datasets_bytes:
            raise UserError(
                f"Job '{self.name}': No valid content found in any linked dataset."
            )

        final_combined_bytes = b"".join(all_datasets_bytes)

        if not final_combined_bytes:
            raise UserError(
                f"Job '{self.name}': Combined content from all datasets is empty after processing."
            )

        # Create a filename for the upload (e.g., based on job name or dataset name)
        upload_filename = f"{self.name or 'job'}_combined_datasets.jsonl"

        file_obj = io.BytesIO(final_combined_bytes)
        file_tuple = (upload_filename, file_obj)

        response = self.provider_id.upload_file(file_tuple, purpose="fine-tune")

        self.write({"training_file_id": response.id})
        self.env.cr.commit()

        return True

    def action_submit(self):
        """Submit job to the provider"""
        self.ensure_one()
        self._submit()
        return True

    def _submit(self):
        self._validate()
        self._prepare()
        if not self.training_file_id:
            raise UserError(
                f"Job '{self.name}': No training file ID found. Please prepare the dataset first."
            )

        if not self.base_model_id:
            raise UserError(f"Job '{self.name}': No base model selected.")

        hyperparameters = self.hyperparameters
        if isinstance(hyperparameters, str):
            try:
                hyperparameters = json.loads(hyperparameters)
            except (json.JSONDecodeError, ValueError):
                hyperparameters = {}
        elif not isinstance(hyperparameters, dict):
            hyperparameters = {}

        response = self.provider_id.create_fine_tuning_job(
            training_file_id=self.training_file_id,
            model_name=self.base_model_id.name,
            hyperparameters=hyperparameters,
        )

        self.write(
            {
                "state": "validating",
                "external_job_id": response.id if hasattr(response, "id") else None,
            }
        )

        _logger.info(
            f"Fine-tuning job '{self.name}' submitted successfully. External job ID: {response.id if hasattr(response, 'id') else 'unknown'}"
        )

    def action_cancel(self):
        """Cancel the training job"""
        self.ensure_one()
        self.provider_id.cancel_fine_tuning_job(job_id=self.external_job_id)
        self.write({"state": "cancelled"})
        return True

    def action_check_status(self):
        """Check the status of the job with the provider"""
        result = self._check_status()

        return result

    def _check_status(self):
        self.ensure_one()
        # TODO: For now it supports openai format but it should be uniform structure
        response = self.provider_id.retrieve_fine_tuning_job(
            job_id=self.external_job_id
        )

        if response.status == "succeeded":
            models_data = self.provider_id.list_models(
                model_id=response.fine_tuned_model
            )
            for model_data in models_data:
                details = model_data.get("details", {})
                name = model_data.get("name") or details.get("id")

                if not name:
                    continue

                # Determine model use and capabilities
                capabilities = details.get("capabilities", ["chat"])
                model_use = self.env["llm.fetch.models.wizard"]._determine_model_use(
                    name, capabilities
                )

                vals = {
                    "name": name,
                    "model_use": model_use,
                    "details": details,
                    "provider_id": self.provider_id.id,
                    "active": True,
                }
                result = self.env["llm.model"].create(vals)
                self.write(
                    {
                        "state": "completed",
                        "result_model_id": result.id,
                        "trained_model_name": response.fine_tuned_model,
                    }
                )
                self.update_training_metrics(
                    self.provider_id.format_fine_tune_metrics(response)
                )
                return True

        elif response.status == "failed":
            self.write({"state": "failed"})
        elif response.status == "cancelled":
            self.write({"state": "cancelled"})
        elif response.status == "running":
            self.write({"state": "training"})
        elif response.status == "queued":
            self.write({"state": "queued"})

        elif response.status == "validating_files":
            self.write({"state": "validating"})

        return True

    def update_training_metrics(self, metrics):
        """Update training metrics from the provider"""
        self.ensure_one()

        # Convert metrics dict to JSON string due to lack of widget support
        if isinstance(metrics, dict):
            metrics_str = json.dumps(metrics, indent=2)
        else:
            metrics_str = str(metrics)

        self.write({"training_metrics": metrics_str})
        return True
