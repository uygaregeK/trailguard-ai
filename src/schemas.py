"""W2.1 — Request Classifier JSON Schema & Deterministic Validation.

Defines the strict JSON schema required by Week 2 Deliverable W2.1:
  - intent: One of the canonical 5 TrailRun TR support intents
  - entities: Extracted exact store identifiers (order_id, sku, tracking, rma)
  - urgency: One of "low", "medium", "high"
"""

from __future__ import annotations

import re
from typing import Any

VALID_INTENTS = {
    "return",
    "order_status",
    "product_question",
    "complaint",
    "other",
}

VALID_URGENCIES = {"low", "medium", "high"}

ENTITY_KEYS = ("order_id", "sku", "tracking", "rma")

ORDER_ID_RE = re.compile(r"^ORD-\d{4}-\d{4,}$")
SKU_RE = re.compile(r"^SKU-[A-Z0-9-]+$")
TRACKING_RE = re.compile(r"^TRK-[A-Z0-9-]+$")
RMA_RE = re.compile(r"^RMA-\d{4}-\d{3,}$")

_ENTITY_PATTERNS: dict[str, tuple[re.Pattern[str], str]] = {
    "order_id": (ORDER_ID_RE, "ORD-YYYY-XXXX"),
    "sku": (SKU_RE, "SKU-..."),
    "tracking": (TRACKING_RE, "TRK-..."),
    "rma": (RMA_RE, "RMA-YYYY-XXX"),
}

_ENTITY_PROP_SCHEMA: dict[str, Any] = {
    "type": ["string", "array", "null"],
    "items": {"type": "string"},
}

CLASSIFIER_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["intent", "entities", "urgency"],
    "properties": {
        "intent": {
            "type": "string",
            "enum": sorted(VALID_INTENTS),
            "description": "Primary support intent of the customer message.",
        },
        "entities": {
            "type": "object",
            "required": list(ENTITY_KEYS),
            "properties": {key: _ENTITY_PROP_SCHEMA for key in ENTITY_KEYS},
        },
        "urgency": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "description": "Urgency level based on race deadlines, damaged gear, or blocked shipment.",
        },
    },
}


def _validate_entity_value(ent_key: str, value: Any) -> list[str]:
    """Validate a single entity field: null, matching string, or non-empty list of matching strings."""
    if value is None:
        return []
    pattern, expected_fmt = _ENTITY_PATTERNS[ent_key]
    if isinstance(value, str):
        if not pattern.match(value):
            return [f"Invalid {ent_key} format: '{value}' (expected {expected_fmt})."]
        return []
    if isinstance(value, list):
        if not value:
            return [f"Invalid {ent_key}: empty list is not allowed; use null instead."]
        errors: list[str] = []
        for idx, item in enumerate(value):
            if not isinstance(item, str) or not pattern.match(item):
                errors.append(
                    f"Invalid {ent_key}[{idx}] format: '{item}' (expected {expected_fmt})."
                )
        return errors
    return [
        f"Invalid {ent_key} type: expected string, non-empty list of strings, or null."
    ]


def validate_classification_payload(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a parsed JSON dictionary against the W2.1 schema.

    Returns:
        (is_valid, error_messages)
    """
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["Payload must be a JSON object."]

    for req_key in ("intent", "entities", "urgency"):
        if req_key not in payload:
            errors.append(f"Missing required top-level key: '{req_key}'.")

    intent = payload.get("intent")
    if intent not in VALID_INTENTS:
        errors.append(
            f"Invalid intent '{intent}'. Must be one of {sorted(VALID_INTENTS)}."
        )

    urgency = payload.get("urgency")
    if urgency not in VALID_URGENCIES:
        errors.append(
            f"Invalid urgency '{urgency}'. Must be one of {sorted(VALID_URGENCIES)}."
        )

    entities = payload.get("entities")
    if not isinstance(entities, dict):
        errors.append("'entities' must be a JSON object.")
    else:
        for ent_key in ENTITY_KEYS:
            if ent_key not in entities:
                errors.append(f"Missing required entity key: 'entities.{ent_key}'.")
            else:
                errors.extend(_validate_entity_value(ent_key, entities.get(ent_key)))

        extra_keys = sorted(set(entities.keys()) - set(ENTITY_KEYS))
        if extra_keys:
            errors.append(f"Unexpected entity keys: {extra_keys}. Allowed: {list(ENTITY_KEYS)}.")

    return len(errors) == 0, errors
