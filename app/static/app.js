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
