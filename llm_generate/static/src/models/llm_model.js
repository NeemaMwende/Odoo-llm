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
  },
});
