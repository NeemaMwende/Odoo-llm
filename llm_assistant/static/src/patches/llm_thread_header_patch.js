/** @odoo-module **/

import { LLMThreadHeader } from "@llm_thread/components/llm_thread_header/llm_thread_header";
import { patch } from "@web/core/utils/patch";

/**
 * Minimal patch to add assistant functionality to existing thread header
 * Reuses all existing patterns and follows DRY principles
 */
patch(LLMThreadHeader.prototype, {
    setup() {
        super.setup();
        console.log('Assistant patch setup() called', this);
        // Reuse existing store - it's already the patched version via useService
        this.assistantStore = this.llmStore;
        console.log('assistantStore set to:', this.assistantStore);
    },

    /**
     * Get current assistant following existing pattern
     */
    get currentAssistant() {
        console.log('Component currentAssistant getter called');
        console.log('assistantStore exists:', !!this.assistantStore);
        console.log('assistantStore keys:', Object.keys(this.assistantStore || {}));
        console.log('assistantStore has currentAssistant:', 'currentAssistant' in (this.assistantStore || {}));
        console.log('assistantStore.llmAssistants:', this.assistantStore?.llmAssistants);
        console.log('assistantStore.activeLLMThread:', this.assistantStore?.activeLLMThread);
        
        if (!this.assistantStore) return null;
        
        // Call the getter directly to trigger logs
        const result = this.assistantStore.currentAssistant;
        console.log('Service currentAssistant result:', result);
        
        return result;
    },

    /**
     * Get available assistants following existing pattern
     */
    get availableAssistants() {
        if (!this.assistantStore?._assistantsLoaded) return [];
        return Array.from(this.assistantStore.llmAssistants.values());
    },

    /**
     * Select assistant following existing update pattern
     */
    async selectAssistant(assistant) {
        if (!this.assistantStore) return;
        
        const assistantId = assistant ? assistant.id : null;
        if (assistantId === this.currentAssistant?.id) return;
        
        try {
            this.state.isLoadingUpdate = true;
            await this.assistantStore.selectAssistant(assistantId);
        } catch (error) {
            this.notification.add("Failed to update assistant", {
                type: "danger"
            });
            console.error("Error updating assistant:", error);
        } finally {
            this.state.isLoadingUpdate = false;
        }
    },

    /**
     * Clear assistant selection
     */
    async clearAssistant() {
        await this.selectAssistant(null);
    }
});