import logging

from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LLMProvider(models.Model):
    _inherit = "llm.provider"

    @api.model
    def _get_available_services(self):
        services = super()._get_available_services()
        return services + [("letta", "Letta")]

    def letta_get_client(self):
        """Get Letta client instance"""
        try:
            from letta_client import Letta
        except ImportError as err:
            raise UserError(
                "Letta client not installed. Please install with: pip install letta-client"
            ) from err

        # Determine if using local or cloud
        if self.api_base and "localhost" in self.api_base:
            # Local server - no auth required
            return Letta(base_url=self.api_base)
        else:
            # Cloud server - requires token and project
            if not self.api_key:
                raise UserError("API key is required for Letta Cloud connection")
            
            # Use api_base as project if provided, otherwise default
            project = "default-project"
            if self.api_base and self.api_base != "https://api.letta.com/v1":
                project = self.api_base
                
            return Letta(token=self.api_key, project=project)

    def letta_models(self, model_id=None):
        """List available models from Letta"""
        client = self.letta_get_client()
        
        try:
            models_response = client.models.list()
            
            # Convert Letta model format to our standard format
            models = []
            for model in models_response:
                model_data = {
                    "name": model.model,
                    "provider": model.provider_name if hasattr(model, 'provider_name') else "letta",
                    "context_window": getattr(model, 'context_window', None),
                    "model_endpoint_type": getattr(model, 'model_endpoint_type', None),
                    "temperature": getattr(model, 'temperature', None),
                    "max_tokens": getattr(model, 'max_tokens', None),
                }
                
                # Filter by specific model if requested
                if model_id and model_data["name"] != model_id:
                    continue
                    
                models.append(model_data)
                
            return models
            
        except Exception as e:
            _logger.error(f"Failed to fetch models from Letta: {str(e)}")
            raise UserError(f"Failed to fetch models from Letta: {str(e)}") from e

    def letta_chat(self, messages, model=None, stream=False, **kwargs):  # pylint: disable=unused-argument
        """Chat completion using Letta agents.
        
        Args:
            messages: List of messages (only latest user message is used)
            model: Model to use (ignored - agent already has model)
            stream: Whether to stream response
            **kwargs: Additional parameters, including thread context
            
        Returns:
            Generator of response chunks if streaming, else complete response
        """
        client = self.letta_get_client()
        
        # Get thread from context
        thread_context = kwargs.get('thread_context', {})
        thread_id = thread_context.get('id')
        
        if not thread_id:
            raise UserError("Thread ID is required for Letta chat")
        
        # Get thread record and ensure it has a Letta agent
        thread_record = self.env['llm.thread'].browse(thread_id)
        if not thread_record.exists():
            raise UserError(f"Thread {thread_id} not found")
            
        agent_id = thread_record.ensure_letta_agent()
        
        # Extract latest user message - Letta agents maintain their own history
        latest_message = messages[-1] if messages else None
        if not latest_message:
            raise UserError("No messages provided")
            
        # Use the standard dispatch to format the message
        formatted_message = self._dispatch("format_message", record=latest_message)
        if not formatted_message or not formatted_message.get('content'):
            raise UserError("Could not format message content")
            
        user_content = formatted_message['content']
            
        try:
            if stream:
                return self._stream_agent_response(client, agent_id, user_content)
            else:
                return self._get_agent_response(client, agent_id, user_content)
                
        except Exception as e:
            _logger.error(f"Letta chat failed for agent {agent_id}: {str(e)}")
            raise UserError(f"Chat failed: {str(e)}") from e

    def letta_embedding(self, texts, model=None):  # pylint: disable=unused-argument
        """Text embedding - not implemented yet"""
        raise NotImplementedError(
            "Letta embedding functionality is not yet implemented. "
            "This provider currently only supports model fetching and chat."
        )

    def letta_generate(self, input_data, model=None, stream=False, **kwargs):  # pylint: disable=unused-argument
        """Content generation - not implemented yet"""
        raise NotImplementedError(
            "Letta generation functionality is not yet implemented. "
            "This provider currently only supports model fetching and chat."
        )

    def letta_format_tools(self, tools):  # pylint: disable=unused-argument
        """Format tools for Letta (basic implementation).
        
        For now, just return basic Letta tools. Custom tool integration
        will be implemented later via MCP server.
        """
        # Return basic Letta built-in tools
        return []

    def letta_format_messages(self, messages, system_prompt=None):  # pylint: disable=unused-argument
        """Format messages for Letta (simplified - agent maintains history).
        
        Note: Letta agents maintain their own conversation history,
        so we only need to return the latest user message.
        """
        if not messages:
            return []
            
        # Return only the latest message - Letta handles conversation state
        latest_message = messages[-1]
        formatted_message = self._dispatch("format_message", record=latest_message)
        return [formatted_message] if formatted_message else []
            
    def _stream_agent_response(self, client, agent_id, user_content):
        """Stream response from Letta agent."""
        try:
            from letta_client.types import MessageCreate
        except ImportError as err:
            raise UserError("letta-client not properly installed") from err
            
        stream = client.agents.messages.create_stream(
            agent_id=agent_id,
            messages=[MessageCreate(role="user", content=user_content)],
            stream_tokens=True
        )
        
        for chunk in stream:
            # Handle different Letta message types
            message_type = getattr(chunk, 'message_type', None)
            
            if message_type == 'assistant_message' and hasattr(chunk, 'content'):
                if chunk.content:
                    yield {"content": chunk.content}
            elif message_type == 'reasoning_message':
                # Skip reasoning messages in basic implementation  
                continue
            elif message_type == 'tool_call_message':
                # Skip tool calls for now
                continue
            elif message_type == 'tool_return_message':
                # Skip tool returns for now
                continue
                
        # Yield final response if no content streamed
        yield {"content": "", "finish_reason": "stop"}
        
    def _get_agent_response(self, client, agent_id, user_content):
        """Get non-streaming response from Letta agent."""
        try:
            from letta_client.types import MessageCreate
        except ImportError as err:
            raise UserError("letta-client not properly installed") from err
            
        # For non-streaming, we'll collect the full response
        response_content = ""
        
        stream = client.agents.messages.create_stream(
            agent_id=agent_id,
            messages=[MessageCreate(role="user", content=user_content)],
            stream_tokens=False  # Even non-streaming uses the stream API
        )
        
        for chunk in stream:
            message_type = getattr(chunk, 'message_type', None)
            if message_type == 'assistant_message' and hasattr(chunk, 'content'):
                if chunk.content:
                    response_content += chunk.content
                    
        return {
            "content": response_content or "I couldn't generate a response.",
            "finish_reason": "stop"
        }