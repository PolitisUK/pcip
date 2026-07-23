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
