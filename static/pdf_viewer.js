import * as pdfjsLib from "/static/pdfjs/pdf.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc = "/static/pdfjs/pdf.worker.mjs";

const viewer = document.querySelector("#viewer");
const status = document.querySelector("#page-status");
const errorBox = document.querySelector("#error");
let pdf;
let scale = 1;
let rendering = false;

function fitScale(page) {
    const baseViewport = page.getViewport({ scale: 1 });
    const availableWidth = Math.max(240, viewer.clientWidth - 8);
    return availableWidth / baseViewport.width;
}

async function renderAllPages() {
    if (!pdf || rendering) return;
    rendering = true;
    viewer.replaceChildren();
    try {
        for (let number = 1; number <= pdf.numPages; number += 1) {
            const page = await pdf.getPage(number);
            const viewport = page.getViewport({ scale });
            const wrapper = document.createElement("section");
            wrapper.className = "page";
            wrapper.style.width = String(viewport.width) + "px";
            wrapper.style.height = String(viewport.height) + "px";

            const canvas = document.createElement("canvas");
            const ratio = window.devicePixelRatio || 1;
            canvas.width = Math.floor(viewport.width * ratio);
            canvas.height = Math.floor(viewport.height * ratio);
            canvas.style.width = String(viewport.width) + "px";
            canvas.style.height = String(viewport.height) + "px";
            wrapper.appendChild(canvas);

            const textLayer = document.createElement("div");
            textLayer.className = "text-layer";
            wrapper.appendChild(textLayer);
            viewer.appendChild(wrapper);

            await page.render({
                canvasContext: canvas.getContext("2d", { alpha: false }),
                viewport,
                transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : null,
            }).promise;

            const textContent = await page.getTextContent();
            const textLayerBuilder = new pdfjsLib.TextLayer({
                textContentSource: textContent,
                container: textLayer,
                viewport,
            });
            await textLayerBuilder.render();
            status.textContent = String(number) + " / " + String(pdf.numPages);
        }
    } finally {
        rendering = false;
    }
}

async function load() {
    try {
        pdf = await pdfjsLib.getDocument("/document.pdf").promise;
        const firstPage = await pdf.getPage(1);
        scale = fitScale(firstPage);
        await renderAllPages();
    } catch (error) {
        console.error(error);
        errorBox.hidden = false;
        status.textContent = "Failed";
    }
}

document.querySelector("#zoom-out").addEventListener("click", async () => {
    scale = Math.max(0.5, scale - 0.15);
    await renderAllPages();
});

document.querySelector("#zoom-in").addEventListener("click", async () => {
    scale = Math.min(3, scale + 0.15);
    await renderAllPages();
});

let resizeTimer;
window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(async () => {
        if (!pdf) return;
        const firstPage = await pdf.getPage(1);
        scale = fitScale(firstPage);
        await renderAllPages();
    }, 250);
});

load();
