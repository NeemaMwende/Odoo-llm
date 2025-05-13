/** @odoo-module **/

import { registerMessagingComponent } from "@mail/utils/messaging_component";
const { Component, useState, onWillStart, useEffect } = owl;

export class LLMMediaForm extends Component {
  setup() {
    this.state = useState({
      formValues: {},
      isLoading: false,
      error: null,
      showAdvancedSettings: false,
    });

    onWillStart(async () => {
      // Initialize form values with defaults after loading config
      this._initializeFormValues();
    });

    // Watch for changes in the model prop to reload config if necessary
    useEffect(
      () => {
        // Re-initialize form values when model changes
        this._initializeFormValues();
      },
      () => [this.llmModel.inputSchema]
    );
  }
  
  // Initialize form values with defaults from schema
  _initializeFormValues() {
    if (!this.formFields || !Array.isArray(this.formFields)) {
      return;
    }
    
    // Create a new object to hold the initial values
    const initialValues = {};
    
    // Set default values from schema
    this.formFields.forEach(field => {
      if (field.default !== undefined) {
        initialValues[field.name] = field.default;
      }
    });
    
    // Update state with initial values
    this.state.formValues = initialValues;
  }

  get llmModel() {
    return this.thread?.llmModel;
  }

  get thread() {
    return this.props.model;
  }

  get inputSchema() {
    if (!this.llmModel) {
      return null;
    }else if (!this.llmModel.inputSchema) {
      return null;
    } else if (typeof this.llmModel.inputSchema === "string") {
      return JSON.parse(this.llmModel.inputSchema);
    } else if (typeof this.llmModel.inputSchema === "object") {
      return this.llmModel.inputSchema;
    }
    return null;
  }

  get formFields() {
    let inputSchema = this.inputSchema;
    if (
      !inputSchema ||
      inputSchema.error ||
      !Array.isArray(inputSchema.fields)
    ) {
      if (inputSchema && inputSchema.error) {
        console.error(
          "LLMMediaForm: Error in input schema:",
          inputSchema.error
        );
      } else if (!inputSchema || !inputSchema.fields) {
        console.warn(
          "LLMMediaForm: inputSchema or inputSchema.fields is not yet available or not an array.",
          inputSchema
        );
      }
      return [];
    }

    // Map over the 'fields' array directly
    return inputSchema.fields.map((field) => {
      // Check if field name is 'prompt' (case insensitive)
      const isPromptField = field.name.toLowerCase() === 'prompt';
      
      return {
        name: field.name,
        label:
          field.label ||
          field.name.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase()),
        type: field.type,
        // Make 'prompt' field required by default
        required: isPromptField ? true : field.required,
        description: field.description,
        default: field.default,
        // For 'enum' type, use 'field.options' directly as it matches the expected structure
        choices: field.type === "enum" ? field.options : undefined,
        minimum: field.minimum,
        maximum: field.maximum,
        format: field.format, // If present for strings, e.g. 'uri'
      };
    });
  }

  // Getter to filter required fields
  get requiredFields() {
    if (!this.formFields || !Array.isArray(this.formFields)) {
      return [];
    }
    return this.formFields.filter((field) => field.required);
  }

  // Getter to filter optional fields
  get optionalFields() {
    if (!this.formFields || !Array.isArray(this.formFields)) {
      return [];
    }
    return this.formFields.filter((field) => !field.required);
  }

  // Toggle advanced settings visibility
  toggleAdvancedSettings() {
    this.state.showAdvancedSettings = !this.state.showAdvancedSettings;
  }

  onInputChange(fieldName, event) {
    const target = event.target;
    let value;
    if (target.type === "checkbox") {
      value = target.checked;
    } else if (target.type === "number" || target.type === "range") {
      value = parseFloat(target.value);
    } else {
      value = target.value;
    }
    
    // Create a new object with the updated value to ensure reactivity
    this.state.formValues = {
      ...this.state.formValues,
      [fieldName]: value,
    };
    
    console.log(`Field ${fieldName} updated to:`, value);
    console.log("Current form values:", this.state.formValues);
  }

  async onSubmit(event) {
    event.preventDefault();
    this.state.isLoading = true;
    this.state.error = null;

    if (!this.llmModel) {
      this.state.error = "Model not available.";
      this.state.isLoading = false;
      return;
    }

    try {
      const composer = this.thread.composer;
      console.log(this.state.formValues)
      composer.postUserMediaGenMessageForLLM(this.state.formValues);
      // We don't reset the form to allow users to make minor adjustments for subsequent generations
    } catch (error) {
      console.error("Error submitting media generation form:", error);
      this.state.error =
        error.message || "An unexpected error occurred during submission.";
    } finally {
      this.state.isLoading = false;
    }
  }

  isStreaming() {
    return this.thread.composer.isStreaming;
  }
}

LLMMediaForm.props = {
  model: { type: Object, optional: false },
};

LLMMediaForm.template = "llm_thread.LLMMediaForm";

registerMessagingComponent(LLMMediaForm);
