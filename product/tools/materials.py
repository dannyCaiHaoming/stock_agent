"""现有资料发现的原生业务接缝；只读来源、实际尝试与精确材料选择。"""
from __future__ import annotations
import copy
import fcntl
import json
import os
from pathlib import Path
from uuid import uuid4

from product.mcp.provenance import parse_timestamp
from product.runtime.hashing import canonical_hash
from product.tools.material_contracts import DISCOVERY_KINDS
from product.tools.research import ResearchAccessError, _read_json, _write_json, _utc_now

POLICY = Path(__file__).resolve().parents[1]/"mcp/live/research-source-policy.json"


def _records(tools):
    directory=tools.root/"materials"
    if directory.is_symlink():
        raise ResearchAccessError("NATIVE_RESEARCH_PATH_UNSAFE")
    return [_read_json(path) for path in directory.glob("attempt-*.json")]


def _verify_record(task, record):
    if (record.get("task_hash") != task["task_hash"]
            or record.get("record_hash") != canonical_hash({k:v for k,v in record.items() if k!="record_hash"})):
        raise ResearchAccessError("NATIVE_MATERIAL_RECORD_BINDING_INVALID")


def _client(tools):
    if getattr(tools,"material_client",None) is not None:
        return tools.material_client
    from product.mcp.live.cache import SnapshotCache
    from product.mcp.live.public_research import OpenAlexResearchClient
    policy=json.loads(POLICY.read_text())["sources"]["openalex"]
    return OpenAlexResearchClient(policy,SnapshotCache(tools.root/"material-cache"),api_key=os.environ.get("OPENALEX_API_KEY"))


def search(tools, *, query):
    return _call(tools,"search",query=query)


def fetch(tools, *, candidate_id):
    return _call(tools,"fetch",candidate_id=candidate_id)


def _call(tools, operation, **arguments):
    task,_gate=tools._authorize()
    if task["capability"] not in DISCOVERY_KINDS or operation not in task["permissions"]:
        raise ResearchAccessError("NATIVE_MATERIAL_SOURCE_ACCESS_FORBIDDEN")
    if operation=="search" and (not isinstance(arguments.get("query"),str) or not 1<=len(arguments["query"].strip())<=240):
        raise ValueError("PUBLIC_RESEARCH_QUERY_INVALID")
    if operation=="fetch" and not isinstance(arguments.get("candidate_id"),str):
        raise ValueError("PUBLIC_RESEARCH_CANDIDATE_INVALID")
    directory=tools.root/"materials"
    if directory.is_symlink():
        raise ResearchAccessError("NATIVE_RESEARCH_PATH_UNSAFE")
    directory.mkdir(mode=0o700,exist_ok=True)
    fd=os.open(directory/".lock",os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"a") as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ResearchAccessError("NATIVE_MATERIAL_REQUEST_BUSY") from exc
        records=_records(tools)
        for record in records:
            _verify_record(task,record)
        policy=json.loads(POLICY.read_text())["sources"]["openalex"]["request_budget"]
        limit=policy["searches_per_security" if operation=="search" else "content_attempts_per_security"]
        if sum(record["operation"]==operation for record in records)>=limit:
            raise ResearchAccessError("NATIVE_MATERIAL_REQUEST_BUDGET_EXHAUSTED")
        candidate=None
        if operation=="fetch":
            candidates=[c for record in records if record["operation"]=="search" and record["status"]=="COMPLETED"
                        for c in record["result"].get("candidates",[]) if c["candidate_id"]==arguments["candidate_id"]]
            if not candidates or any(c!=candidates[0] for c in candidates):
                raise ResearchAccessError("NATIVE_MATERIAL_CANDIDATE_NOT_OBSERVED")
            candidate=candidates[0]
        result,status,error=None,"COMPLETED",None
        try:
            client=_client(tools)
            if operation=="search":
                result=client.search(query=arguments["query"].strip(),security_id=task["security"]["security_id"],decision_cutoff=task["decision_cutoff"])
            else:
                result=client.fetch(candidate)
                if (result.get("verification_status")!="BODY_VERIFIED" or result.get("candidate_id")!=candidate["candidate_id"]
                        or result.get("security_id")!=task["security"]["security_id"]
                        or parse_timestamp(result["published_at"])>parse_timestamp(task["decision_cutoff"])
                        or any(not result.get(k) for k in ("source_id","as_of","retrieved_at"))):
                    raise ValueError("NATIVE_MATERIAL_DOCUMENT_BINDING_INVALID")
        except ValueError as exc:
            error=str(exc).split(":",1)[0]
            if not error or not all(c.isupper() or c.isdigit() or c=="_" for c in error):
                error="PUBLIC_RESEARCH_REQUEST_FAILED"
            status="BLOCKED_CONFIGURATION" if error=="PUBLIC_RESEARCH_CONTENT_API_KEY_REQUIRED" else "SOURCE_LIMITED"
        stamp=_utc_now()
        record={"task_hash":task["task_hash"],"operation":operation,"arguments":arguments,
                "status":status,"failure_code":error,"result":result,
                "source_id":"native-material-attempt:"+task["task_id"],"as_of":stamp,"retrieved_at":stamp}
        record["record_hash"]=canonical_hash(record)
        _write_json(directory/("attempt-"+str(uuid4())+".json"),record)
        tools._record(task,operation,arguments,record)
        return {"status":status,"failure_code":error,"result":copy.deepcopy(result),"record_hash":record["record_hash"]}


def validate_selection(tools, draft):
    task,_gate=tools._authorize()
    kind=task["capability"]
    if kind=="PEER_SELECTION":
        peers={c["candidate_id"]:c for c in task.get("peer_candidates",[])}
        if draft["query_intents"] or draft["status"]=="BLOCKED_CONFIGURATION":
            raise ValueError("RESEARCH_MATERIALS_PEER_SELECTION_INVALID")
        if any(s["candidate_id"] not in peers or s["document_id"] is not None for s in draft["selections"]):
            raise ValueError("RESEARCH_MATERIALS_PEER_SELECTION_INVALID")
        return {"peer_candidates":task.get("peer_candidates",[]),"attempts":[]}
    records=_records(tools)
    for record in records:
        _verify_record(task,record)
    searches=[record for record in records if record["operation"]=="search"]
    if not searches:
        raise ValueError("RESEARCH_MATERIALS_SEARCH_PROOF_MISSING")
    queries={record["arguments"]["query"].strip() for record in searches}
    declared=[item["query"].strip() for item in draft["query_intents"]]
    if len(declared)!=len(set(declared)) or set(declared)!=queries:
        raise ValueError("RESEARCH_MATERIALS_QUERY_INTENT_NOT_EXECUTED")
    documents={record["result"]["document_id"]:record["result"] for record in records
               if record["operation"]=="fetch" and record["status"]=="COMPLETED"}
    for selection in draft["selections"]:
        document=documents.get(selection["document_id"])
        if document is None or document["candidate_id"]!=selection["candidate_id"]:
            raise ValueError("RESEARCH_MATERIALS_DOCUMENT_SELECTION_INVALID")
    blocked=any(record["status"]=="BLOCKED_CONFIGURATION" for record in records)
    if draft["status"]=="READY" and not draft["selections"]:
        raise ValueError("RESEARCH_MATERIALS_READY_WITHOUT_DOCUMENT")
    if draft["status"]=="BLOCKED_CONFIGURATION" and (draft["selections"] or not blocked):
        raise ValueError("RESEARCH_MATERIALS_CONFIGURATION_STATE_INVALID")
    if draft["status"]=="SOURCE_LIMITED" and blocked and not draft["selections"]:
        raise ValueError("RESEARCH_MATERIALS_CONFIGURATION_MASQUERADED_AS_SOURCE_LIMITED")
    if draft["status"]!="READY" and not draft["gaps"]:
        raise ValueError("RESEARCH_MATERIALS_LIMITATION_GAP_REQUIRED")
    return {"attempts":records,"documents":[copy.deepcopy(documents[s["document_id"]]) for s in draft["selections"]]}
