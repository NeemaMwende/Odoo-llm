/** @odoo-module **/

import { llmStoreService } from "@llm_thread/services/llm_store_service";
import { patch } from "@web/core/utils/patch";

/**
 * Minimal patch to add assistant functionality to existing LLM store
 * Reuses all existing patterns and infrastructure
 */
patch(llmStoreService, {
    start(env, services) {
        const llmStore = super.start(env, services);
        const { orm, notification } = services;
        
        // Store the original getDataLoaders method
        const originalGetDataLoaders = llmStore.getDataLoaders.bind(llmStore);
        
        // Add assistant-specific properties to the reactive store
        Object.assign(llmStore, {
            llmAssistants: new Map(),
            _assistantsLoaded: false,

            get currentAssistant() {
                const activeThread = this.activeLLMThread;
                console.log('Getting currentAssistant - activeThread:', activeThread);
                console.log('activeThread.assistant_id:', activeThread?.assistant_id);
                
                if (!activeThread?.assistant_id) return null;
                
                const assistantId = activeThread.assistant_id?.id || activeThread.assistant_id;
                console.log('assistantId to lookup:', assistantId);
                
                const assistant = this.llmAssistants.get(assistantId);
                console.log('Found assistant in Map:', assistant);
                
                return assistant || activeThread.assistant_id;
            },

            async loadLLMAssistants() {
                try {
                    console.log('Loading LLM assistants...');
                    const assistants = await orm.searchRead(
                        'llm.assistant',
                        [['active', '=', true]],
                        ['id', 'name', 'is_public', 'provider_id', 'model_id', 'tool_ids']
                    );
                    console.log('Loaded assistants:', assistants);
                    
                    assistants.forEach(assistant => {
                        this.llmAssistants.set(assistant.id, assistant);
                    });
                    this._assistantsLoaded = true;
                    console.log('Assistants Map after loading:', this.llmAssistants);
                } catch (error) {
                    console.warn('LLM assistants not available - llm_assistant module may not be installed:', error.message);
                }
            },

            async selectAssistant(assistantId) {
                const activeThread = this.activeLLMThread;
                if (!activeThread) {
                    notification.add('No active thread to update', { type: 'warning' });
                    return;
                }

                try {
                    if (assistantId) {
                        await orm.call('llm.thread', 'set_assistant', [activeThread.id, assistantId]);
                    } else {
                        await orm.write('llm.thread', [activeThread.id], { assistant_id: false });
                    }

                    // Reuse existing fetchData pattern
                    await activeThread.fetchData(['assistant_id', 'provider_id', 'model_id', 'tool_ids']);
                    
                } catch (error) {
                    console.error('Error selecting assistant:', error);
                    notification.add('Failed to update assistant', { type: 'danger' });
                }
            },

            // Extend existing getDataLoaders method instead of overriding initialize
            getDataLoaders() {
                const baseLoaders = originalGetDataLoaders();
                console.log('Getting data loaders, base:', baseLoaders.length, 'adding loadLLMAssistants');
                return [...baseLoaders, this.loadLLMAssistants];
            }
        });
        
        return llmStore;
    }
});