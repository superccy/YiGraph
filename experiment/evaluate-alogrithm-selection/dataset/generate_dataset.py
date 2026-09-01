#!/usr/bin/env python3
"""Generate an algorithm-selection evaluation dataset from the knowledge base."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

try:
    import yaml
except ImportError:  # pragma: no cover - depends on local environment
    yaml = None


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_KB_DIR = SCRIPT_DIR.parents[1] / "aag" / "knowledge_base"
DEFAULT_OUTPUT_PATH = SCRIPT_DIR / "algorithm_selection_dataset.json"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT = 120
DEFAULT_MAX_RETRIES = 2


DOMAIN_ROLE_PAIRS: list[dict[str, str]] = [
    {
        "domain": "Social Network",
        "role_name": "Social Network Analyst",
        "professional_info": (
            "You are skilled in the theories and methodologies of social network analysis, "
            "including graph theory, centrality measures, community detection algorithms, "
            "and network visualization techniques. Your core competencies involve using "
            "software like UCINET, Gephi, or Python libraries (NetworkX, igraph) to analyze "
            "relational data, model information diffusion, identify key influencers, and map "
            "organizational structures. You apply these skills in scenarios such as marketing "
            "campaign optimization, organizational behavior consulting, public health "
            "intervention planning, and countering disinformation networks."
        ),
    },
    {
        "domain": "Social Network",
        "role_name": "Social Media Analyst",
        "professional_info": (
            "You possess expertise in social listening methodologies, digital media analytics, "
            "and public sentiment analysis. Your core competencies include using specialized "
            "monitoring tools (e.g., Brandwatch, Talkwalker) to track, collect, and quantify "
            "online mentions across social platforms, forums, and news sites. You are skilled "
            "in applying natural language processing (NLP) concepts for sentiment "
            "classification, topic modeling, and trend detection. Your role involves analyzing "
            "data to identify emerging narratives, assess brand reputation risks, measure "
            "campaign impact, and provide actionable insights for communications, marketing, "
            "or public relations strategies. You understand the ethical and legal "
            "considerations of data privacy in digital monitoring."
        ),
    },
    {
        "domain": "Transportation",
        "role_name": "Traffic Engineer",
        "professional_info": (
            "You possess expertise in traffic flow theory, including the principles of "
            "macroscopic traffic modeling (e.g., flow-density-speed relationships) and "
            "microscopic simulation of vehicle interactions. Your core competencies include "
            "the design and timing optimization of traffic signal systems, the planning and "
            "analysis of one-way streets and turn restrictions, and the application of "
            "intelligent transportation systems (ITS) such as adaptive signal control and "
            "real-time traffic management. You are skilled in using simulation software "
            "(e.g., VISSIM, Synchro) and analyzing data from loop detectors, cameras, and GPS "
            "probes to evaluate congestion, improve intersection capacity, and develop "
            "mitigation strategies for recurring and non-recurring traffic delays."
        ),
    },
    {
        "domain": "Transportation",
        "role_name": "Logistics Operations Analyst",
        "professional_info": (
            "You possess expertise in transportation network design, vehicle routing problems "
            "(VRP), and geospatial analysis. Your core competencies include using "
            "optimization software (like Llamasoft, Paragon) and data analysis tools (SQL, "
            "Python, R) to model constraints such as time windows, vehicle capacity, driver "
            "hours, and real-time traffic. You apply this knowledge to design cost-effective "
            "and efficient delivery routes, reduce fuel consumption and mileage, improve "
            "on-time performance, and dynamically re-route fleets in response to disruptions "
            "or changing demand patterns."
        ),
    },
    {
        "domain": "Recommendation System",
        "role_name": "Recommendation Systems Architect",
        "professional_info": (
            "You possess deep expertise in the mathematical foundations of recommendation "
            "algorithms, including collaborative filtering, content-based filtering, and "
            "hybrid models. Your core competencies include designing and implementing "
            "scalable, real-time recommendation architectures using distributed systems "
            "(e.g., Apache Spark, Flink), vector databases for embeddings, and microservices. "
            "You are skilled in A/B testing frameworks, offline and online evaluation metrics "
            "(precision, recall, NDCG), and managing the full lifecycle of a recommendation "
            "pipeline, from data ingestion and feature engineering to model training, "
            "deployment, and performance monitoring in production environments such as "
            "e-commerce, streaming media, or social platforms."
        ),
    },
    {
        "domain": "Recommendation System",
        "role_name": "Data Scientist - Marketing Analytics",
        "professional_info": (
            "You possess expertise in statistical modeling, machine learning algorithms, and "
            "customer segmentation techniques specific to marketing. Your core competencies "
            "include designing and implementing recommendation engines (collaborative "
            "filtering, content-based, hybrid models), conducting customer lifetime value "
            "(CLV) analysis, and performing attribution modeling to measure campaign "
            "effectiveness. You are skilled in utilizing large-scale datasets for predictive "
            "analytics, A/B testing design, and personalization strategy development, "
            "typically applied in e-commerce, digital advertising, and customer relationship "
            "management (CRM) platforms to optimize user engagement and conversion rates."
        ),
    },
    {
        "domain": "Medicine",
        "role_name": "Computational Biologist",
        "professional_info": (
            "You possess a strong foundation in molecular biology, biochemistry, and "
            "statistical methods, with specialized expertise in bioinformatics tools and "
            "databases for Protein-Protein Interaction (PPI) analysis. Your core "
            "competencies include utilizing and interpreting data from experimental "
            "techniques like yeast two-hybrid (Y2H) and affinity purification-mass "
            "spectrometry (AP-MS), as well as applying computational methods for PPI network "
            "prediction, visualization, and topological analysis. You are skilled in using "
            "software such as Cytoscape for network modeling, scripting in Python or R for "
            "data processing, and leveraging public repositories like STRING and BioGRID. "
            "Your work typically involves integrating PPI networks with genomic or "
            "transcriptomic data to identify key protein complexes and pathways implicated in "
            "diseases, thereby supporting target discovery and mechanistic research in "
            "pharmaceutical and academic settings."
        ),
    },
    {
        "domain": "Medicine",
        "role_name": "Epidemiologist (Modeling Specialist)",
        "professional_info": (
            "You possess expertise in mathematical and statistical modeling of disease "
            "transmission dynamics, including compartmental models (e.g., SIR, SEIR), "
            "agent-based simulations, and network models. Core competencies include "
            "proficiency in programming languages (such as R or Python) for data analysis and "
            "model development, statistical inference for parameter estimation, and the "
            "ability to integrate heterogeneous data sources (e.g., clinical, genomic, "
            "mobility). You apply these skills to forecast outbreak trajectories, evaluate "
            "the potential impact of public health interventions (like vaccination campaigns "
            "or social distancing), and inform real-time policy decisions for infectious "
            "disease control."
        ),
    },
    {
        "domain": "Finance",
        "role_name": "Anti-Money Laundering (AML) Analyst",
        "professional_info": (
            "You possess in-depth knowledge of global AML/CFT (Combating the Financing of "
            "Terrorism) regulations, including the Bank Secrecy Act (BSA), USA PATRIOT Act, "
            "FATF (Financial Action Task Force) recommendations, and relevant EU directives. "
            "Your core competencies include conducting customer due diligence (CDD) and "
            "enhanced due diligence (EDD), transaction monitoring and analysis to identify "
            "suspicious patterns (e.g., structuring, layering), and filing Suspicious "
            "Activity Reports (SARs). You are skilled in using AML-specific software for "
            "screening, monitoring, and case management, and you apply this expertise in "
            "scenarios such as investigating complex financial networks, assessing high-risk "
            "customer relationships, and ensuring regulatory compliance for financial "
            "institutions like banks, fintech companies, and investment firms."
        ),
    },
    {
        "domain": "Finance",
        "role_name": "Credit Risk Analyst",
        "professional_info": (
            "You are proficient in statistical and machine learning models used for credit "
            "risk assessment, including logistic regression, decision trees, and scorecard "
            "development. Your core competencies involve data analysis using SQL and Python/R, "
            "feature engineering from financial and behavioral data, and model validation "
            "techniques to ensure predictive accuracy and regulatory compliance (e.g., with "
            "Basel accords or fair lending laws). You apply these skills to develop, monitor, "
            "and refine credit scoring systems for applications such as consumer lending, "
            "credit card underwriting, and small business loan approvals within banks, "
            "fintech companies, and credit bureaus."
        ),
    },
]


@dataclass(frozen=True)
class AlgorithmRecord:
    name: str
    task_type: str
    task_type_id: str
    application_scenario: str
    principles: str
    solvable_questions: list[str]
    raw: dict[str, Any]


class DatasetGenerationError(Exception):
    """Raised when dataset generation cannot proceed."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--knowledge-base-dir",
        type=Path,
        default=DEFAULT_KB_DIR,
        help="Directory containing task_types.yaml and algorithms.yaml.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to the output JSON dataset.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL),
        help="OpenAI-compatible API base URL. Defaults to OPENAI_BASE_URL or the official API URL.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL"),
        help="Model name. Defaults to OPENAI_MODEL.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OPENAI_API_KEY"),
        help="API key. Defaults to OPENAI_API_KEY.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="HTTP timeout in seconds for each model call.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Maximum retries for a pair when the model response is invalid or duplicated.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    return parser.parse_args()


def configure_logging(level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(levelname)s: %(message)s",
    )


def require_yaml() -> None:
    if yaml is None:
        raise DatasetGenerationError(
            "PyYAML is required to parse the knowledge base. Install it with: pip install pyyaml"
        )


def load_yaml_file(path: Path) -> Any:
    require_yaml()
    if not path.is_file():
        raise DatasetGenerationError(f"YAML file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except Exception as exc:  # pragma: no cover - depends on file content
        raise DatasetGenerationError(f"Failed to parse YAML file {path}: {exc}") from exc


def normalize_to_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def stringify_field(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        parts: list[str] = []
        for key, sub_value in value.items():
            text = stringify_field(sub_value)
            if text:
                parts.append(f"{key}: {text}")
        return " | ".join(parts)
    if isinstance(value, list):
        return " | ".join(item for item in (stringify_field(item) for item in value) if item)
    return str(value).strip()


def load_task_type_lookup(task_types_path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    data = load_yaml_file(task_types_path)
    if not isinstance(data, list):
        raise DatasetGenerationError(f"Expected a list in {task_types_path}, got {type(data).__name__}")

    task_lookup: dict[str, dict[str, Any]] = {}
    algorithm_to_task: dict[str, str] = {}
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise DatasetGenerationError(
                f"Task type entry #{index} in {task_types_path} is not a mapping."
            )
        task_id = stringify_field(item.get("id"))
        task_name = stringify_field(item.get("task_type")) or task_id
        if not task_id:
            raise DatasetGenerationError(f"Task type entry #{index} in {task_types_path} is missing 'id'.")
        task_lookup[task_id] = {
            "id": task_id,
            "task_type": task_name,
            "description": stringify_field(item.get("description")),
            "algorithms": [str(name).strip() for name in normalize_to_list(item.get("algorithm")) if str(name).strip()],
        }
        for algorithm_name in task_lookup[task_id]["algorithms"]:
            algorithm_to_task[algorithm_name] = task_id
    return task_lookup, algorithm_to_task


def build_algorithm_records(
    algorithms_path: Path,
    task_lookup: dict[str, dict[str, Any]],
    algorithm_to_task: dict[str, str],
) -> list[AlgorithmRecord]:
    data = load_yaml_file(algorithms_path)
    if not isinstance(data, list):
        raise DatasetGenerationError(f"Expected a list in {algorithms_path}, got {type(data).__name__}")

    records: list[AlgorithmRecord] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            logging.warning("Skipping non-mapping algorithm entry #%s", index)
            continue

        name = stringify_field(item.get("id"))
        if not name:
            logging.warning("Skipping algorithm entry #%s because 'id' is missing.", index)
            continue

        task_type_id = stringify_field(item.get("task_type_id")) or algorithm_to_task.get(name, "")
        if not task_type_id:
            logging.warning("Skipping algorithm '%s' because no task type could be resolved.", name)
            continue

        if name in algorithm_to_task and algorithm_to_task[name] != task_type_id:
            logging.warning(
                "Algorithm '%s' maps to task '%s' in algorithms.yaml but '%s' in task_types.yaml; using '%s'.",
                name,
                task_type_id,
                algorithm_to_task[name],
                task_type_id,
            )

        task_info = task_lookup.get(task_type_id)
        if not task_info:
            logging.warning(
                "Skipping algorithm '%s' because task type '%s' is not defined in task_types.yaml.",
                name,
                task_type_id,
            )
            continue

        solvable_questions = [
            question.strip()
            for question in normalize_to_list(item.get("solvable_questions"))
            if isinstance(question, str) and question.strip()
        ]

        records.append(
            AlgorithmRecord(
                name=name,
                task_type=task_info["task_type"],
                task_type_id=task_type_id,
                application_scenario=stringify_field(item.get("Application_scenario")),
                principles=stringify_field(item.get("Principles")),
                solvable_questions=solvable_questions,
                raw=item,
            )
        )

    return records


def normalize_question(text: str) -> str:
    lowered = text.lower().strip()
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"[^\w\s]", "", lowered)
    return lowered


def extract_json_object(text: str) -> dict[str, Any]:
    payload = text.strip()
    if not payload:
        raise ValueError("Empty model response.")

    if payload.startswith("```"):
        payload = re.sub(r"^```(?:json)?\s*", "", payload)
        payload = re.sub(r"\s*```$", "", payload)

    try:
        result = json.loads(payload)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", payload, flags=re.DOTALL)
        if not match:
            raise
        result = json.loads(match.group(0))

    if not isinstance(result, dict):
        raise ValueError("Model response JSON is not an object.")
    return result


class OpenAICompatibleClient:
    def __init__(self, api_key: str, base_url: str, model: str, timeout: int) -> None:
        if not api_key:
            raise DatasetGenerationError("Missing API key. Set OPENAI_API_KEY or pass --api-key.")
        if not model:
            raise DatasetGenerationError("Missing model name. Set OPENAI_MODEL or pass --model.")

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def create_json_decision(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise DatasetGenerationError(
                f"OpenAI-compatible API request failed with status {exc.code}: {details}"
            ) from exc
        except error.URLError as exc:
            raise DatasetGenerationError(f"Failed to reach the OpenAI-compatible API: {exc}") from exc

        try:
            parsed = json.loads(raw)
            content = parsed["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise DatasetGenerationError(f"Unexpected API response format: {raw}") from exc

        try:
            return extract_json_object(content)
        except Exception as exc:
            raise DatasetGenerationError(f"Failed to parse JSON from model output: {content}") from exc


def build_system_prompt() -> str:
    return (
        "You are generating a benchmark dataset for algorithm selection.\n"
        "For each algorithm-role pair, decide applicability conservatively.\n"
        "Return exactly one JSON object with keys: applicable, question, reason.\n"
        "Rules:\n"
        "1. applicable must be true only if the algorithm clearly fits the role's domain-specific work.\n"
        "2. If applicable is false, question must be an empty string.\n"
        "3. If applicable is true, question must be a single natural English question that the role would realistically ask.\n"
        "4. The question must be answerable by the algorithm and aligned with the algorithm metadata and examples.\n"
        "5. Do not mention the algorithm name in the question.\n"
        "6. Prefer domain-specific wording over generic graph-analysis wording.\n"
        "7. Be strict. If the fit is ambiguous, return applicable=false."
    )


def build_user_prompt(
    algorithm: AlgorithmRecord,
    role_pair: dict[str, str],
    task_info: dict[str, Any],
    existing_questions: set[str],
    retry_hint: str = "",
) -> str:
    existing = sorted(existing_questions)
    existing_text = "\n".join(f"- {question}" for question in existing[:50]) or "- None yet"

    algorithm_payload = {
        "algorithm": algorithm.name,
        "task_type": algorithm.task_type,
        "task_type_id": algorithm.task_type_id,
        "task_type_description": task_info.get("description", ""),
        "application_scenario": algorithm.application_scenario,
        "principles": algorithm.principles,
        "solvable_questions": algorithm.solvable_questions,
    }
    role_payload = {
        "domain": role_pair["domain"],
        "role_name": role_pair["role_name"],
        "professional_info": role_pair["professional_info"],
    }

    prompt = (
        "Determine whether this algorithm is applicable to the role-domain pair.\n\n"
        f"Algorithm metadata:\n{json.dumps(algorithm_payload, ensure_ascii=False, indent=2)}\n\n"
        f"Role metadata:\n{json.dumps(role_payload, ensure_ascii=False, indent=2)}\n\n"
        "Questions already used in this dataset generation run:\n"
        f"{existing_text}\n\n"
        "Output JSON schema:\n"
        '{\n'
        '  "applicable": true,\n'
        '  "question": "natural English question",\n'
        '  "reason": "brief justification"\n'
        '}\n\n'
        "Decision guidance:\n"
        "- Use the algorithm metadata, task type, solvable_questions, domain, role_name, and professional_info.\n"
        "- Only mark applicable=true if the role would genuinely use this algorithm in domain-specific work.\n"
        "- Skip generic graph methods when the role fit is weak or unclear.\n"
        "- If applicable=true, produce exactly one realistic user-style question.\n"
        "- Keep the question distinct from previous ones when possible.\n"
    )
    if retry_hint:
        prompt += f"\nRetry instruction:\n{retry_hint}\n"
    return prompt


def validate_model_decision(decision: dict[str, Any]) -> tuple[bool, str, str]:
    applicable = decision.get("applicable")
    question = decision.get("question", "")
    reason = decision.get("reason", "")

    if not isinstance(applicable, bool):
        raise ValueError("Field 'applicable' must be a boolean.")
    if not isinstance(question, str):
        raise ValueError("Field 'question' must be a string.")
    if not isinstance(reason, str):
        raise ValueError("Field 'reason' must be a string.")

    question = question.strip()
    reason = reason.strip()
    if applicable and not question:
        raise ValueError("Applicable=true requires a non-empty question.")
    if not applicable:
        question = ""

    return applicable, question, reason


def generate_question_for_pair(
    client: OpenAICompatibleClient,
    algorithm: AlgorithmRecord,
    role_pair: dict[str, str],
    task_info: dict[str, Any],
    seen_questions: set[str],
    max_retries: int,
) -> tuple[bool, str, str]:
    system_prompt = build_system_prompt()
    retry_hint = ""

    for attempt in range(1, max_retries + 2):
        prompt = build_user_prompt(
            algorithm=algorithm,
            role_pair=role_pair,
            task_info=task_info,
            existing_questions=seen_questions,
            retry_hint=retry_hint,
        )
        decision = client.create_json_decision(system_prompt=system_prompt, user_prompt=prompt)
        applicable, question, reason = validate_model_decision(decision)

        if not applicable:
            return False, "", reason

        normalized = normalize_question(question)
        if normalized in seen_questions:
            retry_hint = (
                f'The previous question "{question}" duplicates an existing sample. '
                "Write a different question for this algorithm-role pair, or return applicable=false if no distinct and "
                "natural question is justified."
            )
            logging.debug(
                "Duplicate question for algorithm '%s' and role '%s' on attempt %s: %s",
                algorithm.name,
                role_pair["role_name"],
                attempt,
                question,
            )
            if attempt <= max_retries:
                continue
            return False, "", "Skipped because repeated outputs were duplicates."

        return True, question, reason

    return False, "", "No valid result returned."


def build_dataset(
    algorithms: list[AlgorithmRecord],
    task_lookup: dict[str, dict[str, Any]],
    client: OpenAICompatibleClient,
    max_retries: int,
) -> list[dict[str, Any]]:
    dataset: list[dict[str, Any]] = []
    seen_questions: set[str] = set()

    total_pairs = len(algorithms) * len(DOMAIN_ROLE_PAIRS)
    processed_pairs = 0

    for algorithm in algorithms:
        task_info = task_lookup[algorithm.task_type_id]
        for role_pair in DOMAIN_ROLE_PAIRS:
            processed_pairs += 1
            logging.info(
                "Processing pair %s/%s: algorithm='%s', role='%s'",
                processed_pairs,
                total_pairs,
                algorithm.name,
                role_pair["role_name"],
            )
            try:
                applicable, question, reason = generate_question_for_pair(
                    client=client,
                    algorithm=algorithm,
                    role_pair=role_pair,
                    task_info=task_info,
                    seen_questions=seen_questions,
                    max_retries=max_retries,
                )
            except Exception as exc:
                logging.warning(
                    "Failed pair algorithm='%s', role='%s': %s",
                    algorithm.name,
                    role_pair["role_name"],
                    exc,
                )
                continue

            if not applicable:
                logging.debug(
                    "Skipped algorithm='%s', role='%s': %s",
                    algorithm.name,
                    role_pair["role_name"],
                    reason or "not applicable",
                )
                continue

            normalized = normalize_question(question)
            seen_questions.add(normalized)
            dataset.append(
                {
                    "id": len(dataset) + 1,
                    "algorithm": algorithm.name,
                    "task_type": algorithm.task_type,
                    "question": question,
                    "domain": role_pair["domain"],
                    "role": role_pair["role_name"],
                }
            )
            logging.info(
                "Added sample %s for algorithm='%s', role='%s'",
                len(dataset),
                algorithm.name,
                role_pair["role_name"],
            )
            time.sleep(0.1)

    return dataset


def save_dataset(dataset: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(dataset, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main() -> int:
    args = parse_args()
    configure_logging(args.log_level)

    kb_dir = args.knowledge_base_dir.resolve()
    task_types_path = kb_dir / "task_types.yaml"
    algorithms_path = kb_dir / "algorithms.yaml"

    task_lookup, algorithm_to_task = load_task_type_lookup(task_types_path)
    algorithms = build_algorithm_records(
        algorithms_path=algorithms_path,
        task_lookup=task_lookup,
        algorithm_to_task=algorithm_to_task,
    )
    if not algorithms:
        raise DatasetGenerationError("No algorithms could be loaded from the knowledge base.")

    client = OpenAICompatibleClient(
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        timeout=args.timeout,
    )

    dataset = build_dataset(
        algorithms=algorithms,
        task_lookup=task_lookup,
        client=client,
        max_retries=max(0, args.max_retries),
    )
    save_dataset(dataset, args.output.resolve())

    logging.info("Loaded %s algorithms.", len(algorithms))
    logging.info("Saved %s samples to %s", len(dataset), args.output.resolve())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DatasetGenerationError as exc:
        logging.error("%s", exc)
        raise SystemExit(1)
