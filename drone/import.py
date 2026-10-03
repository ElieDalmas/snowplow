import itertools
import pickle
import sys
import time

import networkx as nx
from networkx.algorithms.matching import max_weight_matching

# Usage: python import.py <neighborhood> [...]
# Reads ../database/maps/<name>.gpickle and writes the eulerized graph
# to ../database/eulerized_maps/<name>_aug.gpickle


def import_G(filename):
    with open(filename, "rb") as f:
        return pickle.load(f).to_undirected()


def save_graph(G, filename):
    with open(filename, "wb") as f:
        pickle.dump(G, f, pickle.HIGHEST_PROTOCOL)
    print(f"Graph saved to {filename}")


def eulerize(G):
    """Chinese postman: duplicate the shortest paths between matched odd vertices."""
    G_bis = nx.MultiGraph(G)
    odd_nodes = [v for v, d in G_bis.degree() if d % 2 == 1]

    # Min weight matching = max weight matching on negated distances
    matching_graph = nx.Graph()
    for u, v in itertools.combinations(odd_nodes, 2):
        length = nx.dijkstra_path_length(G_bis, u, v, weight="length")
        matching_graph.add_edge(u, v, weight=-length)
    matching = max_weight_matching(matching_graph, maxcardinality=True)

    G_aug = nx.MultiGraph(G)
    for u, v in matching:
        path = nx.dijkstra_path(G, u, v, weight="length")
        for a, b in zip(path, path[1:]):
            G_aug.add_edge(a, b, weight=G_bis[a][b][0]["length"])
    return G_aug


if __name__ == "__main__":
    for name in sys.argv[1:]:
        start = time.time()
        G = import_G("../database/maps/" + name + ".gpickle")
        save_graph(eulerize(G), "../database/eulerized_maps/" + name + "_aug.gpickle")
        print(f"{time.time() - start:.1f} s")
