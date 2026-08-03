document.addEventListener("click", function (event) {
  var button = event.target.closest(".js-use-location");
  if (!button) {
    return;
  }

  if (!navigator.geolocation) {
    window.alert("Geolocation is not available in this browser.");
    return;
  }

  var targetId = button.getAttribute("data-location-target");
  var input = targetId ? document.getElementById(targetId) : null;
  if (!input) {
    return;
  }

  navigator.geolocation.getCurrentPosition(
    function (position) {
      input.value = position.coords.latitude + "," + position.coords.longitude;
    },
    function () {
      window.alert("We could not read your location. Please enter it manually.");
    }
  );
});

(function monitorEvidenceScanning() {
  var containers = Array.prototype.slice.call(document.querySelectorAll(".js-evidence-status"));
  containers.forEach(function (container) {
    var statusUrl = container.getAttribute("data-status-url");
    var evidenceId = container.getAttribute("data-evidence-id");
    var state = container.querySelector(".evidence-state");
    if (!statusUrl || !evidenceId || !state || !state.querySelector(".badge.pending")) {
      return;
    }

    var attempts = 0;
    var stopped = false;

    function renderStatus(payload) {
      if (!payload || String(payload.evidence_id) !== evidenceId || !document.body.contains(container)) {
        stopped = true;
        return;
      }
      if (payload.status === "clean" && payload.downloadable) {
        state.innerHTML = '<span class="badge clean">Ready</span> <a class="btn secondary evidence-download" href="/participant-portal/evidence/' + encodeURIComponent(evidenceId) + '">Open file</a>';
        stopped = true;
      } else if (payload.status === "infected") {
        state.innerHTML = '<span class="badge rejected">Rejected</span> <span class="muted">This file was blocked by malware screening. Upload a different file before submitting.</span>';
        stopped = true;
      } else if (payload.status === "failed" || payload.status === "scan_failed") {
        state.innerHTML = '<span class="badge rejected">Scan failed</span> <span class="muted">The file cannot be opened. Please try uploading it again.</span>';
        stopped = true;
      }
    }

    function poll() {
      if (stopped || attempts >= 24) {
        return;
      }
      if (document.visibilityState === "hidden") {
        window.setTimeout(poll, 5000);
        return;
      }
      attempts += 1;
      window.fetch(statusUrl, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        cache: "no-store"
      }).then(function (response) {
        if (!response.ok) {
          throw new Error("status unavailable");
        }
        return response.json();
      }).then(renderStatus).catch(function () {
        // Keep the page usable and retry transient connection failures.
      }).finally(function () {
        if (!stopped && attempts < 24) {
          window.setTimeout(poll, 5000);
        }
      });
    }

    window.setTimeout(poll, 1500);
  });
})();
