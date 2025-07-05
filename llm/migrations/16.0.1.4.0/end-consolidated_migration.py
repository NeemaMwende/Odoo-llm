import logging
from collections import defaultdict

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Consolidated migration for LLM module:
    1. Migrate message subtypes from old module to new module
    2. Find xmlids of old subtypes and batch update messages
    3. Compute llm_role field for all messages using proper batch processing
    4. Trigger role computation per message ID for proper indexing
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    _logger.info("Starting consolidated LLM migration...")

    # Step 1: Migrate message subtypes
    _migrate_message_subtypes(env)
    
    # Step 2: Batch process messages and compute roles
    _batch_process_messages_and_compute_roles(env)
    
    # Step 3: Clean up old references
    _cleanup_old_references(env)
    
    _logger.info("Consolidated LLM migration completed successfully")


def _migrate_message_subtypes(env):
    """Migrate message subtypes from old module to new module."""
    _logger.info("Starting message subtype migration...")
    
    # Mapping of old XML IDs to new XML IDs
    subtype_mapping = {
        "llm_mail_message_subtypes.mt_llm_user": "llm.mt_user",
        "llm_mail_message_subtypes.mt_llm_assistant": "llm.mt_assistant",
        "llm_mail_message_subtypes.mt_llm_tool_result": "llm.mt_tool",
        "llm_mail_message_subtypes.mt_llm_system": "llm.mt_system",
    }
    
    migrated_count = 0
    
    for old_xmlid, new_xmlid in subtype_mapping.items():
        try:
            # Get the old subtype ID
            old_subtype_id = env["ir.model.data"]._xmlid_to_res_id(
                old_xmlid, raise_if_not_found=False
            )
            if not old_subtype_id:
                _logger.info(f"Old subtype {old_xmlid} not found, skipping")
                continue

            # Get the new subtype ID
            new_subtype_id = env["ir.model.data"]._xmlid_to_res_id(
                new_xmlid, raise_if_not_found=False
            )
            if not new_subtype_id:
                _logger.warning(f"New subtype {new_xmlid} not found, skipping")
                continue

            # Find messages using the old subtype
            messages = env["mail.message"].search([("subtype_id", "=", old_subtype_id)])

            if messages:
                _logger.info(
                    f"Migrating {len(messages)} messages from {old_xmlid} to {new_xmlid}"
                )

                # Update messages to use new subtype
                messages.write({"subtype_id": new_subtype_id})
                migrated_count += len(messages)

                _logger.info(f"Successfully migrated {len(messages)} messages")
            else:
                _logger.info(f"No messages found for subtype {old_xmlid}")

        except Exception as e:
            _logger.error(f"Error migrating subtype {old_xmlid}: {str(e)}")
            continue

    _logger.info(f"Message subtype migration completed. Total messages migrated: {migrated_count}")


def _batch_process_messages_and_compute_roles(env):
    """
    Batch process messages and compute roles efficiently.
    
    This approach:
    1. Gets all xmlids for LLM subtypes at once
    2. Batch searches for messages by subtype_id groups
    3. Writes per message ID to properly trigger role computation
    """
    _logger.info("Starting batch role computation...")
    
    # Get all LLM xmlids and their corresponding subtype IDs
    llm_xmlids = [
        "llm.mt_tool",
        "llm.mt_user", 
        "llm.mt_assistant",
        "llm.mt_system",
    ]
    
    # Build mapping of subtype_id to role name
    subtype_id_to_role = {}
    valid_subtype_ids = []
    
    for xmlid in llm_xmlids:
        try:
            subtype_id = env["ir.model.data"]._xmlid_to_res_id(
                xmlid, raise_if_not_found=False
            )
            if subtype_id:
                # Extract role from xmlid (e.g., 'user' from 'llm.mt_user')
                role = xmlid.split(".")[-1][3:]  # Remove 'mt_' prefix
                subtype_id_to_role[subtype_id] = role
                valid_subtype_ids.append(subtype_id)
                _logger.info(f"Found LLM subtype: {xmlid} -> ID {subtype_id} -> role '{role}'")
            else:
                _logger.warning(f"Could not find subtype ID for {xmlid}")
        except Exception as e:
            _logger.error(f"Error processing xmlid {xmlid}: {str(e)}")
            continue
    
    if not valid_subtype_ids:
        _logger.warning("No valid LLM subtype IDs found, skipping role computation")
        return
    
    # Find all messages that use LLM subtypes
    _logger.info(f"Searching for messages with LLM subtypes: {valid_subtype_ids}")
    
    llm_messages = env["mail.message"].search([
        ("subtype_id", "in", valid_subtype_ids)
    ])
    
    if not llm_messages:
        _logger.info("No LLM messages found, skipping role computation")
        return
    
    _logger.info(f"Found {len(llm_messages)} LLM messages to process")
    
    # Group messages by subtype_id for efficient processing
    messages_by_subtype = defaultdict(list)
    for message in llm_messages:
        messages_by_subtype[message.subtype_id.id].append(message)
    
    # Process each subtype group
    total_processed = 0
    
    for subtype_id, messages in messages_by_subtype.items():
        role = subtype_id_to_role.get(subtype_id)
        if not role:
            _logger.warning(f"No role found for subtype_id {subtype_id}, skipping")
            continue
            
        _logger.info(f"Processing {len(messages)} messages for role '{role}'")
        
        # Process messages in batches to avoid memory issues
        batch_size = 100
        for i in range(0, len(messages), batch_size):
            batch = messages[i:i + batch_size]
            
            # Write each message individually to trigger proper role computation
            for message in batch:
                try:
                    # This will trigger the compute method and update the stored field
                    message.write({"subtype_id": message.subtype_id.id})
                    total_processed += 1
                except Exception as e:
                    _logger.error(f"Error updating message {message.id}: {str(e)}")
                    continue
            
            # Log progress for large batches
            if len(messages) > batch_size:
                _logger.info(f"Processed {min(i + batch_size, len(messages))}/{len(messages)} messages for role '{role}'")
    
    _logger.info(f"Role computation completed. Total messages processed: {total_processed}")
    
    # Clear caches to ensure fresh data
    try:
        env["mail.message"].get_llm_roles.clear_cache(env["mail.message"])
        _logger.info("Cleared LLM role cache")
    except Exception as e:
        _logger.warning(f"Could not clear cache: {str(e)}")
    
    # Verify the computation worked
    _verify_role_computation(env, llm_messages)


def _verify_role_computation(env, llm_messages):
    """Verify that role computation worked correctly."""
    _logger.info("Verifying role computation...")
    
    # Refresh the records to get updated computed values
    llm_messages.invalidate_recordset()
    
    # Count messages by role
    role_counts = defaultdict(int)
    messages_without_role = 0
    
    for message in llm_messages:
        if message.llm_role:
            role_counts[message.llm_role] += 1
        else:
            messages_without_role += 1
    
    _logger.info("Role computation verification results:")
    for role, count in role_counts.items():
        _logger.info(f"  {role}: {count} messages")
    
    if messages_without_role > 0:
        _logger.warning(f"  {messages_without_role} messages still without role")
    
    total_with_role = sum(role_counts.values())
    _logger.info(f"Total messages with computed roles: {total_with_role}/{len(llm_messages)}")


def _cleanup_old_references(env):
    """Clean up old XML ID references."""
    _logger.info("Cleaning up old references...")
    
    try:
        # Remove old XML ID references from llm_mail_message_subtypes module
        old_refs = env["ir.model.data"].search([
            ("name", "like", "mt_llm_%"),
            ("module", "=", "llm_mail_message_subtypes")
        ])
        
        if old_refs:
            _logger.info(f"Removing {len(old_refs)} old XML ID references")
            old_refs.unlink()
        else:
            _logger.info("No old XML ID references to clean up")
            
    except Exception as e:
        _logger.warning(f"Could not clean up old XML ID references: {str(e)}")
    
    _logger.info("Cleanup completed")
