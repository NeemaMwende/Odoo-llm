/** @odoo-module **/

import { reactive } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { Deferred } from "@web/core/utils/concurrency";

/**
 * LLM Store Service - Integrates with existing mail.store
 * Provides LLM-specific functionality without breaking mail components
 */
export const llmStoreService = {
    dependencies: ["orm", "mail.store", "notification"],

    start(env, { orm, "mail.store": mailStore, notification }) {
        
        const llmStore = reactive({
            // NOTE: Threads are now loaded via standard mail.store, no need for separate Map
            llmModels: new Map(),          // Map<id, LLMModel> 
            llmProviders: new Map(),       // Map<id, LLMProvider>
            llmTools: new Map(),           // Map<id, LLMTool>
            streamingThreads: new Set(),   // Set<threadId> currently streaming
            eventSources: new Map(),       // Map<threadId, EventSource>
            isReady: new Deferred(),       // Resolves when LLM data is loaded

            // Computed properties - using mailStore as source of truth
            get activeLLMThread() {
                // Check if current active thread in mail.store is an LLM thread
                const activeThread = mailStore.discuss?.thread;
                return (activeThread?.model === 'llm.thread') ? activeThread : null;
            },

            get isLLMThread() {
                return this.activeLLMThread !== null;
            },

            get llmThreadList() {
                // Get all LLM threads from mailStore
                const allThreads = Object.values(mailStore.Thread.records || {});
                return allThreads
                    .filter(thread => thread.model === 'llm.thread')
                    .sort((a, b) => new Date(b.write_date || 0) - new Date(a.write_date || 0));
            },

            // LLM-specific methods using standard fetchData approach
            async ensureThreadLoaded(threadId) {
                // Check if thread already exists in mailStore
                let thread = mailStore.Thread.get({ model: 'llm.thread', id: threadId });
                if (thread) {
                    return thread;
                }
                
                // If thread not found, it might not be accessible to current user
                // or wasn't loaded in init_messaging (e.g., old thread, different user)
                console.warn(`Thread ${threadId} not found in mailStore`);
                return null;
            },

            async sendLLMMessage(threadId, content) {
                if (!threadId || !content?.trim()) return;

                try {
                    // Start LLM streaming - backend will handle both user message creation and AI response
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
                    // Include message parameter for user message creation
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
                console.log('Handling stream message:', data.type, data);
                
                switch (data.type) {
                    case "message_create":
                        // Handle all messages (user and AI) via EventSource
                        console.log('Creating new message:', data.message);
                        const insertResult1 = mailStore.insert({ 'mail.message': [data.message] });
                        console.log('Insert result for create:', insertResult1);
                        
                        // Get the created message and add it to the thread's messages collection
                        const createdMessage = mailStore.Message.get(data.message.id);
                        console.log('Created message retrieved:', createdMessage);
                        
                        // Add message to the thread's messages collection if not already there
                        const createThread = mailStore.discuss?.thread;
                        if (createThread && createdMessage && !createThread.messages.some(m => m.id === createdMessage.id)) {
                            createThread.messages.push(createdMessage);
                            console.log('Added message to thread messages. New count:', createThread.messages.length);
                        }
                        break;
                        
                    case "message_chunk":
                    case "message_update":
                        // Update existing message using standard mail.store.insert() like Odoo does
                        console.log('Updating message:', data.message.id, data.message);
                        
                        // Check current thread's messages before update
                        const currentThread = mailStore.discuss?.thread;
                        console.log('Current active thread:', currentThread);
                        if (currentThread) {
                            console.log('Thread messages before update:', currentThread.messages.length, currentThread.messages.map(m => m.id));
                        }
                        
                        // Use the same pattern as Odoo's standard bus handlers - always use insert
                        // which will update existing messages or create new ones as needed
                        const insertResult2 = mailStore.insert({ 'mail.message': [data.message] }, { html: true });
                        console.log('Insert result for update:', insertResult2);
                        
                        // Check if message was actually updated
                        const updatedMessage = mailStore.Message.get(data.message.id);
                        console.log('Updated message retrieved:', updatedMessage);
                        
                        // Check thread messages after update
                        if (currentThread) {
                            console.log('Thread messages after update:', currentThread.messages.length, currentThread.messages.map(m => m.id));
                        }
                        break;
                        
                    case "error":
                        console.error('Stream error:', data.error);
                        this.stopStreaming(threadId);
                        notification.add(data.error || "AI response error", { type: "danger" });
                        break;
                        
                    case "done":
                        console.log('Stream completed');
                        this.stopStreaming(threadId);
                        break;
                        
                    default:
                        console.warn('Unknown stream message type:', data.type);
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


            async loadLLMTools() {
                try {
                    // Load available tools with minimal fields
                    const tools = await orm.searchRead(
                        'llm.tool',
                        [['active', '=', true]],
                        ['id', 'name']
                    );
                    
                    tools.forEach(tool => {
                        this.llmTools.set(tool.id, tool);
                    });
                } catch (error) {
                    console.warn('LLM tools not available:', error.message);
                    // Don't throw error, just log warning
                }
            },

            // Thread selection using standard Odoo patterns
            async selectThread(threadId) {
                try {
                    // Ensure thread is loaded using standard fetchData
                    const thread = await this.ensureThreadLoaded(threadId);
                    if (!thread) {
                        throw new Error('Thread not found or failed to load');
                    }
                    
                    // Set as active thread in discuss - this is all we need!
                    thread.setAsDiscussThread();
                    
                } catch (error) {
                    console.error('Error selecting thread:', error);
                    notification.add('Failed to load chat thread', { type: 'danger' });
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

            // Initialize LLM store - threads now loaded via standard init_messaging
            async initialize() {
                try {
                    await Promise.all([
                        this.loadLLMProviders(),
                        this.loadLLMModels(),
                        this.loadLLMTools()
                    ]);
                    // NOTE: LLM threads are now loaded automatically via res.users._init_messaging()
                    this.isReady.resolve();
                } catch (error) {
                    console.error('Error initializing LLM store:', error);
                    this.isReady.reject(error);
                }
            },

            // Cleanup
            destroy() {
                // Close all event sources
                this.eventSources.forEach(eventSource => eventSource.close());
                this.eventSources.clear();
                this.streamingThreads.clear();
            }
        });

        // Initialize LLM data after mailStore is ready (which calls init_messaging)
        mailStore.isReady.then(() => {
            llmStore.initialize();
        });

        // NOTE: No longer need thread subscription since threads load automatically via fetchData

        return llmStore;
    }
};

registry.category("services").add("llm.store", llmStoreService);