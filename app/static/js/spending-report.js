(() => {
  const colors = ["#7c6cff", "#36d399", "#ffb648", "#26c6da", "#ff6470", "#9b8cff"];
  const svg = document.getElementById("category-chart");
  const tooltip = document.getElementById("category-tooltip");
  if (svg && tooltip) {
    const currency = svg.dataset.currency || "€";
    const series = JSON.parse(svg.dataset.series || "[]");
    const ns = "http://www.w3.org/2000/svg";
    const radius = 78;
    const circumference = 2 * Math.PI * radius;
    let offset = 0;
    series.forEach((item, index) => {
      const circle = document.createElementNS(ns, "circle");
      const portion = item.percentage / 100;
      circle.setAttribute("cx", "110"); circle.setAttribute("cy", "110");
      circle.setAttribute("r", String(radius)); circle.setAttribute("fill", "none");
      circle.setAttribute("stroke", colors[index % colors.length]);
      circle.setAttribute("stroke-width", "28");
      circle.setAttribute("stroke-dasharray", `${portion * circumference} ${circumference}`);
      circle.setAttribute("stroke-dashoffset", String(-offset * circumference));
      circle.setAttribute("transform", "rotate(-90 110 110)");
      circle.setAttribute("tabindex", "0");
      circle.setAttribute("aria-label", `${item.name}: ${currency}${Number(item.amount).toFixed(2)}, ${item.percentage.toFixed(1)} percent`);
      const show = () => {
        tooltip.textContent = `${item.name} · ${currency}${Number(item.amount).toFixed(2)} · ${item.percentage.toFixed(1)}%`;
        tooltip.classList.add("visible"); circle.classList.add("active");
      };
      const hide = () => { tooltip.classList.remove("visible"); circle.classList.remove("active"); };
      circle.addEventListener("mouseenter", show); circle.addEventListener("focus", show);
      circle.addEventListener("mouseleave", hide); circle.addEventListener("blur", hide);
      svg.appendChild(circle); offset += portion;
    });
  }

  const trend = document.getElementById("trend-chart");
  if (trend) {
    const currency = trend.dataset.currency || "€";
    const series = JSON.parse(trend.dataset.series || "[]");
    const max = Math.max(...series.map(item => item.total), 1);
    series.forEach(item => {
      const column = document.createElement("div"); column.className = "trend-column";
      const value = document.createElement("span"); value.textContent = item.total ? `${currency}${item.total.toFixed(0)}` : "—";
      const bar = document.createElement("i"); bar.style.height = `${Math.max(item.total / max * 100, item.total ? 4 : 0)}%`;
      bar.dataset.tooltip = `${item.month}: ${currency}${item.total.toFixed(2)}`;
      const label = document.createElement("b"); label.textContent = item.label;
      column.append(value, bar, label); trend.appendChild(column);
    });
  }
})();
