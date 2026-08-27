document.addEventListener("click", function (event) {
  var target = event.target.closest("[data-confirm]");
  if (!target) {
    return;
  }

  var message = target.getAttribute("data-confirm") || "Are you sure?";
  if (!window.confirm(message)) {
    event.preventDefault();
  }
});

document.addEventListener("submit", function (event) {
  var form = event.target;
  if (!(form instanceof HTMLFormElement)) {
    return;
  }

  var submitter = event.submitter;
  if (!submitter || submitter.hasAttribute("data-no-loading")) {
    return;
  }

  submitter.classList.add("is-loading");
  submitter.setAttribute("aria-busy", "true");
  submitter.disabled = true;

  if (!submitter.dataset.loadingLabel) {
    submitter.dataset.loadingLabel = submitter.textContent || "Submit";
  }
  submitter.textContent = "Working...";
});

function restoreWorkingControls() {
  document.querySelectorAll("button.is-loading, input.is-loading, .btn.is-loading").forEach(function (control) {
    control.classList.remove("is-loading");
    control.removeAttribute("aria-busy");
    control.disabled = false;
    if (control.dataset.loadingLabel) {
      control.textContent = control.dataset.loadingLabel;
    }
  });
}

// Browsers may restore this DOM from their back/forward cache after a form
// navigation. Restore transient UI state before a researcher can be trapped
// behind a stale disabled “Working…” action.
window.addEventListener("pageshow", restoreWorkingControls);
window.addEventListener("pagehide", function () {
  // Keep bfcache snapshots free of client-only submission state.
  restoreWorkingControls();
});

function setConditionalFields(scope) {
  var selector = scope.querySelector("[data-response-type]");
  if (!selector) return;
  var needsChoices = ["single_choice", "multiple_choice", "ranking"].includes(selector.value);
  scope.querySelectorAll("[data-choice-options]").forEach(function (field) {
    field.hidden = !needsChoices;
    field.querySelectorAll("textarea, input").forEach(function (control) {
      control.disabled = !needsChoices;
    });
  });
}

document.querySelectorAll("form").forEach(function (form) {
  setConditionalFields(form);
  var responseType = form.querySelector("[data-response-type]");
  if (responseType) responseType.addEventListener("change", function () { setConditionalFields(form); });
  var aiToggle = form.querySelector("input[name='ai_enabled']");
  var aiTasks = form.querySelector("[data-ai-tasks]");
  if (aiToggle && aiTasks) {
    var syncAiTasks = function () { aiTasks.hidden = !aiToggle.checked; };
    syncAiTasks();
    aiToggle.addEventListener("change", syncAiTasks);
  }
  var specialCategory = form.querySelector("[data-special-category]");
  var articleNine = form.querySelector("[data-article-nine]");
  if (specialCategory && articleNine) {
    var syncArticleNine = function () { articleNine.hidden = specialCategory.value !== "yes"; };
    syncArticleNine();
    specialCategory.addEventListener("change", syncArticleNine);
  }
});
