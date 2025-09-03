/** @odoo-module **/

import { Message } from "@mail/core/common/message";
import { patch } from "@web/core/utils/patch";

/**
 * Patch Message component to handle LLM-specific message rendering
 * Only affects messages in llm.thread threads
 */
patch(Message.prototype, {
    /**
     * Check if this message is in an LLM thread
     */
    get isLLMMessage() {
        return this.props.message?.res_model === 'llm.thread';
    },

    /**
     * Get LLM role for this message
     */
    get llmRole() {
        return this.props.message?.llm_role;
    },

    /**
     * Check if message is from AI assistant
     */
    get isAssistantMessage() {
        return this.isLLMMessage && this.llmRole === 'assistant';
    },

    /**
     * Check if message is from user
     */
    get isUserMessage() {
        return this.isLLMMessage && this.llmRole === 'user';
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
            if (this.isAssistantMessage && this.props.message?.isPending) {
                className += " o-llm-message-streaming";
            }
        }
        
        return className;
    },

    /**
     * Override author display for LLM messages
     */
    get authorName() {
        if (this.isLLMMessage) {
            if (this.isAssistantMessage) {
                return "AI Assistant";
            }
            // For user messages, use the actual user name
        }
        
        return super.authorName;
    },

    /**
     * Override avatar for LLM messages
     */
    get authorAvatar() {
        if (this.isAssistantMessage) {
            // Return a robot icon or AI avatar
            return "/llm_thread/static/src/img/ai-avatar.png";
        }
        
        return super.authorAvatar;
    }
});