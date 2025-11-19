import json
import os
import shutil
from typing import List

import yaml
from serverlessworkflow.sdk.workflow import Workflow
from serverlessworkflow.sdk.state_machine_generator import StateMachineGenerator
from serverlessworkflow.sdk.state_machine_extensions import CustomHierarchicalMachine
from transitions.extensions.nesting import HierarchicalMachine, NestedState

NestedState.separator = "."

WORKFLOW_PATH = "../test-workflows/loop.sw.yaml"


def get_most_inner_states(
    machine: HierarchicalMachine, state: NestedState
) -> List[NestedState]:
    """
    Get all inner states of a given state in a hierarchical machine.
    """
    inner_states = []
    if state.states:
        for substate in state.states.values():
            inner_states.extend(get_most_inner_states(machine, substate))
    else:
        inner_states = [state]
    return inner_states


def get_paths_to_node(
    machine: HierarchicalMachine, target_node: NestedState
) -> List[List[NestedState]]:
    paths = []

    def dfs(state: NestedState, path):
        path.append(state)
        transitions = [t for t in machine.get_transitions() if t.dest == state.name]
        if not transitions:  # If no incoming transitions, it's a starting state
            if (type(machine.initial) == str and state.name == machine.initial) or (
                type(machine.initial) == list and state.name in machine.initial
            ):  # Ensure the path starts from the initial state
                paths.append(
                    path[::-1]
                )  # Reverse the path to make it start from the initial state
        else:
            for transition in transitions:
                if (
                    transition.source != transition.dest
                ):  # otherwise, it is a foreach state transition
                    dfs(machine.get_state(transition.source), path)
        path.pop()

    # Start DFS from the target node
    dfs(target_node, [])
    return paths


def get_edge_node_info(state: NestedState):
    if len(state.tags) > 0:
        edge_type = state.tags[0]

        def deep_serialize(value):
            if isinstance(value, dict):
                return {k: deep_serialize(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [deep_serialize(v) for v in value]
            elif hasattr(value, "serialize") and callable(value.serialize):
                if not hasattr(value, "_default_values"):
                    value._default_values = {}
                return value.serialize().__dict__
            else:
                return value

        edge_value = deep_serialize(state.metadata[list(state.metadata.keys())[0]])
        if edge_type == "function":
            if (
                edge_value["type"] == "custom"
                and (operation := edge_value["operation"].split(":"))[0] == "knative"
            ):
                edge_type = "function:knative"
                edge_value = {"operation": operation[1].split("/")[1].split("?")[0]}
            else:
                edge_type = f"function:{edge_value['type']}"
                edge_value = None  # TODO -> in the future, change this back to the original edge_value; for now, it is easier to debug without it

        return {"type": edge_type, "value": edge_value}
    return None


def get_nested_transition_path(
    machine: HierarchicalMachine,
    outer_state: NestedState,
    src_state: NestedState,
    machine_path,
):
    final_path = {}
    if machine.get_nested_transitions(src_path=[f"{machine_path}.{src_state.name}"]):
        path = get_nested_path(
            machine, src_state, path=f"{machine_path}.{src_state.name}"
        )
        for t in machine.get_nested_transitions(
            src_path=[f"{machine_path}.{src_state.name}"]
        ):
            next_state_path = get_nested_transition_path(
                machine,
                outer_state,
                outer_state.states[t.dest.split(machine.state_cls.separator)[-1]],
                machine_path,
            )
            transition_path = []

            # TODO -> THIS PIECE OF CODE CAN BE IMPROVED, IT REPEATS TWO TIMES
            if path["type"] == "sequence":
                for p in path["value"]:
                    transition_path.append(p.copy())
                    if next_state_path["type"] == "sequence":
                        for nsp in next_state_path["value"]:
                            transition_path.append(nsp)
                    else:
                        transition_path.append(next_state_path)
            else:
                transition_path.append(path.copy())
                if next_state_path["type"] == "sequence":
                    for nsp in next_state_path["value"]:
                        transition_path.append(nsp)
                else:
                    transition_path.append(next_state_path)
            final_path = {"type": "sequence", "value": transition_path}
    elif src_state.states:
        path = get_nested_path(
            machine, src_state, path=f"{machine_path}.{src_state.name}"
        )
        final_path = path
    else:
        final_path = {
            "type": "sequence",
            "value": [get_edge_node_info(state=src_state)],
        }
    return final_path


def get_nested_path(machine: HierarchicalMachine, state: NestedState, path: str, loop_min: int = 0):
    # verify if the state is one that contains actions
    if state.tags and any(
        t in state.tags for t in ("switch_state", "sleep_state", "inject_state")
    ):
        return None

    if not state.states:
        return {"type": "sequence", "value": [get_edge_node_info(state=state)]}

    if type(state.initial) == str:
        path = get_nested_transition_path(
            machine, state, state.states[state.initial], path
        )
    else:
        parallel = []
        for s in state.initial:
            init = state.states[s]
            parallel.append(get_nested_transition_path(machine, state, init, path))
        path = {"type": "parallel", "value": parallel}

    if state.tags and "foreach_state" in state.tags:
        path = {"type": "loop", "value": path, "min": loop_min}

    return path


def get_paths_to_substate(machine: HierarchicalMachine, target_substate: NestedState):
    def find_outer_path_to_substate(
        machine: HierarchicalMachine,
        outer_state: NestedState,
        state: NestedState,
        target_substate: NestedState,
    ):
        outer_paths = []
        if substates := state.states:
            for substate in substates.values():
                outer_paths.extend(
                    find_outer_path_to_substate(
                        machine, outer_state, substate, target_substate
                    )
                )
                if substate == target_substate:
                    outer_paths.extend(get_paths_to_node(machine, outer_state))
        return outer_paths

    # First, let's find the machine state where the target substate is
    outer_paths = []
    for state in machine.states.values():
        if state != target_substate:
            outer_paths.extend(
                find_outer_path_to_substate(machine, state, state, target_substate)
            )
        else:
            outer_paths.extend(get_paths_to_node(machine, state))

    # the entries are tuples, where the first entry is the path and the second is the property consider-last-entire-node
    rd_outer_paths = []
    for path in outer_paths:
        rd_outer_paths.append((path.copy(), False))
        if 'foreach_state' in path[-1].tags:
            rd_outer_paths.append((path.copy(), True))

    paths = []
    for path, consider_last_entire_node in rd_outer_paths:
        new_path = {"type": "sequence", "value": []}
        for node in (path[:-1] if not consider_last_entire_node else path):
            np = get_nested_path(machine, node, node.name, loop_min=1 if consider_last_entire_node else 0)
            if not np:
                continue
            elif np["type"] == "sequence":
                new_path["value"].extend(np["value"])
                # new_path["value"].append(
                #     np["value"] if len(np["value"]) > 1 else np["value"][0]
                # )
            else:  # TODO should verify if it is of type parallel
                new_path["value"].append(np)

        # For the last node in the path
        last_node_name = path[-1].name
        if machine.get_state(last_node_name).states:
            new_machine = HierarchicalMachine(
                model=None,
                states=list(machine.get_state(last_node_name).states.values()),
                initial=machine.get_state(last_node_name).initial,
                auto_transitions=False,
            )

            for trigger, event in machine.events.items():
                for transition_l in event.transitions.values():
                    for transition in transition_l:
                        if (
                            len(
                                src := transition.source.split(
                                    machine.state_cls.separator
                                )
                            )
                            > 1
                            and src[0] == last_node_name
                        ) and (
                            len(
                                dest := transition.dest.split(
                                    machine.state_cls.separator
                                )
                            )
                            > 1
                            and dest[0] == last_node_name
                        ):
                            new_machine.add_transition(
                                trigger=trigger,
                                source=".".join(src[1:]),
                                dest=".".join(dest[1:]),
                            )

            for np in get_paths_to_substate(new_machine, target_substate):
                newer_path = new_path.copy()
                newer_path["value"].extend(np["value"])
                paths.append(newer_path)
        else:
            paths.append(new_path)

    return paths


def print_path(path, start=""):
    if path.get("type") == "sequence":
        print(f"{start}Sequence")
        for v in path.get("value"):
            print_path(v, start=f"\t{start}")
    elif path.get("type") == "parallel":
        print(f"{start}Parallel")
        for v in path.get("value"):
            print_path(v, start=f"\t{start}")
    else:
        print(f"{start}{path.get('type')}: {path.get('value')}")


def main():
    subflows = []
    with open(WORKFLOW_PATH) as f:
        workflow = Workflow.from_source(f.read())

    machine = CustomHierarchicalMachine(
        model=None,
        initial=None,
        auto_transitions=False,
    )
    StateMachineGenerator(
        workflow=workflow,
        state_machine=machine,
        get_actions=True,
        subflows=subflows,
    ).generate()

    final_paths = {}
    for state in machine.states.values():
        for substate in get_most_inner_states(machine, state):
            if substate.metadata and any(
                e in substate.metadata for e in ("function", "event")
            ):
                paths_to_substate = get_paths_to_substate(machine, substate)
                name = (
                    substate.name
                    if "function" in substate.metadata
                    else (
                        substate.metadata["event"]["source"]
                        if "result" not in substate.metadata["event"]
                        else substate.metadata["event"]["result"]["source"]
                    )
                )
                if name not in final_paths:
                    final_paths[name] = []
                final_paths[name].extend(paths_to_substate)

    if os.path.exists(path := WORKFLOW_PATH.split("/")[-1].split(".")[0]):
        shutil.rmtree(path)
    os.mkdir(path)
    for substate in final_paths:
        # print(substate, final_paths[substate], sep=" -> ")
        with open(f"{path}/{substate}.json", "w") as f:
            json.dump(final_paths[substate], f)
        with open(f"{path}/{substate}.yaml", "w") as f:
            f.write(yaml.dump(final_paths[substate]))


if __name__ == "__main__":
    main()
