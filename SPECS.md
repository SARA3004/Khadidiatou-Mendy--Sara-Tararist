# Spécification du projet

**Il est attendu de vous que vous sachiez expliquer et justifier tous les éléments du projet.**

## 1. Travail préalable

### 1.1 Stabilisation de la simulation

- Mettre en place la perception directionnelle de votre choix
  - Gardez un équilibre en charge cognitive algorithmique et charge du LLM
  - Ex: Si vous mettez un algo de Manhattan en place, le LLM n'a plus grand chose à faire

### 1.2 Game design de la simulation

Définissez les règles finales de game design de la simulation :

- Le joueur doit ramasser UNE pièce ou PLUSIEURS pièce ?
- Les combats sont-il autorisés ?
- Y'a t-il des combats sur la carte ?
- Quel layout de départ (ennemis sur le chemin, pièce leurre, etc.)

## 2. Data ingénierie

Une fois la simulation stabilisée, vous devez produire un benchmark pour démontrer la qualité de votre IA. **L'objectif n'est pas d'atteindre la meilleure qualité possible mais de trouver un point d'équilibre entre charge algorithmique et LLM.**

### 2.1 Définissez les objectifs de votre benchmark

Votre benchmark peut être construit sur trois axes :

- Impact de la charge cognitive algorithmique
- Qualité de la charge du LLM
- Modèles de LLM

Ces axes ne sont pas exhaustifs, vous pouvez en inventer d'autres.

### 2.2 Définissez les KPI (aggrégats métiers) de votre benchmark

A partir de vos objectifs, définissez les indicateurs de performance qui démontreront la qualité ou la non-qualité de la simulation.

Quelques indicateurs en exemple :

- Nombre de paramètre du modèle utilisé
- Nombre de pas pour ramasser UNE pièce
- Moyenne glissante de la distance à la pièce sur le temps
- Nombre de déplacements inutiles
- ...

Il existe de très nombreux indicateurs pertinents en lien avec vos règles de simulation et le benchmark visé.

### 2.3 Architecture de data ingénierie

Contrat de sortie des données de la simulation :

- Instrumenter la ``game_loop`` pour produire des logs de simulation
- Définissez la structure des données générées par la simulation (quelles colonnes ?)
- Comment assurer une certaine cohérence avec les données déjà générées qui vous faites évoluer la simulation en cours de route ?

Pipeline de data ingénierie :

- Mettre en place une architecture en médaillon 
  - Couche bronze → résultats bruts de la simulation
  - Silver → données propres
  - Gold → aggrégats métiers
- **Utilisation obligatoire de :** parquet, duckdb, dbt-duckdb

Etape finale (benchmark) :

- Utiliser ces données pour produire une datavisalisation (reporting) propre pour chaque "typologie" de simulation
  - Le rapport doit se mettre à jour à chaque run ou changement des paramètres de la simulation
  - Il **n'est pas attendu** de mise à jour en temps réel, vous pouvez `dbt run + rebuild dataviz` à chaque fois

## 3. Barème

| Critère | Points |
| --- | --- |
| Qualité du benchmark | /8 |
| Qualité de la data ingénierie | /8 |
| Respect des consignes | /4 |
| **Total** | **/20** |