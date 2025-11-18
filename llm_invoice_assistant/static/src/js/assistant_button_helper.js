/** @odoo-module **/

/**
 * Helper function to open AI assistant chat from any button.
 * Clicks the AI button in chatter and scrolls to the composer.
 *
 * @param {Object} options - Configuration options
 * @param {number} options.clickDelay - Delay before clicking AI button (ms)
 * @param {number} options.scrollDelay - Delay before scrolling to composer (ms)
 * @param {boolean} options.focusComposer - Whether to focus the composer
 */
export function openAIAssistantChat(options = {}) {
    const {
        clickDelay = 100,
        scrollDelay = 300,
        focusComposer = true,
    } = options;

    setTimeout(() => {
        // Find and click AI button in chatter
        const aiButton = document.querySelector(".o-mail-Chatter-aiChat");
        if (!aiButton) {
            console.warn("AI button not found in chatter");
            return;
        }

        aiButton.click();

        // Wait for AI chat to open, then scroll to composer
        setTimeout(() => {
            const composer = document.querySelector(
                ".o-llm-composer-area textarea, .o-mail-Composer-input"
            );
            if (composer) {
                composer.scrollIntoView({
                    behavior: "smooth",
                    block: "center",
                });

                if (focusComposer) {
                    composer.focus();
                }
            } else {
                console.warn("Composer not found");
            }
        }, scrollDelay);
    }, clickDelay);
}

// Make available globally for onclick handlers
window.openAIAssistantChat = openAIAssistantChat;
