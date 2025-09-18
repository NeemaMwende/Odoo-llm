/** @odoo-module **/

import { Chatter } from "@mail/chatter/web_portal/chatter";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

/**
 * Patch Chatter to add AI Chat functionality
 * Adds AI button to chatter topbar for supported models
 */
patch(Chatter.prototype, {
  setup() {
    super.setup();
    this.action = useService("action");
  },

  /**
   * Check if current record supports LLM chat
   * Can be extended to support specific models or conditions
   */
  get supportsLLMChat() {
    return this.props.threadModel && this.props.threadLocalId;
  },

  /**
   * Open AI Chat for current record
   */
  async openAIChat() {
    if (!this.supportsLLMChat) return;

    try {
      await this.action.doAction({
        name: "AI Chat",
        type: "ir.actions.client",
        tag: "llm_thread.chat_client_action",
        context: {
          default_res_model: this.props.threadModel,
          default_res_id: this.props.threadLocalId,
          default_name: `AI Chat - ${this.props.threadModel} #${this.props.threadLocalId}`,
        },
      });
    } catch (error) {
      console.error("Error opening AI chat:", error);
    }
  },
});
