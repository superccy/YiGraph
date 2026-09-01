"""NetworkX registry boundary shared by both planner baselines.

This is the dependency-free subset of YiGraph's dynamic registry needed by
the programmatic graph-tool runtime: module coverage, exclusions, and directed
graph adaptations. Keeping it local makes this experiment package standalone.
"""

from __future__ import annotations

import networkx as nx


MODULES_TO_SCAN = [
    nx.algorithms.centrality,
    nx.algorithms.community,
    nx.algorithms.community.modularity_max,
    nx.algorithms.community.label_propagation,
    nx.algorithms.community.louvain,
    nx.algorithms.link_analysis.pagerank_alg,
    nx.algorithms.link_analysis.hits_alg,
    nx.algorithms.components,
    nx.algorithms.connectivity,
    nx.algorithms.shortest_paths.generic,
    nx.algorithms.shortest_paths.weighted,
    nx.algorithms.shortest_paths.unweighted,
    nx.algorithms.shortest_paths.dense,
    nx.algorithms.simple_paths,
    nx.algorithms.cluster,
    nx.algorithms.clique,
    nx.algorithms.core,
    nx.algorithms.distance_measures,
    nx.algorithms.isomorphism,
    nx.algorithms.matching,
    nx.algorithms.flow,
    nx.algorithms.tree.recognition,
    nx.algorithms.tree.mst,
    nx.algorithms.dag,
    nx.algorithms.cycles,
    nx.algorithms.bridges,
    nx.algorithms.coloring,
    nx.algorithms.similarity,
    nx.algorithms.link_prediction,
    nx.algorithms.bipartite,
    nx.algorithms.bipartite.centrality,
    nx.algorithms.bipartite.cluster,
    nx.algorithms.traversal,
    nx.algorithms.tournament,
    nx.algorithms.operators,
    nx.algorithms.dominating,
    nx.algorithms.efficiency_measures,
    nx.algorithms.euler,
    nx.algorithms.reciprocity,
    nx.algorithms.assortativity,
    nx.algorithms.vitality,
    nx.algorithms.wiener,
]

ALGORITHMS_TO_EXCLUDE = {
    "communicability_betweenness_centrality",
    "current_flow_betweenness_centrality",
    "approximate_current_flow_betweenness_centrality",
    "shortest_path_length",
    "all_simple_paths",
    "all_shortest_paths",
    "all_simple_edge_paths",
}

UNDIRECTED_ONLY_ALGORITHMS = {
    "connected_components": "weakly_connected_components",
    "number_connected_components": "number_weakly_connected_components",
    "node_connected_component": "node_weakly_connected_component",
    "is_connected": "is_weakly_connected",
    "is_bipartite": None,
    "bipartite_sets": None,
    "triangles": None,
    "clustering": None,
}
