from enum import Enum
from typing import List, Tuple
from serverlessworkflow.sdk.workflow import Workflow
from serverlessworkflow.sdk.state_machine_generator import StateMachineGenerator
from transitions.extensions.nesting import HierarchicalMachine, NestedState

NestedState.separator = "."


def get_all_paths(machine: HierarchicalMachine):
    paths = []

    def dfs(state, path):
        path.append(state)
        transitions = [t for t in machine.get_transitions() if t.source == state]
        if not transitions:  # If no outgoing transitions, it's a final state
            paths.append(path[:])
        else:
            for transition in transitions:
                dfs(transition.dest, path)
        path.pop()

    # Start DFS from the initial state
    initial_state = machine.initial
    dfs(initial_state, [])
    return paths


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
                dfs(machine.get_state(transition.source), path)
        path.pop()

    # Start DFS from the target node
    dfs(target_node, [])
    return paths


def get_nested_transition_path(
    machine: HierarchicalMachine,
    outer_state: NestedState,
    src_state: NestedState,
    machine_path,
):
    if not machine.get_nested_transitions(
        src_path=[f"{machine_path}.{src_state.name}"]
    ):
        return [[src_state]]
    final_path = []
    path = get_nested_path(machine, src_state, path=f"{machine_path}.{src_state.name}")
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
        for p in path:
            for nsp in next_state_path:
                transition_path.append(p.copy())
                transition_path[-1].extend(nsp)
        final_path.extend(transition_path)
    return final_path


def get_nested_path(
    machine: HierarchicalMachine, state: NestedState, path: str
) -> List[List[Tuple[NestedState]]]:
    if not state.states:
        return [[state]]

    paths = []
    if type(state.initial) == str:
        initials = [state.states[state.initial]]
    else:
        initials = [state.states[s] for s in state.initial]
    # paths =
    for init in initials:
        paths.extend(get_nested_transition_path(machine, state, init, path))

    return paths
    # for t in machine.get_nested_transitions(src_path=[f"{path}.{init.name}"]):
    #     get_nested_path(machine, nested := state.states[t.dest], path=f"{path}.{nested.name}")


def get_paths_to_substate(machine: HierarchicalMachine, target_substate: str):
    def find_outer_path_to_substate(
        machine: HierarchicalMachine,
        outer_state: NestedState,
        state: NestedState,
        target_substate: str,
    ):
        outer_paths = []
        if substates := state.states:
            for name, substate in substates.items():
                outer_paths.extend(
                    find_outer_path_to_substate(
                        machine, outer_state, substate, target_substate
                    )
                )
                if name == target_substate:
                    outer_paths.extend(get_paths_to_node(machine, outer_state))
        return outer_paths

    # First, let's find the machine state where the target substate is
    outer_paths = []
    for state in machine.states.values():
        if state.name != target_substate:
            outer_paths.extend(
                find_outer_path_to_substate(machine, state, state, target_substate)
            )
        else:
            outer_paths.extend(get_paths_to_node(machine, state))

    paths = []
    for path in outer_paths:
        new_path = []
        for node in path[:-1]:
            # if initial := node.initial:
            for np in get_nested_path(machine, node, node.name):
                new_path.extend(np)
            # new_path.extend(get_nested_path(machine, node, node.name))

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
            # if new_machine.get_nested_transitions(src_path=["advertise-listing/0-1-0.f8-advertise-listing"]):
            #     print(new_machine.get_state("advertise-listing/0-1-0").states)
            for np in get_paths_to_substate(new_machine, target_substate):
                newer_path = new_path.copy()
                newer_path.extend(np)
                paths.append(newer_path)
        else:
            paths.append(new_path)

    return paths


def main():
    subflows = []
    with open("../test-workflows/valve.sw.yaml") as f:
        workflow = Workflow.from_source(f.read())
    with open("../test-workflows/valve-advertise-listing.sw.yaml") as f:
        subflows.append(Workflow.from_source(f.read()))
    with open("../test-workflows/test.sw.yaml") as f:
        subflows.append(Workflow.from_source(f.read()))

    machine = HierarchicalMachine(
        model=None,
        initial=None,
        auto_transitions=False,
    )
    for index, state in enumerate(workflow.states):
        StateMachineGenerator(
            state=state,
            state_machine=machine,
            is_first_state=index == 0,
            get_actions=True,
            subflows=subflows,
        ).generate()

    # target_node = "d2"
    # paths = get_paths_to_node(machine, machine.get_state(target_node))
    # # for path in paths:
    # #     print(" -> ".join([s.name for s in path]))

    target_substate = "f9"  # Replace with the actual substate name
    paths_to_substate = get_paths_to_substate(machine, target_substate)
    print(paths_to_substate)


if __name__ == "__main__":
    main()
