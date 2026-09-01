#!/usr/bin/env python3
"""Generate dependency-resolution dataset samples with GPT-5.4."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALGORITHMS_YAML = PROJECT_ROOT / "aag" / "knowledge_base" / "algorithms.yaml"
DEFAULT_OUTPUT = Path(__file__).resolve().with_name("dependency_resolution_dataset_100_llm.json")
DEFAULT_MODEL = "gpt-5.4-mini"

STRUCTURES = [
    "A->B(data)",
    "A->B(graph)",
    "(graph)A->C<-B(graph)",
    "(data)A->C<-B(data)",
    "(graph)A->C<-B(data)",
]

STRUCTURE_RULES = {
    "A->B(data)": {
        "target_step_id": 2,
        "parent_ids": [1],
        "step_count": 2,
        "gold_graph": 0,
        "gold_param": 1,
        "edges": [{"source": 1, "target": 2, "dependency_type": "data"}],
    },
    "A->B(graph)": {
        "target_step_id": 2,
        "parent_ids": [1],
        "step_count": 2,
        "gold_graph": 1,
        "gold_param": 0,
        "edges": [{"source": 1, "target": 2, "dependency_type": "graph"}],
    },
    "(graph)A->C<-B(graph)": {
        "target_step_id": 3,
        "parent_ids": [1, 2],
        "step_count": 3,
        "gold_graph": 2,
        "gold_param": 0,
        "edges": [
            {"source": 1, "target": 3, "dependency_type": "graph"},
            {"source": 2, "target": 3, "dependency_type": "graph"},
        ],
    },
    "(data)A->C<-B(data)": {
        "target_step_id": 3,
        "parent_ids": [1, 2],
        "step_count": 3,
        "gold_graph": 0,
        "gold_param": 2,
        "edges": [
            {"source": 1, "target": 3, "dependency_type": "data"},
            {"source": 2, "target": 3, "dependency_type": "data"},
        ],
    },
    "(graph)A->C<-B(data)": {
        "target_step_id": 3,
        "parent_ids": [1, 2],
        "step_count": 3,
        "gold_graph": 1,
        "gold_param": 1,
        "edges": [
            {"source": 1, "target": 3, "dependency_type": "graph"},
            {"source": 2, "target": 3, "dependency_type": "data"},
        ],
    },
}


SYSTEM_PROMPT = """You are a dataset generation expert for graph-workflow dependency evaluation.

Generate exactly the requested number of high-quality JSON samples for dependency-resolution benchmarking.

Hard rules:
1. Output JSON only. No markdown. No explanation.
2. The JSON schema, field names, nesting structure, and style must match the provided examples exactly.
3. Use only algorithms from the provided candidate algorithm list.
4. Do not use any algorithm whose task type is Graph Query.
5. Every `question` field must be written in English.
6. Every parent step must keep `output_id = 1` as the raw algorithm output with field_key `original_result`.
7. If a parent contributes a dependency, it must also have `output_id = 2`, and `output_id = 2` must contain only the gold dependency field(s), with no distractor fields.
8. Gold dependencies must be minimal, exact, and fully consistent with the requested structure.
9. The generated sample must be semantically different from previously generated samples of the same structure.
"""


STRICT_EXAMPLES: Dict[str, Dict[str, Any]] = {
    "A->B(data)": {
        "structure": "A->B(data)",
        "target_step_id": 2,
        "data_dependency_parent_ids": [1],
        "steps": [
            {
                "step_id": 1,
                "label": "A",
                "question": "Identify the account connected to the largest number of other accounts in the network.",
                "task_type": "graph_algorithm",
                "graph_algorithm": "degree_centrality",
                "tool_metadata": {
                    "name": "degree_centrality",
                    "engine": "networkx",
                    "input_params": {
                        "G": {"type": "graph", "required": True}
                    }
                },
                "outputs": [
                    {
                        "output_id": 1,
                        "task_subtype": "graph_algorithm",
                        "source": "degree_centrality",
                        "output_schema": {
                            "description": "Raw output of degree_centrality",
                            "type": "dict",
                            "fields": {
                                "original_result": {
                                    "type": "dict[str,float]",
                                    "field_description": "Mapping from node ID to degree centrality score"
                                }
                            }
                        },
                        "value": {
                            "original_result": {
                                "acct_200001": 0.91,
                                "acct_200002": 0.87,
                                "acct_200003": 0.84,
                                "acct_200004": 0.79,
                                "acct_200005": 0.75
                            }
                        }
                    },
                    {
                        "output_id": 2,
                        "task_subtype": "post_processing",
                        "source": "python code",
                        "output_schema": {
                            "description": "Post-processed parameter output",
                            "type": "dict",
                            "fields": {
                                "starting_account_id": {
                                    "type": "str",
                                    "field_description": "The ID of the most influential user account."
                                }
                            }
                        },
                        "value": {
                            "starting_account_id": "acct_200001"
                        }
                    }
                ]
            },
            {
                "step_id": 2,
                "label": "B",
                "question": "Starting from the most influential account to expand the suspicious transaction chain.",
                "task_type": "graph_algorithm",
                "graph_algorithm": "bfs_tree",
                "tool_metadata": {
                    "name": "bfs_tree",
                    "engine": "networkx",
                    "input_params": {
                        "G": {"type": "graph", "required": True},
                        "source": {"type": "node", "required": True},
                        "reverse": {"type": "bool", "required": False, "default": False},
                        "depth_limit": {"type": "int", "required": False}
                    }
                }
            }
        ],
        "gold": {
            "graph_dependencies": [],
            "parameter_dependencies": [
                {
                    "parent_step_id": 1,
                    "parent_step_output_id": 2,
                    "field_key": "starting_account_id",
                    "use_as": "parameter",
                    "maps_to": "source"
                }
            ]
        },
        "id": "example_001",
        "dataset_name": "dependency_resolution_dataset_100",
        "source": "gpt54_generated_example",
        "expected_dependency_summary": {
            "graph_dependency_count": 0,
            "parameter_dependency_count": 1
        },
        "dag": {
            "nodes": [
                {"step_id": 1, "label": "A"},
                {"step_id": 2, "label": "B"}
            ],
            "edges": [
                {"source": 1, "target": 2, "dependency_type": "data"}
            ]
        }
    },
    "A->B(graph)": {
        "structure": "A->B(graph)",
        "target_step_id": 2,
        "data_dependency_parent_ids": [1],
        "steps": [
            {
                "step_id": 1,
                "label": "A",
                "question": "Construct a local subgraph centered on the four most influential accounts.",
                "task_type": "graph_algorithm",
                "graph_algorithm": "out_degree_centrality",
                "tool_metadata": {
                    "name": "out_degree_centrality",
                    "engine": "networkx",
                    "input_params": {
                        "G": {"type": "graph", "required": True}
                    }
                },
                "outputs": [
                    {
                        "output_id": 1,
                        "task_subtype": "graph_algorithm",
                        "source": "out_degree_centrality",
                        "output_schema": {
                            "description": "Raw output of out_degree_centrality",
                            "type": "dict",
                            "fields": {
                                "original_result": {
                                    "type": "dict[str,float]",
                                    "field_description": "Mapping from node ID to out-degree centrality score"
                                }
                            }
                        },
                        "value": {
                            "original_result": {
                                "acct_210001": 0.89,
                                "acct_210002": 0.86,
                                "acct_210003": 0.82,
                                "acct_210004": 0.79,
                                "acct_210005": 0.77
                            }
                        }
                    },
                    {
                        "output_id": 2,
                        "task_subtype": "post_processing",
                        "source": "python code",
                        "output_schema": {
                            "description": "Post-processed graph construction output",
                            "type": "dict",
                            "fields": {
                                "target_account_ids": {
                                    "type": "list[str]",
                                    "field_description": "Account IDs used to construct the subgraph"
                                }
                            }
                        },
                        "value": {
                            "target_account_ids": [
                                "acct_210001",
                                "acct_210002",
                                "acct_210003",
                                "acct_210004"
                            ]
                        }
                    }
                ]
            },
            {
                "step_id": 2,
                "label": "B",
                "question": "Find the separate groups in the subgraph.",
                "task_type": "graph_algorithm",
                "graph_algorithm": "weakly_connected_components",
                "tool_metadata": {
                    "name": "weakly_connected_components",
                    "engine": "networkx",
                    "input_params": {
                        "G": {"type": "graph", "required": True}
                    }
                }
            }
        ],
        "gold": {
            "graph_dependencies": [
                {
                    "parent_step_id": 1,
                    "parent_step_output_id": 2,
                    "field_key": "target_account_ids",
                    "use_as": "graph",
                    "maps_to": "G"
                }
            ],
            "parameter_dependencies": []
        },
        "id": "example_002",
        "dataset_name": "dependency_resolution_dataset_100",
        "source": "gpt54_generated_example",
        "expected_dependency_summary": {
            "graph_dependency_count": 1,
            "parameter_dependency_count": 0
        },
        "dag": {
            "nodes": [
                {"step_id": 1, "label": "A"},
                {"step_id": 2, "label": "B"}
            ],
            "edges": [
                {"source": 1, "target": 2, "dependency_type": "graph"}
            ]
        }
    },
    "(graph)A->C<-B(graph)": {
        "structure": "(graph)A->C<-B(graph)",
        "target_step_id": 3,
        "data_dependency_parent_ids": [1, 2],
        "steps": [
            {
                "step_id": 1,
                "label": "A",
                "question": "Identify the initial group composed of the top three accounts.",
                "task_type": "graph_algorithm",
                "graph_algorithm": "in_degree_centrality",
                "tool_metadata": {
                    "name": "in_degree_centrality",
                    "engine": "networkx",
                    "input_params": {
                        "G": {"type": "graph", "required": True}
                    }
                },
                "outputs": [
                    {
                        "output_id": 1,
                        "task_subtype": "graph_algorithm",
                        "source": "in_degree_centrality",
                        "output_schema": {
                            "description": "Raw output of in_degree_centrality",
                            "type": "dict",
                            "fields": {
                                "original_result": {
                                    "type": "dict[str,float]",
                                    "field_description": "Mapping from node ID to in-degree centrality score"
                                }
                            }
                        },
                        "value": {
                            "original_result": {
                                "acct_220001": 0.93,
                                "acct_220002": 0.88,
                                "acct_220003": 0.84,
                                "acct_220004": 0.81,
                                "acct_220005": 0.78
                            }
                        }
                    },
                    {
                        "output_id": 2,
                        "task_subtype": "post_processing",
                        "source": "python code",
                        "output_schema": {
                            "description": "Post-processed graph construction output",
                            "type": "dict",
                            "fields": {
                                "group_a_account_ids": {
                                    "type": "list[str]",
                                    "field_description": "Three accounts set used to construct the downstream merged subgraph"
                                }
                            }
                        },
                        "value": {
                            "group_a_account_ids": [
                                "acct_220001",
                                "acct_220002",
                                "acct_220003"
                            ]
                        }
                    }
                ]
            },
            {
                "step_id": 2,
                "label": "B",
                "question": "Identify the initial group composed of the top three accounts for downstream subgraph construction.",
                "task_type": "graph_algorithm",
                "graph_algorithm": "out_degree_centrality",
                "tool_metadata": {
                    "name": "out_degree_centrality",
                    "engine": "networkx",
                    "input_params": {
                        "G": {"type": "graph", "required": True}
                    }
                },
                "outputs": [
                    {
                        "output_id": 1,
                        "task_subtype": "graph_algorithm",
                        "source": "out_degree_centrality",
                        "output_schema": {
                            "description": "Raw output of out_degree_centrality",
                            "type": "dict",
                            "fields": {
                                "original_result": {
                                    "type": "dict[str,float]",
                                    "field_description": "Mapping from node ID to out-degree centrality score"
                                }
                            }
                        },
                        "value": {
                            "original_result": {
                                "acct_220101": 0.91,
                                "acct_220102": 0.87,
                                "acct_220103": 0.83,
                                "acct_220104": 0.8,
                                "acct_220105": 0.76
                            }
                        }
                    },
                    {
                        "output_id": 2,
                        "task_subtype": "post_processing",
                        "source": "python code",
                        "output_schema": {
                            "description": "Post-processed graph construction output",
                            "type": "dict",
                            "fields": {
                                "group_b_account_ids": {
                                    "type": "list[str]",
                                    "field_description": "Three accounts set used to construct the downstream merged subgraph"
                                }
                            }
                        },
                        "value": {
                            "group_b_account_ids": [
                                "acct_220101",
                                "acct_220102",
                                "acct_220103"
                            ]
                        }
                    }
                ]
            },
            {
                "step_id": 3,
                "label": "C",
                "question": "Find strongly connected components on the merged subgraph induced by the two upstream account groups.",
                "task_type": "graph_algorithm",
                "graph_algorithm": "strongly_connected_components",
                "tool_metadata": {
                    "name": "strongly_connected_components",
                    "engine": "networkx",
                    "input_params": {
                        "G": {"type": "graph", "required": True}
                    }
                }
            }
        ],
        "gold": {
            "graph_dependencies": [
                {
                    "parent_step_id": 1,
                    "parent_step_output_id": 2,
                    "field_key": "group_a_account_ids",
                    "use_as": "graph",
                    "maps_to": "G"
                },
                {
                    "parent_step_id": 2,
                    "parent_step_output_id": 2,
                    "field_key": "group_b_account_ids",
                    "use_as": "graph",
                    "maps_to": "G"
                }
            ],
            "parameter_dependencies": []
        },
        "id": "example_003",
        "dataset_name": "dependency_resolution_dataset_100",
        "source": "gpt54_generated_example",
        "expected_dependency_summary": {
            "graph_dependency_count": 2,
            "parameter_dependency_count": 0
        },
        "dag": {
            "nodes": [
                {"step_id": 1, "label": "A"},
                {"step_id": 2, "label": "B"},
                {"step_id": 3, "label": "C"}
            ],
            "edges": [
                {"source": 1, "target": 3, "dependency_type": "graph"},
                {"source": 2, "target": 3, "dependency_type": "graph"}
            ]
        }
    },
    "(data)A->C<-B(data)": {
        "structure": "(data)A->C<-B(data)",
        "target_step_id": 3,
        "data_dependency_parent_ids": [1, 2],
        "steps": [
            {
                "step_id": 1,
                "label": "A",
                "question": "Find the most influential account.",
                "task_type": "graph_algorithm",
                "graph_algorithm": "degree_centrality",
                "tool_metadata": {
                    "name": "degree_centrality",
                    "engine": "networkx",
                    "input_params": {
                        "G": {"type": "graph", "required": True}
                    }
                },
                "outputs": [
                    {
                        "output_id": 1,
                        "task_subtype": "graph_algorithm",
                        "source": "degree_centrality",
                        "output_schema": {
                            "description": "Raw output of degree_centrality",
                            "type": "dict",
                            "fields": {
                                "original_result": {
                                    "type": "dict[str,float]",
                                    "field_description": "Mapping from node ID to degree centrality score"
                                }
                            }
                        },
                        "value": {
                            "original_result": {
                                "acct_230001": 0.9,
                                "acct_230002": 0.85,
                                "acct_230003": 0.81,
                                "acct_230004": 0.77,
                                "acct_230005": 0.74
                            }
                        }
                    },
                    {
                        "output_id": 2,
                        "task_subtype": "post_processing",
                        "source": "python code",
                        "output_schema": {
                            "description": "Post-processed parameter output",
                            "type": "dict",
                            "fields": {
                                "source_account_id": {
                                    "type": "str",
                                    "field_description": "The most influential account ID."
                                }
                            }
                        },
                        "value": {
                            "source_account_id": "acct_230001"
                        }
                    }
                ]
            },
            {
                "step_id": 2,
                "label": "B",
                "question": "Compute the best core numbers to determine the depth limit.",
                "task_type": "graph_algorithm",
                "graph_algorithm": "core_number",
                "tool_metadata": {
                    "name": "core_number",
                    "engine": "networkx",
                    "input_params": {
                        "G": {"type": "graph", "required": True}
                    }
                },
                "outputs": [
                    {
                        "output_id": 1,
                        "task_subtype": "graph_algorithm",
                        "source": "core_number",
                        "output_schema": {
                            "description": "Raw output of core_number",
                            "type": "dict",
                            "fields": {
                                "original_result": {
                                    "type": "dict[str,int]",
                                    "field_description": "Mapping from node ID to core number"
                                }
                            }
                        },
                        "value": {
                            "original_result": {
                                "acct_230101": 4,
                                "acct_230102": 3,
                                "acct_230103": 3,
                                "acct_230104": 2,
                                "acct_230105": 2
                            }
                        }
                    },
                    {
                        "output_id": 2,
                        "task_subtype": "post_processing",
                        "source": "python code",
                        "output_schema": {
                            "description": "Post-processed parameter output",
                            "type": "dict",
                            "fields": {
                                "depth_limit_value": {
                                    "type": "int",
                                    "field_description": "Depth limit."
                                }
                            }
                        },
                        "value": {
                            "depth_limit_value": 3
                        }
                    }
                ]
            },
            {
                "step_id": 3,
                "label": "C",
                "question": "Run DFS using the source account and the depth limit.",
                "task_type": "graph_algorithm",
                "graph_algorithm": "dfs_tree",
                "tool_metadata": {
                    "name": "dfs_tree",
                    "engine": "networkx",
                    "input_params": {
                        "G": {"type": "graph", "required": True},
                        "source": {"type": "node", "required": False},
                        "depth_limit": {"type": "int", "required": False}
                    }
                }
            }
        ],
        "gold": {
            "graph_dependencies": [],
            "parameter_dependencies": [
                {
                    "parent_step_id": 1,
                    "parent_step_output_id": 2,
                    "field_key": "source_account_id",
                    "use_as": "parameter",
                    "maps_to": "source"
                },
                {
                    "parent_step_id": 2,
                    "parent_step_output_id": 2,
                    "field_key": "depth_limit_value",
                    "use_as": "parameter",
                    "maps_to": "depth_limit"
                }
            ]
        },
        "id": "example_004",
        "dataset_name": "dependency_resolution_dataset_100",
        "source": "gpt54_generated_example",
        "expected_dependency_summary": {
            "graph_dependency_count": 0,
            "parameter_dependency_count": 2
        },
        "dag": {
            "nodes": [
                {"step_id": 1, "label": "A"},
                {"step_id": 2, "label": "B"},
                {"step_id": 3, "label": "C"}
            ],
            "edges": [
                {"source": 1, "target": 3, "dependency_type": "data"},
                {"source": 2, "target": 3, "dependency_type": "data"}
            ]
        }
    },
    "(graph)A->C<-B(data)": {
        "structure": "(graph)A->C<-B(data)",
        "target_step_id": 3,
        "data_dependency_parent_ids": [1, 2],
        "steps": [
            {
                "step_id": 1,
                "label": "A",
                "question": "Find the biggest community in the graph.",
                "task_type": "graph_algorithm",
                "graph_algorithm": "louvain_communities",
                "tool_metadata": {
                    "name": "louvain_communities",
                    "engine": "networkx",
                    "input_params": {
                        "G": {"type": "graph", "required": True},
                        "weight": {"type": "str", "required": False, "default": "weight"},
                        "resolution": {"type": "float", "required": False, "default": 1},
                        "threshold": {"type": "float", "required": False, "default": 1e-07},
                        "max_level": {"type": "int", "required": False},
                        "seed": {"type": "int", "required": False}
                    }
                },
                "outputs": [
                    {
                        "output_id": 1,
                        "task_subtype": "graph_algorithm",
                        "source": "louvain_communities",
                        "output_schema": {
                            "description": "Raw output of louvain_communities",
                            "type": "dict",
                            "fields": {
                                "original_result": {
                                    "type": "list[set[str]]",
                                    "field_description": "List of detected communities, where each community is represented as a set of account IDs"
                                }
                            }
                        },
                        "value": {
                            "original_result": [
                                [
                                    "acct_240001",
                                    "acct_240002",
                                    "acct_240003",
                                    "acct_240004"
                                ],
                                [
                                    "acct_240005",
                                    "acct_240006",
                                    "acct_240007"
                                ],
                                [
                                    "acct_240008",
                                    "acct_240009"
                                ]
                            ]
                        }
                    },
                    {
                        "output_id": 2,
                        "task_subtype": "post_processing",
                        "source": "python code",
                        "output_schema": {
                            "description": "Post-processed graph construction output",
                            "type": "dict",
                            "fields": {
                                "target_account_ids": {
                                    "type": "list[str]",
                                    "field_description": "Account IDs used to construct the downstream local subgraph"
                                }
                            }
                        },
                        "value": {
                            "target_account_ids": [
                                "acct_240001",
                                "acct_240002",
                                "acct_240003",
                                "acct_240004"
                            ]
                        }
                    }
                ]
            },
            {
                "step_id": 2,
                "label": "B",
                "question": "Compute degree centrality and return a suitable k value for the downstream k-core analysis.",
                "task_type": "graph_algorithm",
                "graph_algorithm": "degree_centrality",
                "tool_metadata": {
                    "name": "degree_centrality",
                    "engine": "networkx",
                    "input_params": {
                        "G": {"type": "graph", "required": True}
                    }
                },
                "outputs": [
                    {
                        "output_id": 1,
                        "task_subtype": "graph_algorithm",
                        "source": "degree_centrality",
                        "output_schema": {
                            "description": "Raw output of degree_centrality",
                            "type": "dict",
                            "fields": {
                                "original_result": {
                                    "type": "dict[str,float]",
                                    "field_description": "Mapping from node ID to degree centrality score"
                                }
                            }
                        },
                        "value": {
                            "original_result": {
                                "acct_240101": 0.89,
                                "acct_240102": 0.86,
                                "acct_240103": 0.83,
                                "acct_240104": 0.8,
                                "acct_240105": 0.77
                            }
                        }
                    },
                    {
                        "output_id": 2,
                        "task_subtype": "post_processing",
                        "source": "python code",
                        "output_schema": {
                            "description": "Post-processed parameter output",
                            "type": "dict",
                            "fields": {
                                "selected_core_k": {
                                    "type": "int",
                                    "field_description": "k parameter for the downstream k_core algorithm"
                                }
                            }
                        },
                        "value": {
                            "selected_core_k": 3
                        }
                    }
                ]
            },
            {
                "step_id": 3,
                "label": "C",
                "question": "Run k_core on the subgraph induced by the selected accounts, using the upstream k value as a parameter.",
                "task_type": "graph_algorithm",
                "graph_algorithm": "k_core",
                "tool_metadata": {
                    "name": "k_core",
                    "engine": "networkx",
                    "input_params": {
                        "G": {"type": "graph", "required": True},
                        "k": {"type": "int", "required": False},
                        "core_number": {"type": "dict[str,int]", "required": False}
                    }
                }
            }
        ],
        "gold": {
            "graph_dependencies": [
                {
                    "parent_step_id": 1,
                    "parent_step_output_id": 2,
                    "field_key": "target_account_ids",
                    "use_as": "graph",
                    "maps_to": "G"
                }
            ],
            "parameter_dependencies": [
                {
                    "parent_step_id": 2,
                    "parent_step_output_id": 2,
                    "field_key": "selected_core_k",
                    "use_as": "parameter",
                    "maps_to": "k"
                }
            ]
        },
        "id": "example_005",
        "dataset_name": "dependency_resolution_dataset_100",
        "source": "gpt54_generated_example",
        "expected_dependency_summary": {
            "graph_dependency_count": 1,
            "parameter_dependency_count": 1
        },
        "dag": {
            "nodes": [
                {"step_id": 1, "label": "A"},
                {"step_id": 2, "label": "B"},
                {"step_id": 3, "label": "C"}
            ],
            "edges": [
                {"source": 1, "target": 3, "dependency_type": "graph"},
                {"source": 2, "target": 3, "dependency_type": "data"}
            ]
        }
    }
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate dependency-resolution dataset samples with GPT-5.4")
    parser.add_argument("--algorithms-yaml", type=Path, default=DEFAULT_ALGORITHMS_YAML)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--base-url", type=str, default="https://gitaigc.com/v1/")
    parser.add_argument("--api-key", type=str, default="sk-cD2EGH7Bkzg5AuRuB32uyCiOKoaHDXqmVZaQgIopsJCG1rK7")
    parser.add_argument("--samples-per-structure", type=int, default=20)
    parser.add_argument("--candidate-size", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--max-retries", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20260331)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run-prompt", action="store_true", help="Print one assembled prompt and exit")
    return parser.parse_args()


def load_yaml(path: Path) -> Any:
    import yaml

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_algorithms(path: Path) -> List[Dict[str, Any]]:
    raw = load_yaml(path)
    filtered = []
    for item in raw:
        if item.get("task_type_id") == "Graph Query":
            continue
        deployment = item.get("Deployment_method", {})
        filtered.append(
            {
                "id": item.get("id"),
                "input_schema": deployment.get("input_schema", {}),
                "output_schema": deployment.get("output_schema", {}),
            }
        )
    if not filtered:
        raise ValueError("No algorithms available after filtering Graph Query")
    return filtered


def summarize_sample(sample: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": sample["id"],
        "algorithms": [step["graph_algorithm"] for step in sample["steps"]],
        "gold": {
            "graph": [f"{item['field_key']} -> {item['maps_to']}" for item in sample["gold"]["graph_dependencies"]],
            "parameter": [f"{item['field_key']} -> {item['maps_to']}" for item in sample["gold"]["parameter_dependencies"]],
        },
        "question_signature": " | ".join(step["question"] for step in sample["steps"]),
    }


def build_user_prompt(
    structure: str,
    candidate_algorithms: Sequence[Dict[str, Any]],
    previous_same_structure: Sequence[Dict[str, Any]],
    batch_size: int,
) -> str:
    rules = STRUCTURE_RULES[structure]
    example_blocks = []
    for name in STRUCTURES:
        example_blocks.append(f"### Example for {name}\n{json.dumps(STRICT_EXAMPLES[name], ensure_ascii=False, indent=2)}")

    return f"""Generate exactly {batch_size} dataset samples for dependency-resolution evaluation.

## Target structure
{structure}

## Required structure summary
- target_step_id: {rules["target_step_id"]}
- data_dependency_parent_ids: {rules["parent_ids"]}
- number of steps: {rules["step_count"]}
- gold graph dependency count: {rules["gold_graph"]}
- gold parameter dependency count: {rules["gold_param"]}

## Candidate algorithms
You may only use algorithms from the following candidate set.
Each algorithm only includes id, input_schema, and output_schema.

{json.dumps(candidate_algorithms, ensure_ascii=False, indent=2)}

## Previously generated samples of the same structure
Avoid semantic duplication with the following existing samples of the same structure.
Do not generate a sample with nearly identical algorithm combinations, dependency fields, or question intent.

{json.dumps(previous_same_structure, ensure_ascii=False, indent=2)}

## Output requirements
Return exactly {batch_size} samples as a single JSON array.
Each array element must be one JSON object with the following top-level fields:
- structure
- target_step_id
- data_dependency_parent_ids
- steps
- gold
- id
- dataset_name
- source
- expected_dependency_summary
- dag

## Hard rules
1. Every `question` field must be in English.
2. The output JSON must strictly follow the same schema, field names, nesting structure, and style as the provided examples.
3. Match the requested structure exactly.
4. Use only algorithms from the candidate set.
5. Every parent step must contain `output_id = 1` with raw algorithm output:
   - field_key must be `original_result`
6. If a parent contributes a gold dependency, it must also contain `output_id = 2`, and `output_id = 2` must contain only the gold dependency field(s), with no distractor fields.
7. `gold.graph_dependencies` and `gold.parameter_dependencies` must exactly match the structure requirements above.
8. `expected_dependency_summary` must exactly match the gold counts.
9. `dag.nodes` and `dag.edges` must exactly match the structure.
10. Use descriptive field names. Never use generic field names such as `result`, `data`, `value`, or `output` for post-processing fields.
11. The generated sample must be directly appendable to the dataset file without any schema transformation.
12. The top-level return value must be a JSON array with exactly {batch_size} objects.

## Examples
{chr(10).join(example_blocks)}

## Output format
Return JSON only.
Return a JSON array, not a single object.
Do not wrap in markdown.
Do not add commentary.
"""


def extract_json_payload(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.S)
        if not match:
            match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def ensure_english(text: str) -> bool:
    return re.search(r"[\u4e00-\u9fff]", text or "") is None


def edge_signature(edges: Sequence[Dict[str, Any]]) -> List[Tuple[int, int, str]]:
    return sorted((int(edge["source"]), int(edge["target"]), edge["dependency_type"]) for edge in edges)


def normalize_sample(sample: Dict[str, Any], sample_id: str, structure: str) -> Dict[str, Any]:
    sample = deepcopy(sample)
    rules = STRUCTURE_RULES[structure]
    sample["structure"] = structure
    sample["id"] = sample_id
    sample["dataset_name"] = "dependency_resolution_dataset_100"
    sample["source"] = "gpt54_generated"
    sample["target_step_id"] = rules["target_step_id"]
    sample["data_dependency_parent_ids"] = rules["parent_ids"]
    sample["expected_dependency_summary"] = {
        "graph_dependency_count": len(sample["gold"]["graph_dependencies"]),
        "parameter_dependency_count": len(sample["gold"]["parameter_dependencies"]),
    }
    sample["dag"] = {
        "nodes": [{"step_id": step["step_id"], "label": step["label"]} for step in sample["steps"]],
        "edges": deepcopy(rules["edges"]),
    }
    return sample


def validate_sample(sample: Dict[str, Any], structure: str, candidate_ids: Sequence[str], existing_signatures: set[Tuple[Any, ...]]) -> None:
    rules = STRUCTURE_RULES[structure]
    required_top = {
        "structure",
        "target_step_id",
        "data_dependency_parent_ids",
        "steps",
        "gold",
        "id",
        "dataset_name",
        "source",
        "expected_dependency_summary",
        "dag",
    }
    missing = required_top - set(sample.keys())
    if missing:
        raise ValueError(f"Missing top-level keys: {sorted(missing)}")
    if sample["structure"] != structure:
        raise ValueError(f"Structure mismatch: expected {structure}, got {sample['structure']}")
    if int(sample["target_step_id"]) != rules["target_step_id"]:
        raise ValueError("target_step_id mismatch")
    if list(sample["data_dependency_parent_ids"]) != rules["parent_ids"]:
        raise ValueError("data_dependency_parent_ids mismatch")
    if len(sample["steps"]) != rules["step_count"]:
        raise ValueError("step count mismatch")
    if edge_signature(sample["dag"]["edges"]) != edge_signature(rules["edges"]):
        raise ValueError("dag edges mismatch")

    graph_count = len(sample["gold"]["graph_dependencies"])
    param_count = len(sample["gold"]["parameter_dependencies"])
    if graph_count != rules["gold_graph"] or param_count != rules["gold_param"]:
        raise ValueError("gold dependency count mismatch")
    if sample["expected_dependency_summary"]["graph_dependency_count"] != graph_count:
        raise ValueError("expected graph dependency count mismatch")
    if sample["expected_dependency_summary"]["parameter_dependency_count"] != param_count:
        raise ValueError("expected parameter dependency count mismatch")

    candidate_ids_set = set(candidate_ids)
    step_map = {}
    for step in sample["steps"]:
        if not ensure_english(step["question"]):
            raise ValueError("question contains non-English characters")
        if step.get("task_type") != "graph_algorithm":
            raise ValueError("task_type must be graph_algorithm")
        if step["graph_algorithm"] not in candidate_ids_set:
            raise ValueError(f"algorithm not in candidate set: {step['graph_algorithm']}")
        step_map[int(step["step_id"])] = step

    for parent_id in rules["parent_ids"]:
        step = step_map[parent_id]
        outputs = step.get("outputs")
        if not outputs:
            raise ValueError(f"parent step {parent_id} missing outputs")
        output_map = {int(out["output_id"]): out for out in outputs}
        if 1 not in output_map:
            raise ValueError(f"parent step {parent_id} missing output_id=1")
        if "original_result" not in output_map[1]["value"]:
            raise ValueError(f"parent step {parent_id} output_id=1 missing original_result")

    for dep in sample["gold"]["graph_dependencies"] + sample["gold"]["parameter_dependencies"]:
        step_id = int(dep["parent_step_id"])
        output_id = int(dep["parent_step_output_id"])
        field_key = dep["field_key"]
        step = step_map.get(step_id)
        if not step:
            raise ValueError("gold references unknown parent step")
        output_map = {int(out["output_id"]): out for out in step.get("outputs", [])}
        if output_id not in output_map:
            raise ValueError("gold references unknown output_id")
        output = output_map[output_id]
        if field_key not in output["value"] or field_key not in output["output_schema"]["fields"]:
            raise ValueError("gold references unknown field_key")

    signature = sample_signature(sample)
    if signature in existing_signatures:
        raise ValueError("duplicate sample signature")


def sample_signature(sample: Dict[str, Any]) -> Tuple[Any, ...]:
    algos = tuple(step["graph_algorithm"] for step in sample["steps"])
    gold_graph = tuple(sorted((item["parent_step_id"], item["parent_step_output_id"], item["field_key"], item["maps_to"]) for item in sample["gold"]["graph_dependencies"]))
    gold_param = tuple(sorted((item["parent_step_id"], item["parent_step_output_id"], item["field_key"], item["maps_to"]) for item in sample["gold"]["parameter_dependencies"]))
    questions = tuple(step["question"].strip().lower() for step in sample["steps"])
    return (sample["structure"], algos, gold_graph, gold_param, questions)


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str, temperature: float):
        from openai import OpenAI

        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.temperature = temperature

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
        )
        return response.choices[0].message.content or ""


def save_dataset(path: Path, dataset: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)


def load_existing_output(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    args = parse_args()
    if not args.api_key and not args.dry_run_prompt:
        raise ValueError("OPENAI_API_KEY or --api-key is required")

    rng = random.Random(args.seed)
    algorithms = load_algorithms(args.algorithms_yaml)

    if args.resume:
        dataset = load_existing_output(args.output)
    else:
        dataset = []

    by_structure: Dict[str, List[Dict[str, Any]]] = {name: [] for name in STRUCTURES}
    for sample in dataset:
        if sample["structure"] in by_structure:
            by_structure[sample["structure"]].append(sample)

    existing_signatures = {sample_signature(sample) for sample in dataset}

    if args.dry_run_prompt:
        structure = STRUCTURES[0]
        candidates = rng.sample(algorithms, min(args.candidate_size, len(algorithms)))
        prompt = build_user_prompt(
            structure,
            candidates,
            [summarize_sample(sample) for sample in by_structure[structure]],
            min(args.batch_size, args.samples_per_structure),
        )
        print(prompt)
        return

    llm = LLMClient(args.base_url, args.api_key, args.model, args.temperature)
    next_id = len(dataset) + 1

    for structure in STRUCTURES:
        while len(by_structure[structure]) < args.samples_per_structure:
            success = False
            previous_summary = [summarize_sample(sample) for sample in by_structure[structure]]
            batch_target = min(args.batch_size, args.samples_per_structure - len(by_structure[structure]))
            for attempt in range(1, args.max_retries + 1):
                candidates = rng.sample(algorithms, min(args.candidate_size, len(algorithms)))
                candidate_ids = [item["id"] for item in candidates]
                user_prompt = build_user_prompt(structure, candidates, previous_summary, batch_target)
                raw = llm.generate(SYSTEM_PROMPT, user_prompt)
                try:
                    payload = extract_json_payload(raw)
                except Exception as exc:
                    print(f"[{structure}] attempt {attempt}/{args.max_retries} failed: {exc}")
                    continue

                if isinstance(payload, dict):
                    payload = [payload]
                if not isinstance(payload, list):
                    print(f"[{structure}] attempt {attempt}/{args.max_retries} failed: top-level payload must be a JSON array")
                    continue
                if len(payload) != batch_target:
                    print(
                        f"[{structure}] attempt {attempt}/{args.max_retries} failed: "
                        f"expected {batch_target} samples, got {len(payload)}"
                    )
                    continue

                accepted_samples: List[Dict[str, Any]] = []
                temp_signatures = set(existing_signatures)
                for index, raw_sample in enumerate(payload, start=1):
                    try:
                        sample = normalize_sample(raw_sample, f"dep_{next_id + len(accepted_samples):03d}", structure)
                        validate_sample(sample, structure, candidate_ids, temp_signatures)
                    except Exception as exc:
                        print(
                            f"[{structure}] attempt {attempt}/{args.max_retries} "
                            f"item {index}/{len(payload)} invalid: {exc}"
                        )
                        continue

                    accepted_samples.append(sample)
                    temp_signatures.add(sample_signature(sample))

                if not accepted_samples:
                    print(f"[{structure}] attempt {attempt}/{args.max_retries} failed: no valid samples in batch")
                    continue

                for sample in accepted_samples:
                    dataset.append(sample)
                    by_structure[structure].append(sample)
                    previous_summary.append(summarize_sample(sample))
                    existing_signatures.add(sample_signature(sample))
                    print(
                        f"[{structure}] generated {len(by_structure[structure])}/{args.samples_per_structure} -> {sample['id']}"
                    )
                next_id += len(accepted_samples)
                save_dataset(args.output, dataset)
                success = True
                break

            if not success:
                raise RuntimeError(f"Failed to generate a valid sample for structure {structure}")

    save_dataset(args.output, dataset)
    print(f"Saved {len(dataset)} samples to {args.output}")


if __name__ == "__main__":
    main()
