/** @odoo-module */

import { registry } from "@web/core/registry";
import { Component, onMounted, onWillUnmount, useRef, useEffect } from "@odoo/owl";

/**
 * Generic JSON Editor Component
 *
 * A reusable component for editing JSON with schema-based autocomplete
 */
export class JsonEditorComponent extends Component {
  setup() {
    this.editorRef = useRef("editor");
    this.editor = null;

    onMounted(() => this.initEditor());
    onWillUnmount(() => this.destroyEditor());

    useEffect(
      () => {
        if (this.editor && this.props.value !== undefined) {
          try {
            const currentValue = this.editor.get();
            // Avoid re-setting if the editor's current value is already what's in props.value
            // This helps prevent potential cursor jumps or loss of intermediate (invalid) user input.
            if (JSON.stringify(currentValue) !== JSON.stringify(this.props.value)) {
              this.setValue(this.props.value);
            }
          } catch (e) {
            // If editor.get() fails (e.g. invalid JSON in 'code' mode), still try to set value from props.
            this.setValue(this.props.value);
          }
        }
      },
      () => [this.props.value] // Dependency array: rerun effect if props.value changes
    );
  }

  initEditor() {
    if (!this.editorRef.el) return;

    // Generate autocomplete options from schema if available
    const autocompleteOptions = this.generateAutocompleteOptions();
    // Default options
    const mode = this.props.mode || "code";
    const options = {
      mode: mode,
      modes: [mode],
      search: true,
      autocomplete: autocompleteOptions,
      onChange: () => {
        if (this.props.onChange) {
          try {
            const json = this.editor.get();
            this.props.onChange({ value: json, isValid: true });
          } catch (e) {
            let textValue = "";
            // Attempt to get raw text if editor.get() fails, useful for invalid JSON feedback
            if (this.editor && typeof this.editor.getText === 'function') {
                textValue = this.editor.getText();
            }
            this.props.onChange({
              value: textValue, // Send raw text on error
              isValid: false,
              error: e.message,
            });
          }
        }
      },
    };

    // Create editor
    this.editor = new JSONEditor(this.editorRef.el, options);

    // Set initial value
    if (this.props.value) {
      this.setValue(this.props.value);
    }
  }

  generateAutocompleteOptions() {
    // If no schema is provided, return default autocomplete (empty)
    if (!this.props.schema) return {};

    const fields = this.props.schema.fields || [];
    const templates = {};
    const enums = {};

    // Create templates for each field type
    fields.forEach((field) => {
      // Create template for this field
      let template;

      switch (field.type) {
        case "string":
          template = field.default || "";
          break;
        case "integer":
        case "number":
          template = field.default || 0;
          break;
        case "boolean":
          template = field.default || false;
          break;
        case "enum":
          if (field.choices && field.choices.length > 0) {
            template = field.choices[0].value;
            // Add enum values for autocomplete
            enums[field.name] = field.choices.map((choice) => choice.value);
          } else {
            template = "";
          }
          break;
        default:
          template = null;
      }

      // Add to templates
      templates[field.name] = template;
    });

    return {
      filter: "start",
      getOptions: function (text, path) {
        // Root level suggestions
        if (path.length === 0) {
          return Object.keys(templates).map((key) => {
            return {
              text: `"${key}": `,
              value: `"${key}": ${JSON.stringify(templates[key])},`,
              title: key,
            };
          });
        }

        // For enum fields, suggest possible values
        const lastSegment = path[path.length - 1];
        if (enums[lastSegment]) {
          return enums[lastSegment].map((value) => {
            if (typeof value === "string") {
              return {
                text: `"${value}"`,
                value: `"${value}"`,
                title: value,
              };
            }
              return {
                text: String(value),
                value: String(value),
                title: String(value),
              };

          });
        }

        return null;
      },
    };
  }

  setValue(value) {
    if (!this.editor) return;

    try {
      if (typeof value === "string") {
        value = JSON.parse(value);
      }
      this.editor.set(value);
    } catch (e) {
      console.error("Error setting JSON value:", e);
    }
  }

  destroyEditor() {
    if (this.editor) {
      this.editor.destroy();
      this.editor = null;
    }
  }
}

JsonEditorComponent.template = "web_json_editor.JsonEditorComponent";
JsonEditorComponent.props = {
  value: { type: [Object, String], optional: true },
  onChange: { type: Function, optional: true },
  height: { type: String, optional: true, default: "400px" },
  mode: { type: String, optional: true, default: "code" },
  schema: { type: Object, optional: true },
};

// Register the component
registry.category("components").add("json_editor", JsonEditorComponent);
