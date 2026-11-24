"""Isolated Streamlit click-bridge proof. Search and exploration of discoverable fictional members."""
from pathlib import Path
from dataclasses import dataclass

import streamlit as st
from streamlit.components.v1 import declare_component

from main import find_connection
from stage5.connection_map import ranked_routes, map_graph
from stage5.directory import exact_member, search_members
from stage5.demo import DIRECTORY, HOME, NAMES, NETWORK, graph_data


st.set_page_config(page_title="6Degrees · Network explorer", layout="wide")
network_component = declare_component(
    "six_degrees_network", path=str(Path(__file__).parent / "stage5" / "component")
)

profile_component = declare_component("member_profile", path=str(Path(__file__).parent / "stage5" / "profile"))
finder_input = declare_component("finder_input", path=str(Path(__file__).parent / "stage5" / "finder"))


def names(route):
    return " → ".join(NAMES[person] for person in route)


@dataclass
class View:
    route: tuple
    origin: str = "home"
    action: str = "home"
    finder: tuple = ("", None, None)
    limit: int = 3


state = st.session_state
if "history" not in state:
    state.history = [View((HOME,))]
    state.revision = state.accepted = 0
    state.consumed_events = set()
    state.query = ""

# Component gestures arrive after the finder widgets have been instantiated.
# Apply the new view’s controls before those widgets render on the next run.
if state.pop("reset_finder", False):
    state.query, saved_region, state.pick = state.history[-1].finder
    state.region = saved_region or "All states"


def restore(view):
    state.query, saved_region, state.pick = view.finder
    state.region = saved_region or "All states"
    state.route_limit = view.limit
    state.revision += 1


def back():
    state.history.pop()
    restore(state.history[-1])


def home():
    state.home_revision = state.revision + 1
    state.history = [View((HOME,))]
    restore(state.history[0])


def clear_pick():
    state.pick = None


def change_limit():
    state.history[-1].limit = state.route_limit
    state.revision += 1


st.title("6Degrees")
st.caption("Interactive network explorer · Stage 6A")

def open_map(person):
    query = state.query
    region = None if state.region == "All states" else state.region
    if person not in search_members(DIRECTORY, query, state=region):
        return
    finder = (query, region, person)
    current = state.history[-1]
    if current.action == "search" and current.route == (person,):
        # Keep the submitted snapshot when Streamlit replays a checked radio
        # while the user edits the controls for their next search.
        return
    if current.action != "search":
        current.finder = finder
    state.history.append(View((person,), "search", "search", finder))
    state.route_limit = 3
    state.revision += 1


def select_result():
    open_map(state.pick)


with st.expander("People Finder", expanded=True):
    query_col, filter_col = st.columns([2, 1])
    with query_col:
        edit = finder_input(query=state.query, view=state.revision, key="finder_input")
    region = filter_col.selectbox("State (optional)", ["All states", *sorted({
        member.state for member in DIRECTORY.values() if member.state
    })], key="region", on_change=clear_pick)
    if region == "All states":
        region = None
    if (isinstance(edit, dict) and edit.get("view") == state.revision
            and isinstance(edit.get("query"), str) and edit.get("event") != state.get("last_edit")):
        state.last_edit = edit["event"]
        if state.query != edit["query"]:
            state.query = edit["query"]
            clear_pick()
        if edit.get("action") == "enter":
            person = exact_member(DIRECTORY, state.query, state=region)
            if person is not None:
                state.pick = person
                open_map(person)
                st.rerun()
    query = state.query
    matches = search_members(DIRECTORY, query, state=region)
    selection = None
    if matches:
        selection = st.radio("Matching members", matches, index=None,
                             format_func=lambda i: DIRECTORY[i].label(i),
                             key="pick", on_change=select_result)
    elif query.strip():
        st.info("No matching members. Try another name, ID, or state.")

current = state.history[-1]
route, origin = current.route, current.origin
is_map = current.action == "search"
focus = route[-1]
shortest = find_connection(HOME, focus, NETWORK)
st.subheader(f"Connection Map · David to {NAMES[focus]}" if is_map else "Explore Mode")
limit_slot = st.empty()
if is_map:
    limit_slot.radio("Maximum routes", [3, 5], horizontal=True, key="route_limit", on_change=change_limit)
    routes = ranked_routes(NETWORK, HOME, focus, current.limit)
    shortest = routes[0] if routes else None
    graph = map_graph(focus, routes)
else:
    graph = graph_data(route, shortest)

def navigate(event, allowed):
    # Widget values survive reruns. Validate both the originating view and the
    # gesture identity before allowing any mutation of the session history.
    if isinstance(event, dict) and event.get("view") == state.revision:
        person = event.get("person")
        event_id = event.get("event")
        if (isinstance(event_id, str) and event_id and event_id not in state.consumed_events
                and (is_map or person != focus) and person in allowed):
            state.consumed_events.add(event_id)
            next_origin = origin
            if person in route:
                next_route = route[:route.index(person) + 1]
            elif person in NETWORK[focus]:
                next_route = (*route, person)
            else:
                # Jump to a visible route reference without inventing a manual edge.
                next_origin = "reference"
                next_route = (person,)
            next_view = View(next_route, next_origin, "click")
            if is_map:
                state.reset_finder = True
            else:
                current.finder = next_view.finder = (query, region, selection)
            state.history.append(next_view)
            state.accepted += 1
            state.revision += 1
            st.rerun()


controls, profile = st.columns([3, 1])
with controls:
    buttons = st.columns([1, 1, 3])
    buttons[0].button("Home", on_click=home)
    buttons[1].button("Back", on_click=back, disabled=len(state.history) == 1)
    trail = []
    for entry in state.history:
        member_id = entry.route[-1]
        label = NAMES[member_id]
        if entry.action == "search":
            label = f"Search ({label} · ID {member_id})"
        trail.append(label)
    st.write("**Navigation trail**", " → ".join(trail))
    event = network_component(graph=graph, mapMode=is_map, view=state.revision, focus=focus, depth=len(state.history), reset=state.get("home_revision") == state.revision,
                              key="explorer", default=None)
    navigate(event, {node["id"] for node in graph["nodes"]})
    st.caption("Drag the background to pan. Scroll to zoom.")
    bold_label = "secondary connection route" if is_map else "manual trail"
    st.caption(f"Thin solid · direct relationship　 Bold solid · {bold_label}　 Dashed blue · shortest route")
    if is_map:
        for rank, path in enumerate(routes, 1):
            hops = len(path) - 1
            st.write(f"{rank}. {names(path)} · {hops} {'degree' if hops == 1 else 'degrees'}")
    st.write("**Explored route**", "No manual steps yet" if origin == "search" and len(route) == 1 else names(route))
    if origin == "search":
        st.caption(f"Search jump to {NAMES[route[0]]} · ID {route[0]}")
    elif route[0] != HOME:
        st.caption(f"This segment began by selecting {NAMES[route[0]]} from a displayed route.")
    st.write("**Shortest known route**", names(shortest) if shortest else "No known connection to David.")
    st.caption(f"Accepted node clicks: {state.accepted} · View revision: {state.revision}")

with profile:
    member = DIRECTORY[focus]
    contacts = NETWORK[focus]
    bio = member.biography.strip()
    event = profile_component(
        view=state.revision, id=focus, name=member.name,
        location=", ".join(filter(None, (member.city, member.state))),
        bio=bio if len(bio) <= 200 else bio[:199].rstrip() + "…",
        photo=member.photo_url, distance=len(shortest) - 1 if shortest else None,
        is_self=focus == HOME, connected=focus in NETWORK[HOME],
        contacts=[{"id": i, "name": NAMES[i]} for i in contacts],
        key="profile_card", default=None,
    )
    navigate(event, contacts)
