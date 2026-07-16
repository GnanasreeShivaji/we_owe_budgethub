// Client-side interactivity (US-02 UI): show/hide inline panels and
// confirm destructive actions before the form submits.
document.addEventListener("click", (e) => {
  const toggle = e.target.closest("[data-toggle]");
  if (toggle) {
    const panel = document.querySelector(toggle.getAttribute("data-toggle"));
    if (panel) panel.hidden = !panel.hidden;
  }
});

document.addEventListener("submit", (e) => {
  const form = e.target.closest("form[data-confirm]");
  if (form && !window.confirm(form.getAttribute("data-confirm"))) {
    e.preventDefault();
  }
});
