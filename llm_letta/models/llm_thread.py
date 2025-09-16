import logging
from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, RedirectWarning

_logger = logging.getLogger(__name__)


class LLMThread(models.Model):
    _inherit = "llm.thread"

    external_id = fields.Char(
        string="External ID",
        help="External system identifier (e.g., Letta agent ID)",
        index=True,
    )
    metadata = fields.Json(
        string="Metadata",
        help="Store additional data like API keys for Letta agents",
    )
    is_letta_provider = fields.Boolean(
        string="Is Letta Provider",
        compute="_compute_is_letta_provider",
        store=False,
    )

    @api.depends("provider_id.service")
    def _compute_is_letta_provider(self):
        """Compute if thread uses Letta provider"""
        for thread in self:
            thread.is_letta_provider = (
                thread.provider_id and thread.provider_id.service == "letta"
            )

    def _prepare_chat_kwargs(self, message_history, use_streaming):
        """Override to add thread context for Letta provider."""
        chat_kwargs = super()._prepare_chat_kwargs(message_history, use_streaming)

        # Add thread context for Letta
        if self.provider_id.service == "letta":
            chat_kwargs["thread_context"] = {"id": self.id}

        return chat_kwargs

    @api.model_create_multi
    def create(self, vals_list):
        """Override to create Letta agents when thread is created with Letta provider."""
        threads = super().create(vals_list)

        for thread in threads:
            if thread.provider_id.service == "letta":
                agent_id = self._create_letta_agent(thread)
                if agent_id:
                    thread.external_id = agent_id

        return threads

    def write(self, vals):
        """Override to handle model/provider changes that require agent recreation."""
        # Cleanup if switching away from Letta provider
        if "provider_id" in vals:
            for thread in self:
                # Check if we're switching away from Letta
                if thread.provider_id.service == "letta":
                    new_provider = self.env['llm.provider'].browse(vals['provider_id'])
                    if new_provider.service != "letta":
                        self._cleanup_letta_resources(thread)

        result = super().write(vals)

        # Check if provider or model changed for Letta threads
        if "provider_id" in vals or "model_id" in vals:
            for thread in self:
                if thread.provider_id.service == "letta":
                    if thread.external_id:
                        # Agent exists - just update its configuration
                        try:
                            client = thread.provider_id.letta_get_client()
                            client.agents.modify(
                                agent_id=thread.external_id,
                                model=thread.model_id.name
                            )
                            _logger.info(
                                f"Updated Letta agent {thread.external_id} with new model: {thread.model_id.name}"
                            )
                        except Exception as e:
                            _logger.error(f"Failed to update Letta agent {thread.external_id}: {e}")
                            # If update fails, try to recreate the agent
                            agent_id = self._create_letta_agent(thread)
                            if agent_id:
                                thread.external_id = agent_id
                                _logger.info(f"Recreated Letta agent as fallback: {agent_id}")
                    else:
                        # No agent exists yet - create one
                        agent_id = self._create_letta_agent(thread)
                        if agent_id:
                            thread.external_id = agent_id
                            _logger.info(f"Created new Letta agent: {agent_id}")

        # Check if tool_ids changed for Letta threads
        if "tool_ids" in vals:
            for thread in self:
                if thread.provider_id.service == "letta" and thread.external_id:
                    # Sync agent tools with updated tool_ids
                    thread.provider_id.letta_sync_agent_tools(
                        thread.external_id, thread.tool_ids
                    )
                    _logger.info(
                        f"Synced tools for Letta agent {thread.external_id}"
                    )

        return result

    def unlink(self):
        """Clean up Letta resources when thread is deleted"""
        for thread in self:
            if thread.provider_id.service == "letta":
                self._cleanup_letta_resources(thread)
        return super().unlink()

    def _cleanup_letta_resources(self, thread):
        """Clean up API keys and Letta agent when thread is deleted or provider changed"""
        # Delete API key if exists
        if thread.metadata and thread.metadata.get('api_key_id'):
            try:
                api_key_record = self.env['res.users.apikeys'].sudo().browse(thread.metadata['api_key_id'])
                if api_key_record.exists():
                    api_key_record.unlink()
                    _logger.info(f"Deleted API key for thread {thread.id}")
            except Exception as e:
                _logger.warning(f"Failed to delete API key for thread {thread.id}: {e}")

        # Delete Letta agent if exists
        if thread.external_id:
            try:
                client = thread.provider_id.letta_get_client()
                client.agents.delete(thread.external_id)
                _logger.info(f"Deleted Letta agent {thread.external_id}")
            except Exception as e:
                _logger.warning(f"Failed to delete Letta agent {thread.external_id}: {e}")

        # Clear metadata
        thread.metadata = {}
        thread.external_id = False

    def _create_letta_agent(self, thread):
        """Create a Letta agent for the given thread.

        Args:
            thread: llm.thread record

        Returns:
            str: Agent ID if successful, None otherwise
        """
        if not thread.model_id:
            return None
        
        # Get Letta client from provider
        client = thread.provider_id.letta_get_client()
        # Build agent configuration
        agent_config = self._build_agent_config(thread)
        # Create agent
        agent = client.agents.create(**agent_config)
        return agent.id

        

    def _build_agent_config(self, thread):
        """Build agent configuration from thread context.

        Args:
            thread: llm.thread record

        Returns:
            dict: Agent configuration for Letta API
        """
        user_name = thread.user_id.name or "User"

        # Build memory blocks from thread context
        memory_blocks = [
            {"label": "persona", "value": "I am a helpful AI assistant."},
            {"label": "human", "value": f"The human's name is {user_name}."},
        ]

        # Add assistant-specific context if available
        if thread.assistant_id and thread.assistant_id.prompt_id:
            context = thread.get_context()
            system_content = thread.assistant_id.prompt_id.render_content(context)
            if system_content:
                memory_blocks[0] = {"label": "persona", "value": system_content}

        # Use the actual selected model (should already include provider prefix)
        model_name = thread.model_id.name

        # Get or create API key for MCP authentication
        api_key = self._ensure_api_key_for_agent(thread)
        
        # Build full configuration
        agent_config = {
            "name": f"thread_{thread.id}",
            "model": model_name,
            "embedding": "openai/text-embedding-3-small",  # TODO: Make this configurable via provider settings
            "memory_blocks": memory_blocks,
            "tools": thread.provider_id.letta_format_tools([]),  # Basic tools for now
        }

        agent_config["tool_exec_environment_variables"] = {
            "ODOO_API_KEY": api_key,
        }

        return agent_config

    def _ensure_api_key_for_agent(self, thread):
        """Get or create API key for Letta agent MCP authentication"""
        # Check if we already have an API key in metadata
        if thread.metadata and thread.metadata.get('api_key'):
            return thread.metadata['api_key']

        # Generate new API key with scope 'rpc'
        # Get maximum allowed duration from user's groups
        max_duration = max(
            (group.api_key_duration for group in thread.user_id.groups_id if group.api_key_duration),
            default=90.0
        )

        # Calculate expiration date
        expiration_date = datetime.now() + timedelta(days=max_duration)
        user = thread.user_id
        # Generate API key programmatically
        api_key = self.env['res.users.apikeys'].sudo().with_user(user)._generate(
            scope='rpc',
            name=f"Letta Agent - Thread {thread.id}",
            expiration_date=expiration_date
        )

        # Find the created API key record to get its ID
        api_key_record = self.env['res.users.apikeys'].sudo().search([
            ('user_id', '=', thread.user_id.id),
            ('name', '=', f"Letta Agent - Thread {thread.id}"),
        ], limit=1, order='create_date desc')

        # Store API key and its ID in metadata
        thread.metadata = {
            'api_key': api_key,
            'api_key_id': api_key_record.id if api_key_record else None
        }

        _logger.info(f"Generated new API key for Letta agent thread {thread.id}")
        return api_key

    def get_letta_agent_id(self):
        """Get the Letta agent ID for this thread.

        Returns:
            str: Agent ID if available, None otherwise
        """
        self.ensure_one()

        if self.provider_id.service == "letta":
            return self.external_id
        else:
            return None

        

    def ensure_letta_agent(self):
        """Ensure this thread has a valid Letta agent.

        Returns:
            str: Agent ID

        Raises:
            UserError: If agent cannot be created or verified
        """
        self.ensure_one()

        if self.provider_id.service != "letta":
            raise UserError("This thread is not configured for Letta provider")

        agent_id = self.external_id

        # Verify agent exists in Letta
        if agent_id:
            client = self.provider_id.letta_get_client()
            client.agents.retrieve(agent_id=agent_id)
            return agent_id
            

        # Create new agent if needed
        if not agent_id:
            agent_id = self._create_letta_agent(self)
            if agent_id:
                self.external_id = agent_id
            else:
                raise UserError("Failed to create Letta agent for this thread")

        return agent_id

    def sync_letta_tools(self):
        """Manual tool synchronization for Letta agent"""
        self.ensure_one()

        if self.provider_id.service != "letta":
            raise UserError("This action is only available for Letta threads")

        if not self.external_id:
            raise UserError("No Letta agent found for this thread")

        try:
            self.provider_id.letta_sync_agent_tools(self.external_id, self.tool_ids)
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "message": f"Tools synchronized successfully for agent {self.external_id}",
                    "type": "success",
                },
            }
        except Exception as e:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "message": f"Failed to sync tools: {str(e)}",
                    "type": "danger",
                },
            }
