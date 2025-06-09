import sys
import re
from statemachine import StateMachine, State
from typing import Dict, List


def sanitize(name: str) -> str:
    # Sanitize to valid Python identifier (simplified)
    name = name.strip()
    if name.startswith('"') and name.endswith('"'):
        name = name[1:-1]
    name = re.sub(r'\W|^(?=\d)', '_', name)
    return name


def parse_plantuml(plantuml: str):
    lines = plantuml.splitlines()
    states: Dict[str, Dict] = {}
    transitions: List[Dict] = []

    current_composite = None

    # Patterns
    re_transition = re.compile(r'^([\w\-\[\]\*]+)\s*-->\s*([\w\-\[\]\*]+)(?:\s*:\s*(.+))?$')

    for line in lines:
        line = line.strip()
        if not line or line.startswith("'") or line.startswith('@') or line.startswith('stateDiagram'):
            continue

        # Transitions
        m_trans = re_transition.match(line)
        if m_trans:
            src, dst, label = m_trans.groups()
            transitions.append({
                "src": sanitize(src),
                "dst": sanitize(dst),
                "label": label,
            })
            # Register states even if not declared explicitly
            for s in [src, dst]:
                s_sanit = sanitize(s)
                if s_sanit not in states:
                    states[s_sanit] = {
                        "label": s,
                        "stereotype": None,
                        "composite": False,
                        "parent": current_composite,
                    }
            continue

        # Other state lines (like descriptions) can be handled here if needed

    return states, transitions


def build_statemachine(name: str, states: Dict[str, Dict], transitions: List[Dict]):
    attrs = {}
    initial_state = None

    # Add states
    for s_name, s_info in states.items():
        if s_info["label"] == '[*]':
            # We treat [*] as a special marker, so skip real state
            continue

    # Determine initial state(s)
    # Find transitions from [*] -> something as initial states
    initial_candidates = [t["dst"] for t in transitions if states.get(t["src"], {}).get("label") == '[*]']
    if initial_candidates:
        initial_state = initial_candidates[0]

    # Define State instances
    for s_name, s_info in states.items():
        if s_info["label"] == '[*]':
            continue
        kwargs = {}
        if s_name == initial_state:
            kwargs["initial"] = True
        attrs[s_name] = State(s_info["label"], **kwargs)

    # Final state handling: treat transitions to [*] as transitions to a final state
    # if any(t["dst"] == sanitize('[*]') for t in transitions):
    #     attrs["final"] = State("final")

    # Add transitions to states
    for idx, t in enumerate(transitions):
        src = t["src"]
        dst = t["dst"]
        label = t["label"]

        # Skip transitions from or to [*] since [*] is start/end marker
        if states.get(src, {}).get("label") == '[*]':
            continue

        if dst == sanitize('[*]'):
            # dst = "final"
            attrs[src]._final = True

        if src not in attrs or dst not in attrs:
            continue  # ignore bad states

        # Create transition method name safely
        # method_name = f"to_{dst}_{idx}"
        method_name = label if label else ""

        # Attach transition dynamically
        attrs[method_name] = attrs[src].to(attrs[dst])

    # Build the StateMachine class
    cls = type(name, (StateMachine,), attrs)
    return cls


# Example usage:

plantuml_code = """
@startuml
entry-event : entry-event
entry-event : type = Event State
[*] --> entry-event
entry-event --> authorization

authorization : authorization
authorization : type = Operation State
authorization : Action mode = sequential
authorization : Num. of actions = 1
authorization --> authorization-decide

authorization-decide : authorization-decide
authorization-decide : type = Switch State
authorization-decide : Condition type = data-based
authorization-decide --> verify-transaction : ${ ."do-verification" == true }
authorization-decide --> result : default

verify-transaction : verify-transaction
verify-transaction : type = Operation State
verify-transaction : Action mode = sequential
verify-transaction : Num. of actions = 1
verify-transaction --> verify-transaction-decide

verify-transaction-decide : verify-transaction-decide
verify-transaction-decide : type = Switch State
verify-transaction-decide : Condition type = data-based
verify-transaction-decide --> transaction : ${ ."do-transaction" == true }
verify-transaction-decide --> result : default

transaction : transaction
transaction : type = Operation State
transaction : Action mode = sequential
transaction : Num. of actions = 1
transaction --> result

result : result
result : type = Operation State
result : Action mode = sequential
result : Num. of actions = 1
result --> [*]
@enduml
"""

states, transitions = parse_plantuml(sys.stdin.read()) #
MyMachine = build_statemachine("MyMachine", states, transitions)
machine = MyMachine()
# print("Initial:", machine.current_state.id)
# machine.to_loading_1()
# print("After transition:", machine.current_state.id)

from statemachine.contrib.diagram import DotGraphMachine
graph = DotGraphMachine(machine)
graph().write_svg("test-workflows/test.svg")
r"(\[*\w[\w\-\.]*\]*)\s*-->\s*(\[*\w[\w\-\.]*\]*)(?:\s*:\s*(.*))?"
