/** @odoo-module **/

import { attr } from "@mail/model/model_field";
import { registerPatch } from "@mail/model/model_core";

registerPatch({
  name: "LLMModel",
  fields: {
    modelUse: attr(), // Field to store the model's use case, e.g., 'chat', 'image_generation'
    inputSchema: attr({
      default: null, // Stores the JSON schema for input parameters
    }),
    outputSchema: attr({
      default: null, // Stores the JSON schema for output parameters
    }),
    isMediaGenerationModel: attr({
      compute() {
        const result = ["image_generation"].includes(this.modelUse);
        return result;
      },
    }),
    // Computed property that returns the effective input schema
    // If a prompt is selected and the model is a media generation model,
    // it will use the prompt's arguments as the input schema
    effectiveInputSchema: attr({
      compute() {
        // Get the thread that this model is associated with
        const thread = this.messaging.models.Thread.all().find(
          (thread) => thread.llmModel && thread.llmModel.id === this.id
        );
        
        // If there's a selected prompt and this is a media generation model, use the prompt's input schema
        if (thread && thread.prompt_id && this.isMediaGenerationModel) {
          try {
            // Use the input_schema_json field which contains a properly formatted JSON schema
            if (thread.prompt_id.inputSchemaJson) {
              return thread.prompt_id.inputSchemaJson;
            }
            return this.inputSchema;
          } catch (error) {
            console.error("Error using prompt schema:", error);
            return this.inputSchema;
          }
        }
        
        // Otherwise, use the model's input schema
        return this.inputSchema;
      },
    }),
  },
});
