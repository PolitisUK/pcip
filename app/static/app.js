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
