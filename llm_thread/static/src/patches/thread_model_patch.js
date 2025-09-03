/** @odoo-module **/

import { Thread } from "@mail/core/common/thread_model";
import { patch } from "@web/core/utils/patch";
import { router } from "@web/core/browser/router";

/**
 * Patch Thread model to properly handle llm.thread URLs
 */
patch(Thread.prototype, {
    /**
     * Override setActiveURL to handle llm.thread model
     */
    setActiveURL() {
        // Handle llm.thread model specifically
        if (this.model === "llm.thread") {
            const activeId = `llm.thread_${this.id}`;
            router.pushState({ active_id: activeId });
            
            if (
                this.store.action_discuss_id &&
                this.store.env.services.action?.currentController?.action.id ===
                    this.store.action_discuss_id
            ) {
                // Keep the action stack up to date (used by breadcrumbs).
                this.store.env.services.action.currentController.action.context.active_id = activeId;
            }
        } else {
            // For all other models, use the original implementation
            super.setActiveURL();
        }
    },
});