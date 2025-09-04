/** @odoo-module **/

import { Message } from "@mail/core/common/message";
import { patch } from "@web/core/utils/patch";
import { LLMToolMessage } from "../components/llm_tool_message/llm_tool_message";

// Import Message model to patch it  
import { Message as MessageModel } from "@mail/core/common/message_model";

/**
 * Patch Message component to handle LLM-specific message rendering
 * Only affects messages in llm.thread threads
 */
patch(Message, {
    components: { ...Message.components, LLMToolMessage },
});

patch(Message.prototype, {
    /**
     * Check if this message is in an LLM thread
     */
    get isLLMMessage() {
        const result = this.props.message?.model === 'llm.thread';
        if (result) {
            console.log('LLM Message detected:', this.props.message?.id, 'role:', this.llmRole);
        }
        return result;
    },

    /**
     * Get LLM role for this message
     */
    get llmRole() {
        return this.props.message?.llm_role;
    },

    /**
     * Check if message is a tool message
     */
    get isToolMessage() {
        return this.isLLMMessage && this.llmRole === 'tool';
    },

    /**
     * Check if assistant message has tool calls
     */
    get hasToolCalls() {
        return this.isLLMMessage && this.llmRole === 'assistant' && this.props.message?.body_json?.tool_calls?.length > 0;
    },

    /**
     * Add LLM-specific CSS classes
     */
    get className() {
        let className = super.className || "";
        
        if (this.isLLMMessage) {
            className += " o-llm-message";
            
            if (this.llmRole) {
                className += ` o-llm-message-${this.llmRole}`;
            }
            
            // Add streaming class for assistant messages that are still being generated
            if (this.llmRole === 'assistant' && this.props.message?.isPending) {
                className += " o-llm-message-streaming";
            }
        }
        
        return className;
    },


});

/**
 * Patch Message model to handle LLM-specific isEmpty computation
 */
patch(MessageModel.prototype, {
    /**
     * Override computeIsEmpty for LLM messages with tool calls or body_json
     */
    computeIsEmpty() {
        console.log('MessageModel.computeIsEmpty called for message:', this.id, 'model:', this.model);
        
        // For LLM messages, apply custom logic
        if (this.model === 'llm.thread') {
            console.log('computeIsEmpty called for LLM message:', this.id, 'llm_role:', this.llm_role);
            
            // Assistant messages with tool calls are never empty
            if (this.llm_role === 'assistant' && this.body_json?.tool_calls?.length > 0) {
                console.log('Assistant message has tool calls, not empty');
                return false;
            }
            
            // Tool messages with body_json are never empty
            if (this.llm_role === 'tool' && this.body_json) {
                console.log('Tool message with body_json, not empty');
                return false;
            }
        }
        
        // Use original computation for other messages
        const result = super.computeIsEmpty();
        console.log('Original computeIsEmpty result:', result, 'for message:', this.id);
        return result;
    },
});