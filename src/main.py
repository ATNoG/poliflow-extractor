from serverlessworkflow.sdk.workflow import Workflow
from serverlessworkflow.sdk.state_machine_generator import StateMachineGenerator
from transitions.extensions.nesting import HierarchicalMachine

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

def get_paths_to_node(machine: HierarchicalMachine, target_node):
    paths = []

    def dfs(state, path):
        path.append(state)
        transitions = [t for t in machine.get_transitions() if t.dest == state]
        if not transitions:  # If no incoming transitions, it's a starting state
            if state == machine.initial:  # Ensure the path starts from the initial state
                paths.append(path[::-1])  # Reverse the path to make it start from the initial state
        else:
            for transition in transitions:
                dfs(transition.source, path)
        path.pop()

    # Start DFS from the target node
    dfs(target_node, [])
    return paths

def get_paths_to_substate(machine: HierarchicalMachine, target_substate):
    paths = []

    def dfs(state, path):
        path.append(state)
        print([t.dest.split(".")[-1] for t in machine.get_transitions()])
        # print(machine.get_transitions())
        transitions = [t for t in machine.get_transitions() if t.dest.split(".")[-1] == state]
        if not transitions:  # If no incoming transitions, it's a starting state
            if state == machine.initial:  # Ensure the path starts from the initial state
                paths.append(path[::-1])  # Reverse the path to make it start from the initial state
        else:
            for transition in transitions:
                dfs(transition.source, path)
        path.pop()

    # Start DFS from the target substate
    dfs(target_substate, [])
    return paths

def get_all_substate_paths(machine: HierarchicalMachine):
    all_paths = {}

    def explore_state(state):
        # Check if the state has nested states
        if hasattr(state, "states") and state.states:
            for substate in state.states:
                explore_state(substate)
        else:
            # Compute paths for the current state
            all_paths[state] = get_paths_to_substates(machine, state)

    # Start exploring from the top-level states
    for state in machine.states.keys():
        explore_state(state)

    return all_paths

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
    
    target_substate = "f1"  # Replace with the actual substate name
    paths_to_substate = get_paths_to_substate(machine, target_substate)
    for path in paths_to_substate:
        print(" -> ".join(path))


if __name__ == "__main__":
    main()
