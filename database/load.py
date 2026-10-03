import pickle
import sys

import networkx as nx

# Usage: python load.py <file.gpickle> [...]

if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("Expecting filename as argument")
        sys.exit(1)

    for filename in sys.argv[1:]:
        print("Opening " + filename)
        with open(filename, "rb") as f:
            G = pickle.load(f)

        print("Number of nodes", len(G.nodes))
        print("Number of edges", len(G.edges))
        print("Average degree", sum(dict(G.degree).values()) / len(G.nodes))
        if G.is_directed():
            print("Strongly connected", nx.is_strongly_connected(G))
        else:
            print("Connected", nx.is_connected(G))
        print()
