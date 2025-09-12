import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LLMThread(models.Model):
    _inherit = "llm.thread"

    external_id = fields.Char(
        string="External ID",
        help="External system identifier (e.g., Letta agent ID)",
        index=True,
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
                try:
                    agent_id = self._create_letta_agent(thread)
                    if agent_id:
                        thread.external_id = agent_id
                        _logger.info(
                            f"Created Letta agent {agent_id} for new thread {thread.id}"
                        )
                except Exception as e:
                    _logger.error(
                        f"Failed to create Letta agent for thread {thread.id}: {e}"
                    )
                    # Don't fail thread creation, just log the error

        return threads

    def write(self, vals):
        """Override to handle model/provider changes that require agent recreation."""
        result = super().write(vals)

        # Check if provider or model changed for Letta threads
        if "provider_id" in vals or "model_id" in vals:
            for thread in self:
                if thread.provider_id.service == "letta":
                    try:
                        # Recreate agent with new configuration
                        old_agent_id = thread.external_id
                        new_agent_id = self._create_letta_agent(thread)

                        if new_agent_id:
                            thread.external_id = new_agent_id
                            _logger.info(
                                f"Recreated Letta agent for thread {thread.id}: {old_agent_id} → {new_agent_id}"
                            )

                            # TODO: Optionally delete old agent from Letta
                            # self._delete_letta_agent(old_agent_id)

                    except Exception as e:
                        _logger.error(
                            f"Failed to recreate Letta agent for thread {thread.id}: {e}"
                        )

        # Check if tool_ids changed for Letta threads
        if "tool_ids" in vals:
            for thread in self:
                if thread.provider_id.service == "letta" and thread.external_id:
                    try:
                        # Sync agent tools with updated tool_ids
                        thread.provider_id.letta_sync_agent_tools(
                            thread.external_id, thread.tool_ids
                        )
                        _logger.info(
                            f"Synced tools for Letta agent {thread.external_id}"
                        )
                    except Exception as e:
                        _logger.error(
                            f"Failed to sync tools for Letta agent {thread.external_id}: {e}"
                        )

        return result

    def _create_letta_agent(self, thread):
        """Create a Letta agent for the given thread.

        Args:
            thread: llm.thread record

        Returns:
            str: Agent ID if successful, None otherwise
        """
        if not thread.model_id:
            _logger.warning(
                f"Cannot create Letta agent for thread {thread.id}: no model selected"
            )
            return None

        try:
            # Get Letta client from provider
            client = thread.provider_id.letta_get_client()

            # Build agent configuration
            agent_config = self._build_agent_config(thread)

            # Create agent
            agent = client.agents.create(**agent_config)
            return agent.id

        except Exception as e:
            _logger.error(f"Error creating Letta agent: {e}")
            return None

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
            try:
                context = thread.get_context()
                system_content = thread.assistant_id.prompt_id.render_content(context)
                if system_content:
                    memory_blocks[0] = {"label": "persona", "value": system_content}
            except Exception as e:
                _logger.warning(f"Failed to render assistant prompt: {e}")

        # Use the actual selected model (no hardcoding!)
        model_name = thread.model_id.name

        # Ensure provider prefix for compatibility
        if "/" not in model_name:
            # Default to openai prefix if no provider specified
            model_name = f"openai/{model_name}"

        # Create or get API key for MCP authentication
        
        api_key = self._ensure_user_api_key(thread.user_id)
        _logger.info(f"Created/found API key for user {thread.user_id.login}")
        

        # Build full configuration
        agent_config = {
            "name": f"thread_{thread.id}",
            "model": model_name,
            "embedding": "openai/text-embedding-3-small",  # Could make this configurable
            "memory_blocks": memory_blocks,
            "tools": thread.provider_id.letta_format_tools([]),  # Basic tools for now
        }

        # Add environment variables for MCP authentication
        if api_key:
            agent_config["tool_exec_environment_variables"] = {
                "ODOO_API_KEY": api_key,
            }

        return agent_config

    def _ensure_user_api_key(self, user):
        """Create long-lived API key for MCP client authentication if it doesn't exist"""
        # Look for existing MCP API key for this user
        existing_key = self.env['res.users.apikeys'].sudo().search([
            ('user_id', '=', user.id),
            ('name', '=', 'MCP Integration Key')
        ], limit=1)
        
        if existing_key:
            _logger.info(f"Using existing API key for user {user.login}")
            return existing_key.key
        
        # Get user's maximum allowed duration (36500 days for LLM managers, 90 days for regular users)
        # TODO: Review if 36500 days (100 years) max expiration is appropriate for API keys
        # Consider security implications of extremely long-lived API keys
        from datetime import datetime, timedelta
        max_duration = max(group.api_key_duration for group in user.groups_id) or 1.0
        expiration = datetime.now() + timedelta(days=max_duration)
        
        _logger.info(f"Creating API key for user {user.login} with {max_duration} days duration")
        
        try:
            # Create new API key with proper expiration date
            key = self.env['res.users.apikeys'].sudo().with_user(user)._generate(
                scope=None,                 # Global key for RPC/HTTP usage
                name='MCP Integration Key', # Description
                expiration_date=expiration  # Respects user group permissions
            )
            
            _logger.info(f"Created new MCP API key for user {user.login}")
            return key
        except Exception as e:
            _logger.error(f"Failed to create API key: {e}")
            return None

    def get_letta_agent_id(self):
        """Get the Letta agent ID for this thread.

        Returns:
            str: Agent ID if available, None otherwise
        """
        self.ensure_one()

        if self.provider_id.service != "letta":
            return None

        return self.external_id

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
            try:
                client = self.provider_id.letta_get_client()
                client.agents.retrieve(agent_id=agent_id)
                return agent_id
            except Exception as e:
                _logger.warning(f"Agent {agent_id} not found in Letta, recreating: {e}")
                agent_id = None

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
