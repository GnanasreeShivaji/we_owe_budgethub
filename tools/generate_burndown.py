#!/usr/bin/env python3
"""Generate a task-hours table and burndown line chart for every Trello sprint.

Usage:
  python tools/generate_burndown.py BOARD.json --progress sprint_progress.json

Each task contains its estimated hours remaining at the end of every session.
Use null when a task was not worked on during that session.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

SPRINT_RE = re.compile(r"Sprint\s*:\s*(Sprint\s*\d+)", re.I)
POINTS_RE = re.compile(r"Story\s*Points\s*:\s*(\d+)", re.I)


def sprint_number(name):
    match = re.search(r"\d+", name)
    return int(match.group()) if match else 999


def read_sprints(board):
    result = {}
    for card in board.get("cards", []):
        desc = card.get("desc", "")
        sprint_match, points_match = SPRINT_RE.search(desc), POINTS_RE.search(desc)
        if sprint_match and points_match:
            sprint = sprint_match.group(1).title()
            result.setdefault(sprint, []).append({
                "name": card.get("name", "Unnamed task").split(" [")[0],
                "points": int(points_match.group(1)),
            })
    return dict(sorted(result.items(), key=lambda item: sprint_number(item[0])))


def task_rows(stories, config, session_count):
    configured = config.get("tasks", {})
    rows = []
    for story in stories:
        values = configured.get(story["name"])
        if values is None:
            values = [story["points"]] + [None] * (session_count - 1)
        values = (values + [None] * session_count)[:session_count]
        rows.append((story["name"], values))
    return rows


def carry_totals(rows, count):
    current = [0.0] * len(rows)
    totals = []
    for column in range(count):
        for index, (_, values) in enumerate(rows):
            if values[column] is not None:
                current[index] = float(values[column])
        totals.append(sum(current))
    return totals


def svg_chart(sprint, stories, config):
    sessions = config.get("sessions") or ["Start"]
    rows = task_rows(stories, config, len(sessions))
    totals = carry_totals(rows, len(sessions))
    max_hours = max(totals + [1])

    width, left, right = 920, 105, 870
    table_top, header_h, row_h = 55, 42, 40
    task_width = 410
    col_width = (right - left - task_width) / len(sessions)
    table_bottom = table_top + header_h + row_h * len(rows)
    chart_top, chart_bottom = table_bottom + 85, table_bottom + 385
    height = chart_bottom + 65

    def x(index):
        if len(sessions) == 1:
            return (left + right) / 2
        return left + index * (right - left) / (len(sessions) - 1)

    def y(value):
        return chart_bottom - value / max_hours * (chart_bottom - chart_top)

    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<style>
text {{ font-family: Arial, sans-serif; fill:#172033 }}
.title {{ font-size:26px; font-weight:bold }} .head {{ font-size:17px; font-weight:bold; fill:white }}
.cell {{ font-size:15px }} .axis {{ font-size:13px }}
.grid {{ stroke:#b9c7dc; stroke-width:1 }} .border {{ stroke:#263244; stroke-width:1.5 }}
</style><rect width="100%" height="100%" fill="white"/>
<text x="{left}" y="34" class="title">{html.escape(sprint)} Burndown Chart</text>
<rect x="{left}" y="{table_top}" width="{right-left}" height="{header_h}" fill="#397fca" class="border"/>
<text x="{left+task_width/2}" y="{table_top+27}" text-anchor="middle" class="head">User stories / tasks</text>''']

    for index, session in enumerate(sessions):
        cell_x = left + task_width + index * col_width
        parts.append(f'<line x1="{cell_x}" y1="{table_top}" x2="{cell_x}" y2="{table_bottom}" class="border"/>')
        parts.append(f'<text x="{cell_x+col_width/2}" y="{table_top+27}" text-anchor="middle" class="head">{html.escape(session)}</text>')

    for row_index, (name, values) in enumerate(rows):
        row_y = table_top + header_h + row_index * row_h
        parts.append(f'<rect x="{left}" y="{row_y}" width="{right-left}" height="{row_h}" fill="#eef2f7" class="border"/>')
        parts.append(f'<text x="{left+10}" y="{row_y+26}" class="cell">{html.escape(name)}</text>')
        for col_index, value in enumerate(values):
            cell_x = left + task_width + col_index * col_width
            parts.append(f'<line x1="{cell_x}" y1="{row_y}" x2="{cell_x}" y2="{row_y+row_h}" class="border"/>')
            label = "" if value is None else f"{value:g}"
            parts.append(f'<text x="{cell_x+col_width/2}" y="{row_y+26}" text-anchor="middle" class="cell">{label}</text>')

    ticks = 5
    for tick in range(ticks + 1):
        value = max_hours * tick / ticks
        yy = y(value)
        parts.append(f'<line x1="{left}" y1="{yy}" x2="{right}" y2="{yy}" class="grid"/>')
        parts.append(f'<text x="{left-12}" y="{yy+5}" text-anchor="end" class="axis">{value:g}</text>')

    for index, session in enumerate(sessions):
        parts.append(f'<text x="{x(index)}" y="{chart_bottom+28}" text-anchor="middle" class="axis">{html.escape(session)}</text>')

    points = " ".join(f"{x(i):.1f},{y(total):.1f}" for i, total in enumerate(totals))
    parts.append(f'<polyline points="{points}" fill="none" stroke="#1769aa" stroke-width="4"/>')
    for index, total in enumerate(totals):
        parts.append(f'<circle cx="{x(index):.1f}" cy="{y(total):.1f}" r="8" fill="#1594df" stroke="#1769aa" stroke-width="2"/>')
        parts.append(f'<text x="{x(index):.1f}" y="{y(total)-14:.1f}" text-anchor="middle" class="axis">{total:g}h</text>')

    parts.append(f'<text x="28" y="{(chart_top+chart_bottom)/2}" transform="rotate(-90 28 {(chart_top+chart_bottom)/2})" text-anchor="middle" class="cell">Remaining hours</text>')
    parts.append('</svg>')
    return "".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("trello_json", type=Path)
    parser.add_argument("--progress", type=Path, default=Path("sprint_progress.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/burndown"))
    args = parser.parse_args()
    board = json.loads(args.trello_json.read_text(encoding="utf-8"))
    progress = json.loads(args.progress.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    for sprint, stories in read_sprints(board).items():
        output = args.output / f'{sprint.lower().replace(" ", "-")}-burndown.svg'
        output.write_text(svg_chart(sprint, stories, progress.get(sprint, {})), encoding="utf-8")
    print(f"Charts generated in {args.output.resolve()}")


if __name__ == "__main__":
    main()
