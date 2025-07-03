import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

def migrate(cr, version):
    """
    Migration to optimize LLM message handling using stored llm_role field.
    
    This migration:
    1. Triggers computation of llm_role for all existing messages
    2. Ensures message integrity and proper role assignment
    3. Clears caches to ensure fresh data
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    _logger.info("Starting LLM role-based optimization migration...")
    
    try:
        # Clear ORM cache to ensure fresh data
        env.registry.clear_cache()
        
        # Find all messages that might be LLM messages
        # We'll let the compute method determine which are actually LLM messages
        all_messages = env['mail.message'].search([
            ('model', '=', 'llm.thread')
        ])
        
        if not all_messages:
            _logger.info("No LLM thread messages found, skipping migration")
            return
        
        _logger.info(f"Found {len(all_messages)} messages in LLM threads")
        
        # Force computation of llm_role field for all messages
        # This will populate the stored field based on subtype_id
        all_messages._compute_llm_role()
        
        # Count how many messages now have llm_role set
        llm_messages = all_messages.filtered(lambda m: m.llm_role)
        _logger.info(f"Computed llm_role for {len(llm_messages)} LLM messages")
        
        # Validate tool messages
        tool_messages = llm_messages.filtered(lambda m: m.llm_role == 'tool')
        invalid_tool_messages = tool_messages.filtered(lambda m: m.tool_call_id and m.llm_role != 'tool')
        
        if invalid_tool_messages:
            _logger.warning(f"Found {len(invalid_tool_messages)} tool messages with invalid tool_call_id")
        
        # Clear method caches to ensure fresh role data
        env['mail.message'].get_llm_roles.clear_cache(env['mail.message'])
        
        _logger.info("LLM role-based optimization migration completed successfully")
        
    except Exception as e:
        _logger.error(f"Error during LLM role-based optimization migration: {str(e)}")
        raise
