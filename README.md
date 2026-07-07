# npc_brain — NPC piloté par LLM + benchmark data engineering

Le principe : un joueur se déplace sur une grille et doit ramasser de l'or, mais ses déplacements ne
sont pas décidés par un algorithme classique — à chaque tour, c'est un LLM (en local via LM Studio)
qui reçoit un résumé de la situation et qui choisit une direction. Le vrai objectif du projet n'est
pas de faire un jeu, c'est de réfléchir à combien on précalcule "à la main" (l'algo) et combien on
laisse au LLM, et de mesurer ça proprement avec une vraie pipeline data (bronze/silver/gold + dbt +
reporting).

Ce README explique les choix qu'on a faits et pourquoi. 

## Setup

```bash
uv venv .venv && source .venv/bin/activate
uv pip install numpy openai python-dotenv pydantic pyarrow duckdb dbt-duckdb
```

`.env` attendu :

```
LLM_API_URL=http://127.0.0.1:1234/v1
LLM_API_TOKEN=...
MODEL=...
```

`LLM_API_URL` pointe vers un serveur compatible OpenAI — on utilise LM Studio en local, donc l'URL se
termine toujours par `/v1`. `MODEL` doit correspondre exactement à l'identifiant affiché dans l'onglet
"Local Server" de LM Studio (souvent avec un préfixe du genre `mistralai/...`).

## Architecture

Tout est dans `npc_brain.ipynb`, organisé en sections sous des titres markdown, dans l'ordre où on les
a écrites :

1. **Modélisation du monde** — la carte est un `np.array` d'entiers (`VOID`, `PLAYER`, `ENNEMY`,
   `GOLD`), `initial_map` définit le layout de départ.
2. **Couche de contrat** — `Direction` (enum HAUT/BAS/GAUCHE/DROITE) et `PlayerDecision` (le schéma
   pydantic que le LLM doit remplir).
3. **Moteur de perception** — `perception(world_map)` calcule ce qu'on transmet au LLM à chaque tour.
4. **Moteur de déplacement** — `allowed_move` / `move`.
5. **Moteur de décision** — `decide()` construit le prompt et appelle le LLM.
6. **Game loop** — `game_loop()` fait tourner tout ça tour par tour et écrit les logs en bronze.
7. **Benchmark multi-modèles** — boucle qui répète `game_loop` sur plusieurs modèles, ajoutée une fois
   le reste stabilisé (détails plus bas).

### Le compromis perception algorithmique vs raisonnement LLM

C'est le vrai sujet du projet (cf. `SPECS.md`) : si on précalcule trop dans `perception()`, le LLM n'a
plus qu'à recopier la réponse et ça ne teste plus grand-chose d'intéressant sur lui. Si on précalcule
trop peu, il doit faire du calcul spatial que même un petit LLM fait mal.

Ce qu'on a choisi de précalculer dans `perception()` :

- les distances euclidiennes (numpy, `compute_distances`) à chaque pièce d'or et à chaque ennemi,
- un **delta signé** vers l'or le plus proche (`nearest_gold_delta`, ex. `{"row": -1, "col": 0}`) avec
  la même convention de signe que `MOVES` — c'est une info brute, pas une direction toute faite, le
  LLM doit quand même la traduire en HAUT/BAS/GAUCHE/DROITE,
- l'historique des 5 derniers déplacements (`move_history`), pour que le LLM évite de rester coincé
  dans un aller-retour sans "mémoire" de ce qu'il vient de faire.

Ce qu'on laisse volontairement au LLM : traduire le delta en direction, juger s'il vaut mieux passer
près d'un ennemi ou faire un détour, et ne pas répéter les mêmes erreurs. Aujourd'hui la perception
reste "omnisciente" (le LLM voit les distances à tout ce qui existe sur la carte, pas seulement ce qui
est proche de lui) — limiter le champ de vision serait une façon assez naturelle de pousser le
curseur encore plus loin côté LLM, mais on ne l'a pas encore fait (cf. limites plus bas).

### Le moteur de décision

`decide()` appelle `client.beta.chat.completions.parse(..., response_format=PlayerDecision)` : on
force directement une sortie JSON conforme au schéma pydantic, en une seule passe, à
`temperature=0.2`. `PlayerDecision` ne contient qu'un champ `direction` pour l'instant — on avait
envisagé de demander en plus une justification textuelle (`directionJustification`, encore présent en
commentaire dans le code), mais on l'a laissée de côté pour garder le parsing simple et les runs
rapides. C'est une piste si on veut un jour observer le raisonnement du LLM et pas juste sa décision
finale.

### Règles de déplacement / game design

| Règle | Décision | Pourquoi |
|---|---|---|
| Pièces à ramasser | Une seule (la partie s'arrête dès qu'elle est ramassée) | On garde le scope minimal pour avancer en priorité sur la partie data engineering (pipeline dbt-duckdb, benchmark). Si le temps le permet, on étendra à "toutes les pièces". |
| Combats | Aucun | Les ennemis sont des obstacles géométriques (case infranchissable via `allowed_move`), pas des adversaires — un vrai système de combat ajouterait de la complexité sans rapport avec l'objectif (mesurer la qualité de navigation/décision du LLM). |
| Carte de départ | Fixe (`initial_map`), avec un ennemi entre le joueur et la pièce la plus proche | Ça oblige déjà le joueur à contourner un obstacle pour atteindre l'or le plus proche, ce qui teste une vraie capacité de décision plutôt que "foncer tout droit". |

### Pipeline de données (architecture médaillon)

- **Bronze** (`data/bronze/turns/*.parquet`) — un fichier parquet par run, écrit directement à la fin
  de `game_loop()` via pyarrow (`pa.Table.from_pylist` + `pq.write_table`), une ligne par tour. Chaque
  ligne porte un `ruleset_version` (`single_gold_no_combat_v1`) pour pouvoir regrouper/filtrer les
  runs correctement si les règles du jeu changent plus tard, sans avoir à réinterpréter en silence un
  schéma qui aurait changé de sens.
- **Silver** ([`stg_simulation_turns.sql`](dbt/models/staging/stg_simulation_turns.sql)) — lit tous
  les parquet bronze via une source dbt, type les colonnes, et calcule deux indicateurs par tour :
  `llm_decision_failed` (le LLM n'a renvoyé aucune direction exploitable) et `move_blocked` (une
  direction a été donnée mais le joueur n'a pas bougé — mur ou case ennemie), plus une moyenne
  glissante sur 3 tours de la distance à l'or le plus proche.
- **Gold** ([`gold_run_summary.sql`](dbt/models/marts/gold_run_summary.sql)) — un run = une ligne :
  `gold_collected`, `steps_to_first_gold`, `avg_nearest_gold_distance`, `wasted_moves`,
  `llm_decision_failures`.
- **Reporting** ([`generate_report.py`](generate_report.py)) — lit la couche gold via duckdb et
  régénère un rapport HTML statique (`reports/index.html`) avec deux graphes SVG faits main (pas par
  run, distance à l'or au fil des tours) et un tableau détaillé, coloré par modèle. Pas de mise à jour
  en temps réel : on relance `dbt run` puis le script à la main après chaque run ou changement de
  règles, ce qui correspond à ce que demande `SPECS.md`.

```bash
cd dbt && dbt run
cd .. && python generate_report.py
```

## Le benchmark

### Pourquoi, et sur quel axe

`SPECS.md` propose trois axes de benchmark possibles : la charge cognitive algorithmique, la qualité
du raisonnement du LLM, et le modèle utilisé. Pour l'instant on travaille sur le troisième : comparer
plusieurs modèles (via LM Studio) sur exactement le même layout et les mêmes règles, pour voir si la
taille ou la famille du modèle change la qualité des décisions. Les deux autres axes (faire varier ce
qu'on précalcule, ou la façon de prompter) restent des pistes ouvertes.

### Comment ça tourne

`decide()` et `game_loop()` prennent maintenant un paramètre `model` (plutôt que de dépendre
uniquement de la variable globale `MODEL` lue depuis `.env`), plus un flag `verbose` pour ne pas
inonder la sortie de logs quand on enchaîne plusieurs runs. La cellule "Benchmark multi-modèles" boucle
sur une liste `MODELS` et répète `game_loop` `RUNS_PER_MODEL` fois par modèle, en passant au modèle
suivant si un appel échoue plutôt que de faire planter toute la boucle.

### Une limite matérielle découverte en le mettant en place

En testant la boucle, on s'est rendu compte que la machine ne tient qu'un seul modèle chargé en
mémoire à la fois dans LM Studio : charger un deuxième modèle pendant qu'un autre était déjà chargé
échouait systématiquement, alors que ça fonctionne très bien une fois l'ancien modèle déchargé
(vérifié avec la CLI `lms`). Deux modèles téléchargés (`qwen/qwen3.5-9b` et `google/gemma-4-12b-qat`)
refusent en plus de se charger même seuls, pour une raison qu'on n'a pas encore creusée. Du coup,
aujourd'hui, seuls `qwen2.5-coder-3b-instruct` et `mistralai/ministral-3-3b` sont confirmés
utilisables, et changer de modèle chargé dans LM Studio entre deux lots de runs reste une étape
manuelle — la boucle ne pilote pas encore LM Studio elle-même.

## Structure du repo

```
ETL/
├── npc_brain.ipynb        # jeu + appel LLM + écriture bronze + boucle benchmark
├── data/bronze/turns/     # logs bruts, un fichier parquet par run
├── dbt/models/            # couches silver et gold
├── warehouse/             # base DuckDB
├── generate_report.py     # génère le rapport HTML
└── reports/index.html     # rapport final
```

