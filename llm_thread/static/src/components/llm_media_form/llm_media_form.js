/** @odoo-module **/

import { registerMessagingComponent } from "@mail/utils/messaging_component";
const { Component, useState, onWillStart, useEffect } = owl;

export class LLMMediaForm extends Component {
    setup() {
        this.state = useState({
            formValues: {},
            isLoading: false,
            error: null,
            success: null,
        });

        onWillStart(async () => {
            await this.loadGenerationConfig();
        });

        // Watch for changes in the model prop to reload config if necessary
        useEffect(() => {
            this.loadGenerationConfig();
        }, () => [this.llmModel]);
    }

    get llmModel() {
        return this.props.model;
    }

    get inputSchema() {
        console.log("Found inputSchema:", this.llmModel?.inputSchema);
        return this.llmModel?.inputSchema;
    }

    // Placeholder for a getter that will transform the JSON schema into an array of field objects for rendering
    get formFields() {
        // Ensure inputSchema and inputSchema.fields are valid
        if (!this.inputSchema || this.inputSchema.error || !Array.isArray(this.inputSchema.fields)) {
            if (this.inputSchema && this.inputSchema.error) {
                console.error("LLMMediaForm: Error in input schema:", this.inputSchema.error);
            } else if (!this.inputSchema || !this.inputSchema.fields) {
                 console.warn("LLMMediaForm: inputSchema or inputSchema.fields is not yet available or not an array.", this.inputSchema);
            }
            return [];
        }

        // Map over the 'fields' array directly
        return this.inputSchema.fields.map(field => ({
            name: field.name, // Use field.name directly
            label: field.label || field.name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
            type: field.type,
            required: field.required, // Assuming 'required' is directly on the field object
            description: field.description,
            default: field.default,
            // For 'enum' type, use 'field.options' directly as it matches the expected structure
            choices: field.type === 'enum' ? field.options : undefined,
            minimum: field.minimum,
            maximum: field.maximum,
            format: field.format // if present for strings, e.g. 'uri'
            // Add any other properties from your schema's field definition
        }));
    }

    async loadGenerationConfig() {
        if (!this.llmModel || !this.llmModel.isMediaGenerationModel) {
            this.state.error = "Not a media generation model or model not available.";
            return;
        }

        // Only fetch if schema is not already loaded or if there was a previous error loading it
        if (!this.llmModel.inputSchema || this.llmModel.inputSchema.error) {
            this.state.isLoading = true;
            this.state.error = null;
            this.state.success = null;
            try {
                await this.llmModel.fetchGenerationConfig();
                if (this.llmModel.inputSchema?.error) { // Check for error after fetch attempt
                    this.state.error = this.llmModel.inputSchema.error;
                }
            } catch (error) {
                console.error("Error fetching generation config in LLMMediaForm:", error);
                this.state.error = error.message || "Failed to load generation configuration.";
            } finally {
                this.state.isLoading = false;
            }
        }
    }

    onInputChange(fieldName, event) {
        const target = event.target;
        let value;
        if (target.type === 'checkbox') {
            value = target.checked;
        } else if (target.type === 'number' || target.type === 'range') {
            value = parseFloat(target.value);
        } else {
            value = target.value;
        }
        this.state.formValues[fieldName] = value;
    }

    async onSubmit(event) {
        event.preventDefault();
        this.state.isLoading = true;
        this.state.error = null;
        this.state.success = null;

        if (!this.llmModel) {
            this.state.error = "Model not available.";
            this.state.isLoading = false;
            return;
        }

        try {
            // Placeholder for actual media generation call
            // const result = await this.llmModel.generateMedia(this.state.formValues);
            // For now, simulate a call and log
            console.log("Form submitted with values:", this.state.formValues);
            console.log("Would call this.llmModel.generateMedia() here.");
            // TODO: Implement generateMedia on LLMModel and call it
            // if (result && result.error) {
            //     this.state.error = result.error;
            // } else {
            //     this.state.success = "Media generation started successfully!"; // Or some other relevant message
            //     this.state.formValues = {}; // Optionally reset form
            // }
            this.state.success = "Form submitted (simulation). Check console."; // Temporary feedback
        } catch (error) {
            console.error("Error submitting media generation form:", error);
            this.state.error = error.message || "An unexpected error occurred during submission.";
        } finally {
            this.state.isLoading = false;
        }
    }
}

LLMMediaForm.props = {
    model: { type: Object, optional: false }, // Expects an LLMModel instance
};

LLMMediaForm.template = "llm_thread.LLMMediaForm";

registerMessagingComponent(LLMMediaForm);
