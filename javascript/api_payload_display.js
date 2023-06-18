{
    const registeredElements = new Set();
    onUiUpdate(() => {
        const panels = gradioApp().querySelectorAll(".api-payload-display");
        if (!panels) return;

        for (const panel of panels) {
            if (registeredElements.has(panel)) continue;
            const pullButton = panel.querySelector('.api-payload-pull');
            const processType = pullButton.id.replace('-api-payload-pull', '');
            const generateButton = gradioApp().querySelector(
                processType === 'txt2img' ? '#txt2img_generate' : '#img2img_generate');

            if (!generateButton) continue;
            generateButton.addEventListener('click', (_, observer) => {
                // There is id conflict on the page. So apply class selector
                // as well.
                const generationInfoElement = gradioApp().querySelector(
                    `#html_info_${processType}.gradio-html`);
                new MutationObserver(() => {
                    // The click is only triggered when
                    // - generation button is clicked
                    // - generation_info has updated
                    pullButton.click();
                    observer.disconnect();
                }).observe(generationInfoElement, { childList: true, subtree: true, });
            });
            registeredElements.add(panel);
        }
    });
}
