/** @odoo-module **/

import { registerMessagingComponent } from "@mail/utils/messaging_component";
import { JsonEditorComponent } from "@web_json_editor/components/json_editor/json_editor";
import { LLMFormFieldsView } from "./llm_form_fields_view";
const { Component, useState, onWillStart, useEffect } = owl;
import { markup } from "@odoo/owl";

export class LLMMediaForm extends Component {
  setup() {
    this.state = useState({
      formValues: {},
      isLoading: false,
      error: null,
      showAdvancedSettings: false,
      inputMode: "form",
      isJsonValid: true,
      jsonEditorError: null,
      renderedTemplate: null,
      isLoadingTemplate: false,
      schemaInfo: null,
      assistantDefaults: {},
      showTemplatePreview: false,
      templatePreviewJson: null,
    });

    onWillStart(async () => {
      await this._loadModelSchema();
      await this._loadAssistantDefaults();
      await this._initializeFormValues();
    });

    // Watch for changes in the model/thread context
    useEffect(
        () => {
          this._handleContextChange();
        },
        () => [
          this.thread?.id,
          this.llmAssistant?.id,
          this.thread?.prompt_id?.id,
          this.llmAssistant?.evaluatedDefaultValues,
          this.llmModel?.id,
        ]
    );
  }

  get thread() {
    return this.props.model;
  }

  get llmModel() {
    return this.thread?.llmModel;
  }

  get llmAssistant() {
    return this.thread?.llmAssistant;
  }

  get llmChat() {
    return this.thread?.llmChat;
  }

  /**
   * Load model schema information from backend
   */
  async _loadModelSchema() {
    if (!this.llmModel?.id) {
      return;
    }

    this.state.isLoading = true;
    try {
      const schemaInfo = await this.llmChat.getModelGenerationIO(this.llmModel.id);
      this.state.schemaInfo = schemaInfo;

      if (schemaInfo.error) {
        this.state.error = schemaInfo.error;
      }
    } catch (error) {
      console.error("Error loading model schema:", error);
      this.state.error = "Failed to load model configuration";
    } finally {
      this.state.isLoading = false;
    }
  }

  /**
   * Load assistant defaults
   */
  async _loadAssistantDefaults() {
    if (!this.thread?.id) {
      this.state.assistantDefaults = {};
      return;
    }

    try {
      const defaults = await this.llmChat.getRenderedPromptDefaults(this.llmAssistant?.id);
      this.state.assistantDefaults = defaults || {};
      console.log("Loaded assistant defaults:", this.state.assistantDefaults);
    } catch (error) {
      console.error("Error loading assistant defaults:", error);
      this.state.assistantDefaults = {};
    }
  }

  /**
   * Get the source schema (from prompt or model)
   */
  get sourceSchema() {
    // Priority 1: If assistant has a prompt with schema, use that
    if (this.llmAssistant?.llmPrompt?.inputSchemaJson) {
      return this.llmAssistant.llmPrompt.inputSchemaJson;
    }

    // Priority 2: If thread has a direct prompt with schema, use that
    if (this.thread?.prompt_id?.inputSchemaJson) {
      return this.thread.prompt_id.inputSchemaJson;
    }

    // Priority 3: Use model's input schema
    return this.state.schemaInfo?.input_schema;
  }

  /**
   * Normalize schema to fix the field-level required issue
   */
  _normalizeSchema(schema) {
    if (!schema || typeof schema !== 'object') {
      return schema;
    }

    // Clone the schema to avoid modifying the original
    const normalizedSchema = JSON.parse(JSON.stringify(schema));

    // Ensure we have a proper schema structure
    if (!normalizedSchema.type) {
      normalizedSchema.type = "object";
    }

    if (!normalizedSchema.properties) {
      return normalizedSchema;
    }

    // Collect required fields from individual property definitions
    const requiredFields = [];

    // Process each property
    Object.entries(normalizedSchema.properties).forEach(([fieldName, fieldDef]) => {
      // Move field-level required to schema-level required array
      if (fieldDef.required === true) {
        requiredFields.push(fieldName);
        delete fieldDef.required; // Remove invalid field-level required
      }

      // Handle other common schema issues
      if (fieldDef.allOf && Array.isArray(fieldDef.allOf)) {
        fieldDef.allOf.forEach(subSchema => {
          if (subSchema.required === true) {
            if (!requiredFields.includes(fieldName)) {
              requiredFields.push(fieldName);
            }
            delete subSchema.required;
          }
        });
      }
    });

    // Merge with existing required array if present
    if (Array.isArray(normalizedSchema.required)) {
      requiredFields.forEach(field => {
        if (!normalizedSchema.required.includes(field)) {
          normalizedSchema.required.push(field);
        }
      });
    } else if (requiredFields.length > 0) {
      normalizedSchema.required = requiredFields;
    }

    return normalizedSchema;
  }

  get inputSchema() {
    const schema = this.sourceSchema;

    if (!schema) {
      return null;
    }

    let parsedSchema;
    if (typeof schema === "string") {
      try {
        parsedSchema = JSON.parse(schema);
      } catch (e) {
        console.error("Error parsing input schema:", e);
        return null;
      }
    } else {
      parsedSchema = schema;
    }

    // Normalize the schema to fix JSON Schema compliance issues
    return this._normalizeSchema(parsedSchema);
  }

  get formFields() {
    const inputSchema = this.inputSchema;

    if (!inputSchema?.properties) {
      return [];
    }

    // Extract required fields array
    const requiredFields = Array.isArray(inputSchema.required) ? inputSchema.required : [];

    // Convert properties object to array of field definitions
    return Object.entries(inputSchema.properties)
        .map(([name, fieldDef]) => {
          // Check if field name is 'prompt' (case insensitive)
          const isPromptField = name.toLowerCase() === "prompt";

          // Handle enum types
          let choices;
          let fieldType = fieldDef.type;

          if (fieldDef.allOf?.[0]?.enum) {
            choices = fieldDef.allOf[0].enum.map((item) => ({
              value: item,
              label: typeof item === "object" ? item.label || item.value : item,
            }));
            fieldType = "enum";
          } else if (fieldDef.enum) {
            choices = fieldDef.enum.map((item) => ({
              value: item,
              label: typeof item === "object" ? item.label || item.value : item,
            }));
            fieldType = "enum";
          }

          return {
            name: name,
            label: fieldDef.title || name.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase()),
            type: fieldType,
            required: isPromptField || requiredFields.includes(name),
            description: this.formatDescription(fieldDef.description),
            default: fieldDef.default,
            choices: choices,
            minimum: fieldDef.minimum,
            maximum: fieldDef.maximum,
            format: fieldDef.format,
            order: fieldDef["x-order"] ?? 999,
          };
        })
        .sort((a, b) => a.order - b.order);
  }

  get requiredFields() {
    return this.formFields.filter((field) => field.required);
  }

  get optionalFields() {
    return this.formFields.filter((field) => !field.required);
  }

  /**
   * Handle context changes (prompt, assistant, etc.)
   */
  async _handleContextChange() {
    console.log("Media form context changed, reinitializing...");

    // Reload schema if model changed
    if (this.llmModel) {
      await this._loadModelSchema();
    }

    await this._loadAssistantDefaults();
    await this._initializeFormValues();

    // If we're in JSON mode, also update the rendered template
    if (this.state.inputMode === "json") {
      await this._loadRenderedTemplate();
    }
  }

  /**
   * Initialize form values with defaults from schema and assistant
   */
  async _initializeFormValues() {
    if (!this.formFields.length) {
      this.state.formValues = {};
      return;
    }

    try {
      // Start with schema defaults
      const initialValues = {};
      this.formFields.forEach((field) => {
        if (field.default !== undefined) {
          initialValues[field.name] = field.default;
        }
      });

      // Apply assistant defaults (these take precedence over schema defaults)
      if (this.state.assistantDefaults && Object.keys(this.state.assistantDefaults).length > 0) {
        Object.assign(initialValues, this.state.assistantDefaults);
        console.log("Applied assistant defaults:", this.state.assistantDefaults);
      }

      this.state.formValues = initialValues;
      console.log("Initialized form values:", initialValues);
    } catch (error) {
      console.error("Error initializing form values:", error);
    }
  }

  /**
   * Load rendered template for JSON mode
   */
  async _loadRenderedTemplate() {
    if (!this.thread?.id) {
      this.state.renderedTemplate = null;
      return;
    }

    this.state.isLoadingTemplate = true;
    try {
      const promptId = this.llmAssistant?.llmPrompt?.id || this.thread?.prompt_id?.id;
      const result = await this.llmChat.renderTemplateForJson(promptId, this.state.formValues);

      this.state.renderedTemplate = result;
      console.log("Loaded rendered template:", result);
    } catch (error) {
      console.error("Error loading rendered template:", error);
      this.state.renderedTemplate = null;
    } finally {
      this.state.isLoadingTemplate = false;
    }
  }

  /**
   * Generate template preview JSON
   */
  async _generateTemplatePreview() {
    if (!this.thread?.id) {
      this.state.templatePreviewJson = null;
      return;
    }

    try {
      // Combine current form values with assistant defaults
      const combinedInputs = {
        ...this.state.assistantDefaults,
        ...this.state.formValues
      };

      // Call the backend to render the final JSON that would be sent
      const result = await this.messaging.rpc({
        model: "llm.thread",
        method: "render_generation_json",
        args: [this.thread.id, combinedInputs],
        kwargs: {
          without_prompt_template: false
        }
      });

      this.state.templatePreviewJson = result;
      console.log("Generated template preview:", result);
    } catch (error) {
      console.error("Error generating template preview:", error);
      this.state.templatePreviewJson = null;
    }
  }

  /**
   * Toggle template preview
   */
  async toggleTemplatePreview() {
    this.state.showTemplatePreview = !this.state.showTemplatePreview;

    if (this.state.showTemplatePreview) {
      await this._generateTemplatePreview();
    }
  }

  /**
   * Toggle input mode between form and JSON editor
   */
  async toggleInputMode() {
    if (this.state.inputMode === "form") {
      this.state.inputMode = "json";
      await this._loadRenderedTemplate();
    } else {
      this.state.inputMode = "form";
    }
    this.state.jsonEditorError = null;
  }

  /**
   * Get the effective JSON values for the JSON editor
   */
  get jsonEditorValue() {
    if (this.state.renderedTemplate && this.state.inputMode === "json") {
      return {
        ...this.state.renderedTemplate,
        ...this.state.formValues,
      };
    }
    return this.state.formValues;
  }

  /**
   * Handler for JSON editor changes
   */
  onJsonEditorChange({ value, isValid, error, validationErrors }) {
    this.state.isJsonValid = isValid;

    if (isValid) {
      this.state.formValues = value;
      this.state.jsonEditorError = null;
    } else {
      if (validationErrors?.length > 0) {
        if (typeof value === "object" && value !== null) {
          this.state.formValues = value;
        }
      } else {
        this.state.jsonEditorError = error || "Invalid JSON format.";
      }
    }
  }

  /**
   * Handle JSON validation errors
   */
  onJsonValidationError(errors) {
    if (errors?.length > 0) {
      const formattedErrors = errors.map((error) => {
        const path = error.path ? error.path.join(".") : "";
        return `${path ? path + ": " : ""}${error.message}`;
      });
      this.state.jsonEditorError = formattedErrors.join("\n");
    } else {
      this.state.jsonEditorError = null;
    }
  }

  /**
   * Handle general JSON editor errors
   */
  onJsonEditorError(error) {
    this.state.jsonEditorError = error.message || "An error occurred in the JSON editor.";
  }

  /**
   * Toggle advanced settings visibility
   */
  toggleAdvancedSettings() {
    this.state.showAdvancedSettings = !this.state.showAdvancedSettings;
  }

  /**
   * Handle form input changes
   */
  onInputChange(fieldName, event) {
    const target = event.target;
    let value;

    const fieldDef = this.formFields.find((field) => field.name === fieldName);

    if (target.type === "checkbox") {
      value = target.checked;
    } else if (target.type === "number" || target.type === "range") {
      value = parseFloat(target.value);
    } else if (fieldDef?.type === "integer") {
      value = parseInt(target.value, 10);
    } else {
      value = target.value;
    }

    this.state.formValues = {
      ...this.state.formValues,
      [fieldName]: value,
    };

    // Update template preview if it's open
    if (this.state.showTemplatePreview) {
      this._generateTemplatePreview();
    }
  }

  /**
   * Validate form values against schema, considering assistant defaults
   */
  _validateFormValues() {
    const errors = [];
    const validatedValues = {};
    const currentFormValues = this.state.formValues;
    const assistantDefaults = this.state.assistantDefaults || {};
    const schemaFieldNames = new Set(this.formFields.map((f) => f.name));

    // Check schema-defined fields
    for (const schemaField of this.formFields) {
      const fieldName = schemaField.name;
      const label = schemaField.label || fieldName;
      let value = currentFormValues[fieldName];

      // If no value provided, check assistant defaults, then schema defaults
      if (value === undefined) {
        if (assistantDefaults[fieldName] !== undefined) {
          value = assistantDefaults[fieldName];
        } else if (schemaField.default !== undefined) {
          value = schemaField.default;
        }
      }

      // Check required fields only if neither form value nor assistant default is provided
      if (schemaField.required) {
        const isMissingOrEmpty =
            value === undefined ||
            value === null ||
            (typeof value === "string" && value.trim() === "") ||
            (Array.isArray(value) && value.length === 0);

        if (isMissingOrEmpty) {
          errors.push(`Field "${label}" is required.`);
          continue;
        }
      }

      // Validate and convert types
      if (value !== undefined) {
        let processedValue = value;
        let typeValidationError = null;

        switch (schemaField.type) {
          case "integer":
            const intValue = parseFloat(value);
            if (isNaN(intValue) || !Number.isInteger(intValue)) {
              typeValidationError = `must be an integer. Received: "${value}"`;
            } else {
              processedValue = intValue;
            }
            break;
          case "number":
            const floatValue = parseFloat(value);
            if (isNaN(floatValue)) {
              typeValidationError = `must be a number. Received: "${value}"`;
            } else {
              processedValue = floatValue;
            }
            break;
          case "boolean":
            if (typeof value === "string") {
              if (value.toLowerCase() === "true") processedValue = true;
              else if (value.toLowerCase() === "false") processedValue = false;
              else typeValidationError = `expects a boolean (true/false). Received: "${value}"`;
            } else if (typeof value !== "boolean") {
              typeValidationError = `expects a boolean. Received: ${typeof value}`;
            }
            break;
          case "string":
            if (value !== null && value !== undefined) {
              processedValue = String(value);
            }
            break;
        }

        if (typeValidationError) {
          errors.push(`Field "${label}" ${typeValidationError}.`);
        } else {
          validatedValues[fieldName] = processedValue;
        }
      }
    }

    return {
      isValid: errors.length === 0,
      errors: errors,
      values: errors.length === 0 ? validatedValues : currentFormValues,
    };
  }

  /**
   * Format field descriptions with HTML markup
   */
  formatDescription(description) {
    if (!description) return "";

    const formattedDesc = description
        .replace(/<([^>]+)>/g, "<code>$1</code>")
        .replace(/'([^']+)'/g, "<em>$1</em>")
        .replace(/\. /g, ". <br/>")
        .replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank">$1</a>');

    return markup(formattedDesc);
  }

  /**
   * Handle form submission
   */
  async onSubmit(event) {
    event.preventDefault();

    const validationResult = this._validateFormValues();

    if (!validationResult.isValid) {
      this.state.error = validationResult.errors.join("\n");
      return;
    }

    if (!this.llmModel?.isMediaGenerationModel) {
      this.state.error = "Selected model is not configured for media generation.";
      return;
    }

    if (!this.thread?.composer) {
      this.state.error = "Composer not available.";
      return;
    }

    this.state.isLoading = true;
    this.state.error = null;

    try {
      const composer = this.thread.composer;

      // Prepare final inputs (only send form values, let backend merge with template)
      const finalInputs = {
        ...validationResult.values,
        _skipPromptTemplate: false // Let backend handle template rendering
      };

      console.log("Submitting media generation request:", finalInputs);

      // Submit through composer
      composer.postUserMediaGenMessageForLLM(finalInputs);

    } catch (error) {
      console.error("Error submitting media generation form:", error);
      this.state.error = error.message || "An unexpected error occurred during submission.";
    } finally {
      this.state.isLoading = false;
    }
  }

  /**
   * Check if streaming is active
   */
  isStreaming() {
    return this.thread?.composer?.isStreaming || false;
  }

  /**
   * Get formatted template preview JSON for display
   */
  get formattedTemplatePreview() {
    if (!this.state.templatePreviewJson) {
      return "No template preview available";
    }

    try {
      return JSON.stringify(this.state.templatePreviewJson, null, 2);
    } catch (error) {
      console.error("Error formatting template preview:", error);
      return "Error formatting preview";
    }
  }
}

LLMMediaForm.props = {
  model: { type: Object, optional: false },
};

LLMMediaForm.template = "llm_thread.LLMMediaForm";
LLMMediaForm.components = { JsonEditorComponent, LLMFormFieldsView };

registerMessagingComponent(LLMMediaForm);
