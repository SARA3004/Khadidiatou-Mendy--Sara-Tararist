# npc_brain — NPC piloté par LLM + benchmark data engineering

## Setup

```bash
uv venv .venv && source .venv/bin/activate
uv pip install numpy openai python-dotenv pydantic pyarrow duckdb dbt-duckdb
```

Variables d'environnement requises (`.env`) : `LLM_API_URL`, `LLM_API_TOKEN`, `MODEL`.

## Architecture de la simulation

Le notebook enchaîne quelques briques simples : la carte du monde, la perception du joueur (ce qu'on transmet au LLM), le moteur de déplacement, l'appel au LLM pour décider, et la boucle de jeu qui répète tout ça jusqu'à la victoire ou la limite de tours.

## Choix de game design (SPECS §1.2)

| Règle | Décision | Pourquoi |
|---|---|---|
| Pièces à ramasser | Une seule |
| Combats | Aucun | Les ennemis ne sont que des obstacles, pas des adversaires|
| Carte de départ | Fixe, avec un ennemi sur le chemin direct | 


## Pipeline de données 

Architecture en médaillon, avec Parquet + DuckDB + dbt-duckdb :

- **Bronze** — les logs bruts de chaque partie, un fichier Parquet par run.
- **Silver** ([`stg_simulation_turns.sql`](dbt/models/staging/stg_simulation_turns.sql)) — nettoyage et indicateurs par tour (mouvement bloqué, échec de décision LLM, tendance de la distance à l'or).
- **Gold** ([`gold_run_summary.sql`](dbt/models/marts/gold_run_summary.sql)) — un run = une ligne de KPI (victoire ou non, nombre de pas, déplacements ratés, échecs LLM).

```bash
cd dbt && dbt run
```
## Benchmark / reporting

[`generate_report.py`](generate_report.py) lit la couche Gold dans DuckDB et régénère [`reports/index.html`](reports/index.html) (graphiques + tableau par run).

```bash
python generate_report.py
```


## Structure du repo

```
prOjet2/
├── npc_brain.ipynb        # jeu + appel LLM + écriture bronze
├── data/bronze/turns/     # logs bruts, un fichier parquet par run
├── dbt/models/            # couches silver et gold
├── warehouse/             # base DuckDB
├── generate_report.py     # génère le rapport HTML
└── reports/index.html     # rapport final
```
