/** @odoo-module **/

import { registerMessagingComponent } from "@mail/utils/messaging_component";
import { useComponentToModel } from "@mail/component_hooks/use_component_to_model";
const { Component, useState } = owl;

export class LLMChatComposer extends Component {
  /**
   * @override
   */
  setup() {
    super.setup();
    useComponentToModel({ fieldName: "component" });
    this.state = useState({
      isMediaFormVisible: false,
    });
  }

  /**
   * @returns {ComposerView}
   */
  get composerView() {
    return this.props.record;
  }

  /**
   * @returns {Thread}
   */
  get thread() {
    return this.composerView?.composer?.activeThread;
  }

  /**
   * @returns {Boolean}
   */
  get isMediaGenerationModel() {
    console.log("isMediaGenerationModel:", this.thread?.llmModel?.isMediaGenerationModel);
    return this.thread?.llmModel?.isMediaGenerationModel === true;
  }

  /**
   * @returns {Boolean}
   */
  get isDisabled() {
    // Read the computed disabled state from the model.
    return this.composerView.composer.isSendDisabled;
  }

  get isStreaming() {
    return this.composerView.composer.isStreaming;
  }

  // --------------------------------------------------------------------------
  // Private
  // --------------------------------------------------------------------------

  /**
   * Intercept send button click
   * @private
   */
  _onClickSend() {
    if (this.isDisabled) {
      return;
    }

    this.composerView.composer.postUserMessageForLLM();
  }

  /**
   * Handles click on the stop button.
   *
   * @private
   */
  _onClickStop() {
    this.composerView.composer.stopLLMThreadLoop();
  }

  /**
   * Method to toggle the visibility of the media form
   */
  toggleMediaForm() {
    this.state.isMediaFormVisible = !this.state.isMediaFormVisible;
  }
}

Object.assign(LLMChatComposer, {
  props: { record: Object },
  template: "llm_thread.LLMChatComposer",
});

registerMessagingComponent(LLMChatComposer);
