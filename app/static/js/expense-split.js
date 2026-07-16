(function () {
  const panel = document.getElementById("split-panel");
  if (!panel) return;

  const method = document.getElementById("split_method");
  const amount = document.getElementById("amount");
  const rows = Array.from(panel.querySelectorAll(".split-member"));
  const preview = document.getElementById("split-preview");
  const hint = document.getElementById("split-hint");

  function update() {
    const mode = method.value;
    const total = Number(amount.value || 0);
    const selected = rows.filter(row => row.querySelector("[type=checkbox]").checked);
    const labels = {
      equal: "Equal split is calculated automatically.",
      exact: "Enter each person's exact amount; the total must match the expense.",
      percentage: "Enter percentages that add up to 100%.",
      shares: "Enter relative shares, for example 1, 1, 2.",
    };
    hint.textContent = labels[mode];

    rows.forEach(row => {
      const checked = row.querySelector("[type=checkbox]").checked;
      const input = row.querySelector(".split-value");
      const unit = row.querySelector(".split-unit");
      input.hidden = mode === "equal";
      input.disabled = !checked || mode === "equal";
      unit.textContent = mode === "percentage" ? "%" : mode === "exact" ? "€" : "";
    });

    if (!selected.length || !total) {
      preview.textContent = "Select participants and enter an expense amount.";
      return;
    }
    let values = selected.map(row => Number(row.querySelector(".split-value").value || 0));
    let calculated;
    if (mode === "equal") calculated = selected.map(() => total / selected.length);
    else if (mode === "percentage") calculated = values.map(value => total * value / 100);
    else if (mode === "shares") {
      const sum = values.reduce((a, b) => a + b, 0);
      calculated = values.map(value => sum ? total * value / sum : 0);
    } else calculated = values;
    preview.textContent = selected.map((row, index) =>
      `${row.querySelector(".check span").textContent}: €${calculated[index].toFixed(2)}`
    ).join(" · ");
  }

  panel.addEventListener("input", update);
  panel.addEventListener("change", update);
  update();
})();
