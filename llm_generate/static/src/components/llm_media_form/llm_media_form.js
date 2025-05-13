/** @odoo-module **/

import { registerMessagingComponent } from "@mail/utils/messaging_component";
import { JsonEditorComponent } from "@web_json_editor/components/json_editor/json_editor"; 
import { LLMFormFieldsView } from "./llm_form_fields_view"; 
const { Component, useState, onWillStart, useEffect } = owl;

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

  // Toggle input mode between form and JSON editor
  toggleInputMode() {
    if (this.state.inputMode === "form") {
      this.state.inputMode = "json";
    } else {
      // When switching back to form, ensure formValues reflect any valid JSON changes
      // If JSON was invalid, formValues would not have been updated by onJsonEditorChange
      this.state.inputMode = "form";
    }
    this.state.jsonEditorError = null; // Clear any previous JSON errors when toggling
  }

  // Handler for changes from JsonEditorComponent
  onJsonEditorChange({ value, isValid, error }) {
    this.state.isJsonValid = isValid;
    if (isValid) {
      this.state.formValues = value; // value is already a JS object if valid
      this.state.jsonEditorError = null;
    } else {
      // Keep the last valid formValues, but show an error.
      // The JsonEditorComponent itself will display the invalid 'value' (raw text).
      this.state.jsonEditorError = error || "Invalid JSON format.";
    }
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
  }

  _validateFormValues() {
    const errors = [];
    const validatedValues = {}; // This will hold values that conform to the schema
    const currentFormValues = this.state.formValues;
    const schemaFieldNames = new Set(this.formFields.map(f => f.name)); // For quick lookup

    // Step 1: Check schema-defined fields: required, presence, and type
    for (const schemaField of this.formFields) {
      const fieldName = schemaField.name;
      const label = schemaField.label || fieldName;
      let value = currentFormValues[fieldName];

      if (value === undefined && schemaField.default !== undefined) {
        value = schemaField.default;
      }

      if (schemaField.required) {
        const isMissingOrEmpty = value === undefined || value === null ||
                                 (typeof value === 'string' && value.trim() === '') ||
                                 (Array.isArray(value) && value.length === 0);
        if (isMissingOrEmpty) {
          errors.push(`Field "${label}" is required.`);
          continue; 
        }
      }

      if (value !== undefined) {
        let processedValue = value;
        let typeValidationError = null;

        switch (schemaField.type) {
          case 'integer':
            const intValue = parseFloat(value);
            if (isNaN(intValue) || !Number.isInteger(intValue)) {
              typeValidationError = `must be an integer. Received: "${value}"`;
            } else {
              processedValue = intValue;
            }
            break;
          case 'number':
            const floatValue = parseFloat(value);
            if (isNaN(floatValue)) {
              typeValidationError = `must be a number. Received: "${value}"`;
            } else {
              processedValue = floatValue;
            }
            break;
          case 'boolean':
            if (typeof value === 'string') {
              if (value.toLowerCase() === 'true') processedValue = true;
              else if (value.toLowerCase() === 'false') processedValue = false;
              else typeValidationError = `expects a boolean (true/false). Received: "${value}"`;
            } else if (typeof value !== 'boolean') {
              typeValidationError = `expects a boolean. Received: ${typeof value}`;
            }
            break;
          case 'string':
            if (value !== null && value !== undefined) {
              processedValue = String(value);
            }
            break;
          // Add cases for 'enum', 'array', 'object' for more complex schemas if needed
        }

        if (typeValidationError) {
          errors.push(`Field "${label}" ${typeValidationError}.`);
        } else {
          validatedValues[fieldName] = processedValue;
        }
      }
    }

    // Step 2: Check for EXTRA fields
    for (const keyInForm in currentFormValues) {
      if (!schemaFieldNames.has(keyInForm)) {
        console.warn(`Extra field "${keyInForm}" provided in form data will be ignored.`);
        // Optionally, treat as an error:
        // errors.push(`Field "${keyInForm}" is not a recognized field.`);
      }
    }

    // Step 3: Return validation result
    if (errors.length > 0) {
      return { isValid: false, errors: errors, values: currentFormValues };
    }
    return { isValid: true, errors: [], values: validatedValues };
  }

  async onSubmit(event) {
    event.preventDefault();
    
    // Call the validation function
    const validationResult = this._validateFormValues(); 

    if (!validationResult.isValid) {
      this.state.error = validationResult.errors.join('\n'); // Display multiple errors
      this.state.isLoading = false; 
      return; // Stop submission
    }

    // If validation passes, proceed
    this.state.isLoading = true;
    this.state.error = null; // Clear any previous errors

    if (!this.llmModel) {
      this.state.error = "Model not available.";
      this.state.isLoading = false;
      return;
    }

    try {
      const composer = this.thread.composer;
      // Send only the validated and cleaned values
      composer.postUserMediaGenMessageForLLM(validationResult.values); 
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

// Register JsonEditorComponent for use in the template
LLMMediaForm.components = { JsonEditorComponent, LLMFormFieldsView };

registerMessagingComponent(LLMMediaForm);
