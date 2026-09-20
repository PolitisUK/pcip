(() => {
  const surface = document.querySelector("[data-canvas-surface]");
  if (!surface) return;
  const viewport = document.querySelector("[data-canvas-viewport]");
  const nodes = [...surface.querySelectorAll("[data-canvas-node]")];
  const edges = [...surface.querySelectorAll("[data-canvas-edges] line")];
  const nodeByRef = new Map(nodes.map((node) => [node.dataset.nodeRef, node]));
  let scale = 1;

  function placeNode(node) {
    node.style.left = `${Number(node.dataset.x) || 0}px`;
    node.style.top = `${Number(node.dataset.y) || 0}px`;
  }

  function drawEdges() {
    edges.forEach((line) => {
      const source = nodeByRef.get(line.dataset.sourceRef);
      const target = nodeByRef.get(line.dataset.targetRef);
      if (!source || !target) {
        line.hidden = true;
        return;
      }
      line.hidden = false;
      line.setAttribute("x1", String((Number(source.dataset.x) || 0) + source.offsetWidth / 2));
      line.setAttribute("y1", String((Number(source.dataset.y) || 0) + source.offsetHeight / 2));
      line.setAttribute("x2", String((Number(target.dataset.x) || 0) + target.offsetWidth / 2));
      line.setAttribute("y2", String((Number(target.dataset.y) || 0) + target.offsetHeight / 2));
    });
  }

  function setZoom(next) {
    scale = Math.max(0.5, Math.min(1.5, next));
    surface.style.setProperty("--canvas-scale", String(scale));
    const output = document.querySelector("[data-canvas-zoom]");
    if (output) output.textContent = `${Math.round(scale * 100)}%`;
  }

  nodes.forEach((node) => {
    placeNode(node);
    const handle = node.querySelector("[data-canvas-drag]");
    const form = node.querySelector("[data-canvas-position-form]");
    if (!handle || !form) return;
    let drag = null;
    handle.addEventListener("pointerdown", (event) => {
      drag = {
        pointerX: event.clientX,
        pointerY: event.clientY,
        x: Number(node.dataset.x) || 0,
        y: Number(node.dataset.y) || 0,
      };
      handle.setPointerCapture(event.pointerId);
      node.classList.add("is-dragging");
    });
    handle.addEventListener("pointermove", (event) => {
      if (!drag) return;
      const x = Math.max(0, Math.min(4000, drag.x + (event.clientX - drag.pointerX) / scale));
      const y = Math.max(0, Math.min(4000, drag.y + (event.clientY - drag.pointerY) / scale));
      node.dataset.x = String(Math.round(x));
      node.dataset.y = String(Math.round(y));
      form.elements.x.value = node.dataset.x;
      form.elements.y.value = node.dataset.y;
      placeNode(node);
      drawEdges();
    });
    handle.addEventListener("pointerup", async () => {
      if (!drag) return;
      drag = null;
      node.classList.remove("is-dragging");
      try {
        const response = await fetch(form.action, { method: "POST", body: new FormData(form), credentials: "same-origin" });
        if (!response.ok) throw new Error("Canvas position request failed");
        const live = document.querySelector("#live-region");
        if (live) live.textContent = "Canvas position saved";
      } catch (_) {
        const live = document.querySelector("#live-region");
        if (live) live.textContent = "Canvas position could not be saved";
      }
    });
  });

  document.querySelector("[data-canvas-zoom-in]")?.addEventListener("click", () => setZoom(scale + 0.1));
  document.querySelector("[data-canvas-zoom-out]")?.addEventListener("click", () => setZoom(scale - 0.1));
  viewport?.addEventListener("scroll", drawEdges, { passive: true });
  setZoom(1);
  drawEdges();
})();
