"""W2.1 — Request Classifier JSON Schema & Deterministic Validation.

Defines the strict JSON schema required by Week 2 Deliverable W2.1:
  - intent: One of the canonical TrailRun TR support intents
  - entities: Extracted exact store identifiers (order_id, sku, tracking_number, rma_id)
  - urgency: One of "low", "medium", "high"
"""

from __future__ import annotations

import re
from typing import Any

VALID_INTENTS = {
    "policy_question",
    "order_lookup",
    "return_request",
    "product_comparison",
    "unanswerable_out_of_scope",
    "adversarial_override",
}

VALID_URGENCIES = {"low", "medium", "high"}

ORDER_ID_RE = re.compile(r"^ORD-\d{4}-\d{4,}$")
SKU_RE = re.compile(r"^SKU-[A-Z0-9-]+$")
TRACKING_RE = re.compile(r"^TRK-[A-Z0-9-]+$")
RMA_RE = re.compile(r"^RMA-\d{4}-\d{3,}$")

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
            "required": ["order_id", "sku", "tracking_number", "rma_id"],
            "properties": {
                "order_id": {"type": ["string", "null"]},
                "sku": {"type": ["string", "null"]},
                "tracking_number": {"type": ["string", "null"]},
                "rma_id": {"type": ["string", "null"]},
            },
        },
        "urgency": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "description": "Urgency level based on race deadlines, damaged gear, or blocked shipment.",
        },
    },
}


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
        for ent_key in ("order_id", "sku", "tracking_number", "rma_id"):
            if ent_key not in entities:
                errors.append(f"Missing required entity key: 'entities.{ent_key}'.")

        order_id = entities.get("order_id")
        if order_id is not None and not ORDER_ID_RE.match(str(order_id)):
            errors.append(f"Invalid order_id format: '{order_id}' (expected ORD-YYYY-XXXX).")

        sku = entities.get("sku")
        if sku is not None and not SKU_RE.match(str(sku)):
            errors.append(f"Invalid sku format: '{sku}' (expected SKU-...).")

        trk = entities.get("tracking_number")
        if trk is not None and not TRACKING_RE.match(str(trk)):
            errors.append(f"Invalid tracking_number format: '{trk}' (expected TRK-...).")

        rma = entities.get("rma_id")
        if rma is not None and not RMA_RE.match(str(rma)):
            errors.append(f"Invalid rma_id format: '{rma}' (expected RMA-YYYY-XXX).")

    return len(errors) == 0, errors

