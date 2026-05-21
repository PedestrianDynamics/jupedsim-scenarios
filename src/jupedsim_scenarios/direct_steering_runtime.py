import math
import random
from typing import Any

from . import simulation_init


def normalize_speed_factor(value: Any) -> float:
    try:
        speed_factor = float(value)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(speed_factor) or speed_factor < 0.0:
        return 1.0
    return min(speed_factor, 3.0)


def random_point_in_polygon(polygon, rng, min_clearance: float = 0.2):
    return simulation_init._random_point_in_polygon(
        polygon,
        rng,
        min_clearance=min_clearance,
    )


def pick_stage_target(wait_state, next_stage_cfg):
    """Pick a target point in the stage polygon.

    Transit stages (waiting_time=0, non-exit) use the polygon centroid
    so agents approach head-on without crossing paths.
    Waiting stages use a random interior point to distribute agents.
    """
    cfg = next_stage_cfg or {}
    polygon = cfg.get("polygon")
    if polygon is None:
        return None

    is_transit = (
        float(cfg.get("waiting_time", 0.0)) <= 0.0
        and cfg.get("stage_type") != "exit"
    )
    if is_transit:
        try:
            centroid = polygon.centroid
            return (centroid.x, centroid.y)
        except AttributeError:
            pass

    target_rng = random.Random(
        int(wait_state.get("base_seed", 0)) + int(wait_state.get("step_index", 0))
    )
    target_clearance = max(
        0.05,
        float(wait_state.get("agent_radius", 0.2)) * 0.8,
    )
    return random_point_in_polygon(
        polygon,
        target_rng,
        min_clearance=target_clearance,
    )


def extract_agent_xy(agent):
    pos = getattr(agent, "position", None)
    if pos is not None:
        if isinstance(pos, (tuple, list)) and len(pos) >= 2:
            return float(pos[0]), float(pos[1])
        if hasattr(pos, "x") and hasattr(pos, "y"):
            return float(pos.x), float(pos.y)
    if hasattr(agent, "x") and hasattr(agent, "y"):
        return float(agent.x), float(agent.y)
    return None, None


def assign_agent_target(agent, target):
    if not target:
        return
    tx, ty = float(target[0]), float(target[1])
    try:
        agent.target = (tx, ty)
        return
    except Exception:
        pass
    try:
        agent.target = [tx, ty]
    except Exception:
        pass


def is_inside_polygon(x, y, polygon):
    if polygon is None:
        return False
    try:
        from shapely.geometry import Point

        point = Point(float(x), float(y))
        return bool(polygon.contains(point) or polygon.touches(point))
    except Exception:
        return False



def sample_wait_time(stage_cfg, base_seed, step_index):
    mean_wait = float(stage_cfg.get("waiting_time", 0.0))
    if stage_cfg.get("waiting_time_distribution") == "gaussian":
        std_wait = float(stage_cfg.get("waiting_time_std", 1.0))
        rng = random.Random(int(base_seed) + int(step_index) * 131 + 17)
        return max(0.1, float(rng.gauss(mean_wait, std_wait)))
    return max(0.0, mean_wait)


def get_agent_desired_speed(agent) -> float | None:
    model_obj = getattr(agent, "model", None)
    if model_obj is None:
        return None
    if hasattr(model_obj, "desired_speed"):
        try:
            return float(model_obj.desired_speed)
        except Exception:
            return None
    return None


def set_agent_desired_speed(agent, speed: float) -> bool:
    model_obj = getattr(agent, "model", None)
    if model_obj is None:
        return False
    if hasattr(model_obj, "desired_speed"):
        try:
            model_obj.desired_speed = float(speed)
            return True
        except Exception:
            return False
    return False


def ensure_agent_speed_state(agent_speed_state: dict[int, dict[str, Any]], agent_id: int, agent):
    state = agent_speed_state.setdefault(
        int(agent_id),
        {"original_speed": None, "active_checkpoint": None},
    )
    current_speed = get_agent_desired_speed(agent)
    if current_speed is not None and state.get("active_checkpoint") is None:
        state["original_speed"] = current_speed
    elif current_speed is not None and state.get("original_speed") is None:
        state["original_speed"] = current_speed
    return state


def restore_agent_speed(agent_speed_state: dict[int, dict[str, Any]], agent_id: int, agent) -> None:
    state = ensure_agent_speed_state(agent_speed_state, agent_id, agent)
    if state.get("active_checkpoint") is None:
        return
    original_speed = state.get("original_speed")
    if original_speed is None:
        return
    if set_agent_desired_speed(agent, float(original_speed)):
        state["active_checkpoint"] = None


def update_checkpoint_speed(
    agent_speed_state: dict[int, dict[str, Any]],
    direct_steering_info: dict[str, dict[str, Any]] | None,
    agent_id: int,
    agent,
    checkpoint_key: str | None,
    stage_cfg: dict[str, Any] | None,
    x: float,
    y: float,
) -> None:
    state = ensure_agent_speed_state(agent_speed_state, agent_id, agent)
    active_zone_key = None
    active_speed_factor = 1.0

    if checkpoint_key and stage_cfg:
        stage_polygon = stage_cfg.get("polygon")
        stage_speed_factor = normalize_speed_factor(stage_cfg.get("speed_factor", 1.0))
        if math.fabs(stage_speed_factor - 1.0) > 1e-9 and is_inside_polygon(
            x, y, stage_polygon
        ):
            active_zone_key = checkpoint_key
            active_speed_factor = stage_speed_factor

    if active_zone_key is None:
        for zone_key, zone_cfg in (direct_steering_info or {}).items():
            zone_speed_factor = normalize_speed_factor(zone_cfg.get("speed_factor", 1.0))
            if math.fabs(zone_speed_factor - 1.0) <= 1e-9:
                continue
            if not is_inside_polygon(x, y, zone_cfg.get("polygon")):
                continue
            if active_zone_key is None or math.fabs(zone_speed_factor - 1.0) > math.fabs(
                active_speed_factor - 1.0
            ):
                active_zone_key = zone_key
                active_speed_factor = zone_speed_factor

    if active_zone_key is not None and math.fabs(active_speed_factor - 1.0) > 1e-9:
        original_speed = state.get("original_speed")
        if original_speed is None:
            return
        slowed_speed = max(0.0, float(original_speed) * active_speed_factor)
        if set_agent_desired_speed(agent, slowed_speed):
            state["active_checkpoint"] = active_zone_key
        return

    restore_agent_speed(agent_speed_state, agent_id, agent)


def check_stage_reached(wait_info, stage_cfg, x, y, current_time, target):
    """Determine whether the agent has reached its current stage.

    Transit stages (waiting_time=0, non-exit, with polygon) use entry-based
    transition: the agent only needs to enter the polygon and dwell briefly.
    Waiting stages and exits use the original distance-based check.

    Returns True if the stage should be considered reached.
    May mutate wait_info["inside_since"] as a side-effect.
    """
    stage_type = stage_cfg.get("stage_type")
    stage_polygon = stage_cfg.get("polygon")

    is_transit = (
        float(stage_cfg.get("waiting_time", 0.0)) <= 0.0
        and stage_type != "exit"
        and stage_polygon is not None
    )

    if is_transit:
        inside = is_inside_polygon(x, y, stage_polygon)
        if inside:
            if wait_info.get("inside_since") is None:
                wait_info["inside_since"] = current_time
            dwell = float(wait_info.get("reach_dwell_seconds", 0.2))
            return (current_time - wait_info["inside_since"]) >= dwell
        wait_info["inside_since"] = None
        return False

    # Original logic for waiting stages and exits
    reach_dist = float(wait_info.get("agent_radius", 0.2)) + 0.5
    if target is None:
        return False
    close_enough = math.hypot(x - float(target[0]), y - float(target[1])) <= reach_dist
    inside_stage = is_inside_polygon(x, y, stage_polygon) if stage_polygon is not None else True
    return close_enough and inside_stage


def advance_path_target(wait_info):
    path_choices = wait_info.get("path_choices", {})
    stage_configs = wait_info.get("stage_configs", {})
    current_stage = wait_info.get("current_target_stage")
    next_candidates = path_choices.get(current_stage, [])
    if not next_candidates:
        wait_info["state"] = "done"
        return

    total = sum(max(0.0, float(weight)) for _, weight in next_candidates)
    if total <= 0:
        next_stage = next_candidates[0][0]
    else:
        choose_rng = random.Random(
            int(wait_info.get("base_seed", 0))
            + int(wait_info.get("step_index", 0)) * 131
            + 53
        )
        pick = choose_rng.random() * total
        running = 0.0
        next_stage = next_candidates[-1][0]
        for stage_key, weight in next_candidates:
            running += max(0.0, float(weight))
            if pick <= running:
                next_stage = stage_key
                break

    if next_stage not in stage_configs:
        wait_info["state"] = "done"
        return

    wait_info["current_origin"] = current_stage
    wait_info["current_target_stage"] = next_stage
    wait_info["step_index"] = int(wait_info.get("step_index", 0)) + 1
    wait_info["target_assigned"] = False
    wait_info["wait_until"] = None
    wait_info["state"] = "to_target"
    wait_info["inside_since"] = None
    wait_info["target"] = pick_stage_target(
        wait_info,
        stage_configs[next_stage],
    )
