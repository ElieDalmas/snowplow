import copy
import math
import os
import pickle
import random

import networkx as nx

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database")

QUARTIERS = [
    "anjou",
    "outremont",
    "plateau_mont_royal",
    "riviere-des-prairies-pointe-aux-trembles",
    "verdun",
]

# (speed in km/h, cost per km and per hour, fixed daily cost)
TYPE_I = (10, 1.1, 500)
TYPE_II = (20, 1.3, 800)

INF = float("inf")


def import_G(filename):
    with open(filename, "rb") as f:
        return pickle.load(f)


def snowize(G, p=0.5):
    """Mark each edge as snowy with probability p."""
    for u, v in G.edges():
        for key in G[u][v]:
            G[u][v][key]["snow"] = 1 if random.random() <= p else 0
    return G


def snow_roads(G_aug, G_bis):
    """Snowy edges as (u, v, key), in the order of the eulerian circuit."""
    edges = []
    for u, v in nx.eulerian_circuit(G_aug):
        for key in G_bis[u][v]:
            if G_bis[u][v][key]["snow"]:
                edges.append((u, v, key))
    return edges


def fix_edges(G, edges):
    """Flip edges that only exist in the other direction in the directed graph."""
    for i, (u, v, key) in enumerate(edges):
        if v not in G[u]:
            edges[i] = (v, u, key)


def load_floyd_warshall(G, quartier):
    """Floyd-Warshall is the bottleneck and does not depend on snow, so it is cached."""
    fw_file = os.path.join(DATABASE, "floyd_warshall_data", quartier + "-FWR.pkl")

    if os.path.exists(fw_file):
        with open(fw_file, "rb") as f:
            predecessors, weights = pickle.load(f)
    else:
        predecessors, weights = nx.floyd_warshall_predecessor_and_distance(G, weight="length")
        predecessors = {u: dict(v) for u, v in predecessors.items()}
        weights = {u: dict(v) for u, v in weights.items()}
        with open(fw_file, "wb") as f:
            pickle.dump((predecessors, weights), f)

    return weights, predecessors


def shortest_key(edges):
    """Key of the shortest edge between two nodes of a multigraph."""
    return min(edges, key=lambda key: edges[key]["length"])


def add_path_route(graph, path):
    """Node path -> list of (u, v, key)."""
    return [(a, b, shortest_key(graph[a][b])) for a, b in zip(path, path[1:])]


def is_accessible(dist_floyd, edge, curr_pos):
    return dist_floyd[0][curr_pos][edge[0]] != INF


def count_accessible(dist_floyd, edges, curr_pos):
    return sum(is_accessible(dist_floyd, edge, curr_pos) for edge in edges)


def get_shortest_path(graph, dist_floyd, curr_pos, edge):
    """Cheapest way to reach and clear `edge` from `curr_pos`, as (distance, route)."""
    u, v, key = edge
    weight_u = dist_floyd[0][curr_pos][u]
    weight_v = dist_floyd[0][curr_pos][v]
    if weight_u == INF and weight_v == INF:
        return None

    # One-way street: it can only be entered from one end
    if v not in graph[u]:
        if weight_v == INF:
            return None
        nodes = nx.reconstruct_path(curr_pos, u, dist_floyd[1])
        return weight_v, add_path_route(graph, nodes) + [(v, u, key)]
    if u not in graph[v]:
        if weight_u == INF:
            return None
        nodes = nx.reconstruct_path(curr_pos, v, dist_floyd[1])
        return weight_u, add_path_route(graph, nodes) + [(u, v, key)]

    if weight_u < weight_v:
        nodes = nx.reconstruct_path(curr_pos, v, dist_floyd[1])
        return weight_u, add_path_route(graph, nodes) + [(u, v, key)]
    nodes = nx.reconstruct_path(curr_pos, u, dist_floyd[1])
    return weight_v, add_path_route(graph, nodes) + [(v, u, key)]


def get_paths(graph, dist_floyd, targets, start):
    """Greedy route for one snowplow: always go to the nearest snowy edge.

    A candidate is skipped if, once there, less than half of the remaining
    reachable edges are still reachable (dead ends of one-way streets).
    """
    unreachable = len(targets) - count_accessible(dist_floyd, targets, start)

    curr_pos = start
    route = []
    while targets:
        nearest = (0, get_shortest_path(graph, dist_floyd, curr_pos, targets[0]))

        for i in range(1, len(targets)):
            candidate = get_shortest_path(graph, dist_floyd, curr_pos, targets[i])
            if not candidate:
                continue
            if not nearest[1] or candidate[0] < nearest[1][0]:
                end = candidate[1][-1][1]
                if count_accessible(dist_floyd, targets, end) >= (len(targets) - unreachable) / 2:
                    nearest = (i, candidate)

        if not nearest[1]:
            return route

        curr_pos = nearest[1][1][-1][1]
        route += nearest[1][1]
        targets.pop(nearest[0])

    return route


def get_total_dist(G, edges):
    total = 0
    for u, v, key in edges:
        try:
            total += G[u][v][key]["length"]
        except KeyError:
            continue
    return total


def sum_dist(G):
    return sum(length for _, _, length in G.edges(data="length"))


def sum_dist_circuit(G_bis, circuit):
    total = 0
    for u, v in circuit:
        for key in G_bis[u][v]:
            total += G_bis[u][v][key]["length"] or 0
    return total


def plow_cost(km, speed, rate, fixed_cost):
    """Total cost and duration in hours. Hourly rate goes up by 0.2 after 8 hours."""
    hours = km / speed
    if hours <= 8:
        hourly = hours * rate
    else:
        hourly = 8 * rate + (hours - 8) * (rate + 0.2)
    return round(fixed_cost + rate * km + hourly, 2), hours


def format_duration(hours):
    h = math.floor(hours)
    return f"{h} h {round((hours - h) * 60)} min"


def is_reachable_from(G, floyd_weight, node, min_count):
    """True if at least `min_count` nodes can reach `node`."""
    count = 0
    for n in G.nodes():
        if floyd_weight[n][node] != INF:
            count += 1
            if count >= min_count:
                return True
    return False


def find_center(G):
    coords = [(d["x"], d["y"]) for _, d in G.nodes(data=True) if "x" in d and "y" in d]
    return (sum(x for x, _ in coords) / len(coords), sum(y for _, y in coords) / len(coords))


def average_pos(edge):
    xs, ys = zip(*edge["geometry"].coords)
    return sum(xs) / len(xs), sum(ys) / len(ys)


def nearest_node(G, coords):
    best_edge = None
    best_dist = INF
    for u, v, data in G.edges(data=True):
        if "geometry" in data:
            x, y = average_pos(data)
            dist = abs(coords[0] - x) + abs(coords[1] - y)
            if dist < best_dist:
                best_dist = dist
                best_edge = (u, v)
    return best_edge[0]


def find_node_by_pos(G, floyd_weight, coords):
    best_node = None
    best_dist = INF
    for n, data in G.nodes(data=True):
        if "x" in data and "y" in data:
            dist = abs(coords[0] - data["x"]) + abs(coords[1] - data["y"])
            if dist < best_dist and is_reachable_from(G, floyd_weight, n, 10):
                best_dist = dist
                best_node = n
    return best_node


def get_bounds(G):
    xs = [d["x"] for _, d in G.nodes(data=True) if "x" in d and "y" in d]
    ys = [d["y"] for _, d in G.nodes(data=True) if "x" in d and "y" in d]
    return min(xs), max(xs), min(ys), max(ys)


def get_anchors(G, floyd_weight):
    """Four reachable nodes near the west, east, south and north edges of the map."""
    xmin, xmax, ymin, ymax = get_bounds(G)
    cx, cy = find_center(G)
    return (
        find_node_by_pos(G, floyd_weight, (xmin, cy)),
        find_node_by_pos(G, floyd_weight, (xmax, cy)),
        find_node_by_pos(G, floyd_weight, (cx, ymin)),
        find_node_by_pos(G, floyd_weight, (cx, ymax)),
    )


def split_by_anchor(dist_floyd, edges, anchors):
    """Assign each edge to the anchor it is closest to."""
    groups = [[] for _ in anchors]
    for x, y, n in edges:
        dists = [min(dist_floyd[0][x][a], dist_floyd[0][y][a]) for a in anchors]
        groups[dists.index(min(dists))].append((x, y, n))
    return groups


def remove_bad_edges(G, floyd_results, edges):
    """Drop edges that more than 5% of the nodes cannot reach."""
    limit = len(G.nodes()) / 20

    def unreachable_count(edge):
        return sum(floyd_results[0][pos][edge[0]] == INF for pos in G.nodes())

    return [edge for edge in edges if unreachable_count(edge) <= limit]


def one_plow(G, floyd_results, snow_edges):
    start = nearest_node(G, find_center(G))
    snow_edges = remove_bad_edges(G, floyd_results, snow_edges)
    route = get_paths(G, floyd_results, snow_edges, start)
    return get_total_dist(G, route) / 1000


def four_plows(G, floyd_results, snow_edges):
    """Split the snowy edges in four zones, every plow leaves from the center."""
    snow_edges = remove_bad_edges(G, floyd_results, snow_edges)
    anchors = get_anchors(G, floyd_results[0])
    groups = split_by_anchor(floyd_results, copy.deepcopy(snow_edges), anchors)
    center = nearest_node(G, find_center(G))
    return [get_total_dist(G, get_paths(G, floyd_results, group, center)) / 1000 for group in groups]


def scenario(G, G_aug, quartier, p):
    G = snowize(G, p)
    G_bis = nx.MultiGraph(G)

    snow_edges = snow_roads(G_aug, G_bis)
    fix_edges(G, snow_edges)

    floyd_results = load_floyd_warshall(G, quartier)

    dists = four_plows(G, floyd_results, snow_edges)
    total_4 = sum(dists)

    fast = [plow_cost(d, *TYPE_II) for d in dists]
    print("\n== Fastest: 4 type II snowplows ==")
    print("Total distance:", round(total_4, 2), "km")
    print("Total cost:", round(sum(c for c, _ in fast), 2), "€")
    print("Time:", format_duration(max(t for _, t in fast)))

    d1 = one_plow(G, floyd_results, snow_edges)
    cost_I, time_I = plow_cost(d1, *TYPE_I)
    cost_II, time_II = plow_cost(d1, *TYPE_II)

    print("\n== Fewest vehicles: 1 snowplow ==")
    print("Total distance:", round(d1, 2), "km")
    print(f"Total cost: {round(cost_I, 2)} € with type I, {round(cost_II, 2)} € with type II")
    print(f"Time: {format_duration(time_I)} with type I, {format_duration(time_II)} with type II")

    print("\n== Cheapest ==")
    cheap = [plow_cost(d, *TYPE_I) for d in dists]
    if d1 < total_4:
        if cost_I < cost_II:
            print("1 type I snowplow")
            print("Total cost:", round(cost_I, 2), "€")
            print("Time:", format_duration(time_I))
        else:
            print("1 type II snowplow")
            print("Total cost:", round(cost_II, 2), "€")
            print("Time:", format_duration(time_II))
        print("Total distance:", round(d1, 2), "km")
    elif cost_I < sum(c for c, _ in cheap):
        print("1 type I snowplow")
        print("Total cost:", round(cost_I, 2), "€")
        print("Time:", format_duration(time_I))
        print("Total distance:", round(d1, 2), "km")
    else:
        print("4 type I snowplows")
        print("Total cost:", round(sum(c for c, _ in cheap), 2), "€")
        print("Time:", format_duration(max(t for _, t in cheap)))
        print("Total distance:", round(total_4, 2), "km")


def main():
    print("================ ERO1 ================")
    for i, name in enumerate(QUARTIERS, 1):
        print(f"{i}) {name}")
    print()
    choice = int(input("Pick a neighborhood (1, 2, ...): "))
    quartier = QUARTIERS[choice - 1]

    G = import_G(os.path.join(DATABASE, "maps", quartier + ".gpickle"))
    G_aug = import_G(os.path.join(DATABASE, "eulerized_maps", quartier + "_aug.gpickle"))
    G_bis = nx.MultiGraph(G)

    print("Total road length:", round(sum_dist(G) / 1000, 2), "km")

    # Drone: 100 € per day plus 0.01 € per km
    km = sum_dist_circuit(G_bis, nx.eulerian_circuit(G_aug)) / 1000
    print("\n== Drone ==")
    print("Distance:", round(km, 2), "km")
    print("Cost:", round(km / 100 + 100, 2), "€")

    scenario(G, G_aug, quartier, 0.3)


if __name__ == "__main__":
    main()
