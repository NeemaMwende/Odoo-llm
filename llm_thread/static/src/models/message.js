/** @odoo-module **/

import { attr } from "@mail/model/model_field";
import { registerPatch } from "@mail/model/model_core";

/**
 * Helper function to safely parse JSON strings.
 * Returns defaultValue if parsing fails or input is invalid.
 * @param {String} jsonString - JSON string to parse
 * @param {any} [defaultValue=undefined] - Default value on failure
 * @returns {any} Parsed JSON or defaultValue
 */
function safeJsonParse(jsonString, defaultValue = undefined) {
  if (!jsonString || typeof jsonString !== "string") {
    return defaultValue;
  }
  try {
    return JSON.parse(jsonString);
  } catch (e) {
    return defaultValue;
  }
}

registerPatch({
  name: "Message",
  modelMethods: {
    /**
     * @override
     */
    convertData(data) {
      const data2 = this._super(data);
      if ("user_vote" in data) {
        data2.user_vote = data.user_vote;
      }
      if ("subtype_xmlid" in data) {
        data2.messageSubtypeXmlid = data.subtype_xmlid;
      }
      if ("tool_call_definition" in data) {
        data2.toolCallDefinition = data.tool_call_definition;
      }
      if ("tool_call_result" in data) {
        data2.toolCallResult = data.tool_call_result;
      }
      if ("tool_calls" in data) {
        data2.toolCallCalls = data.tool_calls;
      }
      if ("tool_call_id" in data && data.tool_call_id !== null) {
        data2.toolCallId = data.tool_call_id;
      }
      // Add LLM role data from the stored field
      if ("llm_role" in data) {
        data2.llmRole = data.llm_role;
      }
      return data2;
    },
  },
  fields: {
    user_vote: attr({
      default: 0,
    }),
    
    /**
     * LLM role for this message ('user', 'assistant', 'tool', 'system')
     * This comes directly from the backend stored field
     */
    llmRole: attr({
      default: null,
    }),
    
    /**
     * Compute parsed tool call definition from llm_tool_call_definition field.
     */
    toolCallDefinition: attr({}),
    toolCallDefinitionFormatted: attr({
      compute() {
        return safeJsonParse(this.toolCallDefinition);
      },
    }),
    toolCallResult: attr({
      default: "",
    }),
    toolCallId: attr({
      default: null,
    }),
    /**
     * Compute parsed tool call result data from llm_tool_call_result field.
     */
    toolCallResultData: attr({
      compute() {
        return safeJsonParse(this.toolCallResult);
      },
    }),
    /**
     * Compute boolean indicating if the tool call result is an error.
     */
    toolCallResultIsError: attr({
      compute() {
        const resultData = this.toolCallResultData;
        return (
          typeof resultData === "object" &&
          resultData !== null &&
          "error" in resultData
        );
      },
    }),
    /**
     * Compute formatted tool call result string (e.g., pretty JSON).
     */
    toolCallResultFormatted: attr({
      compute() {
        const resultData = this.toolCallResultData;
        if (resultData === undefined || resultData === null) {
          return "";
        }
        try {
          return typeof resultData === "object"
            ? JSON.stringify(resultData, null, 2)
            : String(resultData);
        } catch (e) {
          console.error("Error formatting tool call result:", e);
          return String(resultData);
        }
      },
    }),
    toolCallCalls: attr({
      default: [],
    }),
    /**
     * Compute parsed list of tool calls requested by an assistant message.
     */
    formattedToolCalls: attr({
      compute() {
        return safeJsonParse(this.toolCallCalls, []);
      },
    }),
    /**
     * Compute the subtype XML ID (useful for templates).
     * Requires message_format to add subtype_xmlid to the payload.
     */
    messageSubtypeXmlid: attr({}),
  },
});
