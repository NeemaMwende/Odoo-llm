/** @odoo-module **/

/**
 * Helper function to open AI assistant chat from any button.
 * Clicks the AI button in chatter and waits for composer to appear.
 *
 * @param {Object} options - Configuration options
 * @param {number} options.maxRetries - Maximum attempts to find composer (default: 20)
 * @param {number} options.retryDelay - Delay between retries in ms (default: 100)
 * @param {boolean} options.focusComposer - Whether to focus the composer (default: true)
 */
export function openAIAssistantChat(options = {}) {
    const {
        maxRetries = 20,
        retryDelay = 100,
        focusComposer = true,
    } = options;

    // Find and click AI button in chatter
    const aiButton = document.querySelector(".o-mail-Chatter-aiChat");
    if (!aiButton) {
        console.warn("AI button not found in chatter");
        return;
    }

    aiButton.click();

    // Wait for composer with retry mechanism
    let attempts = 0;
    const findComposer = () => {
        const composer = document.querySelector(
            ".o-llm-composer-area textarea, .o-mail-Composer-input"
        );

        if (composer) {
            // Composer found! Scroll and focus
            composer.scrollIntoView({
                behavior: "smooth",
                block: "center",
            });

            if (focusComposer) {
                // Small delay to ensure scroll completes
                setTimeout(() => composer.focus(), 200);
            }
        } else if (attempts < maxRetries) {
            // Not found yet, retry
            attempts++;
            setTimeout(findComposer, retryDelay);
        } else {
            // Give up after max retries
            console.warn(`Composer not found after ${maxRetries} attempts (${maxRetries * retryDelay}ms)`);
        }
    };

    // Start polling for composer
    setTimeout(findComposer, retryDelay);
}

// Make available globally for onclick handlers
window.openAIAssistantChat = openAIAssistantChat;
