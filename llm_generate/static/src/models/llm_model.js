/** @odoo-module **/

import { attr } from "@mail/model/model_field";
import { registerPatch } from "@mail/model/model_core";

registerPatch({
  name: "LLMModel",
  fields: {
    modelUse: attr(), // Field to store the model's use case, e.g., 'chat', 'image_generation'
    generationConfigId: attr(), // Field to store the ID of the llm.generation.config record
    inputSchema: attr({
      default: null, // Stores the JSON schema for input parameters
    }),
    outputSchema: attr({
      default: null, // Stores the JSON schema for output parameters
    }),
    isMediaGenerationModel: attr({
      compute() {
        const result = ['image_generation'].includes(this.modelUse);
        // console.log("isMediaGenerationModel computed:", this.modelUse, result);
        return result;
      },
    }),
  },
  recordMethods: {
    async fetchGenerationConfig() {
      if (!this.id) { // Check if model ID is available
        console.error("LLMModel: Cannot fetch generation config without model ID.");
        return null;
      }
      // Ensure messaging service is available
      if (!this.messaging) {
          console.error("Messaging service not available for LLMModel.");
          this.update({ inputSchema: { error: "Messaging unavailable" }, outputSchema: { error: "Messaging unavailable" } });
          return null;
      }

      const result = await this.messaging.rpc({
        route: '/llm_thread/get_generation_config',
        params: {
          model_id: this.id, // Use the LLMModel's own ID
        },
      });

      console.log("fetchGenerationConfig result:", result);
      if (!result || result.error) {
        console.error("Error fetching generation config:", result.error);
        // Update schemas to reflect the error, so UI can react
        this.update({
          inputSchema: { error: result.error },
          outputSchema: { error: result.error },
        });
        return null;
      }
      
      this.update({
        inputSchema: result.input_schema,
        outputSchema: result.output_schema,
      });
      
      return result; // Return the raw result for potential further use
    },
  },
});
