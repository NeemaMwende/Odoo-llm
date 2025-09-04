# LLM Thread - Odoo 18.0 Migration Guide

## Component Verification: What Actually Exists in Odoo 18.0

### **✅ Components That Exist (Can Extend/Use):**
- `Composer` - `/mail/core/common/composer.js` + template `mail.Composer`
- `Thread` - `/mail/core/common/thread.js` (formerly ThreadView)
- `Message` - `/mail/core/common/message.js`  
- `MailAttachmentDropzone` - `/mail/core/common/mail_attachment_dropzone.js` (formerly DropZone)
- `mail.Chatter` - Template exists in `/mail/chatter/web/chatter.xml`

### **❌ Components That Don't Exist (With Alternative Approaches):**

#### **1. ChatterTopbar → Chatter Template Extension**
- **❌ What's Gone:** No separate `ChatterTopbar` component
- **✅ Alternative:** Extend `mail.Chatter` template's topbar section
- **🎯 Hook Point:** `name="chatter-topbar-left-buttons"` template slot
- **📁 File:** `/mail/chatter/web/chatter.xml` (lines 6-78)

#### **2. MessageList → Thread Component**
- **❌ What's Gone:** No separate `MessageList` component  
- **✅ Alternative:** `Thread` component handles message rendering
- **🎯 Extension:** Patch `Thread.orderedMessages` getter or `mail.Thread` template
- **📁 Files:** `/mail/core/common/thread.js` + `thread.xml`

#### **3. ComposerTextInput → Composer Textarea**
- **❌ What's Gone:** No separate `ComposerTextInput` component
- **✅ Alternative:** `Composer` has integrated textarea with suggestion system
- **🎯 Extension:** Patch `Composer.onKeydown()` or override textarea template
- **📁 Files:** `/mail/core/common/composer.js` + `composer.xml` (lines 44-67)

#### **4. AttachmentBox → AttachmentList Component**
- **❌ What's Gone:** No separate `AttachmentBox` component
- **✅ Alternative:** `AttachmentList` component within Chatter
- **🎯 Extension:** Use existing `AttachmentList` or patch Chatter template
- **📁 File:** `/mail/core/common/attachment_list.js`

#### **5. ActivityBox → Activity Components**
- **❌ What's Gone:** No separate `ActivityBox` component
- **✅ Alternative:** `Activity` components with `mail.ActivityList` template
- **🎯 Extension:** Patch `Activity` component or extend activity templates
- **📁 File:** `/mail/core/web/activity.js`

### **✅ Services/Models That Exist:**
- `mail.store` service - `/mail/core/common/store_service.js`
- `Record` class - `/mail/core/common/record.js`
- Thread, Message, Composer models

### **❌ Services That Don't Exist:**
- `messaging` service - Use `mail.store` instead

---

## Architecture Analysis: Odoo 16.0 vs 18.0

### **What We Had in Odoo 16.0 (Current Patterns)**

Our llm_thread module follows these patterns:

1. **JavaScript Model Patches**: Extended mail models using `registerPatch()` 
2. **Messaging Components**: Used `registerMessagingComponent()` for UI components
3. **Component Extension**: Extended mail components like `ComposerTextInput`, `MessageList`
4. **State Management**: Used messaging service's reactive model system
5. **Template Inheritance**: Extended mail templates like `mail.ChatterTopbar`, `mail.Chatter`

### **What Changed in Odoo 18.0 (New Architecture)**

1. **Record-Based State Management**: Uses `Record.one()`, `Record.many()` reactive system
2. **Service-Oriented Architecture**: Centralized `mail.store` service manages all state  
3. **Direct Component Registration**: Standard OWL components with service injection
4. **No Template Inheritance**: Templates are standalone, no more mail template inheritance
5. **Event-Driven Updates**: Bus service handles real-time updates

---

## Migration Strategy: Adapt Mail Architecture Patterns

### **Phase 1: Create LLM Store Service (Similar to mail.store)**

Following mail module's store service pattern:

```javascript
// /llm_thread/static/src/services/llm_store_service.js
import { reactive } from "@odoo/owl";
import { Record } from "@mail/core/common/record";
import { registry } from "@web/core/registry";

export class LLMThread extends Record {
    static id = "id";
    static _name = "LLMThread";
    
    // Record fields similar to mail.Thread
    name = "";
    messages = Record.many("LLMMessage");
    composer = Record.one("LLMComposer", { 
        compute: () => ({}),
        inverse: "thread"
    });
    model_id = Record.one("LLMModel");
    provider_id = Record.one("LLMProvider");
    isStreaming = false;
    
    // Business logic methods
    async sendMessage(content) {
        // Create optimistic message like mail does
        const tempMessage = this.store.LLMMessage.insert({
            id: `temp_${Date.now()}`,
            content: content,
            author: this.store.self,
            thread: this,
            isPending: true,
            date: luxon.DateTime.now()
        });
        
        try {
            // Start LLM streaming
            await this.startLLMStream(content);
        } catch (error) {
            tempMessage.hasFailed = true;
        }
    }
    
    async startLLMStream(content) {
        this.isStreaming = true;
        const eventSource = new EventSource(
            `/llm/thread/generate?thread_id=${this.id}&message=${encodeURIComponent(content)}`
        );
        
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleStreamMessage(data);
        };
        
        eventSource.onerror = () => {
            this.isStreaming = false;
            eventSource.close();
        };
    }
    
    handleStreamMessage(data) {
        switch (data.type) {
            case "message_create":
                this.store.LLMMessage.insert(data.message);
                break;
            case "message_chunk":
                const message = this.store.LLMMessage.get(data.message.id);
                if (message) {
                    message.update(data.message);
                }
                break;
            case "done":
                this.isStreaming = false;
                break;
        }
    }
}

export class LLMMessage extends Record {
    static id = "id";
    static _name = "LLMMessage";
    
    content = "";
    author = Record.one("Persona");
    thread = Record.one("LLMThread");
    llm_role = ""; // "user" or "assistant"
    date = "";
    isPending = false;
    hasFailed = false;
}

export class LLMComposer extends Record {
    static id = "thread";
    static _name = "LLMComposer";
    
    thread = Record.one("LLMThread");
    text = "";
    isDisabled = false;
    
    get canSend() {
        return this.text.trim() && !this.thread.isStreaming;
    }
    
    async send() {
        if (!this.canSend) return;
        
        const content = this.text.trim();
        this.text = "";
        
        await this.thread.sendMessage(content);
    }
}

// Store Service
export const llmStoreService = {
    dependencies: ["orm", "bus_service", "mail.store"],
    
    start(env, services) {
        const store = reactive({
            // Records
            LLMThread,
            LLMMessage, 
            LLMComposer,
            
            // Computed properties
            get threadList() {
                return Object.values(this.LLMThread.records)
                    .filter(thread => thread.displayToSelf)
                    .sort((a, b) => new Date(b.write_date) - new Date(a.write_date));
            },
            
            get activeThread() {
                return this.discuss?.activeThread;
            },
            
            // Initialize
            async initialize() {
                await this.loadThreads();
            },
            
            async loadThreads() {
                const threads = await services.orm.searchRead(
                    "llm.thread",
                    [["user_id", "=", services.user.userId]],
                    ["id", "name", "provider_id", "model_id", "write_date"]
                );
                
                threads.forEach(thread => {
                    this.LLMThread.insert(thread);
                });
            }
        });
        
        // Initialize records
        Record.register(LLMThread);
        Record.register(LLMMessage);
        Record.register(LLMComposer);
        
        return store;
    }
};

registry.category("services").add("llm.store", llmStoreService);
```

### **Phase 2: Update Components to Use New Architecture**

#### **2.1 Client Action (Following mail's DiscussClientAction pattern)**

```javascript
// /llm_thread/static/src/client_actions/llm_chat_action.js
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class LLMChatClientAction extends Component {
    static template = "llm_thread.LLMChatClientAction";
    static props = ["*"];
    
    setup() {
        this.llmStore = useState(useService("llm.store"));
        this.initialize();
    }
    
    async initialize() {
        await this.llmStore.initialize();
        
        // Handle initial thread selection
        const { action } = this.props;
        const activeId = action.context?.active_id || action.params?.active_id;
        
        if (activeId) {
            await this.llmStore.selectThread(activeId);
        } else if (this.llmStore.threadList.length > 0) {
            await this.llmStore.selectThread(this.llmStore.threadList[0].id);
        }
    }
}

registry.category("actions").add("llm_thread.chat_client_action", LLMChatClientAction);
```

#### **2.2 Thread List Component (Following mail's thread list pattern)**

```javascript
// /llm_thread/static/src/components/thread_list/thread_list.js
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class LLMThreadList extends Component {
    static template = "llm_thread.LLMThreadList";
    static props = {};
    
    setup() {
        this.llmStore = useState(useService("llm.store"));
    }
    
    get threads() {
        return this.llmStore.threadList;
    }
    
    get activeThread() {
        return this.llmStore.activeThread;
    }
    
    async onThreadClick(thread) {
        await this.llmStore.selectThread(thread.id);
    }
    
    async onNewChatClick() {
        const newThread = await this.llmStore.createThread();
        await this.llmStore.selectThread(newThread.id);
    }
}
```

#### **2.3 Thread Component (Following mail's Thread pattern)**

⚠️ **IMPORTANT**: No separate `MessageList` component exists!

In Odoo 18.0:
- **❌ MessageList component** - doesn't exist  
- **✅ Thread component** - handles message display
- **✅ Message component** - individual message rendering

**Updated Approach:**
```javascript
// /llm_thread/static/src/components/thread/llm_thread.js
import { Component, useState, useRef, useEffect } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// Extend or use the existing Thread component pattern
export class LLMThread extends Component {
    static template = "llm_thread.LLMThread";
    static props = {};
    
    setup() {
        this.llmStore = useState(useService("llm.store"));
        this.scrollRef = useRef("scroll");
        
        useEffect(() => {
            this.scrollToBottom();
        }, () => [this.messages.length, this.isStreaming]);
    }
    
    get thread() {
        return this.llmStore.activeThread;
    }
    
    get messages() {
        return this.thread?.messages || [];
    }
    
    get isStreaming() {
        return this.thread?.isStreaming || false;
    }
    
    scrollToBottom() {
        if (this.scrollRef.el) {
            this.scrollRef.el.scrollTop = this.scrollRef.el.scrollHeight;
        }
    }
}
```

#### **2.4 Composer Component (Extending mail's Composer)**

✅ **GOOD NEWS**: `Composer` component exists and can be extended!

```javascript
// /llm_thread/static/src/components/composer/llm_composer.js  
import { Composer } from "@mail/core/common/composer";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

// Option 1: Extend existing Composer
export class LLMComposer extends Composer {
    static template = "llm_thread.LLMComposer";
    
    setup() {
        super.setup();
        this.llmStore = useService("llm.store");
    }
    
    get isLLMThread() {
        return this.thread?.model === 'llm.thread';
    }
    
    get isStreaming() {
        return this.isLLMThread && this.thread?.isStreaming;
    }
    
    async onSendClick() {
        if (this.isLLMThread) {
            // Custom LLM send logic
            await this.thread.sendLLMMessage(this.text);
            this.clear();
        } else {
            // Default mail behavior
            return super.onSendClick();
        }
    }
    
    onStopClick() {
        if (this.isLLMThread) {
            this.thread.stopStreaming();
        }
    }
}

// Option 2: Patch existing Composer for LLM threads
patch(Composer.prototype, {
    setup() {
        super.setup();
        if (this.thread?.model === 'llm.thread') {
            this.llmStore = useService("llm.store");
        }
    }
});
```

### **Phase 3: Handle Chatter Integration (Updated Approach)**

⚠️ **IMPORTANT**: `ChatterTopbar` component doesn't exist in Odoo 18.0!

The chatter architecture changed:
- **❌ No ChatterTopbar component** - integrated into main Chatter template
- **❌ No mail.ChatterTopbar template** - doesn't exist
- **✅ mail.Chatter template exists** - but topbar is embedded within it

**Updated Integration Approach:**
```javascript
// /llm_thread/static/src/components/chatter_patch/chatter_patch.js
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

// Since there's no ChatterTopbar, we need to patch the Chatter template directly
// or create a separate integration point

// Option 1: Add AI button via template inheritance of mail.Chatter
// Option 2: Create custom chatter enhancement
// Option 3: Use activity/attachment integration points
```

**Template Integration (Updated):**
```xml
<!-- Extend mail.Chatter template instead of non-existent ChatterTopbar -->
<t t-name="llm_thread.ChatterAIButton" t-inherit="mail.Chatter" t-inherit-mode="extension">
    <xpath expr="//div[hasclass('o-mail-Chatter-topbar')]" position="inside">
        <button class="btn btn-primary" t-on-click="onAiChatClick">
            <i class="fa fa-robot"/> AI Chat
        </button>
    </xpath>
</t>
```

### **Phase 4: Migration Checklist**

#### **Files to Migrate:**

1. **✅ Create New Architecture:**
   - `services/llm_store_service.js` - Central state management using Record system
   - `client_actions/llm_chat_action.js` - Main client action
   - `components/thread_list/thread_list.js` - Thread list component
   - `patches/thread_patch.js` - Patch Thread component for LLM messages
   - `patches/composer_patch.js` - Patch Composer for LLM input handling
   - `patches/chatter_patch.js` - Add AI button to chatter topbar

2. **🔄 Update Existing Files:**
   - Remove all `registerMessagingComponent()` calls
   - Remove all `registerPatch()` model extensions from `/models/` directory
   - Convert to `patch()` system from `@web/core/utils/patch`
   - Update component props to use standard OWL patterns
   - Replace template inheritance with template extension

3. **❌ Remove Deprecated:**
   - `/models/` directory entirely (old model patches)
   - `llm_chatter_topbar.xml` - Use chatter template extension instead
   - `llm_chatter.xml` - Use standard chatter with patches
   - Old messaging component registrations
   - Template files that inherit from non-existent templates

#### **Key Differences from Mail Module:**

1. **LLM-Specific Features:**
   - Streaming message updates (EventSource)
   - Model/provider selection
   - Tool integration
   - Real-time AI response handling

2. **State Management:**
   - Extend Record system for LLM entities
   - Handle streaming state reactively
   - Manage tool/model configurations

3. **Component Behavior:**
   - Optimistic UI for user messages
   - Progressive AI response display
   - Streaming indicators
   - Stop/retry functionality

---

## Implementation Order:

1. **Create LLM Store Service** - Foundation layer
2. **Update Client Action** - Entry point  
3. **Migrate Core Components** - UI layer
4. **Update Templates** - Remove inheritance
5. **Test Integration** - Verify functionality  
6. **Add LLM Features** - Streaming, tools, etc.

## **Alternative Component Patterns (Exact Implementation)**

### **1. Message List Alternative: Thread Component**

**How Thread Renders Messages:**
```javascript
// /mail/core/common/thread.js
export class Thread extends Component {
    static components = { Message, Transition, DateSection };
    
    get orderedMessages() {
        return this.props.order === "asc"
            ? [...this.props.thread.nonEmptyMessages]
            : [...this.props.thread.nonEmptyMessages].reverse();
    }
}
```

**Template Structure:**
```xml
<!-- /mail/core/common/thread.xml -->
<t t-foreach="orderedMessages" t-as="msg" t-key="msg.id">
    <Message
        className="getMessageClassName(msg)"
        message="msg"
        thread="props.thread"
        squashed="isSquashed(msg, prevMsg)"
    />
</t>
```

**LLM Extension Pattern:**
```javascript
// Patch Thread for LLM-specific message rendering
patch(Thread.prototype, {
    getMessageClassName(message) {
        let className = super.getMessageClassName(message);
        if (message.llm_role === 'assistant') {
            className += ' o-llm-ai-message';
        }
        return className;
    }
});
```

### **2. Topbar Alternative: Chatter Template Extension**

**How Chatter Renders Topbar:**
```xml
<!-- /mail/chatter/web/chatter.xml lines 6-78 -->
<div class="o-mail-Chatter-topbar d-flex flex-shrink-0">
    <t t-else="" name="chatter-topbar-left-buttons">
        <button class="o-mail-Chatter-sendMessage btn" 
                t-on-click="() => this.toggleComposer('message')">
            Send message
        </button>
        <!-- More buttons -->
    </t>
</div>
```

**LLM Extension Pattern:**
```xml
<!-- Extend Chatter topbar -->
<t t-name="llm_thread.ChatterExtension" t-inherit="mail.Chatter" t-inherit-mode="extension">
    <xpath expr="//t[@name='chatter-topbar-left-buttons']" position="after">
        <button class="btn btn-primary" t-on-click="toggleAIChat">
            <i class="fa fa-robot"/> AI Chat
        </button>
    </xpath>
</t>
```

### **3. Text Input Alternative: Composer Textarea**

**How Composer Handles Input:**
```xml
<!-- /mail/core/common/composer.xml lines 44-67 -->
<textarea class="o-mail-Composer-input"
    t-ref="textarea"
    t-on-keydown="onKeydown"
    t-model="props.composer.text"
    t-att-placeholder="placeholder"
/>
```

**JavaScript Handling:**
```javascript
// /mail/core/common/composer.js
onKeydown(ev) {
    switch (ev.key) {
        case "Enter":
            const shouldPost = this.props.mode === "extended" ? ev.ctrlKey : !ev.shiftKey;
            if (shouldPost) {
                this.sendMessage();
            }
            break;
    }
}
```

**LLM Extension Pattern:**
```javascript
// Patch Composer for LLM threads
patch(Composer.prototype, {
    onKeydown(ev) {
        if (this.isLLMThread && ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendLLMMessage();
            return;
        }
        super.onKeydown(ev);
    },
    
    get isLLMThread() {
        return this.props.composer.thread?.model === 'llm.thread';
    },
    
    async sendLLMMessage() {
        const content = this.props.composer.text;
        await this.props.composer.thread.sendLLMMessage(content);
        this.props.composer.clear();
    }
});
```

### **4. Component Architecture (New Structure)**

```
Chatter (main container)
├── Thread (handles message list)
│   └── Message components (individual messages)
├── Composer (handles text input + actions)
│   ├── Textarea (direct DOM element)
│   └── Suggestion system (mentions/commands)
├── AttachmentList (file handling)
└── Activity components (activity management)
```

### **5. Extension Points Summary**

| **Old Component** | **New Alternative** | **Extension Method** | **Hook Point** |
|-------------------|--------------------|--------------------|----------------|
| ChatterTopbar | Chatter template | Template inheritance | `name="chatter-topbar-left-buttons"` |
| MessageList | Thread component | Patch `orderedMessages` | `getMessageClassName()` method |
| ComposerTextInput | Composer textarea | Patch `onKeydown()` | `sendMessage()` method |
| AttachmentBox | AttachmentList | Use existing component | Chatter template section |
| ActivityBox | Activity components | Patch Activity | `mail.ActivityList` template |

This approach reuses Odoo's proven mail architecture patterns while adding LLM-specific functionality through strategic patches and extensions.