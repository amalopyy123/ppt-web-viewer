import * as pdfjsLib from "/static/pdfjs/pdf.mjs";
pdfjsLib.GlobalWorkerOptions.workerSrc = "/static/pdfjs/pdf.worker.mjs";
const viewer = document.querySelector("#viewer");
const status = document.querySelector("#page-status");
const errorBox = document.querySelector("#error");
const prev = document.querySelector("#prev");
const next = document.querySelector("#next");
let pdf;
let currentPage = 1;
let scale = 1;

async function renderPage(number) {
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
    viewer.replaceChildren(wrapper);
    await page.render({ canvasContext: canvas.getContext("2d", { alpha: false }), viewport, transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : null }).promise;
    const textContent = await page.getTextContent();
    pdfjsLib.renderTextLayer({ textContentSource: textContent, container: textLayer, viewport });
    status.textContent = String(number) + " / " + String(pdf.numPages);
    prev.disabled = number <= 1;
    next.disabled = number >= pdf.numPages;
}

async function load() {
    try {
        pdf = await pdfjsLib.getDocument("/document.pdf").promise;
        await renderPage(currentPage);
    } catch (error) {
        console.error(error);
        errorBox.hidden = false;
        status.textContent = "Failed";
    }
}
prev.addEventListener("click", async () => { if (currentPage > 1) { currentPage -= 1; await renderPage(currentPage); } });
next.addEventListener("click", async () => { if (currentPage < pdf.numPages) { currentPage += 1; await renderPage(currentPage); } });
document.querySelector("#zoom-out").addEventListener("click", async () => { scale = Math.max(0.6, scale - 0.2); await renderPage(currentPage); });
document.querySelector("#zoom-in").addEventListener("click", async () => { scale = Math.min(3, scale + 0.2); await renderPage(currentPage); });
load();
