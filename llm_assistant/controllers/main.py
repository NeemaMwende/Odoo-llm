from odoo import http
from odoo.http import request


class LLMAssistantController(http.Controller):
    @http.route("/llm/thread/set_assistant", type="json", auth="user")
    def set_thread_assistant(self, thread_id, assistant_id=False):
        """Set the assistant for a thread and return thread-specific evaluated default values

        Args:
            thread_id (int): ID of the thread to update
            assistant_id (int, optional): ID of the assistant to set, or False to clear

        Returns:
            dict: Result of the operation with evaluated default values if successful
        """
        thread = request.env["llm.thread"].browse(int(thread_id))
        if not thread.exists():
            return {"success": False, "error": "Thread not found"}

        result = thread.set_assistant(assistant_id)
        
        # Return basic result if no assistant was set or operation failed
        if not assistant_id or not result:
            return {
                "success": bool(result),
                "thread_id": thread_id,
                "assistant_id": assistant_id,
            }
        
        # Get the assistant with thread-specific evaluated default values
        assistant = request.env["llm.assistant"].browse(int(assistant_id))
        if assistant.exists():
            # Get thread-specific evaluated default values
            evaluated_values = assistant.get_evaluated_default_values(thread)
            
            return {
                "success": True,
                "thread_id": thread_id,
                "assistant_id": assistant_id,
                "default_values": assistant.default_values,
                "evaluated_default_values": evaluated_values,
            }
        
        return {
            "success": bool(result),
            "thread_id": thread_id,
            "assistant_id": assistant_id,
        }
