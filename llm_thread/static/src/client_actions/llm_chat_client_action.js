/** @odoo-module **/

import { Component, useState, onWillStart, onWillDestroy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { LLMChatContainer } from "@llm_thread/components/llm_chat_container/llm_chat_container";

/**
 * LLM Chat Client Action - Main entry point for LLM chat functionality
 * Follows Odoo 18.0 client action pattern similar to DiscussClientAction
 */
export class LLMChatClientAction extends Component {
    static components = { LLMChatContainer };
    static props = ["*"];
    static template = "llm_thread.LLMChatClientAction";

    setup() {
        this.llmStore = useState(useService("llm.store"));
        this.mailStore = useState(useService("mail.store"));
        this.orm = useService("orm");
        this.notification = useService("notification");
        
        onWillStart(() => {
            return this.initializeLLMChat(this.props);
        });
        
        onWillDestroy(() => {
            this.cleanup();
        });
    }

    /**
     * Initialize LLM chat based on action context
     * Similar to how DiscussClientAction handles thread restoration
     */
    async initializeLLMChat(props) {
        try {
            // Ensure LLM store is initialized
            await this.llmStore.initialize();

            const activeId = this.getActiveId(props);
            
            if (activeId) {
                if (activeId.startsWith('llm.thread_')) {
                    // Direct LLM thread reference
                    const threadId = parseInt(activeId.split('_')[1]);
                    await this.selectLLMThread(threadId);
                } else {
                    // Open form to create new LLM thread for the referenced record
                    await this.openCreateThreadForm(props);
                }
            } else {
                // No specific context, load user's recent threads
                await this.loadUserThreads();
            }
            
        } catch (error) {
            console.error('Error initializing LLM chat:', error);
            this.notification.add('Failed to initialize AI chat', { type: 'danger' });
        }
    }

    /**
     * Get active ID from action context, similar to DiscussClientAction
     */
    getActiveId(props) {
        return (
            props.action.context?.active_id ??
            props.action.params?.active_id ??
            props.action.context?.default_active_id
        );
    }

    /**
     * Select an existing LLM thread
     */
    async selectLLMThread(threadId) {
        try {
            // Load LLM thread data into our store
            await this.llmStore.loadLLMThread(threadId);
            
            // Create/update thread in mail.store for display
            const threadData = await this.orm.read('llm.thread', [threadId], [
                'id', 'name'
            ]);
            
            if (threadData.length > 0) {
                const thread = threadData[0];
                
                // Insert as a thread in mail.store with all required fields
                const threadToInsert = {
                    id: threadId,
                    model: 'llm.thread',
                    name: thread.name,
                    displayName: thread.name,
                    // Add more fields that might be required
                    channel_type: 'llm_chat',  // Use custom channel type for LLM
                    message_needaction_counter: 0,
                    message_unread_counter: 0,
                    isLoaded: true,
                };
                
                console.log('Inserting thread record:', threadToInsert);
                
                // Try both possible key formats
                try {
                    this.mailStore.insert({
                        'mail.thread': [threadToInsert]
                    });
                    console.log('✓ Inserted with mail.thread key');
                } catch (error) {
                    console.log('✗ Failed with mail.thread key:', error);
                    
                    // Try with llm.thread key
                    try {
                        this.mailStore.insert({
                            'llm.thread': [threadToInsert]
                        });
                        console.log('✓ Inserted with llm.thread key');
                    } catch (error2) {
                        console.log('✗ Failed with llm.thread key:', error2);
                    }
                }
                
                // Immediately check if it was inserted
                const immediateCheck = this.mailStore.Thread.get(['llm.thread', threadId]);
                console.log('Immediate check after insertion:', immediateCheck);
                
                // Debug: Show all threads in store
                console.log('All threads in mail.store:', this.mailStore.Thread.records);

                // Load messages for this thread
                await this.loadThreadMessages(threadId);
                
                // Set as active thread in discuss - ensure discuss exists first
                if (!this.mailStore.discuss) {
                    // Create discuss object if it doesn't exist
                    this.mailStore.insert({
                        'mail.thread': [],  // Empty to trigger discuss creation
                    });
                }
                
                // Use correct Thread.get() format: { model, id }
                const threadRecord = this.mailStore.Thread.get({ 
                    model: 'llm.thread', 
                    id: threadId 
                });
                console.log('Thread retrieved with correct format:', threadRecord);
                
                if (this.mailStore.discuss && threadRecord) {
                    this.mailStore.discuss.thread = threadRecord;
                    console.log('Active thread set to:', this.mailStore.discuss.thread);
                } else {
                    console.error('Failed to set active thread - discuss:', this.mailStore.discuss, 'thread:', threadRecord);
                }
                
                // Thread is now set in mail.store.discuss.thread - no additional tracking needed
            }
            
        } catch (error) {
            console.error('Error selecting LLM thread:', error);
            this.notification.add('Failed to load chat thread', { type: 'danger' });
        }
    }

    /**
     * Open llm.thread form to create new thread for a specific record
     */
    async openCreateThreadForm(props) {
        try {
            const context = props.action.context || {};
            const resModel = context.default_res_model;
            const resId = context.default_res_id;
            const name = context.default_name || `AI Chat - ${resModel} #${resId}`;

            await this.action.doAction({
                name: 'Create AI Chat',
                type: 'ir.actions.act_window',
                res_model: 'llm.thread',
                view_mode: 'form',
                views: [[false, 'form']],
                target: 'new',
                context: {
                    default_name: name,
                    default_model: resModel,
                    default_res_id: resId,
                }
            });
            
        } catch (error) {
            console.error('Error opening create thread form:', error);
            this.notification.add('Failed to open chat creation form', { type: 'danger' });
        }
    }

    /**
     * Load user's existing LLM threads
     */
    async loadUserThreads() {
        try {
            const threads = await this.orm.searchRead(
                'llm.thread',
                [['user_id', '=', user.userId]],
                ['id', 'name', 'write_date'],
                { order: 'write_date DESC', limit: 1 }
            );

            if (threads.length > 0) {
                await this.selectLLMThread(threads[0].id);
            }
            // No auto-creation - let user create threads via form
            
        } catch (error) {
            console.error('Error loading user threads:', error);
            this.notification.add('Failed to load chat threads', { type: 'danger' });
        }
    }

    /**
     * Load messages for a thread via the thread's message_ids field
     * This avoids domain filtering issues on mail.message
     */
    async loadThreadMessages(threadId) {
        try {
            // Get the thread with its messages
            const threadData = await this.orm.read('llm.thread', [threadId], ['message_ids']);
            
            if (threadData.length > 0 && threadData[0].message_ids.length > 0) {
                // Load the actual message records
                const messages = await this.orm.read(
                    'mail.message', 
                    threadData[0].message_ids,
                    ['id', 'body', 'author_id', 'date', 'llm_role', 'message_type']
                );
                
                // Sort by date
                messages.sort((a, b) => new Date(a.date) - new Date(b.date));
                
                // Insert messages into mail.store
                this.mailStore.insert({ 'mail.message': messages });
            }
            
        } catch (error) {
            console.error('Error loading thread messages:', error);
        }
    }

    /**
     * Cleanup when component is destroyed
     */
    cleanup() {
        // Stop any streaming
        this.llmStore.destroy();
    }
}

// Register client action
registry.category("actions").add("llm_thread.chat_client_action", LLMChatClientAction);