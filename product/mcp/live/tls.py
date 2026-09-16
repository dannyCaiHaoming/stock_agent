"""已有 urllib 适配共用的 TLS 信任加载；不改变代理或全局 SSL 配置。"""
import ssl

CERTIFI_VERSION = "2026.7.22"
TRUST_VERSION = "live-https-trust/1.0.0"


def verified_https_context():
    from importlib.metadata import version
    import certifi
    if version("certifi") != CERTIFI_VERSION:
        raise ValueError("LIVE_CERTIFI_VERSION_MISMATCH")
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context
