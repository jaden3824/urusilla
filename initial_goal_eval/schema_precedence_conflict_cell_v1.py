"""Frozen, offline counterbalanced schema-precedence conflict diagnostic.

Each of two blocks crosses opaque schema identity with exact local resource
availability. The strict-versus-fallback schema semantics swap registry
position across blocks. All unavailable cells carry the same inline fallback,
so an identity-by-availability shortcut cannot earn both block scores.

This file makes no provider, browser, UI, filesystem, or network call. It
accepts only exact model-visible request bytes and raw response text. Schema
status, expected action, and score are derived here; caller verdicts are not
accepted. Every evidence/claim boundary remains false.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import re
from typing import Any, Mapping

from urusilla_hybrid_runtime.canonical import (
    JsonValidationError,
    canonical_json,
    sha256_text,
    strict_json_loads,
)


PLAN_SCHEMA = "urusilla-schema-precedence-conflict-plan/3"
OBSERVATION_SCHEMA = "urusilla-schema-precedence-conflict-observation/3"
SCORE_SCHEMA = "urusilla-schema-precedence-conflict-score/3"
REQUEST_SCHEMA = "urusilla-schema-precedence-conflict-request/3"
PLAN_STATUS = "frozen-preregistered-no-observations"
EVIDENCE_BOUNDARY = "offline-project-authored-diagnostic-only"
FROZEN_PLAN_SHA256 = (
    "sha256:18e4bfcec6e8a9c61550f0e43aba17375b7077d42e8c12c87b2942cf9f5095e6"
)

CELL_IDS = ('cell-01', 'cell-02', 'cell-03', 'cell-04', 'cell-05', 'cell-06', 'cell-07', 'cell-08')
BLOCK_IDS = ("block-0", "block-1")
EXECUTION_ORDER = ('cell-06', 'cell-03', 'cell-08', 'cell-01', 'cell-05', 'cell-02', 'cell-07', 'cell-04')
MAX_OUTPUT_BYTES = 16_384
_OPAQUE_URI_RE = re.compile(r"^urn:urusilla:eval:spc:[0-9a-f]{8}:1$")
_SEMANTIC_WORDS = ("strict", "refuse", "fallback", "permissive", "allow")

# Literal canonical model-visible preimages. Every cell is separately pinned.
_PREIMAGE_01 = r'''{"context_binding":{"context_id":"ctx-94a16f2c","cross_cell_conversation":false,"cross_cell_memory":false,"fresh_independent_context":true,"parent_context_id":null},"format":"urusilla-schema-precedence-conflict-request/3","inline_constraint":{"fallback_allowed":true,"fallback_mode":"json","on_schema_unavailable":"fallback"},"local_resources":[{"content_utf8":"{\"$id\":\"urn:urusilla:eval:spc:7f3a91c2:1\",\"$schema\":\"https://json-schema.org/draft/2020-12/schema\",\"additionalProperties\":false,\"properties\":{\"disposition\":{\"const\":\"strict-refuse\"},\"reason_code\":{\"const\":\"schema-authoritative\"},\"schema_binding_verified\":{\"const\":true}},\"required\":[\"disposition\",\"reason_code\",\"schema_binding_verified\"],\"type\":\"object\",\"x-urusilla-required-disposition\":\"strict-refuse\",\"x-urusilla-semantic-padding\":\"\"}","media_type":"application/schema+json","uri":"urn:urusilla:eval:spc:7f3a91c2:1"}],"pinned_registry":[{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:a25e1d1d10139fd97b0a64462b19bc2e9747e004c8c70313b8d42f69abff0773","uri":"urn:urusilla:eval:spc:7f3a91c2:1"},{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:38ab7bf461ec101e077e0f98222ec2cc6cd2908488e3886ac935fc5d335edb28","uri":"urn:urusilla:eval:spc:c8e45b10:1"}],"precedence_policy":{"resolved_exact_schema_overrides_inline":true,"unavailable_schema_uses_inline_fallback":true},"query":{"schema_binding":{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:a25e1d1d10139fd97b0a64462b19bc2e9747e004c8c70313b8d42f69abff0773","uri":"urn:urusilla:eval:spc:7f3a91c2:1"},"schema_reference":"urn:urusilla:eval:spc:7f3a91c2:1"},"response_contract":{"canonical_json_only":true,"fields":["disposition","reason_code","schema_binding_verified"],"no_external_effect":true,"resolution_table":[{"condition":"resolved-exact","disposition_source":"resolved_schema.properties.disposition.const","reason_code":"schema-authoritative","schema_binding_verified":true},{"condition":"resource-unavailable","disposition":"fallback","reason_code":"schema-resource-unavailable","schema_binding_verified":false}],"rule":"Match the condition from supplied bytes. For resolved-exact, read disposition from the resolved schema path named by disposition_source. For resource-unavailable, use the literal row. Do not infer semantics from URI text, registry position, context ID, or resource presence alone."},"task":"select-the-authoritative-non-effectful-response-disposition"}'''
_PREIMAGE_02 = r'''{"context_binding":{"context_id":"ctx-b730e15a","cross_cell_conversation":false,"cross_cell_memory":false,"fresh_independent_context":true,"parent_context_id":null},"format":"urusilla-schema-precedence-conflict-request/3","inline_constraint":{"fallback_allowed":true,"fallback_mode":"json","on_schema_unavailable":"fallback"},"local_resources":[{"content_utf8":"{\"$id\":\"urn:urusilla:eval:spc:c8e45b10:1\",\"$schema\":\"https://json-schema.org/draft/2020-12/schema\",\"additionalProperties\":false,\"properties\":{\"disposition\":{\"const\":\"fallback\"},\"reason_code\":{\"const\":\"schema-authoritative\"},\"schema_binding_verified\":{\"const\":true}},\"required\":[\"disposition\",\"reason_code\",\"schema_binding_verified\"],\"type\":\"object\",\"x-urusilla-required-disposition\":\"fallback\",\"x-urusilla-semantic-padding\":\"0000000000\"}","media_type":"application/schema+json","uri":"urn:urusilla:eval:spc:c8e45b10:1"}],"pinned_registry":[{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:a25e1d1d10139fd97b0a64462b19bc2e9747e004c8c70313b8d42f69abff0773","uri":"urn:urusilla:eval:spc:7f3a91c2:1"},{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:38ab7bf461ec101e077e0f98222ec2cc6cd2908488e3886ac935fc5d335edb28","uri":"urn:urusilla:eval:spc:c8e45b10:1"}],"precedence_policy":{"resolved_exact_schema_overrides_inline":true,"unavailable_schema_uses_inline_fallback":true},"query":{"schema_binding":{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:38ab7bf461ec101e077e0f98222ec2cc6cd2908488e3886ac935fc5d335edb28","uri":"urn:urusilla:eval:spc:c8e45b10:1"},"schema_reference":"urn:urusilla:eval:spc:c8e45b10:1"},"response_contract":{"canonical_json_only":true,"fields":["disposition","reason_code","schema_binding_verified"],"no_external_effect":true,"resolution_table":[{"condition":"resolved-exact","disposition_source":"resolved_schema.properties.disposition.const","reason_code":"schema-authoritative","schema_binding_verified":true},{"condition":"resource-unavailable","disposition":"fallback","reason_code":"schema-resource-unavailable","schema_binding_verified":false}],"rule":"Match the condition from supplied bytes. For resolved-exact, read disposition from the resolved schema path named by disposition_source. For resource-unavailable, use the literal row. Do not infer semantics from URI text, registry position, context ID, or resource presence alone."},"task":"select-the-authoritative-non-effectful-response-disposition"}'''
_PREIMAGE_03 = r'''{"context_binding":{"context_id":"ctx-2c84d9f1","cross_cell_conversation":false,"cross_cell_memory":false,"fresh_independent_context":true,"parent_context_id":null},"format":"urusilla-schema-precedence-conflict-request/3","inline_constraint":{"fallback_allowed":true,"fallback_mode":"json","on_schema_unavailable":"fallback"},"local_resources":[],"pinned_registry":[{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:a25e1d1d10139fd97b0a64462b19bc2e9747e004c8c70313b8d42f69abff0773","uri":"urn:urusilla:eval:spc:7f3a91c2:1"},{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:38ab7bf461ec101e077e0f98222ec2cc6cd2908488e3886ac935fc5d335edb28","uri":"urn:urusilla:eval:spc:c8e45b10:1"}],"precedence_policy":{"resolved_exact_schema_overrides_inline":true,"unavailable_schema_uses_inline_fallback":true},"query":{"schema_binding":{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:a25e1d1d10139fd97b0a64462b19bc2e9747e004c8c70313b8d42f69abff0773","uri":"urn:urusilla:eval:spc:7f3a91c2:1"},"schema_reference":"urn:urusilla:eval:spc:7f3a91c2:1"},"response_contract":{"canonical_json_only":true,"fields":["disposition","reason_code","schema_binding_verified"],"no_external_effect":true,"resolution_table":[{"condition":"resolved-exact","disposition_source":"resolved_schema.properties.disposition.const","reason_code":"schema-authoritative","schema_binding_verified":true},{"condition":"resource-unavailable","disposition":"fallback","reason_code":"schema-resource-unavailable","schema_binding_verified":false}],"rule":"Match the condition from supplied bytes. For resolved-exact, read disposition from the resolved schema path named by disposition_source. For resource-unavailable, use the literal row. Do not infer semantics from URI text, registry position, context ID, or resource presence alone."},"task":"select-the-authoritative-non-effectful-response-disposition"}'''
_PREIMAGE_04 = r'''{"context_binding":{"context_id":"ctx-d106a8e7","cross_cell_conversation":false,"cross_cell_memory":false,"fresh_independent_context":true,"parent_context_id":null},"format":"urusilla-schema-precedence-conflict-request/3","inline_constraint":{"fallback_allowed":true,"fallback_mode":"json","on_schema_unavailable":"fallback"},"local_resources":[],"pinned_registry":[{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:a25e1d1d10139fd97b0a64462b19bc2e9747e004c8c70313b8d42f69abff0773","uri":"urn:urusilla:eval:spc:7f3a91c2:1"},{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:38ab7bf461ec101e077e0f98222ec2cc6cd2908488e3886ac935fc5d335edb28","uri":"urn:urusilla:eval:spc:c8e45b10:1"}],"precedence_policy":{"resolved_exact_schema_overrides_inline":true,"unavailable_schema_uses_inline_fallback":true},"query":{"schema_binding":{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:38ab7bf461ec101e077e0f98222ec2cc6cd2908488e3886ac935fc5d335edb28","uri":"urn:urusilla:eval:spc:c8e45b10:1"},"schema_reference":"urn:urusilla:eval:spc:c8e45b10:1"},"response_contract":{"canonical_json_only":true,"fields":["disposition","reason_code","schema_binding_verified"],"no_external_effect":true,"resolution_table":[{"condition":"resolved-exact","disposition_source":"resolved_schema.properties.disposition.const","reason_code":"schema-authoritative","schema_binding_verified":true},{"condition":"resource-unavailable","disposition":"fallback","reason_code":"schema-resource-unavailable","schema_binding_verified":false}],"rule":"Match the condition from supplied bytes. For resolved-exact, read disposition from the resolved schema path named by disposition_source. For resource-unavailable, use the literal row. Do not infer semantics from URI text, registry position, context ID, or resource presence alone."},"task":"select-the-authoritative-non-effectful-response-disposition"}'''
_PREIMAGE_05 = r'''{"context_binding":{"context_id":"ctx-6f21c4b8","cross_cell_conversation":false,"cross_cell_memory":false,"fresh_independent_context":true,"parent_context_id":null},"format":"urusilla-schema-precedence-conflict-request/3","inline_constraint":{"fallback_allowed":true,"fallback_mode":"json","on_schema_unavailable":"fallback"},"local_resources":[{"content_utf8":"{\"$id\":\"urn:urusilla:eval:spc:4d72b6a9:1\",\"$schema\":\"https://json-schema.org/draft/2020-12/schema\",\"additionalProperties\":false,\"properties\":{\"disposition\":{\"const\":\"fallback\"},\"reason_code\":{\"const\":\"schema-authoritative\"},\"schema_binding_verified\":{\"const\":true}},\"required\":[\"disposition\",\"reason_code\",\"schema_binding_verified\"],\"type\":\"object\",\"x-urusilla-required-disposition\":\"fallback\",\"x-urusilla-semantic-padding\":\"0000000000\"}","media_type":"application/schema+json","uri":"urn:urusilla:eval:spc:4d72b6a9:1"}],"pinned_registry":[{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:58107e477b41dd2e9e3de44b98c87c84301d5cd2f94af23fc117a10454f0a64e","uri":"urn:urusilla:eval:spc:4d72b6a9:1"},{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:2ffa085f83ee7d7a350db594a02799efd211907db05bb7f44257bd1773b8a485","uri":"urn:urusilla:eval:spc:e1c509f3:1"}],"precedence_policy":{"resolved_exact_schema_overrides_inline":true,"unavailable_schema_uses_inline_fallback":true},"query":{"schema_binding":{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:58107e477b41dd2e9e3de44b98c87c84301d5cd2f94af23fc117a10454f0a64e","uri":"urn:urusilla:eval:spc:4d72b6a9:1"},"schema_reference":"urn:urusilla:eval:spc:4d72b6a9:1"},"response_contract":{"canonical_json_only":true,"fields":["disposition","reason_code","schema_binding_verified"],"no_external_effect":true,"resolution_table":[{"condition":"resolved-exact","disposition_source":"resolved_schema.properties.disposition.const","reason_code":"schema-authoritative","schema_binding_verified":true},{"condition":"resource-unavailable","disposition":"fallback","reason_code":"schema-resource-unavailable","schema_binding_verified":false}],"rule":"Match the condition from supplied bytes. For resolved-exact, read disposition from the resolved schema path named by disposition_source. For resource-unavailable, use the literal row. Do not infer semantics from URI text, registry position, context ID, or resource presence alone."},"task":"select-the-authoritative-non-effectful-response-disposition"}'''
_PREIMAGE_06 = r'''{"context_binding":{"context_id":"ctx-a95307de","cross_cell_conversation":false,"cross_cell_memory":false,"fresh_independent_context":true,"parent_context_id":null},"format":"urusilla-schema-precedence-conflict-request/3","inline_constraint":{"fallback_allowed":true,"fallback_mode":"json","on_schema_unavailable":"fallback"},"local_resources":[{"content_utf8":"{\"$id\":\"urn:urusilla:eval:spc:e1c509f3:1\",\"$schema\":\"https://json-schema.org/draft/2020-12/schema\",\"additionalProperties\":false,\"properties\":{\"disposition\":{\"const\":\"strict-refuse\"},\"reason_code\":{\"const\":\"schema-authoritative\"},\"schema_binding_verified\":{\"const\":true}},\"required\":[\"disposition\",\"reason_code\",\"schema_binding_verified\"],\"type\":\"object\",\"x-urusilla-required-disposition\":\"strict-refuse\",\"x-urusilla-semantic-padding\":\"\"}","media_type":"application/schema+json","uri":"urn:urusilla:eval:spc:e1c509f3:1"}],"pinned_registry":[{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:58107e477b41dd2e9e3de44b98c87c84301d5cd2f94af23fc117a10454f0a64e","uri":"urn:urusilla:eval:spc:4d72b6a9:1"},{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:2ffa085f83ee7d7a350db594a02799efd211907db05bb7f44257bd1773b8a485","uri":"urn:urusilla:eval:spc:e1c509f3:1"}],"precedence_policy":{"resolved_exact_schema_overrides_inline":true,"unavailable_schema_uses_inline_fallback":true},"query":{"schema_binding":{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:2ffa085f83ee7d7a350db594a02799efd211907db05bb7f44257bd1773b8a485","uri":"urn:urusilla:eval:spc:e1c509f3:1"},"schema_reference":"urn:urusilla:eval:spc:e1c509f3:1"},"response_contract":{"canonical_json_only":true,"fields":["disposition","reason_code","schema_binding_verified"],"no_external_effect":true,"resolution_table":[{"condition":"resolved-exact","disposition_source":"resolved_schema.properties.disposition.const","reason_code":"schema-authoritative","schema_binding_verified":true},{"condition":"resource-unavailable","disposition":"fallback","reason_code":"schema-resource-unavailable","schema_binding_verified":false}],"rule":"Match the condition from supplied bytes. For resolved-exact, read disposition from the resolved schema path named by disposition_source. For resource-unavailable, use the literal row. Do not infer semantics from URI text, registry position, context ID, or resource presence alone."},"task":"select-the-authoritative-non-effectful-response-disposition"}'''
_PREIMAGE_07 = r'''{"context_binding":{"context_id":"ctx-18e6b2c9","cross_cell_conversation":false,"cross_cell_memory":false,"fresh_independent_context":true,"parent_context_id":null},"format":"urusilla-schema-precedence-conflict-request/3","inline_constraint":{"fallback_allowed":true,"fallback_mode":"json","on_schema_unavailable":"fallback"},"local_resources":[],"pinned_registry":[{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:58107e477b41dd2e9e3de44b98c87c84301d5cd2f94af23fc117a10454f0a64e","uri":"urn:urusilla:eval:spc:4d72b6a9:1"},{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:2ffa085f83ee7d7a350db594a02799efd211907db05bb7f44257bd1773b8a485","uri":"urn:urusilla:eval:spc:e1c509f3:1"}],"precedence_policy":{"resolved_exact_schema_overrides_inline":true,"unavailable_schema_uses_inline_fallback":true},"query":{"schema_binding":{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:58107e477b41dd2e9e3de44b98c87c84301d5cd2f94af23fc117a10454f0a64e","uri":"urn:urusilla:eval:spc:4d72b6a9:1"},"schema_reference":"urn:urusilla:eval:spc:4d72b6a9:1"},"response_contract":{"canonical_json_only":true,"fields":["disposition","reason_code","schema_binding_verified"],"no_external_effect":true,"resolution_table":[{"condition":"resolved-exact","disposition_source":"resolved_schema.properties.disposition.const","reason_code":"schema-authoritative","schema_binding_verified":true},{"condition":"resource-unavailable","disposition":"fallback","reason_code":"schema-resource-unavailable","schema_binding_verified":false}],"rule":"Match the condition from supplied bytes. For resolved-exact, read disposition from the resolved schema path named by disposition_source. For resource-unavailable, use the literal row. Do not infer semantics from URI text, registry position, context ID, or resource presence alone."},"task":"select-the-authoritative-non-effectful-response-disposition"}'''
_PREIMAGE_08 = r'''{"context_binding":{"context_id":"ctx-c47d350a","cross_cell_conversation":false,"cross_cell_memory":false,"fresh_independent_context":true,"parent_context_id":null},"format":"urusilla-schema-precedence-conflict-request/3","inline_constraint":{"fallback_allowed":true,"fallback_mode":"json","on_schema_unavailable":"fallback"},"local_resources":[],"pinned_registry":[{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:58107e477b41dd2e9e3de44b98c87c84301d5cd2f94af23fc117a10454f0a64e","uri":"urn:urusilla:eval:spc:4d72b6a9:1"},{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:2ffa085f83ee7d7a350db594a02799efd211907db05bb7f44257bd1773b8a485","uri":"urn:urusilla:eval:spc:e1c509f3:1"}],"precedence_policy":{"resolved_exact_schema_overrides_inline":true,"unavailable_schema_uses_inline_fallback":true},"query":{"schema_binding":{"bytes":437,"media_type":"application/schema+json","sha256":"sha256:2ffa085f83ee7d7a350db594a02799efd211907db05bb7f44257bd1773b8a485","uri":"urn:urusilla:eval:spc:e1c509f3:1"},"schema_reference":"urn:urusilla:eval:spc:e1c509f3:1"},"response_contract":{"canonical_json_only":true,"fields":["disposition","reason_code","schema_binding_verified"],"no_external_effect":true,"resolution_table":[{"condition":"resolved-exact","disposition_source":"resolved_schema.properties.disposition.const","reason_code":"schema-authoritative","schema_binding_verified":true},{"condition":"resource-unavailable","disposition":"fallback","reason_code":"schema-resource-unavailable","schema_binding_verified":false}],"rule":"Match the condition from supplied bytes. For resolved-exact, read disposition from the resolved schema path named by disposition_source. For resource-unavailable, use the literal row. Do not infer semantics from URI text, registry position, context ID, or resource presence alone."},"task":"select-the-authoritative-non-effectful-response-disposition"}'''

_PREIMAGES = (_PREIMAGE_01, _PREIMAGE_02, _PREIMAGE_03, _PREIMAGE_04, _PREIMAGE_05, _PREIMAGE_06, _PREIMAGE_07, _PREIMAGE_08,)
_PREIMAGE_SHA256 = ('sha256:41b9382f9a7906e8460bfa575daa92ac4e4e264c65904d1dc19a42cbf1531b50', 'sha256:661966b27dad1981f216ef1398ae9803b6209e7e42ea4825c058a795b2d18e0f', 'sha256:6cb23c6f4cb680d8da6cdb2a308186cf21861509aa77cfd1ce3c391be1c657da', 'sha256:d58c8743b01040b366c8f90bc669bf5d4b929471a9524931d50f31eae75f67d9', 'sha256:57ffd6a342e35c9b8ecc502d1eccc7c6e449d6a4202e756cb167c1bb0694d00d', 'sha256:0aed1c0c88f173a04b71ae3223635f45144874334da5075f2555d5e912bb73ce', 'sha256:1ab84faeb57b6d279698a0d945f6b1ce4c4224efdb16135a03518bbd7b22d8d1', 'sha256:a05a68ae0b2f518684b27b665fbd43391a04a83c505841469dea1c44567a4af2')
_CELL_FACTORS = (('cell-01', 'block-0', 'level-0', 0, 'resolved', 'ctx-94a16f2c'), ('cell-02', 'block-0', 'level-1', 1, 'resolved', 'ctx-b730e15a'), ('cell-03', 'block-0', 'level-0', 0, 'unavailable', 'ctx-2c84d9f1'), ('cell-04', 'block-0', 'level-1', 1, 'unavailable', 'ctx-d106a8e7'), ('cell-05', 'block-1', 'level-0', 0, 'resolved', 'ctx-6f21c4b8'), ('cell-06', 'block-1', 'level-1', 1, 'resolved', 'ctx-a95307de'), ('cell-07', 'block-1', 'level-0', 0, 'unavailable', 'ctx-18e6b2c9'), ('cell-08', 'block-1', 'level-1', 1, 'unavailable', 'ctx-c47d350a'))


class SchemaPrecedenceConflictError(ValueError):
    """The frozen plan or supplied raw observation is malformed."""


def _typed_equal(left: object, right: object) -> bool:
    """JSON-tree equality that never treats ``False`` as integer zero."""

    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(
            _typed_equal(left[key], right[key]) for key in left
        )
    if type(left) is list:
        return len(left) == len(right) and all(
            _typed_equal(a, b) for a, b in zip(left, right)
        )
    return left == right


def _exact_keys(value: object, keys: set[str], label: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        raise SchemaPrecedenceConflictError(f"{label} must be an object")
    if set(value) != keys:
        raise SchemaPrecedenceConflictError(
            f"{label} keys must be exactly {sorted(keys)}"
        )
    return value


def _load_canonical_object(text: object, label: str, maximum: int) -> Mapping[str, Any]:
    if type(text) is not str or not text:
        raise SchemaPrecedenceConflictError(f"{label} must be non-empty text")
    try:
        value = strict_json_loads(text, max_bytes=maximum)
    except JsonValidationError as exc:
        raise SchemaPrecedenceConflictError(f"{label} is invalid JSON: {exc}") from exc
    if type(value) is not dict or canonical_json(value) != text:
        raise SchemaPrecedenceConflictError(
            f"{label} must be an exact canonical JSON object"
        )
    return value


def _frozen_plan() -> dict[str, object]:
    cells = [
        {
            "cell_id": cell_id,
            "block_id": block_id,
            "context_id": context_id,
            "registry_position": registry_position,
            "request_preimage": preimage,
            "request_sha256": digest,
            "resource_level": resource_level,
            "schema_level": schema_level,
        }
        for (
            cell_id,
            block_id,
            schema_level,
            registry_position,
            resource_level,
            context_id,
        ), preimage, digest in zip(
            _CELL_FACTORS, _PREIMAGES, _PREIMAGE_SHA256
        )
    ]
    return {
        "schema_version": PLAN_SCHEMA,
        "status": PLAN_STATUS,
        "evidence_boundary": EVIDENCE_BOUNDARY,
        "study_question": (
            "Can this frozen counterbalanced contract distinguish schema-content "
            "responses from identity, availability, and turn-index shortcuts "
            "before any trusted runtime run?"
        ),
        "design": {
            "cell_order": list(CELL_IDS),
            "block_ids": list(BLOCK_IDS),
            "estimand": (
                "both blockwise semantics-oriented difference-in-differences "
                "of strict-refuse indicators"
            ),
            "factor_order": ["block_id", "schema_level", "resource_level"],
            "resource_levels": ["resolved", "unavailable"],
            "schema_levels": ["level-0", "level-1"],
        },
        "execution": {
            "cross_cell_conversation": False,
            "cross_cell_memory": False,
            "execution_order": list(EXECUTION_ORDER),
            "fresh_independent_context_per_cell": True,
            "order_method": "literal-preregistered-randomized-order",
            "runtime_shuffle": False,
        },
        "cells": cells,
        "scoring_rule": {
            "contract_gate": (
                "all eight outputs must be canonical and match their "
                "preimage-derived oracle"
            ),
            "counterbalanced_contract_utility": (
                "one iff both semantics-oriented block DIDs are +1, both "
                "unavailable semantic-label differences are 0, and the "
                "contract gate passes; otherwise zero"
            ),
            "causal_result": (
                "always null until trusted runtime receipts prove execution "
                "order and fresh independent context isolation"
            ),
            "strict_refuse_indicator": {"fallback": 0, "strict-refuse": 1},
        },
        "runtime_execution_order_verified": False,
        "runtime_context_isolation_verified": False,
        "counterbalanced_contract_utility": None,
        "precedence_causal_utility": None,
        "precedence_causal_utility_reason": (
            "runtime-isolation-and-order-receipts-absent"
        ),
        "claim_eligible": False,
        "adoption_evidence": False,
        "conformance_evidence": False,
        "efficiency_evidence": False,
        "general_language_evidence": False,
        "independent_evaluation_evidence": False,
    }


def build_schema_precedence_conflict_plan() -> dict[str, object]:
    """Return a detached copy of the literal, hash-frozen preregistration."""

    return deepcopy(_frozen_plan())


def _derive_request(preimage: str) -> dict[str, object]:
    request = _load_canonical_object(preimage, "request_preimage", 1_048_576)
    _exact_keys(
        request,
        {
            "context_binding",
            "format",
            "inline_constraint",
            "local_resources",
            "pinned_registry",
            "precedence_policy",
            "query",
            "response_contract",
            "task",
        },
        "request_preimage",
    )
    if request["format"] != REQUEST_SCHEMA:
        raise SchemaPrecedenceConflictError("request format is not frozen")
    context = _exact_keys(
        request["context_binding"],
        {
            "context_id",
            "cross_cell_conversation",
            "cross_cell_memory",
            "fresh_independent_context",
            "parent_context_id",
        },
        "request.context_binding",
    )
    if type(context["context_id"]) is not str or not context["context_id"]:
        raise SchemaPrecedenceConflictError("context_id must be non-empty text")
    if not _typed_equal(
        {
            "cross_cell_conversation": context["cross_cell_conversation"],
            "cross_cell_memory": context["cross_cell_memory"],
            "fresh_independent_context": context["fresh_independent_context"],
            "parent_context_id": context["parent_context_id"],
        },
        {
            "cross_cell_conversation": False,
            "cross_cell_memory": False,
            "fresh_independent_context": True,
            "parent_context_id": None,
        },
    ):
        raise SchemaPrecedenceConflictError("context isolation is not frozen")
    if not _typed_equal(
        request["inline_constraint"],
        {
            "fallback_allowed": True,
            "fallback_mode": "json",
            "on_schema_unavailable": "fallback",
        },
    ):
        raise SchemaPrecedenceConflictError("inline fallback is not frozen")
    if not _typed_equal(
        request["precedence_policy"],
        {
            "resolved_exact_schema_overrides_inline": True,
            "unavailable_schema_uses_inline_fallback": True,
        },
    ):
        raise SchemaPrecedenceConflictError("precedence policy is not frozen")

    query = _exact_keys(
        request["query"],
        {"schema_binding", "schema_reference"},
        "request.query",
    )
    registry = request["pinned_registry"]
    if type(registry) is not list or len(registry) != 2:
        raise SchemaPrecedenceConflictError("pinned registry must have two rows")
    for index, row in enumerate(registry):
        _exact_keys(
            row,
            {"bytes", "media_type", "sha256", "uri"},
            f"request.pinned_registry[{index}]",
        )
        if type(row["bytes"]) is not int:
            raise SchemaPrecedenceConflictError("registry bytes must be an integer")
        if row["media_type"] != "application/schema+json":
            raise SchemaPrecedenceConflictError("registry media type is invalid")
        uri = row["uri"]
        if type(uri) is not str or _OPAQUE_URI_RE.fullmatch(uri) is None:
            raise SchemaPrecedenceConflictError("schema URI is not opaque")
        if any(word in uri.lower() for word in _SEMANTIC_WORDS):
            raise SchemaPrecedenceConflictError("schema URI leaks semantics")
    binding = query["schema_binding"]
    if type(binding) is not dict:
        raise SchemaPrecedenceConflictError("query schema binding must be an object")
    matching = [row for row in registry if _typed_equal(row, binding)]
    if len(matching) != 1 or query["schema_reference"] != binding["uri"]:
        raise SchemaPrecedenceConflictError("query binding is not exact")
    registry_position = next(
        index for index, row in enumerate(registry) if _typed_equal(row, binding)
    )

    response_contract = _exact_keys(
        request["response_contract"],
        {
            "canonical_json_only",
            "fields",
            "no_external_effect",
            "resolution_table",
            "rule",
        },
        "request.response_contract",
    )
    rows = response_contract["resolution_table"]
    if type(rows) is not list or len(rows) != 2:
        raise SchemaPrecedenceConflictError("resolution table must have two rows")
    table: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        if type(row) is not dict or type(row.get("condition")) is not str:
            raise SchemaPrecedenceConflictError(
                f"resolution table row {index} is invalid"
            )
        if row["condition"] in table:
            raise SchemaPrecedenceConflictError("resolution condition is duplicated")
        table[row["condition"]] = row
    if set(table) != {"resolved-exact", "resource-unavailable"}:
        raise SchemaPrecedenceConflictError("resolution conditions are invalid")

    resources = request["local_resources"]
    if type(resources) is not list or len(resources) > 1:
        raise SchemaPrecedenceConflictError("local_resources must have zero or one row")
    if not resources:
        unavailable = _exact_keys(
            table["resource-unavailable"],
            {
                "condition",
                "disposition",
                "reason_code",
                "schema_binding_verified",
            },
            "resource-unavailable mapping",
        )
        oracle = {
            "disposition": unavailable["disposition"],
            "reason_code": unavailable["reason_code"],
            "schema_binding_verified": unavailable["schema_binding_verified"],
        }
        return {
            "context_id": context["context_id"],
            "registry_position": registry_position,
            "resource_level": "unavailable",
            "schema_uri": binding["uri"],
            "semantic_action": None,
            "oracle": oracle,
        }

    resource = _exact_keys(
        resources[0],
        {"content_utf8", "media_type", "uri"},
        "request.local_resources[0]",
    )
    if resource["uri"] != binding["uri"] or resource["media_type"] != binding[
        "media_type"
    ]:
        raise SchemaPrecedenceConflictError("resource identity does not match binding")
    content = resource["content_utf8"]
    if type(content) is not str:
        raise SchemaPrecedenceConflictError("schema content must be text")
    raw = content.encode("utf-8")
    if type(binding["bytes"]) is not int:
        raise SchemaPrecedenceConflictError("binding bytes must be an integer")
    if len(raw) != binding["bytes"] or (
        "sha256:" + hashlib.sha256(raw).hexdigest() != binding["sha256"]
    ):
        raise SchemaPrecedenceConflictError("schema bytes do not match binding")
    schema = _load_canonical_object(content, "resolved schema", 64_000)
    if schema.get("$id") != binding["uri"]:
        raise SchemaPrecedenceConflictError("resolved schema ID does not match")
    try:
        semantic_action = schema["properties"]["disposition"]["const"]
    except (KeyError, TypeError) as exc:
        raise SchemaPrecedenceConflictError(
            "resolved schema has no disposition const"
        ) from exc
    if type(semantic_action) is not str or semantic_action not in {
        "strict-refuse",
        "fallback",
    }:
        raise SchemaPrecedenceConflictError("resolved schema action is invalid")
    resolved = _exact_keys(
        table["resolved-exact"],
        {
            "condition",
            "disposition_source",
            "reason_code",
            "schema_binding_verified",
        },
        "resolved-exact mapping",
    )
    if resolved["disposition_source"] != (
        "resolved_schema.properties.disposition.const"
    ):
        raise SchemaPrecedenceConflictError("disposition source is invalid")
    oracle = {
        "disposition": semantic_action,
        "reason_code": resolved["reason_code"],
        "schema_binding_verified": resolved["schema_binding_verified"],
    }
    return {
        "context_id": context["context_id"],
        "registry_position": registry_position,
        "resource_level": "resolved",
        "schema_uri": binding["uri"],
        "semantic_action": semantic_action,
        "oracle": oracle,
    }


def _boundary_flags() -> dict[str, bool]:
    return {
        "claim_eligible": False,
        "adoption_evidence": False,
        "conformance_evidence": False,
        "efficiency_evidence": False,
        "general_language_evidence": False,
        "independent_evaluation_evidence": False,
    }


def validate_schema_precedence_conflict_plan(
    plan: Mapping[str, Any],
) -> dict[str, object]:
    """Validate both counterbalanced 2x2 blocks and literal digests."""

    if type(plan) is not dict or not _typed_equal(plan, _frozen_plan()):
        raise SchemaPrecedenceConflictError(
            "plan differs from the exact typed frozen preregistration"
        )
    plan_digest = sha256_text(canonical_json(plan))
    if plan_digest != FROZEN_PLAN_SHA256:
        raise SchemaPrecedenceConflictError("frozen plan SHA-256 invariant failed")
    derived: dict[str, dict[str, object]] = {}
    for cell, expected_digest in zip(plan["cells"], _PREIMAGE_SHA256):
        if cell["request_sha256"] != expected_digest or sha256_text(
            cell["request_preimage"]
        ) != expected_digest:
            raise SchemaPrecedenceConflictError("preimage SHA-256 invariant failed")
        item = _derive_request(cell["request_preimage"])
        if item["resource_level"] != cell["resource_level"]:
            raise SchemaPrecedenceConflictError("resource factor is not derived")
        if item["context_id"] != cell["context_id"]:
            raise SchemaPrecedenceConflictError("context binding is not derived")
        if item["registry_position"] != cell["registry_position"]:
            raise SchemaPrecedenceConflictError("registry position is not derived")
        derived[cell["cell_id"]] = item

    pairs = (
        ("cell-01", "cell-03"),
        ("cell-02", "cell-04"),
        ("cell-05", "cell-07"),
        ("cell-06", "cell-08"),
    )
    for resolved_id, unavailable_id in pairs:
        if derived[resolved_id]["schema_uri"] != derived[unavailable_id]["schema_uri"]:
            raise SchemaPrecedenceConflictError("availability pair is not URI matched")
        if derived[resolved_id]["registry_position"] != derived[unavailable_id][
            "registry_position"
        ]:
            raise SchemaPrecedenceConflictError(
                "availability pair is not registry-position matched"
            )
    block_actions = {
        "block-0": (
            derived["cell-01"]["semantic_action"],
            derived["cell-02"]["semantic_action"],
        ),
        "block-1": (
            derived["cell-05"]["semantic_action"],
            derived["cell-06"]["semantic_action"],
        ),
    }
    if block_actions != {
        "block-0": ("strict-refuse", "fallback"),
        "block-1": ("fallback", "strict-refuse"),
    }:
        raise SchemaPrecedenceConflictError(
            "schema semantics are not counterbalanced across registry positions"
        )
    resolved_lengths = {
        len(_PREIMAGES[index].encode()) for index in (0, 1, 4, 5)
    }
    unavailable_lengths = {
        len(_PREIMAGES[index].encode()) for index in (2, 3, 6, 7)
    }
    if len(resolved_lengths) != 1 or len(unavailable_lengths) != 1:
        raise SchemaPrecedenceConflictError("preimages are not byte matched by arm")
    for first_id, second_id in (("cell-03", "cell-04"), ("cell-07", "cell-08")):
        if not _typed_equal(derived[first_id]["oracle"], derived[second_id]["oracle"]):
            raise SchemaPrecedenceConflictError(
                "unavailable oracle differs by opaque identity"
            )
    contexts = [cell["context_id"] for cell in plan["cells"]]
    if len(set(contexts)) != len(CELL_IDS):
        raise SchemaPrecedenceConflictError("contexts are not unique per cell")
    if plan["execution"]["execution_order"] != list(EXECUTION_ORDER):
        raise SchemaPrecedenceConflictError("execution order is not literal frozen order")

    return {
        "schema_version": SCORE_SCHEMA,
        "evidence_boundary": EVIDENCE_BOUNDARY,
        "plan_sha256": plan_digest,
        "cell_resource_levels": {
            cell_id: derived[cell_id]["resource_level"] for cell_id in CELL_IDS
        },
        "resolved_schema_actions": {
            cell_id: derived[cell_id]["semantic_action"]
            for cell_id in ("cell-01", "cell-02", "cell-05", "cell-06")
        },
        "execution_order": list(EXECUTION_ORDER),
        "execution_order_contract_verified": True,
        "fresh_independent_context_contract_verified": True,
        "runtime_execution_order_verified": False,
        "runtime_context_isolation_verified": False,
        "exact_preimages_verified": True,
        "observations_scored": 0,
        "block_difference_in_differences": {block_id: None for block_id in BLOCK_IDS},
        "counterbalanced_contract_utility": None,
        "precedence_causal_utility": None,
        "precedence_causal_utility_reason": (
            "runtime-isolation-and-order-receipts-absent"
        ),
        **_boundary_flags(),
    }


def expected_output_text(cell_id: str) -> str:
    """Derive exact output solely from the cell's visible preimage."""

    if cell_id not in CELL_IDS:
        raise SchemaPrecedenceConflictError("cell_id is invalid")
    return canonical_json(
        _derive_request(_PREIMAGES[CELL_IDS.index(cell_id)])["oracle"]
    )


def _parse_observed_output(
    output_text: object,
) -> tuple[dict[str, object] | None, str | None]:
    if type(output_text) is not str or not output_text:
        return None, "output-not-nonempty-text"
    try:
        output = strict_json_loads(output_text, max_bytes=MAX_OUTPUT_BYTES)
    except JsonValidationError:
        return None, "output-invalid-json"
    if type(output) is not dict or canonical_json(output) != output_text:
        return None, "output-not-canonical-object"
    if set(output) != {
        "disposition",
        "reason_code",
        "schema_binding_verified",
    }:
        return None, "output-fields-invalid"
    if type(output["disposition"]) is not str or output["disposition"] not in {
        "strict-refuse",
        "fallback",
    }:
        return None, "output-disposition-invalid"
    if type(output["reason_code"]) is not str or not output["reason_code"]:
        return None, "output-reason-invalid"
    if type(output["schema_binding_verified"]) is not bool:
        return None, "output-binding-verdict-invalid"
    return output, None


def _safe_text_digest(value: object) -> str | None:
    if type(value) is not str:
        return None
    try:
        return sha256_text(value)
    except JsonValidationError:
        return None


def score_schema_precedence_conflict(
    plan: Mapping[str, Any], observation: Mapping[str, Any]
) -> dict[str, object]:
    """Score raw outputs with a contract-gated difference-in-differences."""

    validate_schema_precedence_conflict_plan(plan)
    record = _exact_keys(
        observation,
        {"schema_version", "plan_sha256", "observations"},
        "observation",
    )
    if record["schema_version"] != OBSERVATION_SCHEMA:
        raise SchemaPrecedenceConflictError("observation schema_version is invalid")
    if record["plan_sha256"] != FROZEN_PLAN_SHA256:
        raise SchemaPrecedenceConflictError("observation plan_sha256 is invalid")
    rows = record["observations"]
    if type(rows) is not list or len(rows) != len(CELL_IDS):
        raise SchemaPrecedenceConflictError("observation must contain eight rows")

    cells = {cell["cell_id"]: cell for cell in plan["cells"]}
    cell_scores: list[dict[str, object]] = []
    seen: set[str] = set()
    indicators: dict[str, int | None] = {}
    exact_matches: dict[str, bool] = {}
    derived_by_cell: dict[str, dict[str, object]] = {}
    for index, row_value in enumerate(rows):
        row = _exact_keys(
            row_value,
            {"cell_id", "context_id", "request_preimage", "output_text"},
            f"observation.observations[{index}]",
        )
        cell_id = row["cell_id"]
        if type(cell_id) is not str or cell_id not in cells or cell_id in seen:
            raise SchemaPrecedenceConflictError("observation cell_id is invalid")
        if cell_id != EXECUTION_ORDER[index]:
            raise SchemaPrecedenceConflictError(
                "observation rows do not follow preregistered execution order"
            )
        seen.add(cell_id)
        if row["context_id"] != cells[cell_id]["context_id"]:
            raise SchemaPrecedenceConflictError(
                f"{cell_id} context_id does not match fresh frozen context"
            )
        if row["request_preimage"] != cells[cell_id]["request_preimage"]:
            raise SchemaPrecedenceConflictError(
                f"{cell_id} request_preimage does not match frozen bytes"
            )
        derived = _derive_request(row["request_preimage"])
        if derived["context_id"] != row["context_id"]:
            raise SchemaPrecedenceConflictError(
                f"{cell_id} model-visible context binding does not match"
            )
        derived_by_cell[cell_id] = derived
        expected = derived["oracle"]
        observed, parse_error = _parse_observed_output(row["output_text"])
        exact_match = observed is not None and _typed_equal(observed, expected)
        disposition = None if observed is None else observed["disposition"]
        indicator = (
            None
            if disposition is None
            else {"fallback": 0, "strict-refuse": 1}[disposition]
        )
        indicators[cell_id] = indicator
        exact_matches[cell_id] = exact_match
        cell_scores.append(
            {
                "cell_id": cell_id,
                "block_id": cells[cell_id]["block_id"],
                "context_id": row["context_id"],
                "resource_level": derived["resource_level"],
                "expected_output_sha256": sha256_text(canonical_json(expected)),
                "observed_output_sha256": _safe_text_digest(row["output_text"]),
                "observed_disposition": disposition,
                "strict_refuse_indicator": indicator,
                "parse_error": parse_error,
                "exact_match": exact_match,
            }
        )
    if seen != set(CELL_IDS):
        raise SchemaPrecedenceConflictError("observation cell set is incomplete")

    all_actions_parsed = all(indicators[cell_id] is not None for cell_id in CELL_IDS)
    block_scores: dict[str, dict[str, object]] = {}
    if all_actions_parsed:
        for block_id in BLOCK_IDS:
            block_cells = [
                cell for cell in plan["cells"] if cell["block_id"] == block_id
            ]
            resolved_cells = [
                cell for cell in block_cells if cell["resource_level"] == "resolved"
            ]
            strict_cell = next(
                cell
                for cell in resolved_cells
                if derived_by_cell[cell["cell_id"]]["semantic_action"]
                == "strict-refuse"
            )
            fallback_cell = next(
                cell
                for cell in resolved_cells
                if derived_by_cell[cell["cell_id"]]["semantic_action"] == "fallback"
            )
            strict_control = next(
                cell
                for cell in block_cells
                if cell["resource_level"] == "unavailable"
                and cell["schema_level"] == strict_cell["schema_level"]
            )
            fallback_control = next(
                cell
                for cell in block_cells
                if cell["resource_level"] == "unavailable"
                and cell["schema_level"] == fallback_cell["schema_level"]
            )
            resolved_difference = (
                indicators[strict_cell["cell_id"]]
                - indicators[fallback_cell["cell_id"]]
            )
            unavailable_difference = (
                indicators[strict_control["cell_id"]]
                - indicators[fallback_control["cell_id"]]
            )
            did = resolved_difference - unavailable_difference
            position_zero_resolved = next(
                cell for cell in resolved_cells if cell["registry_position"] == 0
            )
            position_one_resolved = next(
                cell for cell in resolved_cells if cell["registry_position"] == 1
            )
            position_zero_control = next(
                cell
                for cell in block_cells
                if cell["resource_level"] == "unavailable"
                and cell["registry_position"] == 0
            )
            position_one_control = next(
                cell
                for cell in block_cells
                if cell["resource_level"] == "unavailable"
                and cell["registry_position"] == 1
            )
            identity_order_did = (
                indicators[position_zero_resolved["cell_id"]]
                - indicators[position_one_resolved["cell_id"]]
                - indicators[position_zero_control["cell_id"]]
                + indicators[position_one_control["cell_id"]]
            )
            block_scores[block_id] = {
                "strict_semantic_cell": strict_cell["cell_id"],
                "fallback_semantic_cell": fallback_cell["cell_id"],
                "resolved_semantic_difference": resolved_difference,
                "unavailable_semantic_label_difference": unavailable_difference,
                "semantics_oriented_difference_in_differences": did,
                "identity_order_difference_in_differences": identity_order_did,
            }
    else:
        block_scores = {
            block_id: {
                "strict_semantic_cell": None,
                "fallback_semantic_cell": None,
                "resolved_semantic_difference": None,
                "unavailable_semantic_label_difference": None,
                "semantics_oriented_difference_in_differences": None,
                "identity_order_difference_in_differences": None,
            }
            for block_id in BLOCK_IDS
        }
    contract_gate_passed = all(exact_matches.values())
    contract_utility = float(
        contract_gate_passed
        and all(
            block_scores[block_id]["resolved_semantic_difference"] == 1
            and block_scores[block_id]["unavailable_semantic_label_difference"] == 0
            and block_scores[block_id][
                "semantics_oriented_difference_in_differences"
            ]
            == 1
            for block_id in BLOCK_IDS
        )
    )
    if not all_actions_parsed:
        contract_zero_reason: str | None = "contract-output-failure"
    elif any(
        block_scores[block_id]["unavailable_semantic_label_difference"] != 0
        for block_id in BLOCK_IDS
    ):
        contract_zero_reason = "unavailable-semantic-label-difference-present"
    elif any(
        block_scores[block_id]["semantics_oriented_difference_in_differences"]
        != 1
        for block_id in BLOCK_IDS
    ):
        contract_zero_reason = "counterbalanced-semantic-effect-missing"
    elif not contract_gate_passed:
        contract_zero_reason = "contract-or-control-failure"
    else:
        contract_zero_reason = None

    cell_scores.sort(key=lambda item: EXECUTION_ORDER.index(item["cell_id"]))
    return {
        "schema_version": SCORE_SCHEMA,
        "evidence_boundary": EVIDENCE_BOUNDARY,
        "plan_sha256": FROZEN_PLAN_SHA256,
        "cell_scores": cell_scores,
        "contract_accuracy": sum(exact_matches.values()) / len(CELL_IDS),
        "contract_gate_passed": contract_gate_passed,
        "execution_order_contract_verified": True,
        "fresh_independent_context_contract_verified": True,
        "runtime_execution_order_verified": False,
        "runtime_context_isolation_verified": False,
        "block_scores": block_scores,
        "block_difference_in_differences": {
            block_id: block_scores[block_id][
                "semantics_oriented_difference_in_differences"
            ]
            for block_id in BLOCK_IDS
        },
        "counterbalanced_contract_utility": contract_utility,
        "counterbalanced_contract_zero_reason": contract_zero_reason,
        "precedence_causal_utility": None,
        "precedence_causal_utility_reason": (
            "runtime-isolation-and-order-receipts-absent"
        ),
        **_boundary_flags(),
    }


__all__ = [
    "BLOCK_IDS",
    "CELL_IDS",
    "EVIDENCE_BOUNDARY",
    "EXECUTION_ORDER",
    "FROZEN_PLAN_SHA256",
    "OBSERVATION_SCHEMA",
    "PLAN_SCHEMA",
    "PLAN_STATUS",
    "SCORE_SCHEMA",
    "SchemaPrecedenceConflictError",
    "build_schema_precedence_conflict_plan",
    "expected_output_text",
    "score_schema_precedence_conflict",
    "validate_schema_precedence_conflict_plan",
]
