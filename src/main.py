from typing import List, Tuple
from serverlessworkflow.sdk.workflow import Workflow
from serverlessworkflow.sdk.state_machine_generator import StateMachineGenerator
from transitions.extensions.nesting import HierarchicalMachine, NestedState

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

def get_paths_to_node(machine: HierarchicalMachine, target_node: NestedState) -> List[List[NestedState]]:
    paths = []

    def dfs(state: NestedState, path):
        path.append(state)
        transitions = [t for t in machine.get_transitions() if t.dest == state.name]
        if not transitions:  # If no incoming transitions, it's a starting state
            if state.name == machine.initial:  # Ensure the path starts from the initial state
                paths.append(path[::-1])  # Reverse the path to make it start from the initial state
        else:
            for transition in transitions:
                dfs(machine.get_state(transition.source), path)
        path.pop()

    # Start DFS from the target node
    dfs(target_node, [])
    return paths

def get_nested_path(machine: HierarchicalMachine, state: NestedState, path: str) -> List[List[Tuple[NestedState]]]:
    if not state.states:
        return [[state]]

    def get_nested_transition_path(src_state: NestedState, machine_path):
        if not machine.get_nested_transitions(src_path=[f"{machine_path}.{src_state.name}"]):
            return [[src_state]]
        final_path = []
        path = get_nested_path(machine, src_state, path=f"{machine_path}.{src_state.name}")
        for t in machine.get_nested_transitions(src_path=[f"{machine_path}.{src_state.name}"]):
            next_state_path = get_nested_transition_path(state.states[t.dest.split(machine.state_cls.separator)[-1]], machine_path)
            transition_path = []
            for p in path:
                for nsp in next_state_path:
                    transition_path.append(p.copy())
                    transition_path[-1].extend(nsp)
            final_path.extend(transition_path)
        return final_path
        
    
    paths = []
    if type(state.initial) == str:
        initials = [state.states[state.initial]]
    else:
        initials = [state.states[s] for s in state.initial]
    # paths = 
    for init in initials:
        paths.extend(get_nested_transition_path(init, path))
    
    return paths
        # for t in machine.get_nested_transitions(src_path=[f"{path}.{init.name}"]):
        #     get_nested_path(machine, nested := state.states[t.dest], path=f"{path}.{nested.name}")
    

def get_paths_to_substate(machine: HierarchicalMachine, target_substate: str):

    def find_outer_path_to_substate(machine: HierarchicalMachine, outer_state: NestedState, state: NestedState, target_substate: str):
        outer_paths = []
        if substates := state.states:
            for name, substate in substates.items():
                outer_paths.extend(find_outer_path_to_substate(machine, outer_state, substate, target_substate))
                if name == target_substate:
                    outer_paths.extend(get_paths_to_node(machine, outer_state))
        return outer_paths

    # First, let's find the machine state where the target substate is
    outer_paths = []
    for state in machine.states.values():
        outer_paths.extend(find_outer_path_to_substate(machine, state, state, target_substate))
        # print(state, machine.get_transitions())
        # if substates := state.states:
        #     for name, substate in substates.items():
        #         if name == target_substate:
        #             outer_path = get_paths_to_node(machine, state)

    print(outer_paths)

    # paths = []
    # print(get_nested_path(machine, machine.get_state("f1-upload-listing"), "f1-upload-listing"))

    # print(machine.get_state("f1-upload-listing").initial)

    paths = []
    for path in outer_paths:
        new_path = []
        for node in path:
            # if initial := node.initial:
            for np in get_nested_path(machine, node, node.name):
                new_path.extend(np)
            # new_path.extend(get_nested_path(machine, node, node.name))
        paths.append(new_path)

                # if type(initial) == "str":
                #     for t in machine.get_nested_transitions(src_path=[f"{node.name}.{initial}"]):
                #         t.dest

    # def dfs(state, path):
    #     path.append(state)
    #     print([t.dest.split(".")[-1] for t in machine.get_transitions()])
    #     # print(machine.get_transitions())
    #     transitions = [t for t in machine.get_transitions() if t.dest.split(".")[-1] == state]
    #     if not transitions:  # If no incoming transitions, it's a starting state
    #         if state == machine.initial:  # Ensure the path starts from the initial state
    #             paths.append(path[::-1])  # Reverse the path to make it start from the initial state
    #     else:
    #         for transition in transitions:
    #             dfs(transition.source, path)
    #     path.pop()

    # # Start DFS from the target substate
    # dfs(target_substate, [])
    return paths

# def get_all_substate_paths(machine: HierarchicalMachine):
#     all_paths = {}

#     def explore_state(state):
#         # Check if the state has nested states
#         if hasattr(state, "states") and state.states:
#             for substate in state.states:
#                 explore_state(substate)
#         else:
#             # Compute paths for the current state
#             all_paths[state] = get_paths_to_substates(machine, state)

#     # Start exploring from the top-level states
#     for state in machine.states.keys():
#         explore_state(state)

#     return all_paths

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
            state=state, state_machine=machine, is_first_state=index == 0, get_actions=True, subflows=subflows
        ).source_code()
    
    target_node = "d2"
    paths = get_paths_to_node(machine, machine.get_state(target_node))
    # for path in paths:
    #     print(" -> ".join([s.name for s in path]))
    
    
    target_substate = "f6"  # Replace with the actual substate name
    paths_to_substate = get_paths_to_substate(machine, target_substate)
    print(paths_to_substate)
    # for path in paths_to_substate:
    #     print(" -> ".join(path))


if __name__ == "__main__":
    main()
