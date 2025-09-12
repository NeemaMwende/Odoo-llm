"""
MCP Exception Classes

Custom exception hierarchy for consistent error handling across MCP components.
"""

from mcp.types import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
)


class MCPError(Exception):
    """Base MCP exception with JSON-RPC error code"""
    
    def __init__(self, message: str, code: int = INTERNAL_ERROR):
        super().__init__(message)
        self.code = code
        self.message = message


class MCPParseError(MCPError):
    """JSON parsing error"""
    
    def __init__(self, message: str = "Parse error"):
        super().__init__(message, PARSE_ERROR)


class MCPInvalidRequestError(MCPError):
    """Invalid JSON-RPC request structure"""
    
    def __init__(self, message: str = "Invalid JSON-RPC request"):
        super().__init__(message, INVALID_REQUEST)


class MCPMethodNotFoundError(MCPError):
    """JSON-RPC method not found"""
    
    def __init__(self, method: str):
        message = f"Method not found: {method}"
        super().__init__(message, METHOD_NOT_FOUND)


class MCPInvalidParamsError(MCPError):
    """Invalid method parameters"""
    
    def __init__(self, message: str = "Invalid parameters"):
        super().__init__(message, INVALID_PARAMS)


class MCPAccessDeniedError(MCPError):
    """Access denied to resource - maps to INVALID_PARAMS per MCP spec"""
    
    def __init__(self, message: str = "Access denied"):
        super().__init__(message, INVALID_PARAMS)


class MCPAuthenticationError(MCPError):
    """Authentication failure - maps to INVALID_PARAMS per MCP spec"""
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, INVALID_PARAMS)


class MCPToolNotFoundError(MCPError):
    """Tool not found"""
    
    def __init__(self, tool_name: str):
        message = f"Tool not found: {tool_name}"
        super().__init__(message, INVALID_PARAMS)


class MCPToolAccessDeniedError(MCPError):
    """Tool access denied - maps to INVALID_PARAMS per MCP spec"""
    
    def __init__(self, tool_name: str):
        message = f"Access denied to tool: {tool_name}"
        super().__init__(message, INVALID_PARAMS)