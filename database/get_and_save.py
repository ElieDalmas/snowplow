import pickle
import sys

import osmnx as ox

# Usage: python get_and_save.py <neighborhood>
# The whole city is fetched with "Montréal, Québec, Canada" as place name.

if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("Expecting neighborhood name as argument")
        sys.exit(1)

    name = sys.argv[1]
    G = ox.graph_from_place(name + ", Montréal, Québec, Canada", network_type="drive")
    G = ox.distance.add_edge_lengths(G)

    filename = "maps/" + name + ".gpickle"
    with open(filename, "wb") as f:
        pickle.dump(G, f, pickle.HIGHEST_PROTOCOL)
    print(f"Graph saved to {filename}")
