(() => {
  const form = document.getElementById("research-assistant-form");
  const submit = document.getElementById("research-assistant-submit");
  const progress = document.getElementById("research-assistant-progress");
  if (!form || !submit || !progress) return;
  form.addEventListener("submit", () => {
    submit.disabled = true;
    submit.setAttribute("aria-disabled", "true");
    progress.hidden = false;
  });
})();
