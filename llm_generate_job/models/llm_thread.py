import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LLMThread(models.Model):
    _inherit = "llm.thread"

    # Generation job relationships
    generation_job_ids = fields.One2many(
        "llm.generation.job",
        "thread_id",
        string="Generation Jobs",
        help="All generation jobs for this thread"
    )
    
    # Generation status
    is_generating = fields.Boolean(
        string="Is Generating",
        compute="_compute_is_generating",
        store=True,
        help="True if thread has active generation jobs"
    )
    
    current_generation_job_id = fields.Many2one(
        "llm.generation.job",
        string="Current Generation Job",
        compute="_compute_current_generation_job",
        help="Current active generation job"
    )
    
    # Generation statistics
    total_generation_jobs = fields.Integer(
        string="Total Generation Jobs",
        compute="_compute_generation_stats",
        help="Total number of generation jobs"
    )
    
    successful_generation_jobs = fields.Integer(
        string="Successful Jobs",
        compute="_compute_generation_stats",
        help="Number of successful generation jobs"
    )
    
    failed_generation_jobs = fields.Integer(
        string="Failed Jobs",
        compute="_compute_generation_stats",
        help="Number of failed generation jobs"
    )
    
    generation_success_rate = fields.Float(
        string="Success Rate (%)",
        compute="_compute_generation_stats",
        help="Generation success rate percentage"
    )

    @api.depends("generation_job_ids.state")
    def _compute_is_generating(self):
        for thread in self:
            thread.is_generating = bool(
                thread.generation_job_ids.filtered(
                    lambda j: j.state in ["queued", "running"]
                )
            )

    @api.depends("generation_job_ids.state")
    def _compute_current_generation_job(self):
        for thread in self:
            active_jobs = thread.generation_job_ids.filtered(
                lambda j: j.state in ["queued", "running"]
            )
            thread.current_generation_job_id = active_jobs[:1] if active_jobs else False

    @api.depends("generation_job_ids.state")
    def _compute_generation_stats(self):
        for thread in self:
            jobs = thread.generation_job_ids
            thread.total_generation_jobs = len(jobs)
            thread.successful_generation_jobs = len(
                jobs.filtered(lambda j: j.state == "completed")
            )
            thread.failed_generation_jobs = len(
                jobs.filtered(lambda j: j.state == "failed")
            )
            
            if thread.total_generation_jobs > 0:
                thread.generation_success_rate = (
                    thread.successful_generation_jobs / thread.total_generation_jobs
                ) * 100
            else:
                thread.generation_success_rate = 0.0

    def _generate_response(self, last_message):
        """Generate response with queue support - overrides llm_generate._generate_response
        
        This method provides queue-based generation capabilities while maintaining
        backward compatibility with direct generation.
        
        Args:
            last_message: The last user message containing generation data in body_json
            
        Yields:
            dict: Generation progress updates
        """
        self.ensure_one()
        
        # Check if already generating
        if self.is_generating:
            raise UserError(_("Thread is already generating a response."))
        
        # Determine whether to use queue or direct generation
        # Auto-detect based on model having a queue
        queue = self.env['llm.generation.queue'].search([
            ('model_id', '=', self.model_id.id),
            ('enabled', '=', True)
        ], limit=1)
        use_queue = bool(queue)
        
        if use_queue:
            # Use queue-based generation
            yield from self._generate_with_queue_from_message(last_message)
        else:
            # Use direct generation (call parent method)
            yield from super()._generate_response(last_message)

    def _generate_with_queue_from_message(self, last_message):
        """Generate using the job queue system from an existing message"""
        self.ensure_one()
        
        # Create generation job from the message
        job = self._create_generation_job_from_message(last_message)
        
        # Queue the job
        job.action_queue()
        
        # Monitor the job and yield updates
        yield from self._monitor_generation_job(job)

    def _create_generation_job_from_message(self, last_message):
        """Create a generation job record from an existing message"""
        self.ensure_one()
        
        # Prepare generation inputs from message body_json (following llm_generate pattern)
        generation_inputs = last_message.body_json or {}
        
        # If the message has attachment_ids, include them
        if hasattr(last_message, 'attachment_ids') and last_message.attachment_ids:
            generation_inputs['attachment_ids'] = last_message.attachment_ids.ids

        # Create job record
        job = self.env["llm.generation.job"].create({
            "thread_id": self.id,
            "provider_id": self.provider_id.id,
            "model_id": self.model_id.id,
            "input_message_id": last_message.id,
            "generation_inputs": generation_inputs,
            "state": "draft",
        })

        return job
        
    def _create_generation_job(self, user_message_body=None, **kwargs):
        """Create a generation job record (legacy method for backward compatibility)"""
        self.ensure_one()
        
        # Post user message first if provided
        input_message = None
        if user_message_body:
            input_message = self.message_post(
                body=user_message_body,
                llm_role="user",
                author_id=self.env.user.partner_id.id,
                **kwargs
            )

        # Prepare generation inputs
        generation_inputs = dict(kwargs)
        if user_message_body:
            generation_inputs["user_message_body"] = user_message_body

        # Create job record
        job = self.env["llm.generation.job"].create({
            "thread_id": self.id,
            "provider_id": self.provider_id.id,
            "model_id": self.model_id.id,
            "input_message_id": input_message.id if input_message else False,
            "generation_inputs": generation_inputs,
            "state": "draft",
        })

        return job

    def _monitor_generation_job(self, job):
        """Monitor generation job and yield streaming updates"""
        import time
        
        while job.state in ["queued", "running"]:
            # Yield status updates
            yield {
                "type": "job_status",
                "job_id": job.id,
                "state": job.state,
                "message": self._get_job_status_message(job),
            }

            # Check for result message updates
            if job.output_message_id:
                yield {
                    "type": "message_update",
                    "message": job.output_message_id.message_format()[0],
                }

            # Wait before next check
            time.sleep(1)  # Polling interval
            job.refresh()

        # Final status
        if job.state == "completed":
            message_data = None
            if job.output_message_id:
                message_data = job.output_message_id.message_format()[0]
            
            yield {
                "type": "done",
                "job_id": job.id,
                "message": message_data,
            }
        elif job.state == "failed":
            yield {
                "type": "error",
                "error": job.error_message or "Generation failed",
                "job_id": job.id,
            }
        elif job.state == "cancelled":
            yield {
                "type": "cancelled",
                "job_id": job.id,
                "message": "Generation was cancelled",
            }

    def _get_job_status_message(self, job):
        """Get user-friendly status message for job"""
        if job.state == "queued":
            queue = self.env["llm.generation.queue"].search([
                ("provider_id", "=", job.provider_id.id)
            ], limit=1)
            
            if queue:
                position = self.env["llm.generation.job"].search_count([
                    ("provider_id", "=", job.provider_id.id),
                    ("state", "=", "queued"),
                    ("queued_at", "<", job.queued_at),
                ]) + 1
                
                return f"Queued (position {position})"
            else:
                return "Queued"
        elif job.state == "running":
            return "Generating response..."
        else:
            return job.state.title()

    def action_cancel_generation(self):
        """Cancel current generation job"""
        self.ensure_one()
        
        if not self.is_generating:
            raise UserError(_("No active generation to cancel"))
        
        current_job = self.current_generation_job_id
        if current_job:
            current_job.action_cancel()
            return True
        
        return False

    def action_retry_last_failed_generation(self):
        """Retry the last failed generation job"""
        self.ensure_one()
        
        failed_job = self.generation_job_ids.filtered(
            lambda j: j.state == "failed"
        ).sorted("create_date", reverse=True)[:1]
        
        if not failed_job:
            raise UserError(_("No failed generation jobs to retry"))
        
        if failed_job.can_retry:
            failed_job.action_retry()
            return True
        else:
            raise UserError(_("Cannot retry this failed job"))

    def get_generation_history(self):
        """Get generation history for this thread"""
        self.ensure_one()
        
        jobs = self.generation_job_ids.sorted("create_date", reverse=True)
        
        history = []
        for job in jobs:
            history.append({
                "id": job.id,
                "state": job.state,
                "created_at": job.create_date,
                "queued_at": job.queued_at,
                "started_at": job.started_at,
                "completed_at": job.completed_at,
                "duration": job.duration,
                "queue_duration": job.queue_duration,
                "retry_count": job.retry_count,
                "error_message": job.error_message,
                "input_message_id": job.input_message_id.id if job.input_message_id else None,
                "output_message_id": job.output_message_id.id if job.output_message_id else None,
            })
        
        return history

    def get_generation_stats(self):
        """Get comprehensive generation statistics"""
        self.ensure_one()
        
        return {
            "total_jobs": self.total_generation_jobs,
            "successful_jobs": self.successful_generation_jobs,
            "failed_jobs": self.failed_generation_jobs,
            "success_rate": self.generation_success_rate,
            "is_generating": self.is_generating,
            "current_job_id": self.current_generation_job_id.id if self.current_generation_job_id else None,
        }
