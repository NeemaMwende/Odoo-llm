import logging
from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LLMGenerationQueue(models.Model):
    _name = "llm.generation.queue"
    _description = "LLM Generation Queue"
    _rec_name = "display_name"

    # Queue identification
    provider_id = fields.Many2one(
        "llm.provider",
        string="Provider",
        required=True,
        ondelete="cascade",
        help="LLM provider this queue manages"
    )
    
    # Queue configuration
    max_concurrent_jobs = fields.Integer(
        string="Max Concurrent Jobs",
        default=5,
        help="Maximum number of jobs that can run simultaneously"
    )
    enabled = fields.Boolean(
        string="Enabled",
        default=True,
        help="Whether this queue is enabled for processing"
    )
    
    # Queue statistics
    current_running_jobs = fields.Integer(
        string="Running Jobs",
        compute="_compute_job_counts",
        help="Number of currently running jobs"
    )
    queued_jobs_count = fields.Integer(
        string="Queued Jobs",
        compute="_compute_job_counts",
        help="Number of jobs waiting in queue"
    )
    total_jobs_today = fields.Integer(
        string="Total Jobs Today",
        compute="_compute_job_counts",
        help="Total jobs processed today"
    )
    
    # Performance metrics
    avg_queue_time = fields.Float(
        string="Avg Queue Time (seconds)",
        compute="_compute_performance_metrics",
        help="Average time jobs spend in queue"
    )
    avg_processing_time = fields.Float(
        string="Avg Processing Time (seconds)",
        compute="_compute_performance_metrics",
        help="Average job processing time"
    )
    success_rate = fields.Float(
        string="Success Rate (%)",
        compute="_compute_performance_metrics",
        help="Percentage of successful jobs"
    )
    
    # Status fields
    display_name = fields.Char(
        string="Display Name",
        compute="_compute_display_name",
        store=True,
    )
    queue_health = fields.Selection([
        ('healthy', 'Healthy'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
        ('disabled', 'Disabled'),
    ], string="Queue Health", compute="_compute_queue_health")
    
    # Timestamps
    last_processed_at = fields.Datetime(
        string="Last Processed",
        help="When the queue last processed a job"
    )
    
    # Related fields for UI - computed field for recent jobs
    recent_job_ids = fields.Many2many(
        'llm.generation.job',
        string='Recent Jobs',
        compute='_compute_recent_jobs',
        help='Recent jobs for this provider'
    )
    
    # Configuration
    auto_retry_failed = fields.Boolean(
        string="Auto Retry Failed Jobs",
        default=True,
        help="Automatically retry failed jobs"
    )
    retry_delay_minutes = fields.Integer(
        string="Retry Delay (minutes)",
        default=5,
        help="Minutes to wait before retrying failed jobs"
    )

    @api.depends('provider_id')
    def _compute_display_name(self):
        for queue in self:
            if queue.provider_id:
                queue.display_name = f"{queue.provider_id.name} Queue"
            else:
                queue.display_name = "Generation Queue"

    @api.depends('provider_id')
    def _compute_job_counts(self):
        for queue in self:
            domain_base = [('provider_id', '=', queue.provider_id.id)]
            
            # Current running jobs
            queue.current_running_jobs = self.env['llm.generation.job'].search_count(
                domain_base + [('state', '=', 'running')]
            )
            
            # Queued jobs
            queue.queued_jobs_count = self.env['llm.generation.job'].search_count(
                domain_base + [('state', '=', 'queued')]
            )
            
            # Total jobs today
            today = fields.Date.today()
            queue.total_jobs_today = self.env['llm.generation.job'].search_count(
                domain_base + [('create_date', '>=', today)]
            )

    @api.depends('provider_id')
    def _compute_performance_metrics(self):
        for queue in self:
            # Get recent completed jobs (last 24 hours)
            recent_cutoff = fields.Datetime.now() - timedelta(hours=24)
            recent_jobs = self.env['llm.generation.job'].search([
                ('provider_id', '=', queue.provider_id.id),
                ('state', 'in', ['completed', 'failed']),
                ('completed_at', '>=', recent_cutoff),
            ])
            
            if recent_jobs:
                # Average queue time
                queue_times = [j.queue_duration for j in recent_jobs if j.queue_duration > 0]
                queue.avg_queue_time = sum(queue_times) / len(queue_times) if queue_times else 0.0
                
                # Average processing time
                processing_times = [j.duration for j in recent_jobs if j.duration > 0]
                queue.avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0.0
                
                # Success rate
                successful_jobs = recent_jobs.filtered(lambda j: j.state == 'completed')
                queue.success_rate = (len(successful_jobs) / len(recent_jobs)) * 100 if recent_jobs else 0.0
            else:
                queue.avg_queue_time = 0.0
                queue.avg_processing_time = 0.0
                queue.success_rate = 0.0

    @api.depends('enabled', 'current_running_jobs', 'max_concurrent_jobs', 'queued_jobs_count')
    def _compute_queue_health(self):
        for queue in self:
            if not queue.enabled:
                queue.queue_health = 'disabled'
            elif queue.current_running_jobs >= queue.max_concurrent_jobs:
                if queue.queued_jobs_count > queue.max_concurrent_jobs * 2:
                    queue.queue_health = 'critical'
                else:
                    queue.queue_health = 'warning'
            else:
                queue.queue_health = 'healthy'

    @api.depends('provider_id')
    def _compute_recent_jobs(self):
        for queue in self:
            if queue.provider_id:
                recent_cutoff = fields.Datetime.now() - timedelta(hours=24)
                recent_jobs = self.env['llm.generation.job'].search([
                    ('provider_id', '=', queue.provider_id.id),
                    ('create_date', '>=', recent_cutoff),
                ], limit=10, order='create_date desc')
                queue.recent_job_ids = recent_jobs
            else:
                queue.recent_job_ids = self.env['llm.generation.job']

    @api.model_create_multi
    def create(self, vals_list):
        """Ensure only one queue per provider"""
        for vals in vals_list:
            if 'provider_id' in vals:
                existing = self.search([('provider_id', '=', vals['provider_id'])])
                if existing:
                    raise UserError(
                        _("A queue already exists for provider '%s'") % 
                        existing.provider_id.name
                    )
        return super().create(vals_list)

    def action_enable(self):
        """Enable the queue"""
        self.ensure_one()
        self.write({'enabled': True})
        _logger.info(f"Enabled generation queue for provider {self.provider_id.name}")

    def action_disable(self):
        """Disable the queue"""
        self.ensure_one()
        self.write({'enabled': False})
        _logger.info(f"Disabled generation queue for provider {self.provider_id.name}")

    def action_process_queue(self):
        """Manually trigger queue processing"""
        self.ensure_one()
        return self._process_provider_queue(self.provider_id)

    def action_clear_queue(self):
        """Clear all queued jobs (move to cancelled state)"""
        self.ensure_one()
        queued_jobs = self.env['llm.generation.job'].search([
            ('provider_id', '=', self.provider_id.id),
            ('state', '=', 'queued'),
        ])
        
        if queued_jobs:
            queued_jobs.write({
                'state': 'cancelled',
                'completed_at': fields.Datetime.now(),
                'error_message': 'Queue cleared by administrator',
            })
            _logger.info(f"Cleared {len(queued_jobs)} jobs from queue for provider {self.provider_id.name}")
        
        return len(queued_jobs)

    def action_retry_failed_jobs(self):
        """Retry all failed jobs that can be retried"""
        self.ensure_one()
        failed_jobs = self.env['llm.generation.job'].search([
            ('provider_id', '=', self.provider_id.id),
            ('state', '=', 'failed'),
            ('retry_count', '<', self.env['llm.generation.job']._fields['max_retries'].default),
        ])
        
        retried_count = 0
        for job in failed_jobs:
            if job.can_retry:
                job.action_retry()
                retried_count += 1
        
        _logger.info(f"Retried {retried_count} failed jobs for provider {self.provider_id.name}")
        return retried_count

    def action_view_jobs(self):
        """Open the jobs view for this provider"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Jobs for {self.provider_id.name}',
            'res_model': 'llm.generation.job',
            'view_mode': 'tree,form',
            'domain': [('provider_id', '=', self.provider_id.id)],
            'context': {'default_provider_id': self.provider_id.id},
        }

    @api.model
    def _get_or_create_queue(self, provider_id):
        """Get or create a queue for the specified provider"""
        queue = self.search([('provider_id', '=', provider_id)], limit=1)
        if not queue:
            queue = self.create({
                'provider_id': provider_id,
            })
        return queue

    @api.model
    def _process_provider_queue(self, provider):
        """Process pending jobs for a specific provider"""
        if isinstance(provider, int):
            provider = self.env['llm.provider'].browse(provider)
        
        queue = self._get_or_create_queue(provider.id)
        
        if not queue.enabled:
            return 0
        
        # Get available slots
        available_slots = queue.max_concurrent_jobs - queue.current_running_jobs
        if available_slots <= 0:
            return 0
        
        # Get pending jobs
        pending_jobs = self.env['llm.generation.job'].search([
            ('provider_id', '=', provider.id),
            ('state', '=', 'queued'),
        ], order='queued_at asc', limit=available_slots)
        
        processed_count = 0
        for job in pending_jobs:
            try:
                job.action_start()
                processed_count += 1
                _logger.info(f"Started generation job {job.id} for provider {provider.name}")
            except Exception as e:
                _logger.error(f"Failed to start generation job {job.id}: {e}")
                job.action_fail(str(e))
        
        if processed_count > 0:
            queue.write({'last_processed_at': fields.Datetime.now()})
        
        return processed_count

    @api.model
    def _process_all_queues(self):
        """Process all enabled queues - called by cron"""
        processed_total = 0
        
        for queue in self.search([('enabled', '=', True)]):
            try:
                processed = self._process_provider_queue(queue.provider_id)
                processed_total += processed
                _logger.debug(f"Processed {processed} jobs for provider {queue.provider_id.name}")
            except Exception as e:
                _logger.error(f"Error processing queue for provider {queue.provider_id.name}: {e}")
        
        if processed_total > 0:
            _logger.info(f"Total jobs processed across all queues: {processed_total}")
        
        return processed_total

    @api.model
    def _check_job_statuses(self):
        """Check status of all running jobs - called by cron"""
        running_jobs = self.env['llm.generation.job'].search([
            ('state', '=', 'running'),
            ('external_job_id', '!=', False),
        ])
        
        updated_count = 0
        
        for job in running_jobs:
            try:
                status = job.check_status()
                if status:
                    if status.get('state') == 'completed':
                        # Handle completion
                        if status.get('output_message_id'):
                            job.action_complete(status['output_message_id'])
                        else:
                            job.action_complete()
                        updated_count += 1
                    elif status.get('state') == 'failed':
                        job.action_fail(status.get('error_message'))
                        updated_count += 1
            except Exception as e:
                _logger.error(f"Error checking status for job {job.id}: {e}")
                # Don't fail the job here, let it timeout naturally
        
        if updated_count > 0:
            _logger.info(f"Updated status for {updated_count} running jobs")
        
        return updated_count

    @api.model
    def _auto_retry_failed_jobs(self):
        """Auto-retry failed jobs that are eligible - called by cron"""
        # Auto-retry failed jobs that are eligible
        
        retry_cutoff = fields.Datetime.now() - timedelta(minutes=5)  # Default retry delay
        
        failed_jobs = self.env['llm.generation.job'].search([
            ('state', '=', 'failed'),
            ('completed_at', '<=', retry_cutoff),
            ('retry_count', '<', 3),  # Default max retries
        ])
        
        # Filter by queues that have auto-retry enabled
        auto_retry_queues = self.search([('auto_retry_failed', '=', True)])
        provider_ids = auto_retry_queues.mapped('provider_id').ids
        
        eligible_jobs = failed_jobs.filtered(lambda j: j.provider_id.id in provider_ids)
        
        retried_count = 0
        for job in eligible_jobs:
            if job.can_retry:
                job.action_retry()
                retried_count += 1
        
        if retried_count > 0:
            _logger.info(f"Auto-retried {retried_count} failed jobs")
        
        return retried_count

    def action_view_jobs(self):
        """View all jobs for this provider"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Jobs - {self.provider_id.name}',
            'res_model': 'llm.generation.job',
            'view_mode': 'tree,form',
            'domain': [('provider_id', '=', self.provider_id.id)],
            'context': {'default_provider_id': self.provider_id.id},
        }

    def action_view_queued_jobs(self):
        """View queued jobs for this provider"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Queued Jobs - {self.provider_id.name}',
            'res_model': 'llm.generation.job',
            'view_mode': 'tree,form',
            'domain': [('provider_id', '=', self.provider_id.id), ('state', '=', 'queued')],
            'context': {'default_provider_id': self.provider_id.id},
        }

    def action_view_today_jobs(self):
        """View today's jobs for this provider"""
        self.ensure_one()
        today = fields.Date.today()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Today\'s Jobs - {self.provider_id.name}',
            'res_model': 'llm.generation.job',
            'view_mode': 'tree,form',
            'domain': [('provider_id', '=', self.provider_id.id), ('create_date', '>=', today)],
            'context': {'default_provider_id': self.provider_id.id},
        }

    def get_queue_stats(self):
        """Get comprehensive queue statistics"""
        self.ensure_one()
        
        # Get job counts by state
        job_counts = {}
        for state in ['draft', 'queued', 'running', 'completed', 'failed', 'cancelled']:
            job_counts[state] = self.env['llm.generation.job'].search_count([
                ('provider_id', '=', self.provider_id.id),
                ('state', '=', state),
            ])
        
        # Get recent performance data
        recent_cutoff = fields.Datetime.now() - timedelta(hours=24)
        recent_jobs = self.env['llm.generation.job'].search([
            ('provider_id', '=', self.provider_id.id),
            ('create_date', '>=', recent_cutoff),
        ])
        
        return {
            'queue_id': self.id,
            'provider_name': self.provider_id.name,
            'enabled': self.enabled,
            'max_concurrent_jobs': self.max_concurrent_jobs,
            'queue_health': self.queue_health,
            'job_counts': job_counts,
            'performance': {
                'avg_queue_time': self.avg_queue_time,
                'avg_processing_time': self.avg_processing_time,
                'success_rate': self.success_rate,
                'total_jobs_24h': len(recent_jobs),
            },
            'last_processed_at': self.last_processed_at,
        }
