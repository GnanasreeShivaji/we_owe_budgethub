(function () {
  function point(cx, cy, radius, angle) {
    const radians = (angle - 90) * Math.PI / 180;
    return [cx + radius * Math.cos(radians), cy + radius * Math.sin(radians)];
  }

  document.querySelectorAll(".contribution-pie").forEach(svg => {
    const values = (svg.dataset.values || "")
      .split(",")
      .map(Number)
      .filter(value => value > 0);
    const total = values.reduce((sum, value) => sum + value, 0);
    if (!total) return;

    let startAngle = 0;
    values.forEach((value, index) => {
      const sweep = value / total * 360;
      const endAngle = startAngle + sweep;
      const [startX, startY] = point(100, 100, 86, startAngle);
      const [endX, endY] = point(100, 100, 86, endAngle);
      const largeArc = sweep > 180 ? 1 : 0;
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");

      if (values.length === 1) {
        path.setAttribute("d", "M 100 14 A 86 86 0 1 1 99.99 14 Z");
      } else {
        path.setAttribute(
          "d",
          `M 100 100 L ${startX} ${startY} A 86 86 0 ${largeArc} 1 ${endX} ${endY} Z`
        );
      }
      path.setAttribute("class", `chart-color-${index % 5}`);
      path.setAttribute("stroke", "var(--card)");
      path.setAttribute("stroke-width", "2");
      svg.appendChild(path);
      startAngle = endAngle;
    });
  });
})();
