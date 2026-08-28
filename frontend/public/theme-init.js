(function () {
  var stored = localStorage.getItem("smart-task-theme");
  var isDark = stored === "dark";
  document.documentElement.classList.toggle("dark", isDark);
})();
