"""两类已实现研究输入的纯验证与绑定，不读取宿主配置。"""
from product.intake.v3 import validate_handoff
from product.runtime.single_stock_input import INPUT_KIND, single_stock_subject, validate_single_stock_request

def is_fixture(value):
    return value.get("input_kind") == "FIXTURE_COUNCIL"


def is_single_stock(value):
    return value.get("input_kind") == INPUT_KIND

def validate_research_input(value, *, historical=False):
    if is_fixture(value):
        from product.tools.fixture_input import validate_fixture_request
        validate_fixture_request(value, require_source=not historical)
    elif is_single_stock(value):
        validate_single_stock_request(value)
    else:
        validate_handoff(value)

def research_subjects(value):
    validate_research_input(value)
    if is_fixture(value):
        from product.tools.fixture_input import fixture_subjects
        return fixture_subjects(value)
    return [single_stock_subject(value)] if is_single_stock(value) else value["portfolio"]["positions"]

def research_input_ref(value):
    if is_fixture(value):
        return "inputs/fixture.json"
    return "audit/single-stock-request.json" if is_single_stock(value) else "audit/portfolio-handoff.json"

def research_input_binding(value, *, historical=False):
    validate_research_input(value, historical=historical)
    if is_single_stock(value) or is_fixture(value):
        return {"input_kind": value["input_kind"], "input_request_id": value["request_id"],
                "input_request_hash": value["request_hash"], "input_artifact_ref": research_input_ref(value)}
    return {key: value[key] for key in ("handoff_id", "handoff_hash", "portfolio_hash")}

def artifact_input_binding(value):
    """已通过各自 Schema 的阶段/报告绑定字段，不重新解释原输入。"""
    keys = ("input_kind", "input_request_id", "input_request_hash", "input_artifact_ref") if is_single_stock(value) else (
        "handoff_id", "handoff_hash", "portfolio_hash")
    return {key: value[key] for key in keys}
