"""研究作者选择已成功计算的公共语义结构。"""

SELECTION_SCHEMA = {
    "type": "array", "uniqueItems": True,
    "items": {"type": "object", "additionalProperties": False,
              "required": ["calculation_ref", "claim_ids"],
              "properties": {
                  "calculation_ref": {"type": "string", "pattern": r"^k\.[0-9a-f]{12}\.[0-9a-f]{24}$"},
                  "claim_ids": {"type": "array", "minItems": 1, "uniqueItems": True,
                                "items": {"type": "string", "minLength": 1}},
              }},
}
