/** @odoo-module **/

import { Message } from "@mail/core/common/message";
import { patch } from "@web/core/utils/patch";

/**
 * Patch Message Component to add generation-specific properties
 * Extends the message display for generation inputs and outputs
 */
patch(Message.prototype, {
  /**
   * Check if this is an LLM user message with generation data
   */
  get isLLMUserGenerationMessage() {
    const message = this.props.message;
    return (
      message?.model === "llm.thread" &&
      message?.llm_role === "user" &&
      message?.body_json &&
      Object.keys(message.body_json).length > 0
    );
  },

  /**
   * Get formatted generation data for display
   */
  get generationDataFormatted() {
    const message = this.props.message;
    if (!message?.body_json) {
      return "";
    }

    try {
      return JSON.stringify(message.body_json, null, 2);
    } catch (error) {
      console.error("Error formatting generation data:", error);
      return String(message.body_json);
    }
  },
});
