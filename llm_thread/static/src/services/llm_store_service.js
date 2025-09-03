/** @odoo-module **/

import { reactive } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

/**
 * LLM Store Service - Integrates with existing mail.store
 * Provides LLM-specific functionality without breaking mail components
 */
export const llmStoreService = {
    dependencies: ["orm", "bus_service", "mail.store", "notification"],

    start(env, { orm, bus_service, "mail.store": mailStore, notification }) {
        
        const llmStore = reactive({
            // LLM-specific data
            llmThreads: new Map(),         // Map<id, LLMThread>
            llmModels: new Map(),          // Map<id, LLMModel> 
            llmProviders: new Map(),       // Map<id, LLMProvider>
            streamingThreads: new Set(),   // Set<threadId> currently streaming
            eventSources: new Map(),       // Map<threadId, EventSource>

            // Computed properties
            get activeLLMThread() {
                // Check if current active thread in mail.store is an LLM thread
                const activeThread = mailStore.discuss?.thread;
                if (activeThread?.model === 'llm.thread') {
                    return this.llmThreads.get(activeThread.id);
                }
                return null;
            },

            get isLLMThread() {
                return this.activeLLMThread !== null;
            },

            get llmThreadList() {
                return Array.from(this.llmThreads.values())
                    .sort((a, b) => new Date(b.write_date) - new Date(a.write_date));
            },

            // LLM-specific methods
            async loadLLMThread(threadId) {
                try {
                    const threadData = await orm.read('llm.thread', [threadId], [
                        'id', 'name', 'model_id', 'provider_id', 'user_id', 'write_date'
                    ]);
                    
                    if (threadData.length > 0) {
                        this.llmThreads.set(threadId, threadData[0]);
                        return threadData[0];
                    }
                } catch (error) {
                    console.error('Error loading LLM thread:', error);
                    notification.add('Failed to load LLM thread', { type: 'danger' });
                }
                return null;
            },

            async sendLLMMessage(threadId, content) {
                if (!threadId || !content?.trim()) return;

                try {
                    // Create optimistic user message in mail.store (so it appears in UI immediately)
                    const tempMessage = {
                        id: `temp_${Date.now()}`,
                        body: content,
                        author: [user.userId, user.name],
                        res_model: 'llm.thread',
                        res_id: threadId,
                        message_type: 'comment',
                        llm_role: 'user',
                        date: luxon.DateTime.now().toISO(),
                        isPending: true
                    };

                    // Insert into mail.store so it appears in Thread component
                    mailStore.insert({ 'mail.message': [tempMessage] });

                    // Start LLM streaming
                    await this.startLLMStreaming(threadId, content);

                } catch (error) {
                    console.error('Error sending LLM message:', error);
                    notification.add('Failed to send message', { type: 'danger' });
                }
            },

            async startLLMStreaming(threadId, message) {
                // Stop any existing stream for this thread
                this.stopStreaming(threadId);
                
                this.streamingThreads.add(threadId);

                try {
                    const eventSource = new EventSource(
                        `/llm/thread/generate?thread_id=${threadId}&message=${encodeURIComponent(message)}`
                    );
                    
                    this.eventSources.set(threadId, eventSource);

                    eventSource.onmessage = (event) => {
                        const data = JSON.parse(event.data);
                        this.handleStreamMessage(threadId, data);
                    };

                    eventSource.onerror = (error) => {
                        console.error('EventSource error:', error);
                        this.stopStreaming(threadId);
                        notification.add('Connection error during AI response', { type: 'danger' });
                    };

                } catch (error) {
                    console.error('Error starting stream:', error);
                    this.stopStreaming(threadId);
                    notification.add('Failed to start AI response', { type: 'danger' });
                }
            },

            stopStreaming(threadId) {
                const eventSource = this.eventSources.get(threadId);
                if (eventSource) {
                    eventSource.close();
                    this.eventSources.delete(threadId);
                }
                this.streamingThreads.delete(threadId);
            },

            handleStreamMessage(threadId, data) {
                switch (data.type) {
                    case "message_create":
                        // Insert AI response into mail.store
                        data.message.llm_role = 'assistant';
                        mailStore.insert({ 'mail.message': [data.message] });
                        break;
                        
                    case "message_chunk":
                    case "message_update":
                        // Update existing message in mail.store
                        const existingMessage = Object.values(mailStore.Message.records)
                            .find(msg => msg.id === data.message.id);
                        
                        if (existingMessage) {
                            Object.assign(existingMessage, data.message);
                        } else {
                            data.message.llm_role = 'assistant';
                            mailStore.insert({ 'mail.message': [data.message] });
                        }
                        break;
                        
                    case "error":
                        this.stopStreaming(threadId);
                        notification.add(data.error || "AI response error", { type: "danger" });
                        break;
                        
                    case "done":
                        this.stopStreaming(threadId);
                        break;
                }
            },

            async loadLLMModels() {
                try {
                    // Check if llm.model exists first - use correct field names
                    const models = await orm.searchRead(
                        'llm.model',
                        [['active', '=', true]],
                        ['id', 'name', 'provider_id', 'default', 'model_use']
                    );
                    
                    models.forEach(model => {
                        this.llmModels.set(model.id, model);
                    });
                } catch (error) {
                    console.warn('LLM models not available - llm module may not be installed:', error.message);
                    // Don't throw error, just log warning
                }
            },

            async loadLLMProviders() {
                try {
                    // Check if llm.provider exists first - use correct field names
                    const providers = await orm.searchRead(
                        'llm.provider',
                        [['active', '=', true]],
                        ['id', 'name', 'service']
                    );
                    
                    providers.forEach(provider => {
                        this.llmProviders.set(provider.id, provider);
                    });
                } catch (error) {
                    console.warn('LLM providers not available - llm module may not be installed:', error.message);
                    // Don't throw error, just log warning
                }
            },

            // Helper methods for components
            isStreamingThread(threadId) {
                return this.streamingThreads.has(threadId);
            },

            getStreamingStatus() {
                const activeThread = mailStore.discuss?.thread;
                if (activeThread?.model === 'llm.thread') {
                    return this.isStreamingThread(activeThread.id);
                }
                return false;
            },

            // Initialize LLM store
            async initialize() {
                await Promise.all([
                    this.loadLLMProviders(),
                    this.loadLLMModels()
                ]);
            },

            // Cleanup
            destroy() {
                // Close all event sources
                this.eventSources.forEach(eventSource => eventSource.close());
                this.eventSources.clear();
                this.streamingThreads.clear();
            }
        });

        // Initialize when service starts
        llmStore.initialize();

        // Subscribe to thread changes to load LLM data when needed
        const originalDiscussThreadSetter = Object.getOwnPropertyDescriptor(mailStore.discuss, 'thread')?.set;
        if (originalDiscussThreadSetter) {
            Object.defineProperty(mailStore.discuss, 'thread', {
                ...Object.getOwnPropertyDescriptor(mailStore.discuss, 'thread'),
                set(thread) {
                    originalDiscussThreadSetter.call(this, thread);
                    
                    // Load LLM data if switching to LLM thread
                    if (thread?.model === 'llm.thread' && !llmStore.llmThreads.has(thread.id)) {
                        llmStore.loadLLMThread(thread.id);
                    }
                }
            });
        }

        return llmStore;
    }
};

registry.category("services").add("llm.store", llmStoreService);