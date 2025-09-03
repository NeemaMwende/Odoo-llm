/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Thread } from "@mail/core/common/thread";
import { Composer } from "@mail/core/common/composer";

/**
 * LLM Chat Container - Main container for LLM chat UI
 * Uses existing mail Thread and Composer components with LLM patches
 */
export class LLMChatContainer extends Component {
  static components = { Thread, Composer };
  static template = "llm_thread.LLMChatContainer";
  
  setup() {
    this.llmStore = useState(useService("llm.store"));
    this.mailStore = useState(useService("mail.store"));
    this.action = useService("action");
    
    // No need for local thread tracking - use mail.store.discuss.thread
  }

  /**
   * Get the active thread from standard mail.store.discuss
   */
  get activeThread() {
    const thread = this.mailStore.discuss?.thread;
    console.log('LLMChatContainer activeThread:', thread, 'discuss:', this.mailStore.discuss);
    return thread;
  }

  /**
   * Check if we have an active LLM thread
   */
  get hasActiveThread() {
    return this.activeThread?.model === 'llm.thread';
  }

  /**
   * Get composer for the active thread
   */
  get threadComposer() {
    return this.activeThread?.composer;
  }

  /**
   * Check if this thread is currently streaming
   */
  get isStreaming() {
    return this.llmStore.getStreamingStatus();
  }

  /**
   * Open llm.thread form to create new chat
   */
  async openCreateChatForm() {
    try {
      await this.action.doAction({
        name: 'Create AI Chat',
        type: 'ir.actions.act_window',
        res_model: 'llm.thread',
        view_mode: 'form',
        views: [[false, 'form']],
        target: 'new',
      });
    } catch (error) {
      console.error('Error opening create chat form:', error);
    }
  }
}

LLMChatContainer.props = {
  "*": true, // Accept any props (like updateActionState)
};