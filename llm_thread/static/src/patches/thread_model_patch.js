/** @odoo-module **/

import { Thread } from "@mail/core/common/thread_model";
import { patch } from "@web/core/utils/patch";
import { router } from "@web/core/browser/router";

/**
 * Patch Thread model to properly handle llm.thread URLs
 */
patch(Thread.prototype, {
  /**
   * Update action context with active_id
   * @param {String} activeId - Active ID to set
   */
  _updateActionContext(activeId) {
    if (
      !this.store?.action_discuss_id ||
      !this.store.env?.services?.action?.currentController?.action
    ) {
      return;
    }

    const currentAction =
      this.store.env.services.action.currentController.action;
    if (currentAction.id !== this.store.action_discuss_id) {
      return;
    }

    // Keep the action stack up to date (used by breadcrumbs).
    if (!currentAction.context) {
      currentAction.context = {};
    }
    currentAction.context.active_id = activeId;
  },

  /**
   * Override setActiveURL to handle llm.thread model
   */
  setActiveURL() {
    // Handle llm.thread model specifically
    if (this.model === "llm.thread") {
      try {
        const activeId = `llm.thread_${this.id}`;

        // Safely update router state
        if (router && router.pushState) {
          router.pushState({ active_id: activeId });
        }

        // Update action context if available
        this._updateActionContext(activeId);
      } catch (error) {
        console.warn("Error updating URL for LLM thread:", error);
        // Continue without failing
      }
    } else {
      // For all other models, use the original implementation
      super.setActiveURL();
    }
  },
});
