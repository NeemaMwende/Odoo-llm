import logging

from odoo import http
from odoo.http import request


class LLMAssistantController(http.Controller):
    def _get_thread_and_assistant(self, thread_id, assistant_id=False):
        """Helper method to get thread and assistant records
        
        Args:
            thread_id (int): ID of the thread
            assistant_id (int, optional): ID of the assistant, or False to clear
            
        Returns:
            tuple: (thread, assistant, error_response)
                  If successful, error_response will be None
                  If error, thread and/or assistant will be None
        """
        thread = request.env["llm.thread"].browse(int(thread_id))
        if not thread.exists():
            return None, None, {"success": False, "error": "Thread not found"}
            
        # If no assistant_id, return just the thread
        if not assistant_id:
            return thread, None, None
            
        assistant = request.env["llm.assistant"].browse(int(assistant_id))
        if not assistant.exists():
            return thread, None, {"success": False, "error": "Assistant not found"}
            
        return thread, assistant, None
        
    def _get_assistant_values(self, thread, assistant, include_prompt=True):
        """Get thread-specific evaluated default values for an assistant
        
        Args:
            thread (llm.thread): Thread record
            assistant (llm.assistant): Assistant record
            include_prompt (bool): Whether to include prompt data
            
        Returns:
            dict: Result with evaluated default values and prompt data
        """
        # Get thread-specific evaluated default values
        evaluated_values = assistant.get_evaluated_default_values(thread)
        
        result = {
            "success": True,
            "thread_id": thread.id,
            "assistant_id": assistant.id,
            "default_values": assistant.default_values,
            "evaluated_default_values": evaluated_values,
        }
        
        # Get the prompt details if requested
        if include_prompt and assistant.prompt_id:
            prompt = assistant.prompt_id
            result["prompt"] = {
                "id": prompt.id,
                "name": prompt.name,
                "input_schema_json": prompt.input_schema_json,
            }
        
        return result
    
    @http.route("/llm/thread/set_assistant", type="json", auth="user")
    def set_thread_assistant(self, thread_id, assistant_id=False):
        """Set the assistant for a thread and return thread-specific evaluated default values

        Args:
            thread_id (int): ID of the thread to update
            assistant_id (int, optional): ID of the assistant to set, or False to clear

        Returns:
            dict: Result of the operation with evaluated default values if successful
        """
        # Get thread and assistant
        thread, assistant, error = self._get_thread_and_assistant(thread_id, assistant_id)
        if error:
            return error
            
        # Set the assistant on the thread
        result = thread.set_assistant(assistant_id if assistant else False)
        
        # Return basic result if no assistant was set or operation failed
        if not assistant or not result:
            return {
                "success": bool(result),
                "thread_id": thread_id,
                "assistant_id": assistant_id if assistant else False,
            }
        
        # Get assistant values with the thread context
        return self._get_assistant_values(thread, assistant)
        
    @http.route("/llm/thread/get_assistant_values", type="json", auth="user")
    def get_thread_assistant_values(self, thread_id, assistant_id):
        """Get thread-specific evaluated default values for an assistant

        Args:
            thread_id (int): ID of the thread
            assistant_id (int): ID of the assistant

        Returns:
            dict: Result with evaluated default values
        """
        # Get thread and assistant
        thread, assistant, error = self._get_thread_and_assistant(thread_id, assistant_id)
        if error:
            return error
            
        # Get assistant values with the thread context
        return self._get_assistant_values(thread, assistant)
