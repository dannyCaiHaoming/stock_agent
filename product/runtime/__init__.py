"""确定性业务支持；仅在显式请求旧发现/候选接口时加载其依赖。"""
from importlib import import_module

from .hashing import canonical_hash, canonical_json, file_hash

__all__ = [
    "ProductDiscovery", "ResourceRecord", "canonical_hash", "canonical_json",
    "discover_product_resources", "file_hash", "load_version_manifest", "validate_version_manifest",
]


def __getattr__(name):
    if name in {"ProductDiscovery", "ResourceRecord", "discover_product_resources"}:
        return getattr(import_module(".discovery", __name__), name)
    if name in {"load_version_manifest", "validate_version_manifest"}:
        return getattr(import_module(".versioning", __name__), name)
    raise AttributeError(name)
