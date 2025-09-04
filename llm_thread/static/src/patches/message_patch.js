/** @odoo-module **/

import { Message } from "@mail/core/common/message";
import { patch } from "@web/core/utils/patch";
import { LLMToolMessage } from "../components/llm_tool_message/llm_tool_message";

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
        return this.props.message?.model === 'llm.thread';
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
        const result = this.isLLMMessage && this.llmRole === 'tool';
        // Debug logging
        if (this.props.message?.model === 'llm.thread') {
            console.log('LLM Message Debug:', {
                messageId: this.props.message?.id,
                model: this.props.message?.model,
                isLLMMessage: this.isLLMMessage,
                llmRole: this.llmRole,
                isToolMessage: result,
                hasBodyJson: !!this.props.message?.body_json
            });
        }
        return result;
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