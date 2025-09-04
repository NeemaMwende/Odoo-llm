/** @odoo-module **/

import { llmStoreService } from "@llm_thread/services/llm_store_service";
import { patch } from "@web/core/utils/patch";

/**
 * Patch the LLM store service to add assistant-related fields and data
 */
patch(llmStoreService, {
    start(env, services) {
        const llmStore = super.start(env, services);
        
        // Extend the llmStore object with assistant-specific data
        Object.assign(llmStore, {
            llmAssistants: new Map(), // Map<id, LLMAssistant>
            
            // Override the getThreadFields method to include assistant_id
            getThreadFields() {
                const baseFields = super.getThreadFields();
                return [...baseFields, 'assistant_id'];
            },
            
            async loadLLMAssistants() {
                try {
                    const assistants = await services.orm.searchRead(
                        'llm.assistant',
                        [['active', '=', true]],
                        ['id', 'name', 'description', 'is_public', 'provider_id', 'model_id']
                    );
                    
                    assistants.forEach(assistant => {
                        this.llmAssistants.set(assistant.id, assistant);
                    });
                } catch (error) {
                    console.warn('LLM assistants not available:', error.message);
                }
            },
            
            // Override initialize to also load assistants
            async initialize() {
                await super.initialize();
                await this.loadLLMAssistants();
            }
        });
        
        return llmStore;
    }
});