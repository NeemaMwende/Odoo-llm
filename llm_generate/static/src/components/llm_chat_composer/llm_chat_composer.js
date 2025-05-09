/** @odoo-module **/

import { LLMChatComposer } from "@llm_thread/components/llm_chat_composer/llm_chat_composer";
import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";

patch(
  LLMChatComposer.prototype,
  "llm_generate.llm_chat_composer_patch",
  {
    setup() {
        this._super();
        this.state = useState({
          isMediaFormVisible: false,
        });
      },
    /**
     * @returns {Thread}
     */
    get thread() {
        return this.composerView?.composer?.activeThread;
    },

    /**
     * @returns {Boolean}
     */
    get isMediaGenerationModel() {
        return this.thread?.llmModel?.isMediaGenerationModel === true;
    },
    /**
     * Method to toggle the visibility of the media form
     */
    toggleMediaForm() {
      this.state.isMediaFormVisible = !this.state.isMediaFormVisible;
    },
  }
);
