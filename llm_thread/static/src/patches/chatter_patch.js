/** @odoo-module **/

import { Chatter } from "@mail/chatter/web_portal/chatter";
import { LLMChatContainer } from "@llm_thread/components/llm_chat_container/llm_chat_container";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

// Register LLMChatContainer component with Chatter
Object.assign(Chatter.components, { LLMChatContainer });

/**
 * Patch Chatter to add AI Chat functionality
 * Adds AI button to chatter topbar and inline AI chat mode
 */
patch(Chatter.prototype, {
  setup() {
    super.setup();
    this.orm = useService("orm");
    this.notification = useService("notification");
    this.busService = useService("bus_service");

    // Add LLM chat state
    Object.assign(this.state, {
      isChattingWithLLM: false,
      llmThreadId: null,
    });

    // Subscribe to bus notification for opening AI chat
    // Odoo 18 uses busService.subscribe() not addEventListener()
    this.busService.subscribe("llm.thread/open_in_chatter", (payload) => {
      console.log("[Chatter] Bus notification received!", payload);
      this.handleOpenAIChatNotification(payload);
    });

    console.log("[Chatter] Subscribed to llm.thread/open_in_chatter");
  },

  /**
   * Handle notification to open AI chat in chatter
   *
   * @param {Object} data - Notification payload
   */
  async handleOpenAIChatNotification(data) {
    const { thread_id, model, res_id } = data;

    // Only handle if notification is for THIS chatter's record
    if (this.props.threadModel !== model || this.props.threadId !== res_id) {
      return;
    }

    console.log(
      `[Chatter] Bus notification received to open AI chat for thread ${thread_id} on ${model}/${res_id}`
    );

    // If AI chat is already open, don't do anything
    if (this.state.isChattingWithLLM) {
      console.log("[Chatter] AI chat already open, ignoring notification");
      return;
    }

    // Simply trigger the existing AI button click handler
    // This reuses all the existing logic for opening AI chat
    await this.onAIChatClick();
  },

  /**
   * Check if current record supports LLM chat
   * Can be extended to support specific models or conditions
   *
   * @returns {boolean}
   */
  get shouldShowAIButton() {
    return this.props.threadModel && this.props.threadId;
  },

  /**
   * Toggle AI Chat mode - replaces chatter content with LLM chat
   */
  async onAIChatClick() {
    if (!this.shouldShowAIButton) return;

    if (this.state.isChattingWithLLM) {
      // Exit AI chat mode
      this.state.isChattingWithLLM = false;
      this.state.llmThreadId = null;

      // Clear discuss thread
      if (this.store.discuss) {
        this.store.discuss.thread = undefined;
      }
    } else {
      // Enter AI chat mode - find or create thread
      try {
        const threadId = await this.ensureLLMThread();
        if (threadId) {
          // Set the LLM thread as the active discuss thread
          const llmThread = this.store.Thread.insert({
            model: "llm.thread",
            id: threadId,
          });

          // Initialize discuss if needed and set thread
          if (!this.store.discuss) {
            this.store.discuss = {};
          }
          this.store.discuss.thread = llmThread;

          // Fetch thread data
          await llmThread.fetchData(["messages"]);

          this.state.isChattingWithLLM = true;
          this.state.llmThreadId = threadId;
        }
      } catch (error) {
        console.error("Failed to start AI chat:", error);
        this.notification.add(
          error.message || "Failed to start AI chat",
          { type: "danger" }
        );
      }
    }
  },

  /**
   * Find existing LLM thread for current record or create new one
   *
   * @returns {Promise<number|null>} Thread ID
   */
  async ensureLLMThread() {
    // Search for existing thread linked to this record
    const existingThreads = await this.orm.searchRead(
      "llm.thread",
      [
        ["model", "=", this.props.threadModel],
        ["res_id", "=", this.props.threadId],
      ],
      ["id"],
      { limit: 1 }
    );

    if (existingThreads.length > 0) {
      return existingThreads[0].id;
    }

    // Try to find default chat model
    let modelId = null;
    let providerId = null;

    const defaultModels = await this.orm.searchRead(
      "llm.model",
      [
        ["model_use", "in", ["chat", "multimodal"]],
        ["default", "=", true],
        ["active", "=", true],
      ],
      ["id", "provider_id"],
      { limit: 1 }
    );

    if (defaultModels.length > 0) {
      modelId = defaultModels[0].id;
      providerId = defaultModels[0].provider_id[0];
    } else {
      // Fallback: Get first provider and its first chat model
      const providers = await this.orm.searchRead(
        "llm.provider",
        [["active", "=", true]],
        ["id"],
        { limit: 1 }
      );

      if (providers.length === 0) {
        throw new Error("No active LLM provider found. Please configure a provider first.");
      }

      providerId = providers[0].id;

      const models = await this.orm.searchRead(
        "llm.model",
        [
          ["provider_id", "=", providerId],
          ["model_use", "in", ["chat", "multimodal"]],
          ["active", "=", true],
        ],
        ["id"],
        { limit: 1 }
      );

      if (models.length === 0) {
        throw new Error("No active chat model found. Please configure a model first.");
      }

      modelId = models[0].id;
    }

    // Create new thread with provider and model
    const name = `AI Chat - ${this.props.threadModel} #${this.props.threadId}`;
    const threadIds = await this.orm.create("llm.thread", [
      {
        name: name,
        model: this.props.threadModel,
        res_id: this.props.threadId,
        provider_id: providerId,
        model_id: modelId,
      },
    ]);

    // orm.create returns array of IDs, extract first one
    return Array.isArray(threadIds) ? threadIds[0] : threadIds;
  },
});
