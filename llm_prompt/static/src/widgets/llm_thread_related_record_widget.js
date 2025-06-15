/** @odoo-module **/

import { Component, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class LLMThreadRelatedRecordWidget extends Component {
    static template = "llm_prompt.LLMThreadRelatedRecordWidget";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.orm = useService("orm");
        this.messaging = useService("messaging");

        this.state = useState({
            mockThread: null,
            isLoading: false,
        });

        onMounted(() => {
            this._updateMockThread();
        });

        // Watch for changes in the related record fields
        if (this.env.model) {
            this.env.model.addEventListener("update", this._onModelUpdate.bind(this));
        }
    }

    _onModelUpdate() {
        this._updateMockThread();
    }

    _updateMockThread() {
        const record = this.props.record;

        // Create a mock thread object that mimics the structure expected by LLMChatThreadRelatedRecord
        const mockThread = {
            id: 0, // Mock thread ID for the wizard
            relatedThreadModel: record.data.related_record_model || null,
            relatedThreadId: record.data.related_record_id || null,
            relatedThread: Boolean(record.data.related_record_model && record.data.related_record_id),

            // Mock the llmChat property if needed
            llmChat: {
                refreshThread: async (threadId) => {
                    // Mock refresh - reload the wizard record instead
                    await this.props.record.load();
                }
            },

            // Mock methods that the component might call
            update: (updates) => {
                // Handle updates to the mock thread
                if (updates.relatedThreadModel !== undefined || updates.relatedThreadId !== undefined) {
                    this._updateWizardRecord(
                        updates.relatedThreadModel,
                        updates.relatedThreadId
                    );
                }
            }
        };

        this.state.mockThread = mockThread;
    }

    async _updateWizardRecord(model, recordId) {
        try {
            this.state.isLoading = true;

            await this.orm.write("llm.prompt.test", [this.props.record.resId], {
                related_record_model: model || false,
                related_record_id: recordId || false,
            });

            // Reload the record to get updated data
            await this.props.record.load();

            // Update the mock thread
            this._updateMockThread();

        } catch (error) {
            console.error("Error updating wizard record:", error);
            if (this.messaging) {
                this.messaging.notify({
                    message: "Failed to update related record",
                    type: "danger",
                });
            }
        } finally {
            this.state.isLoading = false;
        }
    }

    async _clearRecord() {
        await this._updateWizardRecord(null, null);
    }

    get hasValidThread() {
        return Boolean(this.state.mockThread);
    }

    get mockThread() {
        return this.state.mockThread;
    }
}

// Register the widget
registry.category("fields").add("llm_thread_related_record_widget", LLMThreadRelatedRecordWidget);
