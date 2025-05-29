/** @odoo-module **/

import { many } from "@mail/model/model_field";
import { registerPatch } from "@mail/model/model_core";

// Define assistant-related fields to fetch from server
const ASSISTANT_THREAD_FIELDS = ["assistant_id"];

/**
 * Patch the LLMChat model to add assistants
 */
registerPatch({
  name: "LLMChat",
  fields: {
    // Use attr instead of many for direct array access
    llmAssistants: many("LLMAssistant"),
  },
  recordMethods: {
    /**
     * Load assistants from the server
     */
    async loadAssistants() {
      // First, load assistants with their basic data and prompt_id
      const assistantResult = await this.messaging.rpc({
        model: "llm.assistant",
        method: "search_read",
        kwargs: {
          domain: [["active", "=", true]],
          fields: ["name", "default_values", "evaluated_default_values", "prompt_id"],
        },
      });
      
      // Extract all prompt IDs to fetch their details
      const promptIds = assistantResult
        .map(assistant => assistant.prompt_id && assistant.prompt_id[0])
        .filter(id => id); // Filter out falsy values
      
      // If we have prompt IDs, fetch their details
      let promptsById = {};
      if (promptIds.length > 0) {
        const promptResult = await this.messaging.rpc({
          model: "llm.prompt",
          method: "search_read",
          kwargs: {
            domain: [["id", "in", promptIds]],
            fields: ["name", "input_schema_json"],
          },
        });
        
        // Create a map of prompts by ID for easy lookup
        promptsById = promptResult.reduce((acc, prompt) => {
          acc[prompt.id] = {
            id: prompt.id,
            name: prompt.name,
            inputSchemaJson: prompt.input_schema_json,
          };
          return acc;
        }, {});
      }
      
      // Map assistant data and include prompt details if available
      const assistantData = assistantResult.map((assistant) => {
        const data = {
          id: assistant.id,
          name: assistant.name,
          defaultValues: assistant.default_values,
          evaluatedDefaultValues: assistant.evaluated_default_values,
        };
        
        // If this assistant has a prompt, include its ID and create the relationship
        if (assistant.prompt_id && assistant.prompt_id[0]) {
          const promptId = assistant.prompt_id[0];
          data.promptId = promptId;
          
          // If we have the prompt details, include them
          if (promptsById[promptId]) {
            data.llmPrompt = promptsById[promptId];
          }
        }
        
        return data;
      });

      this.update({ llmAssistants: assistantData });
    },

    /**
     * Override ensureThread to load assistants as well
     * @override
     */
    async ensureThread(options) {
      // Load assistants if not already loaded
      if (!this.llmAssistants || this.llmAssistants.length === 0) {
        await this.loadAssistants();
      }

      // Call the original method
      return this._super(options);
    },

    /**
     * Override initializeLLMChat to include assistant loading
     * @override
     */
    async initializeLLMChat(
      action,
      initActiveId,
      postInitializationPromises = []
    ) {
      // Pass our loadAssistants promise to the original method
      return this._super(action, initActiveId, [
        ...postInitializationPromises,
        this.loadAssistants(),
      ]);
    },

    /**
     * Override loadThreads to include assistant_id field
     * @override
     */
    async loadThreads(additionalFields = []) {
      // Call the super method with our additional fields
      return this._super([...additionalFields, ...ASSISTANT_THREAD_FIELDS]);
    },

    /**
     * Override refreshThread to include assistant_id field
     * @override
     */
    async refreshThread(threadId, additionalFields = []) {
      // Call the super method with our additional fields
      return this._super(threadId, [
        ...additionalFields,
        ...ASSISTANT_THREAD_FIELDS,
      ]);
    },

    /**
     * Override _mapThreadDataFromServer to add assistant information
     * @override
     */
    _mapThreadDataFromServer(threadData) {
      // Get the base mapped data from super
      const mappedData = this._super(threadData);

      // Add assistant information if present
      if (threadData.assistant_id) {
        mappedData.llmAssistant = {
          id: threadData.assistant_id[0],
          name: threadData.assistant_id[1],
        };
      }

      return mappedData;
    },
  },
});
