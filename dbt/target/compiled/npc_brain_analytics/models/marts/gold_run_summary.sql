-- Couche gold : un run de simulation = une ligne de KPI métier
with turns as (
    select * from "simulation"."main"."stg_simulation_turns"
)

select
    run_id,
    model,
    ruleset_version,
    min(run_started_at) as run_started_at,
    max(max_turns) as max_turns,
    count(*) as turns_played,

    -- objectif atteint ou non
    bool_or(gold_collected) as gold_collected,
    min(case when gold_collected then turn end) as steps_to_first_gold,

    -- qualité de la trajectoire
    avg(nearest_gold_distance) as avg_nearest_gold_distance,
    sum(case when move_blocked then 1 else 0 end) as wasted_moves,
    sum(case when llm_decision_failed then 1 else 0 end) as llm_decision_failures

from turns
group by run_id, model, ruleset_version