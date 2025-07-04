/** @odoo-module **/

import { attr } from "@mail/model/model_field";
import { registerPatch } from "@mail/model/model_core";

registerPatch({
  name: "LLMModel",
  fields: {
    /**
     * Check if this model is configured for media generation
     * Based purely on model_use field containing "generation"
     */
    isMediaGenerationModel: attr({
      compute() {
        if (!this.modelUse) {
          return false;
        }
        
        // Check if model_use contains "generation"
        const generationTypes = ["image_generation", "generation"];
        return generationTypes.includes(this.modelUse);
      },
    }),
    
    /**
     * Get the effective input schema from details or fallback
     */
    effectiveInputSchema: attr({
      compute() {
        // Priority: details.input_schema, then direct inputSchema field
        if (this.details && this.details.input_schema) {
          return this.details.input_schema;
        }
        return this.inputSchema || null;
      },
    }),
    
    /**
     * Get the effective output schema from details or fallback
     */
    effectiveOutputSchema: attr({
      compute() {
        // Priority: details.output_schema, then direct outputSchema field
        if (this.details && this.details.output_schema) {
          return this.details.output_schema;
        }
        return this.outputSchema || null;
      },
    }),
  },
});
