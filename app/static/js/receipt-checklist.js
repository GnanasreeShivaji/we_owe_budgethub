(() => {
  const scanButton = document.getElementById("scan-receipt");
  if (!scanButton) return;

  const receiptInput = document.getElementById("receipt");
  const amountInput = document.getElementById("amount");
  const splitMethod = document.getElementById("split_method");
  const splitPanel = document.getElementById("split-panel");
  const checklist = document.getElementById("receipt-checklist");
  const status = document.getElementById("receipt-scan-status");
  const form = scanButton.closest("form");
  const currencySelect = document.getElementById("currency");
  const symbols = {EUR: "€", USD: "$", INR: "₹", GBP: "£"};

  const escapeHtml = (value) => String(value)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;");

  scanButton.addEventListener("click", async () => {
    const file = receiptInput.files && receiptInput.files[0];
    if (!file) {
      status.textContent = "Choose a receipt image first.";
      return;
    }
    scanButton.disabled = true;
    status.textContent = "Reading product names and prices…";
    const data = new FormData();
    data.append("receipt", file);
    const csrf = form.querySelector('input[name="csrf_token"]');
    if (csrf) data.append("csrf_token", csrf.value);
    try {
      const response = await fetch(scanButton.dataset.scanUrl, {method: "POST", body: data});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Receipt scanning failed.");
      const currency = currencySelect
        ? (symbols[currencySelect.value] || `${currencySelect.value} `)
        : (result.currency || form.dataset.currencySymbol || "€");
      checklist.innerHTML = `
        <div class="receipt-checklist-head">
          <div><strong>Who had each item?</strong><span>Tick one person, or several to divide an item equally.</span></div>
          <strong>${currency}${escapeHtml(result.total)}</strong>
        </div>
        <input type="hidden" name="receipt_item_count" value="${result.items.length}">
        ${result.items.map((item, index) => `
          <div class="receipt-item-row">
            <div class="receipt-item-name">
              <label>Name<input name="receipt_item_name_${index}" value="${escapeHtml(item.name)}" maxlength="180" required></label>
              <label>Qty<input class="receipt-quantity" type="number" name="receipt_item_quantity_${index}" value="${escapeHtml(item.quantity)}" min="1" max="100" required></label>
              <label>Unit price<input class="receipt-unit-price" type="number" name="receipt_item_unit_price_${index}" value="${escapeHtml(item.unit_price)}" min="0.01" step="0.01" required></label>
              <strong class="receipt-line-total">${currency}${escapeHtml(item.price)}</strong>
            </div>
            <div class="receipt-member-checks">
              ${result.members.map(member => `<label><input type="checkbox" name="receipt_item_${index}_member_${member.id}" value="1" ${result.members.length === 1 ? "checked" : ""}><span>${escapeHtml(member.name)}</span></label>`).join("")}
            </div>
          </div>`).join("")}`;
      checklist.hidden = false;
      const recalculate = () => {
        let total = 0;
        checklist.querySelectorAll(".receipt-item-row").forEach(row => {
          const quantity = Number(row.querySelector(".receipt-quantity").value || 0);
          const unit = Number(row.querySelector(".receipt-unit-price").value || 0);
          const line = quantity * unit; total += line;
          row.querySelector(".receipt-line-total").textContent = `${currency}${line.toFixed(2)}`;
        });
        amountInput.value = total.toFixed(2);
        checklist.querySelector(".receipt-checklist-head > strong").textContent = `${currency}${total.toFixed(2)}`;
        amountInput.dispatchEvent(new Event("input", {bubbles: true}));
      };
      checklist.querySelectorAll(".receipt-quantity,.receipt-unit-price").forEach(input => input.addEventListener("input", recalculate));
      amountInput.value = result.total;
      amountInput.dispatchEvent(new Event("input", {bubbles: true}));
      if (splitMethod) splitMethod.value = "receipt";
      if (splitPanel) splitPanel.hidden = true;
      status.textContent = `${result.items.length} items found. Check the people who had each one.`;
    } catch (error) {
      status.textContent = error.message;
      checklist.hidden = true;
    } finally {
      scanButton.disabled = false;
    }
  });
})();
