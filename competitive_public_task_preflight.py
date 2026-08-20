#!/usr/bin/env python3
"""Zero-call public-task preflight for a three-arm agent dialogue study.

The program downloads only two allowlisted files from one immutable AutoForm
revision, verifies every frozen input, builds reproducible two-agent evidence
allocations, renders complete initial prompts, counts four pinned tokenizers,
and estimates the requested cheapest smoke stage.  It never imports a model or
provider SDK and it does not score answers.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from importlib import metadata
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.request import Request, urlopen


FORMAT = "competitive-public-task-preflight-v1"
SOURCE_COMMIT = "8df94501c462e7f7b4708e5f0297fbdcf8e12ffa"
SOURCE_TREE_URL = f"https://github.com/thunlp/AutoForm/tree/{SOURCE_COMMIT}"
SOURCE_LICENSE_URL = (
    f"https://github.com/thunlp/AutoForm/blob/{SOURCE_COMMIT}/LICENSE"
)
DATA_SEEDS = (20240826, 20250424, 20260820)
ARMS = ("cte", "json", "adaptive")
AGENTS = ("A", "B")
CACHE_SUBDIR = Path("work/competitive_public_task_preflight")

TIKTOKEN_VERSION = "0.11.0"
TOKENIZERS_VERSION = "0.21.4"
EXPECTED_TOKENIZER_FINGERPRINTS = {
    "cl100k_base": "71ced6cb6d5ceaae87e197590efe6fdd17dd24d4de21d70d2fdb55c521be664d",
    "o200k_base": "09311460aa0d9f00d1bc48745675297643886c99663fca8d60cb8b021bd3ecdc",
    "qwen2_5_7b_instruct": "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
    "mistral_7b_instruct_v03": "e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49",
}

CURRENT_IMPLEMENTATION = "urusilla_generalization_surface_v06.py"
EXPECTED_CURRENT_IMPLEMENTATION_SHA256 = (
    "85ab4676698acb2a887e31c297ed938d09c898a39d645b710a71149064fce753"
)
EXPECTED_CURRENT_PROFILE_SHA256 = (
    "f6368ee3e9ae9dd3b9a7335b5e3a0b3999e376c5a4e800f5ea8733e8f722a50d"
)
EXPECTED_CURRENT_SNAPSHOT_SHA256 = (
    "81993226c8fe9b2bd631a2e63e59355fa8e31e993ecbe14af1848a9c5a44bb57"
)

CTE_CONTRACT = (
    "Send only task-relevant facts. Preserve source ownership. Use these lines in "
    "this order: ACT: ask|propose|agree|reject; CLAIM: <short claim or ?>; "
    "EVIDENCE: <[A|B] atomic facts or NONE>; NEED: <missing fact or NONE>; "
    "ANSWER: <exact answer or ?>. No greeting, repetition, unsupported claim, or "
    "private reasoning."
)
JSON_CONTRACT = (
    "Return exactly one JSON object with keys in this order and no whitespace: "
    "{\"a\":\"<exact answer or ?>\",\"c\":[\"<short claim>\"],\"e\":[{\"f\":"
    "\"<atomic fact>\",\"s\":\"A|B\"}],\"n\":[\"<missing fact>\"],\"x\":"
    "\"ask|propose|agree|reject\"}. Use empty arrays when absent. Do not add keys "
    "or prose."
)
ADAPTIVE_CONTRACT = (
    "Return exactly one minified bridge record with keys in this order and no "
    "whitespace: {\"a\":\"<exact answer or ?>\",\"c\":[\"<short claim>\"],\"e\":["
    "{\"f\":\"<atomic fact>\",\"s\":\"A|B\"}],\"n\":[\"<missing fact>\"],"
    "\"x\":\"ask|propose|agree|reject\"}. The verified bridge maps this record to "
    "the negotiated receiver-specific adaptive surface. It rejects unknown fields, "
    "invalid types, integrity errors, and unknown profile state. Use empty arrays "
    "when absent. Do not add prose or private reasoning. Frozen profile SHA-256: "
    + EXPECTED_CURRENT_PROFILE_SHA256
    + "."
)
ARM_CONTRACTS = {
    "cte": CTE_CONTRACT,
    "json": JSON_CONTRACT,
    "adaptive": ADAPTIVE_CONTRACT,
}

# Frozen after the first verified local observation.  The release path rejects
# any changed value.
EXPECTED_SPLIT_DIGESTS: Mapping[str, Mapping[str, str]] = {
    "hotpotqa": {
        "20240826|alternating": "b554fd496a4dc4b448a15c895dd3ef4b819d3448090a015a426f7da1a89cd748",
        "20240826|forced": "6fd431148a726a83d2d57cdcddf3cf453f5919313c2eab4c56b62bf0de02c4a7",
        "20250424|alternating": "359e4c9d619321faa69a05dbf5ce086297e47e8718e4a6cf62c83bb877ff0f9d",
        "20250424|forced": "a70a127972a7de8898b371e01aaa71c08bc37926d053fcdf3e4d8ae387399145",
        "20260820|alternating": "ca86017e89707a1c6ceb0e966adddd7ea7774314d8360d8bb7adc704f2d8ea8e",
        "20260820|forced": "2872701267fd42e39ffea51fb40e9638b031ea97c1567f544a3649dd4f1bf063",
    },
    "wikihop": {
        "20240826|alternating": "9a5dcd2bea740b16839651fa88e241f8a960760b5a83e49f62942fb13ea25208",
        "20250424|alternating": "1e28152547d6b99370e407b6b1176bafc78d484ddbd0bf9c05c01205b1d76b0d",
        "20260820|alternating": "d15788b0f7c51c6bc6dc19db049eb3957e711f61028495287a84879001d66b57",
    },
}
EXPECTED_PROMPT_GROUP_DIGESTS: Mapping[str, str] = {
    "hotpotqa|20240826|alternating|adaptive": "fd63da34363f3b3707a2bdfcd4ee2330aff8058243da70b932985f5ed4b20336",
    "hotpotqa|20240826|alternating|cte": "c9c2699deda0f3f050ed37ed2b0950bba6ceb951a5c273aa835aea5335e3ce14",
    "hotpotqa|20240826|alternating|json": "73e3770d56f160bdae34349cc6f81d95c2938b282e8ada068c22e5ee183300ab",
    "hotpotqa|20240826|forced|adaptive": "4935659f8799fb8db307c0999aa128a5b0c9a7cb0eac6192d7f295bba85d7d4e",
    "hotpotqa|20240826|forced|cte": "6c31ede82c9758cb28e411e459009af6bca10885e1613f4ebdebe6b78f45d20e",
    "hotpotqa|20240826|forced|json": "ad32cae386cbc872061553c930fef38114821d69112e46ed7a1273c564540f05",
    "hotpotqa|20250424|alternating|adaptive": "4a28f70fc149649eadd6e863687a84bf47e3084a779cfaacb47580d3b0b482a6",
    "hotpotqa|20250424|alternating|cte": "21b31fa0f0771a3a938aedcb9c215ac75edda0dd6a5b20f1162d04b30ce7f733",
    "hotpotqa|20250424|alternating|json": "44f5e947a532d88fbccf5148f6c7baa36a67b78d6c14323e956df4ca936371ab",
    "hotpotqa|20250424|forced|adaptive": "c04074b273edeca35a11adda4b6093c40ef1103c57f4b8c993d4069152dd84a4",
    "hotpotqa|20250424|forced|cte": "53b1df4eee80f89b9c569cba8cfa4b343eba150d139ffe3feb951ad06949bedf",
    "hotpotqa|20250424|forced|json": "482cbc43f91fd74b156ddf3235c8685bb53e47bb006b1354f35e1952ec2a617e",
    "hotpotqa|20260820|alternating|adaptive": "000dc1d989b35f33aa570285a8ecd6346e3741d46d276cad43123b34e687dd8b",
    "hotpotqa|20260820|alternating|cte": "58da8f6a185d5532189ea76f3915f828166ad8bb8d72d0e946cb81004ed6b4ae",
    "hotpotqa|20260820|alternating|json": "b404cb69fc153f273e91c22c9254cec7ad79d8ca984519aa2b5dab65aa68be74",
    "hotpotqa|20260820|forced|adaptive": "2a46daab83cb5e8288bb87692cf1a3f5f2c8363ed65c5feba6ba6f2bbe97d4f0",
    "hotpotqa|20260820|forced|cte": "4b39005549d8278da7fb930b66c9719906152b799f43cd4258e3ce4ee079e3e3",
    "hotpotqa|20260820|forced|json": "7294f6bf77a612fb5415504ec08d95a6f29be17cb188b91ab9f255884927a636",
    "wikihop|20240826|alternating|adaptive": "336ab33e5d91025632d8360d176dd4899928ffd294e1013791fb3f718980ba2b",
    "wikihop|20240826|alternating|cte": "707815dfb6e9c9f590138709f29d0dc4336e442c63a03bfce5dec69989907181",
    "wikihop|20240826|alternating|json": "49979372077c031f53d8ebc9d1dd2638af228f55d85a88f581b8cd7ad32ec661",
    "wikihop|20250424|alternating|adaptive": "206831a0b7e70dd4c6e4e21a7bf0ae9d401c0d69476bf9da542a1a0e69c7ded6",
    "wikihop|20250424|alternating|cte": "1bd48b1739bc8b5319797751dd2158891623f9aa40573ecde668e6d114ccb919",
    "wikihop|20250424|alternating|json": "783317c268d23f8699ef20bb4b44fb5650f1cec8e8ed7bd1322f111a88084080",
    "wikihop|20260820|alternating|adaptive": "d88a753ff5a1a3bac1edce870db07bd39ee9f12e637a436ae9b0f5b8c0deff90",
    "wikihop|20260820|alternating|cte": "bfcde37f7e637f4e1b7bdf061bc3ea2773afa9e1a9a75a00479f6737084875f7",
    "wikihop|20260820|alternating|json": "0344758d7dce516019f759f6c4c9a1af617c09d04cacf4877537905879c95a57",
}
EXPECTED_PROMPT_SET_SHA256 = (
    "1b7b8d415812a358dbe92d1fcd158f69a57884f6bb735ec0855c0f624b26c7c9"
)
EXPECTED_A1_ITEM_SET_SHA256 = (
    "9eee61ecaeee10a0b2826bd0eaeb541fd3e6da0c047ea7043213a9b7c4ea675d"
)
EXPECTED_SNAPSHOT_SHA256 = (
    "4642d1386640037edfbfcf17f8a94152847ec27217335c14100152238cc4b70b"
)


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    cache_name: str
    relative_path: str
    expected_sha256: str
    records: int
    required_fields: tuple[str, ...]
    dataset_url: str
    license_name: str
    license_url: str

    @property
    def raw_url(self) -> str:
        return (
            f"https://raw.githubusercontent.com/thunlp/AutoForm/{SOURCE_COMMIT}/"
            f"{self.relative_path}"
        )


DATASETS = (
    DatasetSpec(
        key="hotpotqa",
        cache_name="hotpotqa.jsonl",
        relative_path="data/hotpot_qa/test_single.jsonl",
        expected_sha256=(
            "eca49392985ba260a44ae48dd6a439d73092e021f68d4d6d433c3226a1e51284"
        ),
        records=100,
        required_fields=(
            "answer",
            "context",
            "id",
            "input",
            "level",
            "supporting_paragraphs",
            "type",
        ),
        dataset_url="https://hotpotqa.github.io/",
        license_name="CC BY-SA 4.0",
        license_url="https://creativecommons.org/licenses/by-sa/4.0/",
    ),
    DatasetSpec(
        key="wikihop",
        cache_name="wikihop.jsonl",
        relative_path="data/wiki_hop_qa/test_processed.jsonl",
        expected_sha256=(
            "724cca64b47d0f2181170a23124cfd844c124391c76c6c867b597b6ff9195f39"
        ),
        records=100,
        required_fields=("answer", "context", "input"),
        dataset_url="https://zenodo.org/records/6407402",
        license_name="CC BY-SA 3.0",
        license_url="https://creativecommons.org/licenses/by-sa/3.0/",
    ),
)
DATASET_BY_KEY = {item.key: item for item in DATASETS}
ALLOWLISTED_URLS = frozenset(item.raw_url for item in DATASETS)
EXPECTED_DOWNLOAD_DIGESTS = {
    item.raw_url: item.expected_sha256 for item in DATASETS
}


@dataclass(frozen=True)
class Item:
    dataset: str
    source_index: int
    key: str
    question: str
    answer: str
    contexts: tuple[str, ...]
    support_indices: tuple[int, ...]
    forced_eligible: bool
    forced_reason: str


@dataclass(frozen=True)
class Split:
    owner_a: tuple[int, ...]
    owner_b: tuple[int, ...]

    def owner(self, name: str) -> tuple[int, ...]:
        if name == "A":
            return self.owner_a
        if name == "B":
            return self.owner_b
        raise ValueError(f"unknown agent: {name}")


@dataclass(frozen=True)
class TokenizerProfile:
    key: str
    display_name: str
    implementation: str
    vocabulary_size: int
    fingerprint: str
    count: Callable[[str], int]


@dataclass(frozen=True)
class PromptRecord:
    dataset: str
    seed: int
    split_mode: str
    arm: str
    item_key: str
    source_index: int
    agent: str
    prompt: str
    task_slice: str
    role_slice: str

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.prompt.encode("utf-8"))


def project_root() -> Path:
    return Path(__file__).resolve().parent


def default_cache_dir() -> Path:
    return project_root() / CACHE_SUBDIR


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def sequence_sha256(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        raw = value.encode("utf-8")
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def _download_exact(url: str, target: Path) -> None:
    if url not in ALLOWLISTED_URLS:
        raise RuntimeError(f"download URL is not allowlisted: {url}")
    request = Request(url, headers={"User-Agent": f"{FORMAT}/1"})
    with urlopen(request, timeout=120) as response:
        final_url = response.geturl()
        if final_url != url:
            raise RuntimeError(f"unexpected redirect: {final_url}")
        data = response.read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024:
        raise RuntimeError("source artifact exceeds the 64 MiB preflight limit")
    actual = sha256_bytes(data)
    expected = EXPECTED_DOWNLOAD_DIGESTS[url]
    if actual != expected:
        raise RuntimeError(
            f"download digest mismatch: expected {expected}, got {actual}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".download")
    temporary.write_bytes(data)
    temporary.replace(target)


def obtain_dataset(spec: DatasetSpec, cache_dir: Path, *, offline: bool) -> Path:
    target = cache_dir / spec.cache_name
    if not target.is_file():
        if offline:
            raise RuntimeError(f"missing cached artifact in offline mode: {target}")
        _download_exact(spec.raw_url, target)
    actual = sha256_file(target)
    if actual != spec.expected_sha256:
        raise RuntimeError(
            f"dataset digest drift for {spec.key}: expected "
            f"{spec.expected_sha256}, got {actual}"
        )
    return target


def _require_nonempty_text(value: Any, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise RuntimeError(f"{label} must be a non-empty string")
    return value


def _stable_wikihop_key(index: int, row: Mapping[str, Any]) -> str:
    material = canonical_json(
        {"context": row["context"], "input": row["input"]}
    ).encode("utf-8")
    return f"wikihop:{index:03d}:{sha256_bytes(material)[:16]}"


def _hotpot_question(row: Mapping[str, Any], index: int) -> str:
    marker = "\n\n# Question\n"
    value = _require_nonempty_text(row["input"], f"hotpotqa[{index}].input")
    if value.count(marker) != 1:
        raise RuntimeError(f"hotpotqa[{index}] has a changed question marker")
    prefix, question = value.split(marker, 1)
    expected_prefix = "# Contexts\n" + "\n".join(
        "- " + block for block in row["context"]
    )
    if prefix != expected_prefix:
        raise RuntimeError(f"hotpotqa[{index}] input/context rendering drifted")
    return _require_nonempty_text(question, f"hotpotqa[{index}].question")


def _hotpot_support_indices(
    row: Mapping[str, Any], index: int
) -> tuple[tuple[int, ...], bool, str]:
    paragraphs = tuple(
        part.strip()
        for part in _require_nonempty_text(
            row["supporting_paragraphs"],
            f"hotpotqa[{index}].supporting_paragraphs",
        ).split("\n\n")
        if part.strip()
    )
    if len(paragraphs) < 2:
        return (), False, "fewer_than_two_gold_paragraphs"
    matched: list[int] = []
    for paragraph in paragraphs:
        positions = [
            context_index
            for context_index, context in enumerate(row["context"])
            if paragraph in context
        ]
        if len(positions) != 1:
            return (), False, "gold_paragraph_match_is_not_unique"
        matched.append(positions[0])
    unique = tuple(dict.fromkeys(matched))
    if len(unique) < 2:
        return unique, False, "gold_paragraphs_cover_fewer_than_two_contexts"
    return unique, True, "two_or_more_uniquely_matched_gold_contexts"


def validate_rows(spec: DatasetSpec, rows: Sequence[Any]) -> tuple[Item, ...]:
    if len(rows) != spec.records:
        raise RuntimeError(
            f"record-count drift for {spec.key}: expected {spec.records}, got {len(rows)}"
        )
    items: list[Item] = []
    seen_keys: set[str] = set()
    required = set(spec.required_fields)
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise RuntimeError(f"{spec.key}[{index}] must be an object")
        if set(raw) != required:
            raise RuntimeError(
                f"{spec.key}[{index}] field drift: expected {sorted(required)}, "
                f"got {sorted(raw)}"
            )
        answer = _require_nonempty_text(raw["answer"], f"{spec.key}[{index}].answer")
        contexts_raw = raw["context"]
        if not isinstance(contexts_raw, list) or len(contexts_raw) < 2:
            raise RuntimeError(f"{spec.key}[{index}].context must contain at least two blocks")
        contexts = tuple(
            _require_nonempty_text(value, f"{spec.key}[{index}].context[{position}]")
            for position, value in enumerate(contexts_raw)
        )
        if spec.key == "hotpotqa":
            key = _require_nonempty_text(raw["id"], f"hotpotqa[{index}].id")
            if raw["level"] != "hard" or raw["type"] not in {"bridge", "comparison"}:
                raise RuntimeError(f"hotpotqa[{index}] level/type drifted")
            question = _hotpot_question(raw, index)
            support_indices, eligible, reason = _hotpot_support_indices(raw, index)
        elif spec.key == "wikihop":
            key = _stable_wikihop_key(index, raw)
            question = _require_nonempty_text(raw["input"], f"wikihop[{index}].input")
            support_indices = ()
            eligible = False
            reason = "gold_support_annotations_absent"
        else:
            raise RuntimeError(f"unsupported dataset: {spec.key}")
        if key in seen_keys:
            raise RuntimeError(f"duplicate item key in {spec.key}: {key}")
        seen_keys.add(key)
        items.append(
            Item(
                dataset=spec.key,
                source_index=index,
                key=key,
                question=question,
                answer=answer,
                contexts=contexts,
                support_indices=support_indices,
                forced_eligible=eligible,
                forced_reason=reason,
            )
        )
    return tuple(items)


def load_dataset(spec: DatasetSpec, path: Path) -> tuple[Item, ...]:
    raw = path.read_bytes()
    if sha256_bytes(raw) != spec.expected_sha256:
        raise RuntimeError(f"dataset changed after acquisition: {spec.key}")
    if not raw.endswith(b"\n"):
        raise RuntimeError(f"{spec.key} JSONL must end with a newline")
    rows: list[Any] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        try:
            rows.append(json.loads(line))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"invalid JSON in {spec.key} line {line_number}"
            ) from exc
    return validate_rows(spec, rows)


def _rank_context(item: Item, seed: int, position: int) -> bytes:
    digest = hashlib.sha256()
    digest.update(f"{FORMAT}|split|{item.dataset}|{seed}|{item.key}|{position}|".encode())
    digest.update(item.contexts[position].encode("utf-8"))
    return digest.digest()


def alternating_split(item: Item, seed: int) -> Split:
    order = sorted(
        range(len(item.contexts)),
        key=lambda position: (_rank_context(item, seed, position), position),
    )
    return Split(tuple(order[0::2]), tuple(order[1::2]))


def forced_split(item: Item, seed: int) -> Split:
    if not item.forced_eligible:
        raise RuntimeError(f"item is not forced-split eligible: {item.key}")
    order = sorted(
        range(len(item.contexts)),
        key=lambda position: (_rank_context(item, seed, position), position),
    )
    support_set = set(item.support_indices)
    supports = [position for position in order if position in support_set]
    remaining = [position for position in order if position not in support_set]
    owner_a = supports[0::2]
    owner_b = supports[1::2]
    for position in remaining:
        if len(owner_a) <= len(owner_b):
            owner_a.append(position)
        else:
            owner_b.append(position)
    result = Split(tuple(owner_a), tuple(owner_b))
    if not (set(result.owner_a) & support_set and set(result.owner_b) & support_set):
        raise RuntimeError("forced split failed to distribute gold context ownership")
    if sorted(result.owner_a + result.owner_b) != list(range(len(item.contexts))):
        raise RuntimeError("forced split lost or duplicated context blocks")
    return result


def split_digest(items: Sequence[Item], seed: int, mode: str) -> str:
    records: list[str] = []
    for item in items:
        if mode == "alternating":
            value = alternating_split(item, seed)
        elif mode == "forced":
            if not item.forced_eligible:
                continue
            value = forced_split(item, seed)
        else:
            raise RuntimeError(f"unknown split mode: {mode}")
        records.append(
            canonical_json(
                {
                    "item": item.key,
                    "owner_a": list(value.owner_a),
                    "owner_b": list(value.owner_b),
                }
            )
        )
    return sequence_sha256(records)


def _prompt_slices(
    item: Item, split: Split, agent: str, arm: str
) -> tuple[str, str, str]:
    if arm not in ARM_CONTRACTS:
        raise RuntimeError(f"unknown prompt arm: {arm}")
    peer = "B" if agent == "A" else "A"
    role = (
        f"You are evidence agent {agent} in a two-agent question-answering episode.\n"
        "The agents alternate. Use only the question, your private evidence, and later "
        "partner messages.\n"
        "Every factual statement must preserve source owner A or B. Do not expose "
        "private reasoning.\n"
        "Stop only when both agents have the same answer candidate and no evidence "
        "request remains.\n"
        f"Your partner is agent {peer}.\n"
        "Output contract:\n"
        + ARM_CONTRACTS[arm]
    )
    evidence = []
    for local_position, source_position in enumerate(split.owner(agent), start=1):
        evidence.append(
            f"[OWNER:{agent}:BLOCK:{local_position}:SOURCE:{source_position}]\n"
            + item.contexts[source_position]
        )
    task = (
        "Question:\n"
        + item.question
        + f"\nPrivate evidence owned by {agent}:\n"
        + "\n\n".join(evidence)
    )
    prompt = role + "\n\n" + task
    return prompt, task, role


def render_prompt(item: Item, split: Split, agent: str, arm: str) -> str:
    return _prompt_slices(item, split, agent, arm)[0]


def build_prompt_records(
    datasets: Mapping[str, Sequence[Item]],
) -> tuple[PromptRecord, ...]:
    records: list[PromptRecord] = []
    for dataset in sorted(datasets):
        items = datasets[dataset]
        for seed in DATA_SEEDS:
            modes = ("alternating", "forced") if dataset == "hotpotqa" else ("alternating",)
            for mode in modes:
                for item in items:
                    if mode == "forced" and not item.forced_eligible:
                        continue
                    split = alternating_split(item, seed) if mode == "alternating" else forced_split(item, seed)
                    for arm in ARMS:
                        for agent in AGENTS:
                            prompt, task_slice, role_slice = _prompt_slices(
                                item, split, agent, arm
                            )
                            records.append(
                                PromptRecord(
                                    dataset=dataset,
                                    seed=seed,
                                    split_mode=mode,
                                    arm=arm,
                                    item_key=item.key,
                                    source_index=item.source_index,
                                    agent=agent,
                                    prompt=prompt,
                                    task_slice=task_slice,
                                    role_slice=role_slice,
                                )
                            )
    return tuple(records)


def prompt_group_key(record: PromptRecord) -> str:
    return f"{record.dataset}|{record.seed}|{record.split_mode}|{record.arm}"


def prompt_group_digests(records: Sequence[PromptRecord]) -> dict[str, str]:
    grouped: dict[str, list[PromptRecord]] = {}
    for record in records:
        grouped.setdefault(prompt_group_key(record), []).append(record)
    result: dict[str, str] = {}
    for key, values in sorted(grouped.items()):
        ordered = sorted(values, key=lambda row: (row.source_index, row.agent))
        result[key] = sequence_sha256(
            f"{row.item_key}|{row.agent}|{row.sha256}" for row in ordered
        )
    return result


def prompt_set_sha256(records: Sequence[PromptRecord]) -> str:
    ordered = sorted(
        records,
        key=lambda row: (
            row.dataset,
            row.seed,
            row.split_mode,
            row.arm,
            row.source_index,
            row.agent,
        ),
    )
    return sequence_sha256(
        f"{prompt_group_key(row)}|{row.item_key}|{row.agent}|{row.sha256}"
        for row in ordered
    )


def _require_version(distribution: str, expected: str) -> str:
    try:
        actual = metadata.version(distribution)
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError(f"missing dependency: {distribution}=={expected}") from exc
    if actual != expected:
        raise RuntimeError(
            f"dependency drift: {distribution} must be {expected}, found {actual}"
        )
    return actual


def _tiktoken_fingerprint(encoding: Any) -> str:
    digest = hashlib.sha256()
    pattern = encoding._pat_str.encode("utf-8")
    digest.update(len(pattern).to_bytes(8, "big"))
    digest.update(pattern)
    for token, rank in sorted(
        encoding._mergeable_ranks.items(), key=lambda item: (item[1], item[0])
    ):
        digest.update(len(token).to_bytes(4, "big"))
        digest.update(token)
        digest.update(rank.to_bytes(8, "big"))
    for token, rank in sorted(encoding._special_tokens.items()):
        raw = token.encode("utf-8")
        digest.update(len(raw).to_bytes(4, "big"))
        digest.update(raw)
        digest.update(rank.to_bytes(8, "big"))
    return digest.hexdigest()


def load_tokenizers(asset_root: Path) -> tuple[TokenizerProfile, ...]:
    _require_version("tiktoken", TIKTOKEN_VERSION)
    _require_version("tokenizers", TOKENIZERS_VERSION)
    import tiktoken
    from tokenizers import Tokenizer

    profiles: list[TokenizerProfile] = []
    for name in ("cl100k_base", "o200k_base"):
        encoding = tiktoken.get_encoding(name)

        def count_tiktoken(text: str, *, current: Any = encoding) -> int:
            return len(
                current.encode(text, allowed_special=set(), disallowed_special=())
            )

        profile = TokenizerProfile(
            key=name,
            display_name=name,
            implementation=f"tiktoken {TIKTOKEN_VERSION}",
            vocabulary_size=encoding.n_vocab,
            fingerprint=_tiktoken_fingerprint(encoding),
            count=count_tiktoken,
        )
        profiles.append(profile)

    open_specs = (
        (
            "qwen2_5_7b_instruct",
            "Qwen2.5-7B-Instruct tokenizer",
            "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539",
        ),
        (
            "mistral_7b_instruct_v03",
            "Mistral-7B-Instruct-v0.3 tokenizer",
            "e553af6fff7d7ad76e830608b218c5c0b0822998d5a1a96099a74cd3c1cb1a49",
        ),
    )
    for key, display_name, expected in open_specs:
        path = asset_root / key / "tokenizer.json"
        if not path.is_file():
            raise RuntimeError(f"missing pinned tokenizer asset: {path}")
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(
                f"tokenizer asset drift for {key}: expected {expected}, got {actual}"
            )
        tokenizer = Tokenizer.from_file(str(path))

        def count_open(text: str, *, current: Any = tokenizer) -> int:
            return len(current.encode(text, add_special_tokens=False).ids)

        profiles.append(
            TokenizerProfile(
                key=key,
                display_name=display_name,
                implementation=f"tokenizers {TOKENIZERS_VERSION}",
                vocabulary_size=tokenizer.get_vocab_size(with_added_tokens=True),
                fingerprint=actual,
                count=count_open,
            )
        )
    observed = {profile.key: profile.fingerprint for profile in profiles}
    if observed != EXPECTED_TOKENIZER_FINGERPRINTS:
        raise RuntimeError(f"tokenizer fingerprint drift: {observed}")
    return tuple(profiles)


def nearest_rank(values: Sequence[int], fraction: float) -> int:
    if not values:
        raise ValueError("cannot summarize an empty sequence")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def prompt_token_metrics(
    records: Sequence[PromptRecord], profiles: Sequence[TokenizerProfile]
) -> dict[str, Any]:
    totals: dict[str, Any] = {}
    for dataset in sorted({row.dataset for row in records}):
        totals[dataset] = {}
        for mode in sorted({row.split_mode for row in records if row.dataset == dataset}):
            totals[dataset][mode] = {}
            for arm in ARMS:
                subset = [
                    row
                    for row in records
                    if row.dataset == dataset
                    and row.split_mode == mode
                    and row.arm == arm
                ]
                arm_result: dict[str, Any] = {
                    "prompts": len(subset),
                    "utf8_bytes": sum(len(row.prompt.encode("utf-8")) for row in subset),
                    "tokenizers": {},
                }
                for profile in profiles:
                    counts = [profile.count(row.prompt) for row in subset]
                    task_counts = [profile.count(row.task_slice) for row in subset]
                    role_counts = [profile.count(row.role_slice) for row in subset]
                    arm_result["tokenizers"][profile.key] = {
                        "total": sum(counts),
                        "min": min(counts),
                        "p25": nearest_rank(counts, 0.25),
                        "p50": nearest_rank(counts, 0.50),
                        "p75": nearest_rank(counts, 0.75),
                        "p95": nearest_rank(counts, 0.95),
                        "max": max(counts),
                        "task_slice_total": sum(task_counts),
                        "role_slice_total": sum(role_counts),
                    }
                totals[dataset][mode][arm] = arm_result
    return totals


def current_artifact_metrics(
    profiles: Sequence[TokenizerProfile], root: Path
) -> dict[str, Any]:
    source = root / CURRENT_IMPLEMENTATION
    actual = sha256_file(source)
    if actual != EXPECTED_CURRENT_IMPLEMENTATION_SHA256:
        raise RuntimeError(
            "current adaptive implementation drift: "
            f"expected {EXPECTED_CURRENT_IMPLEMENTATION_SHA256}, got {actual}"
        )
    import urusilla_generalization_surface_v06 as current

    if current.EXPECTED_SNAPSHOT_SHA256 != EXPECTED_CURRENT_SNAPSHOT_SHA256:
        raise RuntimeError("current adaptive snapshot lock drifted")
    development = current.build_datasets()["development"]
    profile = current.derive_alias_profile(development)
    profile_sha = current.profile_sha256(profile)
    if profile_sha != EXPECTED_CURRENT_PROFILE_SHA256:
        raise RuntimeError("current adaptive profile drifted")
    result: dict[str, Any] = {
        "implementation_sha256": actual,
        "profile_sha256": profile_sha,
        "snapshot_sha256": current.EXPECTED_SNAPSHOT_SHA256,
        "tokenizers": {},
    }
    for profile_tokenizer in profiles:
        raw_metrics = current.cold_artifact_metrics(profile_tokenizer, profile)
        metrics = {
            key: {"tokens": value[0], "utf8_bytes": value[1]}
            for key, value in raw_metrics.items()
        }
        result["tokenizers"][profile_tokenizer.key] = {
            "artifacts": metrics,
            "conservative_all_artifacts_tokens": sum(
                item["tokens"] for item in metrics.values()
            ),
            "conservative_all_artifacts_bytes": sum(
                item["utf8_bytes"] for item in metrics.values()
            ),
        }
    return result


def select_a1_items(datasets: Mapping[str, Sequence[Item]]) -> dict[str, tuple[Item, ...]]:
    selected: dict[str, tuple[Item, ...]] = {}
    for dataset, items in sorted(datasets.items()):
        eligible = [item for item in items if dataset != "hotpotqa" or item.forced_eligible]
        ranked = sorted(
            eligible,
            key=lambda item: (
                hashlib.sha256(
                    f"{FORMAT}|a1|20260820|{dataset}|{item.key}".encode()
                ).digest(),
                item.source_index,
            ),
        )
        selected[dataset] = tuple(ranked[:20])
    return selected


def a1_item_set_sha256(selected: Mapping[str, Sequence[Item]]) -> str:
    return sequence_sha256(
        f"{dataset}|{item.source_index}|{item.key}"
        for dataset in sorted(selected)
        for item in selected[dataset]
    )


def _a1_prompt_lookup(
    selected: Mapping[str, Sequence[Item]], profiles: Sequence[TokenizerProfile]
) -> dict[tuple[str, str, str, str], int]:
    result: dict[tuple[str, str, str, str], int] = {}
    for dataset in sorted(selected):
        mode = "forced" if dataset == "hotpotqa" else "alternating"
        for item in selected[dataset]:
            split = forced_split(item, 20260820) if mode == "forced" else alternating_split(item, 20260820)
            for arm in ARMS:
                for agent in AGENTS:
                    prompt = render_prompt(item, split, agent, arm)
                    for profile in profiles:
                        result[(item.key, arm, agent, profile.key)] = profile.count(prompt)
    return result


def cost_preflight(
    selected: Mapping[str, Sequence[Item]],
    profiles: Sequence[TokenizerProfile],
    artifacts: Mapping[str, Any],
) -> dict[str, Any]:
    pairs = (("O", "G"), ("G", "Q"), ("Q", "O"))
    provider_price = {
        "O": {"input_per_million": 0.25, "output_per_million": 2.00},
        "G": {"input_per_million": 0.75, "output_per_million": 3.75},
    }
    prompt_counts = _a1_prompt_lookup(selected, profiles)
    def tokenizer_key(model: str) -> str:
        if model == "O":
            return "o200k_base"
        if model == "Q":
            return "qwen2_5_7b_instruct"
        return "max_four"

    def initial_tokens(item_key: str, arm: str, agent: str, model: str) -> int:
        key = tokenizer_key(model)
        if key != "max_four":
            return prompt_counts[(item_key, arm, agent, key)]
        return max(
            prompt_counts[(item_key, arm, agent, profile.key)]
            for profile in profiles
        )

    def cold_tokens(model: str) -> int:
        key = tokenizer_key(model)
        if key != "max_four":
            return artifacts["tokenizers"][key]["conservative_all_artifacts_tokens"]
        return max(
            value["conservative_all_artifacts_tokens"]
            for value in artifacts["tokenizers"].values()
        )

    scenarios = {
        "lower_planning": {
            "output_tokens": 80,
            "history_overhead": 16,
            "request_reserve": 64,
        },
        "conservative_upper": {
            "output_tokens": 250,
            "history_overhead": 32,
            "request_reserve": 128,
        },
    }
    item_count = sum(len(values) for values in selected.values())
    episodes = item_count * len(ARMS) * len(pairs)
    base_calls = episodes * 8
    paid_calls = 0
    local_calls = 0
    final_calls = {"paid": 0, "local": 0}
    scenario_results: dict[str, Any] = {}
    for scenario_name, assumptions in scenarios.items():
        provider_totals = {
            provider: {"input_tokens": 0, "output_tokens": 0, "calls": 0}
            for provider in provider_price
        }
        local_totals = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
        for dataset in sorted(selected):
            for item in selected[dataset]:
                for arm in ARMS:
                    for left, right in pairs:
                        models = (left, right)
                        for turn in range(8):
                            agent_index = turn % 2
                            agent = AGENTS[agent_index]
                            model = models[agent_index]
                            input_tokens = (
                                initial_tokens(item.key, arm, agent, model)
                                + assumptions["request_reserve"]
                                + turn
                                * (
                                    assumptions["output_tokens"]
                                    + assumptions["history_overhead"]
                                )
                            )
                            if arm == "adaptive" and turn < 2:
                                input_tokens += cold_tokens(model)
                            if model in provider_price:
                                provider_totals[model]["input_tokens"] += input_tokens
                                provider_totals[model]["output_tokens"] += assumptions["output_tokens"]
                                provider_totals[model]["calls"] += 1
                            else:
                                local_totals["input_tokens"] += input_tokens
                                local_totals["output_tokens"] += assumptions["output_tokens"]
                                local_totals["calls"] += 1
        cost = 0.0
        for provider, totals in provider_totals.items():
            price = provider_price[provider]
            totals["input_cost_usd"] = round(
                totals["input_tokens"] / 1_000_000 * price["input_per_million"],
                6,
            )
            totals["output_cost_usd"] = round(
                totals["output_tokens"] / 1_000_000 * price["output_per_million"],
                6,
            )
            totals["cost_usd"] = round(
                totals["input_cost_usd"] + totals["output_cost_usd"], 6
            )
            cost += totals["cost_usd"]
        scenario_results[scenario_name] = {
            "assumptions": assumptions,
            "providers": provider_totals,
            "local": local_totals,
            "paid_cost_usd": round(cost, 6),
            "with_20_percent_retry_and_price_reserve_usd": round(cost * 1.20, 6),
        }
    for left, right in pairs:
        for turn in range(8):
            model = (left, right)[turn % 2]
            if model in provider_price:
                paid_calls += item_count * len(ARMS)
            else:
                local_calls += item_count * len(ARMS)
        final_model = right
        final_calls["paid" if final_model in provider_price else "local"] += item_count * len(ARMS)
    if base_calls != paid_calls + local_calls:
        raise RuntimeError("call-accounting reconciliation failed")
    return {
        "stage": "requested_three_arm_a1_preflight",
        "items": item_count,
        "arms": list(ARMS),
        "ordered_pairs": [list(pair) for pair in pairs],
        "episodes": episodes,
        "base_calls": base_calls,
        "paid_calls": paid_calls,
        "local_calls": local_calls,
        "final_calls": final_calls,
        "twenty_percent_call_reserve": math.ceil(base_calls * 0.20),
        "twenty_percent_paid_call_reserve": math.ceil(paid_calls * 0.20),
        "pricing_checked_date": "2026-08-20",
        "pricing": provider_price,
        "google_tokenizer_note": (
            "The maximum count across the four pinned local tokenizers is a planning "
            "proxy, not provider billing telemetry."
        ),
        "scenarios": scenario_results,
    }


def _verify_lock(name: str, observed: Any, expected: Any) -> None:
    if expected in ({}, "pending"):
        raise RuntimeError(f"unfrozen preflight lock: {name}")
    if observed != expected:
        raise RuntimeError(f"{name} drift: expected {expected}, got {observed}")


def build_snapshot(
    cache_dir: Path,
    asset_root: Path,
    *,
    offline: bool,
) -> tuple[dict[str, Any], tuple[PromptRecord, ...]]:
    datasets: dict[str, tuple[Item, ...]] = {}
    source_rows: dict[str, Any] = {}
    for spec in DATASETS:
        path = obtain_dataset(spec, cache_dir, offline=offline)
        items = load_dataset(spec, path)
        datasets[spec.key] = items
        reasons: dict[str, int] = {}
        for item in items:
            reasons[item.forced_reason] = reasons.get(item.forced_reason, 0) + 1
        source_rows[spec.key] = {
            "raw_url": spec.raw_url,
            "source_tree_url": SOURCE_TREE_URL,
            "source_commit": SOURCE_COMMIT,
            "source_code_license": "Apache-2.0",
            "source_code_license_url": SOURCE_LICENSE_URL,
            "dataset_url": spec.dataset_url,
            "dataset_license": spec.license_name,
            "dataset_license_url": spec.license_url,
            "sha256": sha256_file(path),
            "records": len(items),
            "required_fields": list(spec.required_fields),
            "context_blocks": {
                "min": min(len(item.contexts) for item in items),
                "max": max(len(item.contexts) for item in items),
                "total": sum(len(item.contexts) for item in items),
            },
            "forced_eligible": sum(item.forced_eligible for item in items),
            "forced_ineligible": sum(not item.forced_eligible for item in items),
            "forced_reasons": dict(sorted(reasons.items())),
        }
    split_rows: dict[str, dict[str, str]] = {}
    distribution_rows: dict[str, Any] = {}
    for dataset, items in sorted(datasets.items()):
        split_rows[dataset] = {}
        distribution_rows[dataset] = {}
        for seed in DATA_SEEDS:
            alternating = split_digest(items, seed, "alternating")
            split_rows[dataset][f"{seed}|alternating"] = alternating
            naturally_distributed = sum(
                item.forced_eligible
                and bool(set(alternating_split(item, seed).owner_a) & set(item.support_indices))
                and bool(set(alternating_split(item, seed).owner_b) & set(item.support_indices))
                for item in items
            )
            distribution_rows[dataset][str(seed)] = {
                "eligible": sum(item.forced_eligible for item in items),
                "naturally_distributed": naturally_distributed,
            }
            if any(item.forced_eligible for item in items):
                forced = split_digest(items, seed, "forced")
                split_rows[dataset][f"{seed}|forced"] = forced
                distribution_rows[dataset][str(seed)]["forced_distributed"] = sum(
                    item.forced_eligible for item in items
                )
    records = build_prompt_records(datasets)
    group_digests = prompt_group_digests(records)
    full_prompt_digest = prompt_set_sha256(records)
    profiles = load_tokenizers(asset_root)
    token_metrics = prompt_token_metrics(records, profiles)
    artifacts = current_artifact_metrics(profiles, project_root())
    selected = select_a1_items(datasets)
    selected_digest = a1_item_set_sha256(selected)
    cost = cost_preflight(selected, profiles, artifacts)
    prompt_hashes = [record.sha256 for record in records]
    snapshot: dict[str, Any] = {
        "format": FORMAT,
        "scope": "local_preflight_only",
        "model_calls": 0,
        "paid_calls": 0,
        "task_success_measured": False,
        "sources": source_rows,
        "data_seeds": list(DATA_SEEDS),
        "split_algorithm": (
            "SHA-256 ranks each context by format, dataset, seed, item key, source "
            "index, and exact context bytes; alternating ownership starts with A."
        ),
        "split_digests": split_rows,
        "forced_distribution": distribution_rows,
        "prompt_contract_sha256": {
            arm: sha256_bytes(text.encode("utf-8"))
            for arm, text in ARM_CONTRACTS.items()
        },
        "prompt_groups": group_digests,
        "prompt_set_sha256": full_prompt_digest,
        "prompt_records": len(records),
        "unique_prompt_text_sha256": len(set(prompt_hashes)),
        "duplicate_prompt_records": len(prompt_hashes) - len(set(prompt_hashes)),
        "tokenizers": [
            {
                "key": profile.key,
                "display_name": profile.display_name,
                "implementation": profile.implementation,
                "vocabulary_size": profile.vocabulary_size,
                "fingerprint": profile.fingerprint,
            }
            for profile in profiles
        ],
        "prompt_token_metrics": token_metrics,
        "current_adaptive_artifacts": artifacts,
        "a1_selection": {
            "sha256": selected_digest,
            "items": {
                dataset: [
                    {"source_index": item.source_index, "item_key": item.key}
                    for item in values
                ]
                for dataset, values in selected.items()
            },
            "hotpotqa_split": "forced",
            "wikihop_split": "alternating_due_to_missing_gold_support_annotations",
            "seed": 20260820,
        },
        "cost_preflight": cost,
        "ledger_status": {
            "task_input": "initial prompt slices counted locally; future requests count every replay",
            "system_role": "initial role and output-contract slices counted locally",
            "agent_input_history": "bounded in the cost preflight; no observed value",
            "agent_output_visible": "80 to 250 tokens per call assumed; no observed value",
            "final_answer": "last call classified separately in planning; no observed value",
            "format_induction": "zero model tokens in this preflight",
            "encode_decode_model": "zero model tokens; deterministic local bridge planned",
            "negotiation_profile": "all current cold artifacts conservatively charged once per endpoint",
            "repair_retry": "zero observed; 20 percent planning reserve",
            "tool_request": "zero by protocol",
            "tool_result": "zero by protocol",
            "safety_filter": "zero in this preflight; future usage must be logged",
            "judge": "zero in this preflight; excluded from runtime and included in future study cost",
            "hidden_reasoning_billed": "unknown until provider usage is returned",
        },
        "wire_latency_status": {
            "initial_prompt_utf8_bytes": "measured in prompt_token_metrics",
            "cold_artifact_utf8_bytes": "measured in current_adaptive_artifacts",
            "message_payload_and_envelope_bytes": "not observable before model output",
            "retransmitted_bytes": "zero observed; future runs must record",
            "encode_decode_queue_network_model_repair_end_to_end_latency": (
                "not measured in this zero-call preflight"
            ),
        },
    }
    snapshot_digest = sha256_bytes(canonical_json(snapshot).encode("utf-8"))
    snapshot["snapshot_sha256"] = snapshot_digest
    _verify_lock("split digests", split_rows, EXPECTED_SPLIT_DIGESTS)
    _verify_lock(
        "prompt group digests", group_digests, EXPECTED_PROMPT_GROUP_DIGESTS
    )
    _verify_lock("prompt set", full_prompt_digest, EXPECTED_PROMPT_SET_SHA256)
    _verify_lock("A1 item set", selected_digest, EXPECTED_A1_ITEM_SET_SHA256)
    _verify_lock("snapshot", snapshot_digest, EXPECTED_SNAPSHOT_SHA256)
    return snapshot, records


def write_cache_outputs(
    snapshot: Mapping[str, Any], records: Sequence[PromptRecord], cache_dir: Path
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = cache_dir / "preflight_snapshot.json"
    manifest_path = cache_dir / "prompt_manifest.jsonl"
    snapshot_path.write_text(canonical_json(snapshot) + "\n", encoding="utf-8")
    with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in sorted(
            records,
            key=lambda row: (
                row.dataset,
                row.seed,
                row.split_mode,
                row.arm,
                row.source_index,
                row.agent,
            ),
        ):
            handle.write(
                canonical_json(
                    {
                        "agent": record.agent,
                        "arm": record.arm,
                        "dataset": record.dataset,
                        "item_key": record.item_key,
                        "prompt_sha256": record.sha256,
                        "seed": record.seed,
                        "source_index": record.source_index,
                        "split_mode": record.split_mode,
                    }
                )
                + "\n"
            )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=default_cache_dir())
    parser.add_argument(
        "--assets-dir",
        type=Path,
        default=project_root() / "work" / "tokenizer_assets",
    )
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--no-cache-output", action="store_true")
    arguments = parser.parse_args(argv)
    snapshot, records = build_snapshot(
        arguments.cache_dir,
        arguments.assets_dir,
        offline=arguments.offline,
    )
    if not arguments.no_cache_output:
        write_cache_outputs(snapshot, records, arguments.cache_dir)
    print(canonical_json(snapshot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
