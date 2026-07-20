(() => {
  const panel = document.getElementById("payer-panel");
  const totalInput = document.querySelector('input[name="amount"]');
  const preview = document.getElementById("payment-preview");
  if (!panel || !totalInput || !preview) return;

  const form = panel.closest("form");
  const currencySelect = document.getElementById("currency");
  const symbols = {EUR: "€", USD: "$", INR: "₹", GBP: "£"};
  const currency = () => currencySelect
    ? (symbols[currencySelect.value] || `${currencySelect.value} `)
    : (form.dataset.currencySymbol || "€");

  const rows = [...panel.querySelectorAll(".split-member")];

  function update() {
    const total = Number(totalInput.value || 0);
    let paid = 0;
    let selected = 0;
    rows.forEach((row) => {
      const check = row.querySelector(".payer-check");
      const amount = row.querySelector(".payment-value");
      amount.disabled = !check.checked;
      if (check.checked) {
        selected += 1;
        paid += Number(amount.value || 0);
      }
    });

    if (selected === 1) {
      const only = rows.find((row) => row.querySelector(".payer-check").checked);
      const input = only.querySelector(".payment-value");
      if (!input.value && total > 0) {
        input.value = total.toFixed(2);
        paid = total;
      }
    }

    const remaining = total - paid;
    const symbol = currency();
    document.querySelectorAll(".expense-currency-marker").forEach((item) => { item.textContent = symbol; });
    preview.textContent = selected
      ? `Paid ${symbol}${paid.toFixed(2)} of ${symbol}${total.toFixed(2)} · ${remaining === 0 ? "Complete" : `Remaining ${symbol}${remaining.toFixed(2)}`}`
      : "Select at least one payer.";
    preview.classList.toggle("error", selected === 0 || Math.abs(remaining) > 0.009);
  }

  panel.addEventListener("input", update);
  panel.addEventListener("change", update);
  totalInput.addEventListener("input", update);
  if (currencySelect) currencySelect.addEventListener("change", update);
  update();
})();
