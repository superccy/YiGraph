# YiGraph

<div align="center">

<table border="0" cellspacing="0" cellpadding="0">
  <tr>
    <td align="center" valign="middle" style="padding-right: 30px;">
      <img src="figure/logo.png" alt="YiGraph Logo" width="180" />
    </td>
    <td align="left" valign="middle">
      <h2 style="margin: 0; font-size: 24px; font-weight: 600; color: #2c3e50;">YiGraph: Enabling Autonomous Graph Data Analysis with<br/>Algorithm-centric Agentic Workflow Construction</h2>
    </td>
  </tr>
</table>

<p style="margin-top: 20px;">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python"></a>
  <a href="http://iDC-NEU.github.io/YiGraphDocs/"><img src="https://img.shields.io/badge/📚-Docs-purple.svg" alt="Docs"></a>
  <a href="#-contact-us"><img src="https://img.shields.io/badge/📞-Contact_Us-green.svg" alt="Contact"></a>
</p>

English

</div>

---

## 📖 Project Introduction

**YiGraph is an end-to-end intelligent graph data analysis agent system** designed to help users quickly gain insights into key relationships from complex data.

YiGraph can automatically extract entities and relationships from various raw data sources such as logs, documents, and tables to build structured graph data. Users only need to describe business problems in **natural language**, and the system will automatically plan the analysis process, complete calculations, and generate **clear, interpretable, and traceable analysis reports**.

Internally, **large language models** are responsible for understanding user intent, breaking down analysis tasks, and organizing final outputs. The core technology supporting the reliability of analysis results is the **AAG (Analytics-Augmented Generation) framework**. AAG treats analytical computation as a core capability, invoking graph algorithms and graph systems at key stages to complete verifiable calculations, which are then interpreted and summarized by the model.

Therefore, YiGraph is not just a conversational AI that "answers questions", but an intelligent graph analysis agent that can transform business problems into **executable and reviewable analysis processes**.

### Applicable Scenarios

YiGraph can flexibly adapt to different industries and business needs, covering various complex relational data analysis scenarios, including but not limited to:

- **Financial anti-money laundering and suspicious transaction analysis**: Automatically build transaction networks from massive transaction flows to identify abnormal fund paths and suspicious transaction loops
- **E-commerce risk control and wool party identification**: Integrate multi-source data such as accounts, devices, and addresses to build graphs and discover organized fraud and associated malicious behavior
- **Enterprise association and risk investigation**: Build graphs through enterprise, equity, and transaction relationships to penetrate complex structures and identify potential compliance and operational risks
- **Park/city event analysis**: Unify access control, trajectory, and event data into graphs to restore personnel relationships and event evolution processes
- **Supply chain risk analysis**: Integrate enterprise and transaction data to build supply chain networks, locate hidden associated risks and transmission paths

---

## ⚡ Core Features

### 1. Knowledge-Driven Task Planning

The system first understands what the user's question "wants to solve", then breaks it down into executable analysis steps:
- What data fields and relationships are needed
- What kind of graph should be built (which entities, which relationships)
- What analysis methods and parameters should be used
- How analysis results should be interpreted and presented

> You don't need to understand graph algorithms; the system will translate "what I want to query" into "how to do the analysis".

### 2. Algorithm-Centric Reliable Execution

YiGraph will not let the model arbitrarily "write a piece of uncontrollable code and run it". Instead, it centers on "verifiable algorithm modules" for invocation and combination, making each analysis step:
- **Reproducible**: Same input yields stable and consistent output
- **Traceable**: Know which algorithms were used and which steps were executed
- **More reliable**: Key calculations are completed by professional modules rather than pure text reasoning

### 3. Task-Aware Graph Construction

YiGraph will not indiscriminately build all raw data into one large graph. It will selectively extract and construct "entities and relationships relevant to the problem" based on current task needs, avoiding interference from irrelevant structures, and organize the graph into a form more suitable for execution, thereby improving efficiency and result quality.

### 4. Flexible Data Support

Supports multiple data source inputs:
- **Graph Data**
- **Text Data**: Documents, logs, reports, and other unstructured data

The system will automatically extract entities and relationships from raw data to build structured graph data.

### 5. Multiple Operating Modes

- **Normal Mode**: Users only need to submit their business questions. YiGraph will automatically parse the problem, select appropriate graph algorithms, execute the computation, and generate an analysis report. This mode is suitable for non-technical or general business users.
- **Interactive Mode**: Users collaborate with YiGraph to analyze business problems. For a given question, YiGraph interacts with the LLM to determine the computation workflow and graph algorithms, then executes the plan and returns an analysis report. This mode is suitable for advanced users who are familiar with both the business and graph algorithms.
- **Expert Mode**: Users directly specify the business problem along with the solution approach, computation steps, and graph algorithms. YiGraph then executes the provided plan and returns an analysis report. This mode is intended for expert users with deep knowledge of the business and graph algorithms.

## 🚀 Quick Start

### 1. Environment Preparation

#### 1.1 Python Version Requirements

- Python >= **3.11**

Please confirm that the current Python version meets the requirements:

```bash
python --version
# or
python3 --version
```

#### 1.2 Create Virtual Environment with Conda (Recommended)

```bash
conda create -n AAG python=3.11
conda activate AAG
```

#### 1.3 Neo4j Installation and Configuration

YiGraph requires Neo4j as the graph database. This guide uses **Neo4j 3.5.25**.

##### 1.3.1 Java Version Requirements

Neo4j 3.5.25 requires Java 8 or Java 11. Please check your Java version:

```bash
java -version
```

If Java is not installed, please install the appropriate version first.

##### 1.3.2 Download and Extract Neo4j

1. Download the Neo4j 3.5.25 installation package from the official website (usually in `.tar.gz` or `.zip` format)
2. Extract the package to your desired location:

**Linux/Mac systems (.tar.gz format):**
```bash
tar -xzf neo4j-community-3.5.25-unix.tar.gz
cd neo4j-community-3.5.25
```

**Windows systems (.zip format):**
- Right-click the archive and select "Extract to current folder"
- Or use command: `unzip neo4j-community-3.5.25-windows.zip`
- Navigate to the extracted directory

##### 1.3.3 Configure Neo4j

Enter the `conf` directory and edit the `neo4j.conf` file:

```bash
cd conf
```

Add or modify the following settings in `neo4j.conf`:

```properties
dbms.connectors.default_listen_address=0.0.0.0
dbms.connectors.default_advertised_address=localhost
dbms.connector.bolt.listen_address=0.0.0.0:7687
dbms.connector.http.listen_address=0.0.0.0:7474
dbms.connector.https.enabled=true
```

##### 1.3.4 Start and Stop Neo4j

Navigate to the `bin` directory to start or stop Neo4j:

**Start Neo4j:**
```bash
cd bin
./neo4j start
```

**Stop Neo4j:**
```bash
./neo4j stop
```

After starting Neo4j, you can access the web interface at `http://localhost:7474` to verify the installation.

### 2. Get Source Code and Install Dependencies

#### 2.1 Download Source Code

```bash
git clone https://github.com/iDC-NEU/YiGraph.git
cd YiGraph
```

#### 2.2 Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure System Parameters

#### 3.1 Configure Inference and Retrieval Engine

Edit the configuration file:

```text
config/engine_config.yaml
```

Example configuration:

```yaml
# Running mode: interactive / batch
mode: interactive

# Reasoner module configuration
reasoner:
  llm:
    provider: "openai"   # Options: ollama / openai
    openai:
      base_url: "https://your-api-endpoint/v1/"
      api_key: "your-api-key"
      model: "gpt-4o-mini"

# Retrieval module configuration
retrieval:
  database:
    graph:
      space_name: "AMLSim1K"
      server_ip: "127.0.0.1"
      server_port: "9669"
    vector:
      collection_name: "graphllm_collection"
      host: "localhost"
      port: 19530
  embedding:
    model_name: "BAAI/bge-large-en-v1.5"
    device: "cuda:2"
  rag:
    graph:
      k_hop: 2
    vector:
      k_similarity: 5
```

#### 3.2 Configure Dataset

Edit the configuration file:

```text
config/data_upload_config.yaml
```

Example configuration:

```yaml
datasets:
  - name: AMLSim1K
    type: graph
    schema:
      vertex:
        - type: account
          path: "/path/to/accounts.csv"
          format: csv
          id_field: acct_id
      edge:
        - type: transfer
          path: "/path/to/transactions.csv"
          format: csv
          source_field: orig_acct
          target_field: bene_acct
```

> Please modify `path` to your local actual data file path.

### 4. Experiment

#### Experiment Scripts

- `evaluate-alogrithm-selection/`: algorithm selection experiments. The directory name keeps the repository's current spelling.
- `evaluate-dependency-resolve/`: dependency resolution experiments.

Run commands from the project root:

```bash
cd <repo-root>
```

If the active Python environment cannot import `aag`, activate the project environment first:

```bash
conda activate <project-env>
python <script> [args]
```

Most evaluation scripts read `config/engine_config.yaml`. For LLM calls, make sure `reasoner.llm.provider`, `base_url`, `api_key`, and `model` are valid.

#### Scripts

| Script | Purpose | Default input | Default output |
| --- | --- | --- | --- |
| `evaluate-alogrithm-selection/dataset/generate_dataset.py` | Generate algorithm-selection samples from the knowledge base | `aag/knowledge_base/` | `evaluate-alogrithm-selection/dataset/algorithm_selection_dataset.json` |
| `evaluate-alogrithm-selection/baseline/evaluate.py` | Direct algorithm selection without task-type routing | `evaluate-alogrithm-selection/dataset/dataset1.json` | `evaluate-alogrithm-selection/baseline/deepseek-reasoner.json` |
| `evaluate-alogrithm-selection/hierarchical/evaluate_algorithm_selection.py` | Select task type first, then algorithm | `evaluate-alogrithm-selection/dataset/dataset1.json` | `evaluate-alogrithm-selection/hierarchical/evaluation2.json` |
| `evaluate-dependency-resolve/generate_dependency_resolution_dataset_llm.py` | Generate dependency-resolution samples | `aag/knowledge_base/algorithms.yaml` | `evaluate-dependency-resolve/dependency_resolution_dataset_100_llm.json` |
| `evaluate-dependency-resolve/evaluate_dependency_resolution.py` | Evaluate `DataDependencyResolver` dependency detection | `evaluate-dependency-resolve/dependency_resolution_dataset_100_llm.json` | `evaluate-dependency-resolve/report.json` |

#### Common Commands

Generate the algorithm-selection dataset:

```bash
python experiment/evaluate-alogrithm-selection/dataset/generate_dataset.py \
  --model gpt-4o-mini \
  --api-key "$OPENAI_API_KEY" \
  --base-url https://api.openai.com/v1 \
  --output experiment/evaluate-alogrithm-selection/dataset/dataset1.json
```

Run the direct algorithm-selection baseline:

```bash
python experiment/evaluate-alogrithm-selection/baseline/evaluate.py --limit 10
```

Run the hierarchical algorithm-selection evaluation:

```bash
python experiment/evaluate-alogrithm-selection/hierarchical/evaluate_algorithm_selection.py --limit 10
```

Generate dependency-resolution samples:

```bash
python experiment/evaluate-dependency-resolve/generate_dependency_resolution_dataset_llm.py \
  --api-key "$OPENAI_API_KEY" \
  --base-url https://api.openai.com/v1/ \
  --model gpt-4o-mini \
  --samples-per-structure 20 \
  --batch-size 5
```

Evaluate dependency resolution:

```bash
python experiment/evaluate-dependency-resolve/evaluate_dependency_resolution.py \
  --max-samples 10 \
  --verbose-errors
```

#### Key Parameters

##### Algorithm-Selection Dataset Generation

`generate_dataset.py`

| Parameter | Description |
| --- | --- |
| `--knowledge-base-dir` | Directory containing `task_types.yaml` and `algorithms.yaml`. |
| `--output` | Output JSON dataset path. |
| `--base-url` | OpenAI-compatible API base URL. Defaults to `OPENAI_BASE_URL` or `https://api.openai.com/v1`. |
| `--model` | Model name. Defaults to `OPENAI_MODEL`. |
| `--api-key` | API key. Defaults to `OPENAI_API_KEY`. |
| `--timeout` | Per-request timeout in seconds. |
| `--max-retries` | Retries for invalid or duplicated model responses. |
| `--log-level` | Logging verbosity. |

##### Algorithm-Selection Evaluations

`baseline/evaluate.py` and `hierarchical/evaluate_algorithm_selection.py`

| Parameter | Description |
| --- | --- |
| `--config` | Path to `engine_config.yaml`. |
| `--dataset` | Algorithm-selection dataset path. |
| `--output` | Detailed result JSON path. |
| `--limit` | Evaluate only the first N samples. Use `--limit 1` for smoke tests. |
| `--filter-correct` | Use `all`, `incorrect`, or `correct` when the dataset has a `correct` field. |
| `--log-level` | Logging verbosity. |
| `--fail-fast` | Stop on the first failed sample. |

Baseline reports `algorithm_accuracy`. Hierarchical reports both `task_type_accuracy` and `algorithm_accuracy`.

##### Dependency Dataset Generation

`generate_dependency_resolution_dataset_llm.py`

| Parameter | Description |
| --- | --- |
| `--algorithms-yaml` | Algorithm knowledge-base YAML path. |
| `--output` | Output dataset path. |
| `--model` | Model used for generation. |
| `--base-url` | OpenAI-compatible API base URL. |
| `--api-key` | API key. Prefer passing this explicitly instead of relying on the script default. |
| `--samples-per-structure` | Number of samples to generate for each dependency structure. |
| `--candidate-size` | Number of candidate algorithms included in each prompt. |
| `--batch-size` | Target number of samples per model call. |
| `--max-retries` | Maximum retries per structure. |
| `--seed` | Random seed. |
| `--temperature` | Model temperature. |
| `--resume` | Continue from an existing output file. |

##### Dependency-Resolution Evaluation

`evaluate_dependency_resolution.py`

| Parameter | Description |
| --- | --- |
| `--dataset` | Dependency-resolution dataset path. |
| `--config` | Path to `engine_config.yaml`. |
| `--output` | Evaluation report JSON path. |
| `--max-samples` | Evaluate only the first N samples. |
| `--sample-ids` | Evaluate only selected sample IDs, for example `dep_001 dep_002`. |
| `--verbose-errors` | Print gold/predicted mismatches. |

---

### Acknowledgments

This project benefits from the following open source projects:

- [NetworkX](https://networkx.org/) - Graph analysis and algorithm library
- [PyTorch Geometric](https://pytorch-geometric.readthedocs.io/) - Graph deep learning framework
- [NebulaGraph](https://www.nebula-graph.io/) - Distributed graph database
- [Milvus](https://milvus.io/) - Vector database
- [LlamaIndex](https://www.llamaindex.ai/) - RAG framework

Thanks to all contributors for their hard work!

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

<div align="center">

**Making Graph Data Analysis Simpler and Smarter**

</div>

---


