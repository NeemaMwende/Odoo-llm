import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

def migrate(cr, version):
    """
    Migration to compute llm_role field for existing messages.
    
    Simple migration that just ensures the llm_role field is computed
    for all existing messages. The constraint will automatically handle
    any integrity issues since it only validates when llm_role is not False.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    _logger.info("Starting LLM role field computation migration...")
    
    try:
        # Find all messages in LLM threads
        llm_thread_messages = env['mail.message'].search([
            ('model', '=', 'llm.thread')
        ])
        
        if not llm_thread_messages:
            _logger.info("No LLM thread messages found, skipping migration")
            return
        
        _logger.info(f"Found {len(llm_thread_messages)} messages in LLM threads")
        
        # Force computation of llm_role field - this will populate the stored field
        llm_thread_messages._compute_llm_role()
        
        # Count results
        llm_messages = llm_thread_messages.filtered(lambda m: m.llm_role)
        _logger.info(f"Computed llm_role for {len(llm_messages)} LLM messages")
        
        # Clear caches
        env['mail.message'].get_llm_roles.clear_cache(env['mail.message'])
        
        _logger.info("LLM role field computation migration completed successfully")
        
    except Exception as e:
        _logger.error(f"Error during LLM role migration: {str(e)}")
        raise
