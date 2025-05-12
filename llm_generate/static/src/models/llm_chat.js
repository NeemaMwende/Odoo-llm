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
            "generation_config_id",
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
        generationConfigId: model.generation_config_id
          ? model.generation_config_id[0]
          : undefined,
      }));

      this.update({ llmModels: llmModelData });
    },
  },
});
