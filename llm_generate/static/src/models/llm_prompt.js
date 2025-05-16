/** @odoo-module **/

import { attr, many, one } from "@mail/model/model_field";
import { registerModel } from "@mail/model/model_core";

registerModel({
  name: "LLMPrompt",
  fields: {
    id: attr({
      identifying: true,
    }),
    name: attr(),
    argumentsJson: attr({
      default: "{}",
    }),
    threads: many("Thread", {
      inverse: "prompt_id",
    }),
  },
});
