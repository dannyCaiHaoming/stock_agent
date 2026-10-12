"""冻结来源原字节/身份闭包校验；不加载宿主/Stage或发现控制配置。"""
import hashlib
from product.mcp.provenance import content_hash

def validate_raw_records(snapshot: dict, read_object) -> dict[str, bytes]:
    """从引用的内容字节验证；hash 摘要无法替代存在的对象。"""
    objects = {}
    for record in snapshot["raw_records"]:
        if (not isinstance(record, dict) or record.get("schema_version") != "live-cache/1.0.0"
                or record.get("record_hash") != content_hash({k: v for k, v in record.items() if k != "record_hash"})
                or record.get("key_hash") != content_hash(record.get("key"))):
            raise ValueError("LIVE_RAW_RECORD_INVALID")
        digest = record["raw_content_hash"]
        import re
        if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            raise ValueError("LIVE_RAW_HASH_INVALID")
        raw = read_object(digest)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("LIVE_RAW_OBJECT_HASH_MISMATCH")
        objects[digest] = raw
    required = {fact["raw_content_hash"] for fact in snapshot["facts"] if fact["kind"] != "derived"}
    if snapshot.get("schema_version") in ("live-snapshot/3.0.0", "live-snapshot/4.0.0"):
        required.update(p["record"]["raw_content_hash"] for p in snapshot["universe"]["pages"])
    if snapshot.get("identity"):
        required.update(item["raw_content_hash"] for key in ("sec_mapping", "security_metadata")
                        for item in snapshot["identity"][key])
    if not required <= set(objects):
        raise ValueError("LIVE_RAW_EVIDENCE_OBJECT_MISSING")
    if snapshot.get("schema_version") in ("live-snapshot/3.0.0", "live-snapshot/4.0.0"):
        from types import SimpleNamespace
        from product.mcp.live.nasdaq import validate_universe
        validate_universe(snapshot["universe"], SimpleNamespace(read=lambda record: objects[record["raw_content_hash"]]))
    if snapshot.get("identity"):
        from product.mcp.live.security_metadata import METADATA_VERSION, EASTMONEY_METADATA_VERSION, parse_chart_identity, parse_eastmoney_identity, bind_disclosure_security
        for metadata in snapshot["identity"]["security_metadata"]:
            if metadata.get("metadata_version") not in (METADATA_VERSION, EASTMONEY_METADATA_VERSION):
                continue  # 原有合成测试的身份记录；真实入口另要求此版本。
            quote = metadata["quote_identity"]
            if quote["raw_content_hash"] not in objects:
                raise ValueError("LIVE_RAW_IDENTITY_OBJECT_MISSING")
            if metadata["metadata_version"] == EASTMONEY_METADATA_VERSION:
                matching = [r for r in snapshot["raw_records"] if r["raw_content_hash"] == quote["raw_content_hash"]
                            and r["key"].get("provider") == "eastmoney"]
                if len(matching) != 1:
                    raise ValueError("LIVE_RAW_IDENTITY_RECORD_MISSING")
                rebuilt_quote = parse_eastmoney_identity(objects[quote["raw_content_hash"]], ticker=quote["ticker"],
                    exchange=quote["exchange"], record=matching[0])
            else:
                rebuilt_quote = parse_chart_identity(objects[quote["raw_content_hash"]], ticker=quote["ticker"], record={
                "raw_content_hash": quote["raw_content_hash"], "retrieved_at": quote["retrieved_at"],
                "key": {"endpoint": quote["source_locator"]}})
            # metadata.retrieved_at 是两来源最大值；不拿它改写原始披露获取时间。
            source_records = [r for r in snapshot["raw_records"] if r["raw_content_hash"] == metadata["raw_content_hash"]]
            document = dict(metadata, retrieved_at=min((r["retrieved_at"] for r in source_records)))
            if rebuilt_quote != quote or bind_disclosure_security(objects[metadata["raw_content_hash"]], document, rebuilt_quote) != metadata:
                raise ValueError("LIVE_RAW_IDENTITY_BINDING_MISMATCH")
    return objects
