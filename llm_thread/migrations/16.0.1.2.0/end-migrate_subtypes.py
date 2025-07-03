import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

def migrate(cr, version):
    """
    Migrate existing LLM message subtypes from llm_mail_message_subtypes to llm base module.
    
    This migration:
    1. Maps old subtype XML IDs to new ones
    2. Updates existing mail.message records to use new subtypes
    3. Logs the migration progress
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Mapping of old XML IDs to new XML IDs
    subtype_mapping = {
        'llm_mail_message_subtypes.mt_llm_user': 'llm.mt_user',
        'llm_mail_message_subtypes.mt_llm_assistant': 'llm.mt_assistant', 
        'llm_mail_message_subtypes.mt_llm_tool_result': 'llm.mt_tool',
        'llm_mail_message_subtypes.mt_llm_system': 'llm.mt_system',
    }
    
    _logger.info("Starting LLM message subtype migration...")
    
    migrated_count = 0
    
    for old_xmlid, new_xmlid in subtype_mapping.items():
        try:
            # Get the old subtype ID
            old_subtype_id = env['ir.model.data']._xmlid_to_res_id(old_xmlid, raise_if_not_found=False)
            if not old_subtype_id:
                _logger.info(f"Old subtype {old_xmlid} not found, skipping")
                continue
                
            # Get the new subtype ID
            new_subtype_id = env['ir.model.data']._xmlid_to_res_id(new_xmlid, raise_if_not_found=False)
            if not new_subtype_id:
                _logger.warning(f"New subtype {new_xmlid} not found, skipping")
                continue
                
            # Find messages using the old subtype
            messages = env['mail.message'].search([
                ('subtype_id', '=', old_subtype_id)
            ])
            
            if messages:
                _logger.info(f"Migrating {len(messages)} messages from {old_xmlid} to {new_xmlid}")
                
                # Update messages to use new subtype
                messages.write({'subtype_id': new_subtype_id})
                migrated_count += len(messages)
                
                _logger.info(f"Successfully migrated {len(messages)} messages")
            else:
                _logger.info(f"No messages found for subtype {old_xmlid}")
                
        except Exception as e:
            _logger.error(f"Error migrating subtype {old_xmlid}: {str(e)}")
            continue
    
    _logger.info(f"LLM message subtype migration completed. Total messages migrated: {migrated_count}")
    
    # Clean up: Remove old XML ID references if they exist
    try:
        env['ir.model.data'].search([
            ('name', 'like', 'mt_llm_%'),
            ('module', '=', 'llm_mail_message_subtypes')
        ]).unlink()
        _logger.info("Cleaned up old XML ID references")
    except Exception as e:
        _logger.warning(f"Could not clean up old XML ID references: {str(e)}")
