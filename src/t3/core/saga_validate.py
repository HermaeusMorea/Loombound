"""Graph normalisation and validation for Loombound saga structures."""
from __future__ import annotations


def _normalise(data: dict) -> dict:
    nodes = data.get("waypoints", data.get("nodes", []))
    data = dict(data)
    if isinstance(nodes, dict):
        normalised: list[dict] = []
        for waypoint_id, spec in nodes.items():
            if isinstance(spec, dict):
                spec = dict(spec)
                spec.setdefault("waypoint_id", waypoint_id)
                normalised.append(spec)
        data["waypoints"] = normalised
    elif isinstance(nodes, list):
        data["waypoints"] = [n for n in nodes if isinstance(n, dict)]
    data.pop("nodes", None)
    return data


def validate_graph(
    nodes: list[dict],
    start_waypoint_id: str,
    expected_node_count: int | None = None,
) -> list[str]:
    errors: list[str] = []
    if not nodes:
        errors.append("nodes list is empty — model returned no nodes or wrong format")
        return errors
    bad = [i for i, n in enumerate(nodes) if not isinstance(n, dict)]
    if bad:
        errors.append(f"nodes[{bad}] are not objects — malformed response from model")
        return errors
    node_ids = {n["waypoint_id"] for n in nodes}

    if start_waypoint_id not in node_ids:
        errors.append(f"start_waypoint_id '{start_waypoint_id}' not found in nodes")

    if expected_node_count is not None and len(node_ids) != expected_node_count:
        errors.append(
            f"Expected exactly {expected_node_count} unique nodes, got {len(node_ids)}"
        )

    for node in nodes:
        for ref in node.get("next_waypoints", []):
            if ref not in node_ids:
                errors.append(
                    f"'{node['waypoint_id']}' → '{ref}': referenced node does not exist"
                )

    if not any(not n.get("next_waypoints") for n in nodes):
        errors.append("No terminal nodes (next_waypoints: []) — saga has no ending")

    return errors
