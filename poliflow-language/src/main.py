import os, argparse, shutil, json, yaml
from typing import Any
from collections.abc import Iterable
from poliflow_language.validation import validate

SAVE_PATH = "extracted/"

os.makedirs(SAVE_PATH, exist_ok=True)

AtomicNode = dict[str, Any]
PathElem = Any  # atomic node dict or control-node dict
Path = list[PathElem]


def load_workflow(path: str) -> dict[str, Any]:
    with open(path) as f:
        workflow = yaml.safe_load(f)

    valid, message = validate(workflow)

    if not valid:
        raise Exception(f"Non-valid workflow: {message}")

    return workflow


def build_state_map(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["id"]: s for s in workflow["states"]}


def make_atomic_node(state: dict[str, Any]) -> AtomicNode:
    # Normalize atomic repr used in examples
    t = state["type"]
    v = state.get("value")
    return {"type": t, "value": v}

def expand_parallel_sequence(
    state_id,
    states: dict[str, dict[str, Any]],
    visited: list[str],
):
    elems: list[str] = states[state_id].get("value", [])
    # start with one empty path
    sequences = [[]]
    for elem_id in elems:
        expanded = expand_state(elem_id, states, visited + [state_id])
        if len(expanded) > 1:
            copies = []
            for s in sequences:
                copies.append(s.copy())
            sequences = []
            for e in expanded:
                for c in copies:
                    new_copy = c.copy()
                    new_copy.extend(e)
                    sequences.append(new_copy)
        else:
            for s in sequences:
                s.extend(expanded[0])
    return sequences

def expand_state(
    state_id: str,
    states: dict[str, dict[str, Any]],
    visited: list[str] | None = None,
) -> list[Path]:
    """
    Expand a state into one-or-more paths. Each returned Path is a list of path elements.
    Control-nodes (switch/parallel) are added as single elements whose 'value' contains
    sub-sequences.
    """
    visited = visited or []
    if state_id in visited:
        # cycle protection: stop expansion here (could mark loop)
        return [[{"type": "loop-stop", "value": state_id}]]

    if state_id not in states:
        # unknown state: represent as opaque reference
        return [[{"type": "unknown", "value": state_id}]]

    state = states[state_id]
    stype = state["type"]

    # atomic types
    if stype in ("function:knative", "database", "event-source"):
        node = make_atomic_node(state)
        if "transition" in state and state["transition"]:
            tails = expand_state(state["transition"], states, visited + [state_id])
            final = []
            for t in tails:
                final.append([node.copy()])
                final[-1][0]["transitions"] = []
                final[-1][0]["transitions"].extend(t)
            return final # [[node] + tail for tail in tails]
        else:
            return [[node]]

    if stype == "sequence":
        return [[{"type": "sequence", "value": s}] for s in expand_parallel_sequence(state_id, states, visited)]

    if stype == "parallel":
        return [[{"type": "parallel", "value": s}] for s in expand_parallel_sequence(state_id, states, visited)]

    if stype == "switch":
        branches = state.get("value", [])
        branch_sequences: list[Path] = []
        for b in branches:
            expanded = expand_state(b, states, visited + [state_id])
            for e in expanded:
                branch_sequences.append(e)
        return [[{"type": "sequence", "value": b}] for b in branch_sequences]

    if stype == "loop":
        body: str = state.get("value")
        branch_sequences: list[Path] = []
        node = {"type": "loop"}

        expanded = expand_state(body, states, visited + [state_id])
        final = []
        for t in expanded:
            final.append([node.copy()])
            final[-1][0]["value"] = []
            final[-1][0]["value"].extend(t)
        return final 
    
    # fallback: unknown control type
    raise Exception(f"Unknown type: {stype}")


def generate_all_paths(workflow: dict[str, Any]) -> list[Path]:
    states = build_state_map(workflow)
    all_paths: list[Path] = []
    for entry in workflow.get("entries", []):
        expanded = expand_state(entry, states, visited=[])
        all_paths.extend(expanded)
    # wrap full paths as top-level sequence objects (matching your example)
    wrapped = [{"type": "sequence", "value": p} for p in all_paths]
    return wrapped


PathElem = dict[str, Any]
Path = list[PathElem]

def _branch_to_seq(branch: PathElem | list[PathElem]) -> list[PathElem]:
    if isinstance(branch, list):
        return branch
    if isinstance(branch, dict) and branch.get("type") == "sequence" and isinstance(branch.get("value"), list):
        return branch["value"]
    return [branch] if isinstance(branch, dict) else []


def collect_atomic_values(elem: PathElem, acc: set):
    """Recursively collect all atomic entities values."""
    if not isinstance(elem, dict):
        return

    et = elem.get("type")

    if et in ("event-source", "database", "function:knative"):
        op = elem.get("value")
        if op:
            acc.add(op)
        for t in elem.get("transitions", []) or []:
            collect_in_sequence(_branch_to_seq(t), acc)

    elif et in ("switch", "parallel", "loop", "sequence"):
        for branch in elem.get("value", []) or []:
            collect_in_sequence(_branch_to_seq(branch), acc)

    # elif et in ("event", "database"):
    #     for t in elem.get("transitions", []) or []:
    #         collect_in_sequence(_branch_to_seq(t), acc)

    else:
        for t in elem.get("transitions", []) or []:
            collect_in_sequence(_branch_to_seq(t), acc)


def collect_in_sequence(seq: Iterable[PathElem], acc: set):
    for e in seq:
        collect_atomic_values(e, acc)


def prune_sequence_to_target(seq: list[PathElem], target_op: str) -> list[PathElem] | None:
    pruned = []
    for e in seq:
        if not isinstance(e, dict):
            continue
        et = e.get("type")
        if et in ("event-source", "database", "function:knative") and e.get("value") == target_op:
            return pruned

        # search transitions for target
        for key in ("transitions", "value"):
            branches = e.get(key, [])
            if not isinstance(branches, list):
                continue
            for b in branches:
                inner = _branch_to_seq(b)
                res = prune_sequence_to_target(inner, target_op)
                if res is not None:
                    new_e = dict(e)
                    new_e[key] = [{"type": "sequence", "value": res}]
                    pruned.append(new_e)
                    return pruned

        pruned.append(e)
    return None


def prune_sequence_after_target(seq: list[PathElem], target_op: str) -> list[PathElem] | None:
    """
    Return all elements that can be reached *after* the target_op.
    Outbound means following the transitions of the target node,
    not re-traversing back up the structure.
    """
    for e in seq:
        if not isinstance(e, dict):
            continue

        et = e.get("type")
        val = e.get("value")

        # Case 1: Found the target atomic node
        if et in ("function:knative", "database", "event-source") and val == target_op:
            # Outbound = direct contents of its transitions
            out_elems: list[PathElem] = []
            for t in e.get("transitions", []) or []:
                # flatten transitions like {"type":"sequence","value":[...]}
                if isinstance(t, dict) and t.get("type") == "sequence" and isinstance(t.get("value"), list):
                    out_elems.extend(t["value"])
                elif isinstance(t, list):
                    out_elems.extend(t)
                elif isinstance(t, dict):
                    out_elems.append(t)
            return out_elems or []  # may be empty if terminal node

        # Case 2: recurse into nested control-flow nodes
        if et in ("sequence", "parallel", "switch", "loop"):
            for b in e.get("value", []) or []:
                inner = _branch_to_seq(b)
                res = prune_sequence_after_target(inner, target_op)
                if res is not None:
                    return res

        # Case 3: also check transitions for nested appearance
        for t in e.get("transitions", []) or []:
            inner = _branch_to_seq(t)
            res = prune_sequence_after_target(inner, target_op)
            if res is not None:
                return res

    return None


def extract_per_function_paths(full_paths: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """
    Extract inbound and outbound paths per function across all entry sequences.
    """
    per_fn: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for top in full_paths:
        if top.get("type") != "sequence":
            continue

        seq = top.get("value", [])
        # recursively collect all function ops
        ops = set()
        collect_in_sequence(seq, ops)

        for op in ops:
            pruned_in = prune_sequence_to_target(seq, op)
            if pruned_in is not None:
                per_fn.setdefault(op, {}).setdefault("inbound", []).append({"type": "sequence", "value": pruned_in})

            pruned_out = prune_sequence_after_target(seq, op)
            if pruned_out is not None:
                per_fn.setdefault(op, {}).setdefault("outbound", []).append({"type": "sequence", "value": pruned_out})

    return per_fn

def main(workflow_path: str):
    wf = load_workflow(workflow_path)
    full = generate_all_paths(wf)
    perfn = extract_per_function_paths(full)

    if os.path.exists(path := SAVE_PATH + workflow_path.split("/")[-1].split(".")[0]):
        shutil.rmtree(path)
    os.mkdir(path)

    for k in perfn:
        with open(f"{path}/{k}.json", "w") as f:
            f.write(json.dumps(perfn[k]))
        with open(f"{path}/{k}.yaml", "w") as f:
            f.write(yaml.dump(perfn[k]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser("extractor")
    parser.add_argument(
        "-w",
        "--workflow",
        help="The workflow path to use as ground truth",
        type=str,
        required=True,
    )
    args = parser.parse_args()

    main(args.workflow)
