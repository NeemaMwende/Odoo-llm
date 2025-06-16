/** @odoo-module **/

import { registerPatch } from "@mail/model/model_core";

registerPatch({
  name: "LLMChat",
  recordMethods: {
    /**
     * Override
     * Loads LLM models from the server.
     */
    async loadLLMModels() {
      try {
        const result = await this.messaging.rpc({
          model: "llm.model",
          method: "search_read",
          kwargs: {
            domain: [],
            fields: [
              "name",
              "id",
              "provider_id",
              "default",
              "model_use",
              "input_schema",
              "output_schema",
            ],
          },
        });

        const llmModelData = result.map((model) => ({
          id: model.id,
          name: model.name,
          llmProvider: model.provider_id
              ? { id: model.provider_id[0], name: model.provider_id[1] }
              : undefined,
          default: model.default,
          modelUse: model.model_use,
          inputSchema: model.input_schema,
          outputSchema: model.output_schema,
        }));

        this.update({ llmModels: llmModelData });
      } catch (error) {
        console.error("Error loading LLM models:", error);
      }
    },

    /**
     * Get rendered prompt defaults for the current thread
     * @param {number} assistantId - Optional assistant ID to use instead of thread's assistant
     * @returns {Promise<Object>} Rendered default values
     */
    async getRenderedPromptDefaults(assistantId = null) {
      if (!this.activeThread?.id) {
        return {};
      }

      try {
        const result = await this.messaging.rpc({
          model: "llm.thread",
          method: "get_rendered_prompt_defaults",
          args: [this.activeThread.id],
          kwargs: {
            assistant_id: assistantId || this.activeThread.llmAssistant?.id || false,
          },
        });

        return result || {};
      } catch (error) {
        console.error("Error getting rendered prompt defaults:", error);
        return {};
      }
    },

    /**
     * Render template for JSON editor
     * @param {number} promptId - Optional prompt ID to use
     * @param {Object} currentValues - Current form values to merge
     * @returns {Promise<Object>} Rendered template values
     */
    async renderTemplateForJson(promptId = null, currentValues = null) {
      if (!this.activeThread?.id) {
        return currentValues || {};
      }

      try {
        const result = await this.messaging.rpc({
          model: "llm.thread",
          method: "render_template_for_json",
          args: [this.activeThread.id],
          kwargs: {
            prompt_id: promptId || this.activeThread.llmAssistant?.llmPrompt?.id || this.activeThread.prompt_id?.id || false,
            current_values: currentValues,
          },
        });

        return result || currentValues || {};
      } catch (error) {
        console.error("Error rendering template for JSON:", error);
        return currentValues || {};
      }
    },

    /**
     * Get model generation I/O schema by model ID
     * @param {number} modelId - Model ID
     * @returns {Promise<Object>} Model schema information
     */
    async getModelGenerationIO(modelId) {
      try {
        const result = await this.messaging.rpc({
          model: "llm.thread",
          method: "get_model_generation_io_by_id",
          args: [modelId],
        });

        return result;
      } catch (error) {
        console.error("Error getting model generation IO:", error);
        return {
          error: error.message,
          input_schema: null,
          output_schema: null,
          model_id: modelId,
          model_name: null,
        };
      }
    },

    /**
     * Refresh assistant's evaluated defaults
     * @param {number} assistantId - Optional assistant ID
     * @returns {Promise<Object>} Refreshed default values
     */
    async refreshAssistantDefaults(assistantId = null) {
      if (!this.activeThread?.id) {
        return {};
      }

      try {
        const result = await this.messaging.rpc({
          model: "llm.thread",
          method: "refresh_assistant_defaults",
          args: [this.activeThread.id],
          kwargs: {
            assistant_id: assistantId || this.activeThread.llmAssistant?.id || false,
          },
        });

        return result || {};
      } catch (error) {
        console.error("Error refreshing assistant defaults:", error);
        return {};
      }
    },
  },
});
