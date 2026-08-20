(function () {
  var stored = localStorage.getItem("smart-task-theme");
  var isDark = stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.classList.toggle("dark", isDark);
})();
