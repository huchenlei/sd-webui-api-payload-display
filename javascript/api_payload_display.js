{
    const registeredElements = new Set();

    function waitForData(dataElement) {
        return new Promise((resolve) => {
            const oldData = dataElement.value;
            const intervalId = setInterval(() => {
                if (dataElement.value != oldData) {
                    resolve(dataElement.value);
                    clearInterval(intervalId);
                }
            }, 200);
        });
    }

    function updateJsonTree(wrapper, data) {
        // Create json-tree
        const tree = jsonTree.create(JSON.parse(data), wrapper);
        // Expand all (or selected) child nodes of root
        tree.expand(function (node) {
            return node.childNodes.length < 2;
        });
    }

    onUiUpdate(() => {
        const panels = gradioApp().querySelectorAll(".api-payload-display");
        if (!panels) return;

        for (const panel of panels) {
            if (registeredElements.has(panel)) continue;
            const pullButton = panel.querySelector('.api-payload-pull');
            const payloadTextbox = panel.querySelector('.api-payload-content textarea');
            const wrapper = panel.querySelector('.api-payload-json-tree');
            const processType = pullButton.id.replace('-api-payload-pull', '');
            const generateButton = gradioApp().querySelector(
                processType === 'txt2img' ? '#txt2img_generate' : '#img2img_generate');

            if (!generateButton) continue;

            generateButton.addEventListener('click', () => {
                // There is id conflict on the page. So apply class selector
                // as well.
                const resultElement = gradioApp().querySelector(
                    `#${processType}_results`);

                new MutationObserver((_, observer) => {
                    // The click is only triggered when
                    // - generation button is clicked
                    // - progress bar appears
                    const dataPromise = waitForData(payloadTextbox);
                    pullButton.click();
                    dataPromise.then(data => updateJsonTree(wrapper, data));

                    observer.disconnect();
                }).observe(resultElement, { childList: true });
            });

            registeredElements.add(panel);
        }
    });
}
