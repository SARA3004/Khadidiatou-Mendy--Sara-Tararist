"""Reconstruit le rapport HTML de benchmark à partir de la couche gold (dbt-duckdb).

Usage : après un `dbt run` dans dbt/, exécuter ce script pour régénérer
reports/index.html. Pas de mise à jour temps réel : on relance ce script
manuellement à chaque nouveau run de simulation ou changement de paramètres.
"""

import os
import duckdb
from pathlib import Path

ROOT = Path(__file__).parent
WAREHOUSE = ROOT / "warehouse" / "simulation.duckdb"
REPORT_PATH = ROOT / "reports" / "index.html"

# Palette catégorielle fixe (cf. skill dataviz), assignée par ordre de première apparition du modèle
CATEGORICAL = [
    {"light": "#2a78d6", "dark": "#3987e5"},  # blue
    {"light": "#1baf7a", "dark": "#199e70"},  # aqua
    {"light": "#eda100", "dark": "#c98500"},  # yellow
    {"light": "#008300", "dark": "#008300"},  # green
    {"light": "#4a3aa7", "dark": "#9085e9"},  # violet
    {"light": "#e34948", "dark": "#e66767"},  # red
    {"light": "#e87ba4", "dark": "#d55181"},  # magenta
    {"light": "#eb6834", "dark": "#d95926"},  # orange
]


def fetch_data():
    # stg_simulation_turns est une VUE qui lit "../data/bronze/turns/*.parquet" (chemin relatif
    # au dossier dbt/, là où tourne `dbt run`). On se place dans ce même dossier le temps
    # de la requête pour que ce chemin relatif se résolve correctement.
    prev_cwd = os.getcwd()
    os.chdir(ROOT / "dbt")
    try:
        con = duckdb.connect(str(WAREHOUSE), read_only=True)
        runs = con.execute("""
            select run_id, model, ruleset_version, run_started_at, max_turns,
                   turns_played, gold_collected, steps_to_first_gold,
                   avg_nearest_gold_distance, wasted_moves, llm_decision_failures
            from gold_run_summary
            order by run_started_at
        """).fetchall()
        run_cols = [d[0] for d in con.description]

        trajectories = con.execute("""
            select run_id, turn, nearest_gold_distance
            from stg_simulation_turns
            order by run_id, turn
        """).fetchall()
        con.close()
    finally:
        os.chdir(prev_cwd)

    runs = [dict(zip(run_cols, r)) for r in runs]
    traj_by_run = {}
    for run_id, turn, dist in trajectories:
        traj_by_run.setdefault(run_id, []).append((turn, dist))
    return runs, traj_by_run


def assign_colors(runs):
    models_in_order = []
    for r in runs:
        if r["model"] not in models_in_order:
            models_in_order.append(r["model"])
    return {m: CATEGORICAL[i % len(CATEGORICAL)] for i, m in enumerate(models_in_order)}


def svg_bar_chart(runs, colors):
    if not runs:
        return "<p class='empty'>Aucun run à afficher.</p>"

    width, height = 640, 260
    pad_left, pad_bottom, pad_top = 40, 30, 16
    plot_w = width - pad_left - 20
    plot_h = height - pad_bottom - pad_top

    max_steps = max((r["steps_to_first_gold"] or r["max_turns"]) for r in runs) or 1
    n = len(runs)
    slot_w = plot_w / n
    bar_w = min(28, slot_w * 0.5)

    bars, labels = [], []
    for i, r in enumerate(runs):
        steps = r["steps_to_first_gold"]
        failed = steps is None
        value = steps if not failed else r["max_turns"]
        bar_h = (value / max_steps) * plot_h
        x = pad_left + i * slot_w + (slot_w - bar_w) / 2
        y = pad_top + (plot_h - bar_h)
        color = colors[r["model"]]
        opacity = "0.35" if failed else "1"
        title = f"{r['model']} — run {r['run_id'][:8]} — " + (
            f"{steps} pas pour ramasser l'or" if not failed else "or non ramassé (timeout)"
        )
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{max(bar_h, 2):.1f}" '
            f'rx="4" fill="var(--c{list(colors).index(r["model"]) + 1})" opacity="{opacity}">'
            f'<title>{title}</title></rect>'
        )
        labels.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{height - pad_bottom + 16}" '
            f'class="axis-label" text-anchor="middle">{r["run_id"][:6]}</text>'
        )

    gridlines = []
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        y = pad_top + plot_h * (1 - frac)
        gridlines.append(f'<line x1="{pad_left}" y1="{y:.1f}" x2="{width - 20}" y2="{y:.1f}" class="grid" />')
        gridlines.append(f'<text x="{pad_left - 8}" y="{y + 4:.1f}" class="axis-label" text-anchor="end">{round(max_steps * frac)}</text>')

    return f'''
    <svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="Nombre de pas pour ramasser l'or, par run">
        {''.join(gridlines)}
        {''.join(bars)}
        {''.join(labels)}
    </svg>
    '''


def svg_trajectory_chart(runs, traj_by_run, colors):
    if not traj_by_run:
        return "<p class='empty'>Aucune trajectoire à afficher.</p>"

    width, height = 640, 260
    pad_left, pad_bottom, pad_top = 40, 30, 16
    plot_w = width - pad_left - 20
    plot_h = height - pad_bottom - pad_top

    max_turn = max(t for pts in traj_by_run.values() for t, _ in pts) or 1
    max_dist = max(d for pts in traj_by_run.values() for _, d in pts if d is not None) or 1

    paths = []
    run_by_id = {r["run_id"]: r for r in runs}
    for run_id, pts in traj_by_run.items():
        r = run_by_id[run_id]
        color_idx = list(colors).index(r["model"]) + 1
        coords = []
        for turn, dist in pts:
            x = pad_left + (turn / max_turn) * plot_w
            y = pad_top + plot_h - (dist / max_dist) * plot_h
            coords.append((x, y))
        path_d = " ".join(f'{"M" if i == 0 else "L"}{x:.1f},{y:.1f}' for i, (x, y) in enumerate(coords))
        paths.append(f'<path d="{path_d}" fill="none" stroke="var(--c{color_idx})" stroke-width="2" stroke-linecap="round" />')
        for (x, y), (turn, dist) in zip(coords, pts):
            paths.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="var(--c{color_idx})"><title>{r["model"]} — tour {turn} — distance {round(dist, 2)}</title></circle>')

    gridlines = []
    for frac in (0, 0.25, 0.5, 0.75, 1.0):
        y = pad_top + plot_h * (1 - frac)
        gridlines.append(f'<line x1="{pad_left}" y1="{y:.1f}" x2="{width - 20}" y2="{y:.1f}" class="grid" />')
        gridlines.append(f'<text x="{pad_left - 8}" y="{y + 4:.1f}" class="axis-label" text-anchor="end">{round(max_dist * frac, 1)}</text>')

    return f'''
    <svg viewBox="0 0 {width} {height}" class="chart" role="img" aria-label="Distance à l'or le plus proche au fil des tours">
        {''.join(gridlines)}
        {''.join(paths)}
    </svg>
    '''


def legend_html(colors):
    items = []
    for i, model in enumerate(colors):
        items.append(f'<span class="legend-item"><span class="swatch" style="background: var(--c{i + 1})"></span>{model}</span>')
    return f'<div class="legend">{"".join(items)}</div>'


def table_html(runs):
    rows = []
    for r in runs:
        status = "✅ ramassé" if r["gold_collected"] else "❌ non ramassé"
        rows.append(f'''
        <tr>
            <td>{r["run_id"][:8]}</td>
            <td>{r["model"]}</td>
            <td>{r["ruleset_version"]}</td>
            <td>{r["turns_played"]}</td>
            <td>{status}</td>
            <td>{r["steps_to_first_gold"] if r["steps_to_first_gold"] is not None else "—"}</td>
            <td>{round(r["avg_nearest_gold_distance"], 2)}</td>
            <td>{r["wasted_moves"]}</td>
            <td>{r["llm_decision_failures"]}</td>
        </tr>''')
    return f'''
    <table class="data-table">
        <thead><tr>
            <th>Run</th><th>Modèle</th><th>Ruleset</th><th>Tours joués</th>
            <th>Résultat</th><th>Pas pour l'or</th><th>Distance moy.</th>
            <th>Déplacements bloqués</th><th>Échecs LLM</th>
        </tr></thead>
        <tbody>{''.join(rows)}</tbody>
    </table>
    '''


def stat_tile(label, value, sublabel=""):
    return f'''
    <div class="tile">
        <div class="tile-label">{label}</div>
        <div class="tile-value">{value}</div>
        <div class="tile-sub">{sublabel}</div>
    </div>
    '''


def build_html(runs, traj_by_run):
    colors = assign_colors(runs)
    total = len(runs)
    successes = sum(1 for r in runs if r["gold_collected"])
    success_rate = f"{round(100 * successes / total)}%" if total else "—"
    steps_values = [r["steps_to_first_gold"] for r in runs if r["steps_to_first_gold"] is not None]
    avg_steps = f"{round(sum(steps_values) / len(steps_values), 1)}" if steps_values else "—"

    color_vars_light = "\n".join(f"      --c{i+1}: {c['light']};" for i, c in enumerate(colors.values()))
    color_vars_dark = "\n".join(f"      --c{i+1}: {c['dark']};" for i, c in enumerate(colors.values()))

    return f'''<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<title>Benchmark NPC Brain — reporting</title>
<style>
  :root {{
    --surface-1: #fcfcfb;
    --page: #f9f9f7;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --muted: #898781;
    --grid: #e1e0d9;
    --border: rgba(11,11,11,0.10);
{color_vars_light}
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --surface-1: #1a1a19;
      --page: #0d0d0d;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --muted: #898781;
      --grid: #2c2c2a;
      --border: rgba(255,255,255,0.10);
{color_vars_dark}
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px; background: var(--page); color: var(--text-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .subtitle {{ color: var(--text-secondary); margin: 0 0 28px; font-size: 14px; }}
  .tiles {{ display: flex; gap: 16px; margin-bottom: 28px; flex-wrap: wrap; }}
  .tile {{
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px;
    padding: 16px 20px; min-width: 160px; flex: 1;
  }}
  .tile-label {{ font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }}
  .tile-value {{ font-size: 28px; font-weight: 600; margin-top: 4px; }}
  .tile-sub {{ font-size: 12px; color: var(--text-secondary); margin-top: 2px; }}
  section {{
    background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px;
    padding: 20px; margin-bottom: 20px; overflow-x: auto;
  }}
  section h2 {{ font-size: 15px; margin: 0 0 12px; }}
  .chart {{ width: 100%; height: auto; display: block; }}
  .grid {{ stroke: var(--grid); stroke-width: 1; }}
  .axis-label {{ fill: var(--muted); font-size: 10px; }}
  .legend {{ display: flex; gap: 16px; margin-top: 8px; flex-wrap: wrap; }}
  .legend-item {{ font-size: 12px; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; }}
  .swatch {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
  .data-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  .data-table th {{
    text-align: left; color: var(--muted); font-weight: 500; font-size: 11px;
    text-transform: uppercase; letter-spacing: .03em; padding: 8px 10px; border-bottom: 1px solid var(--grid);
  }}
  .data-table td {{ padding: 8px 10px; border-bottom: 1px solid var(--grid); font-variant-numeric: tabular-nums; }}
  .empty {{ color: var(--muted); font-size: 13px; }}
</style>
</head>
<body>
  <h1>Benchmark NPC Brain</h1>
  <p class="subtitle">Reporting généré depuis la couche gold (dbt-duckdb) — à régénérer via <code>dbt run</code> + <code>python generate_report.py</code> après chaque nouveau run ou changement de règles.</p>

  <div class="tiles">
    {stat_tile("Runs enregistrés", total)}
    {stat_tile("Taux de succès", success_rate, f"{successes}/{total} runs ont ramassé l'or")}
    {stat_tile("Pas moyens jusqu'à l'or", avg_steps, "parmi les runs réussis")}
  </div>

  <section>
    <h2>Nombre de pas pour ramasser l'or, par run</h2>
    {svg_bar_chart(runs, colors)}
    {legend_html(colors)}
  </section>

  <section>
    <h2>Distance à l'or le plus proche au fil des tours</h2>
    {svg_trajectory_chart(runs, traj_by_run, colors)}
    {legend_html(colors)}
  </section>

  <section>
    <h2>Détail par run</h2>
    {table_html(runs)}
  </section>
</body>
</html>
'''


def main():
    runs, traj_by_run = fetch_data()
    html = build_html(runs, traj_by_run)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(html, encoding="utf-8")
    print(f"Rapport régénéré : {REPORT_PATH} ({len(runs)} run(s))")


if __name__ == "__main__":
    main()
