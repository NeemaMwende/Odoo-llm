"""
MCP Transport Handler

Handles HTTP transport and SSE streaming following MCP streamable_http specification.
"""

import asyncio
import logging
import time
from typing import Optional

from mcp.server.streamable_http import (
    CONTENT_TYPE_JSON,
    CONTENT_TYPE_SSE,
    MCP_SESSION_ID_HEADER,
)
from mcp.types import (
    INTERNAL_ERROR,
    METHOD_NOT_FOUND,
    ErrorData,
    JSONRPCError,
    JSONRPCResponse,
)

from odoo import http
from odoo.http import request

from .mcp_exceptions import MCPError

_logger = logging.getLogger(__name__)

# HTTP status codes
HTTP_NO_CONTENT = 204
HTTP_OK = 200


class MCPTransport:
    """
    Handles MCP HTTP transport including SSE streaming.

    Follows MCP streamable_http specification for proper transport handling.
    """

    def __init__(self, session_manager, validator, request_handler):
        self.session_manager = session_manager
        self.validator = validator
        self.request_handler = request_handler

    def ensure_valid_id(self, request_id: Optional[any]) -> int:
        """
        Ensure we have a valid JSON-RPC ID.

        Uses the original request ID if present, otherwise generates
        a timestamp-based ID for better uniqueness.
        """
        if request_id is not None:
            return request_id
        return int(time.time() * 1000)  # Milliseconds since epoch

    def build_json_rpc_response(
        self, request_id: Optional[any], result: dict = None, error: dict = None
    ):
        """Build a JSON-RPC 2.0 response using proper MCP SDK Pydantic models"""
        if error:
            # For error responses, use JSONRPCError with ErrorData
            error_data = ErrorData(
                code=error.get("code", INTERNAL_ERROR),
                message=error.get("message", "Internal error"),
                data=error.get("data"),
            )
            response = JSONRPCError(
                jsonrpc="2.0",
                id=self.ensure_valid_id(request_id),
                error=error_data,
            )
        else:
            # For success responses, use JSONRPCResponse
            response = JSONRPCResponse(
                jsonrpc="2.0",
                id=self.ensure_valid_id(request_id),
                result=result or {},
            )

        return response

    def json_rpc_http_response(
        self, request_id: Optional[any], result: dict = None, error: dict = None
    ):
        """Build and return a JSON-RPC HTTP response using MCP SDK Pydantic model"""
        response_model = self.build_json_rpc_response(request_id, result, error)
        return http.Response(
            response_model.model_dump_json(),
            headers={"Content-Type": CONTENT_TYPE_JSON},
            status=HTTP_OK,  # JSON-RPC always returns 200 OK, errors are in the response body
        )

    def http_error_response(self, request_id: Optional[any], code: int, message: str):
        """Build a JSON-RPC 2.0 error response"""
        error = {"code": code, "message": message}
        return self.json_rpc_http_response(request_id, error=error)

    def handle_post_request(self):
        """Handle POST requests - JSON-RPC 2.0 messages"""
        _logger.info("POST request handler started")
        try:
            # Validate protocol headers
            _logger.info("Validating accept headers...")
            accept_error = self.validator.validate_accept_headers("POST")
            if accept_error:
                _logger.info(f"Accept header validation failed: {accept_error}")
                return self.http_error_response(None, 406, accept_error)

            _logger.info("Validating content type...")
            content_type_error = self.validator.validate_content_type("POST")
            if content_type_error:
                _logger.info(f"Content type validation failed: {content_type_error}")
                return self.http_error_response(None, 415, content_type_error)

            _logger.info("Getting server config...")
            server_config = self.session_manager.get_server_config()
            _logger.info("Validating protocol version...")
            self.validator.validate_protocol_version(server_config)
            # Protocol version validation is informational only

            # Both stateless and stateful POST requests return JSON responses
            # The difference is only in session tracking (which we handle via session_manager)
            _logger.info("Parsing request...")
            request_data = self.request_handler.parse_request()
            _logger.info(
                f"Parsed request method: {getattr(request_data.root, 'method', 'unknown')}"
            )

            _logger.info("Routing request...")
            result = self.request_handler.route_request(request_data)
            _logger.info(f"Request handler returned: {type(result)}")

            # If result is already an HTTP response (like notifications), return it
            if isinstance(result, http.Response):
                _logger.info("Result is already HTTP response, returning directly")
                return result

            # Otherwise, wrap in JSON-RPC response with the original request ID
            request_id = getattr(request_data.root, "id", None)
            _logger.info(f"Using request ID: {request_id}")
            _logger.info("Wrapping result in JSON-RPC response...")
            json_response = self.json_rpc_http_response(request_id, result=result)
            _logger.info("POST request completed successfully")
            return json_response

        except MCPError as e:
            # Handle MCP-specific errors with proper error codes
            _logger.error(f"MCP error: {e.message}")
            return self.http_error_response(None, e.code, e.message)
        except Exception as e:
            # Handle unexpected errors
            _logger.exception(f"Unexpected error in POST request: {e}")
            return self.http_error_response(
                None, INTERNAL_ERROR, f"Internal error: {str(e)}"
            )

    def handle_get_request(self):
        """Handle GET requests - SSE streaming for stateful mode"""
        _logger.info("GET request handler started")

        # Validate protocol headers
        _logger.info("Validating accept headers for GET...")
        accept_error = self.validator.validate_accept_headers("GET")
        if accept_error:
            _logger.info(f"GET accept header validation failed: {accept_error}")
            return self.http_error_response(None, 406, accept_error)

        _logger.info("Getting server config for GET...")
        server_config = self.session_manager.get_server_config()
        _logger.info(f"Server config stateless mode: {server_config.stateless_mode}")
        self.validator.validate_protocol_version(server_config)
        # Protocol version validation is informational only

        if self.session_manager.is_stateless_mode():
            _logger.info("GET request rejected - server in stateless mode")
            return self.http_error_response(
                None, METHOD_NOT_FOUND, "GET not supported in stateless mode"
            )

        _logger.info("Starting SSE stream...")
        return self.handle_sse_stream()

    def handle_delete_request(self):
        """Handle DELETE requests - Session termination"""
        if self.session_manager.is_stateless_mode():
            return self.http_error_response(
                None, METHOD_NOT_FOUND, "DELETE not supported in stateless mode"
            )

        return self.handle_session_delete()

    def handle_sse_stream(self):
        """Handle SSE streaming with resumability support"""
        _logger.info("SSE stream handler started")
        session_id = self.session_manager.get_session_id()
        _logger.info(f"Session ID: {session_id}")

        # Validate session ID format
        if not self.session_manager.validate_session_id_format(session_id):
            _logger.info(f"Invalid session ID format: {session_id}")
            return self.http_error_response(None, 400, "Invalid session ID format")

        # Handle resumability - check for Last-Event-ID header
        last_event_id = request.httprequest.headers.get("last-event-id")
        if last_event_id:
            _logger.info(f"Replaying events from: {last_event_id}")
            return self.replay_events(session_id, last_event_id)

        _logger.info("Creating new SSE stream...")

        def generate():
            try:
                # Send connection established event
                connection_msg = JSONRPCResponse(
                    jsonrpc="2.0",
                    id=0,  # Use 0 for SSE notifications instead of None
                    result={"type": "connected", "timestamp": time.time()},
                )

                yield self.yield_sse_event("connected", connection_msg, session_id)

                # Send a few initial pings then close
                # In real implementation, this would be event-driven
                for ping_count in range(1, 4):  # Send 3 pings then close
                    ping_msg = JSONRPCResponse(
                        jsonrpc="2.0",
                        id=ping_count,  # Use ping count as ID
                        result={
                            "type": "ping",
                            "count": ping_count,
                            "timestamp": time.time(),
                        },
                    )

                    yield self.yield_sse_event("ping", ping_msg, session_id)

                # Send close event
                close_msg = JSONRPCResponse(
                    jsonrpc="2.0",
                    id=99,  # Use 99 for close event
                    result={"type": "stream_closed", "timestamp": time.time()},
                )
                yield self.yield_sse_event("close", close_msg, session_id)

                _logger.info(f"SSE stream completed for session {session_id}")

            except Exception as e:
                _logger.error(f"Error in SSE generator: {e}")

        return http.Response(
            generate(),
            content_type=CONTENT_TYPE_SSE,
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                MCP_SESSION_ID_HEADER: session_id,
            },
        )

    def handle_session_delete(self):
        """Handle session deletion"""
        try:
            session_id = self.session_manager.get_session_id()

            # Log session deletion for protocol compliance
            self.session_manager.log_session_deletion(session_id)

            return http.Response("", status=HTTP_NO_CONTENT)

        except Exception as e:
            _logger.error(f"Error deleting session: {e}")
            return self.http_error_response(
                None, INTERNAL_ERROR, f"Failed to delete session: {str(e)}"
            )

    def run_async_in_sync(self, coro):
        """Helper to run async coroutines in sync context"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def yield_sse_event(
        self, event_type: str, message: JSONRPCResponse, session_id: str
    ):
        """Helper to yield SSE events with optional resumability"""
        if self.session_manager.is_resumability_enabled():
            event_store = self.session_manager.get_event_store()
            event_id = self.run_async_in_sync(
                event_store.store_event(session_id, message)
            )
            return f"event: {event_type}\ndata: {message.model_dump_json()}\nid: {event_id}\n\n"
        else:
            return f"event: {event_type}\ndata: {message.model_dump_json()}\n\n"

    def replay_events(self, session_id: str, last_event_id: str):
        """Replay events after specified event ID for resumability"""
        try:
            event_store = self.session_manager.get_event_store()

            def generate():
                try:
                    # Send reconnection event
                    reconnect_msg = JSONRPCResponse(
                        jsonrpc="2.0",
                        id=0,  # Use 0 for reconnect notification
                        result={"type": "reconnected", "resumed_from": last_event_id},
                    )
                    yield f"event: reconnected\ndata: {reconnect_msg.model_dump_json()}\n\n"

                    # Collect events to replay
                    events_to_replay = []

                    async def replay_callback(event_message):
                        events_to_replay.append(event_message)

                    # Replay missed events using the event store
                    resumed_stream_id = self.run_async_in_sync(
                        event_store.replay_events_after(last_event_id, replay_callback)
                    )

                    # Yield all collected events
                    for event_message in events_to_replay:
                        event_data = event_message.message.model_dump_json()
                        yield f"event: message\ndata: {event_data}\nid: {event_message.event_id}\n\n"

                    if resumed_stream_id:
                        _logger.info(
                            f"Resumed stream {resumed_stream_id} from event {last_event_id}"
                        )

                    # Continue with a few more pings then close
                    for ping_count in range(1, 4):  # Send 3 pings then close
                        ping_msg = JSONRPCResponse(
                            jsonrpc="2.0",
                            id=ping_count,  # Use ping count as ID
                            result={
                                "type": "ping",
                                "count": ping_count,
                                "timestamp": time.time(),
                            },
                        )

                        yield self.yield_sse_event("ping", ping_msg, session_id)

                    # Send close event
                    close_msg = JSONRPCResponse(
                        jsonrpc="2.0",
                        id=99,  # Use 99 for close event
                        result={"type": "stream_closed", "timestamp": time.time()},
                    )
                    yield self.yield_sse_event("close", close_msg, session_id)

                    _logger.info(
                        f"Resumed SSE stream completed for session {session_id}"
                    )

                except Exception as e:
                    _logger.error(f"Error in replay generator: {e}")

            return http.Response(
                generate(),
                content_type=CONTENT_TYPE_SSE,
                headers={
                    "Cache-Control": "no-cache, no-transform",
                    "Connection": "keep-alive",
                    MCP_SESSION_ID_HEADER: session_id,
                },
            )

        except Exception as e:
            _logger.error(f"Failed to replay events: {e}")
            return self.http_error_response(
                None, INTERNAL_ERROR, f"Failed to resume stream: {str(e)}"
            )
