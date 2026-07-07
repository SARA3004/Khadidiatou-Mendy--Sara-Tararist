
  
  create view "simulation"."main"."stg_simulation_turns__dbt_tmp" as (
    -- Couche silver : typage propre + indicateurs calculés au niveau du tour
select
    run_id,
    cast(run_started_at as timestamp) as run_started_at,
    model,
    ruleset_version,
    max_turns,
    turn,
    player_row,
    player_col,
    golds_count,
    nearest_gold_distance,
    ennemies_count,
    nearest_ennemy_distance,
    nearest_gold_delta_row,
    nearest_gold_delta_col,
    llm_direction,
    new_row,
    new_col,
    gold_collected,

    -- le LLM n'a pas su produire une décision exploitable ce tour-là
    (llm_direction is null) as llm_decision_failed,

    -- une décision a été prise mais le joueur n'a pas bougé (mur ou case ennemie)
    (
        llm_direction is not null
        and new_row = player_row
        and new_col = player_col
    ) as move_blocked,

    -- moyenne glissante (3 tours) de la distance à l'or le plus proche, par run
    avg(nearest_gold_distance) over (
        partition by run_id
        order by turn
        rows between 2 preceding and current row
    ) as gold_distance_rolling_avg_3

from '../data/bronze/turns/*.parquet'
  );
