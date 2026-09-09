#!/bin/bash
# 只读检测；原始输出仅保存在调用者指定的本地证据目录。
set -eu
if [ "${1:-}" = "--help" ]; then
  echo '用法：bash detect-host-proxy.sh [本地证据目录]'
  exit 0
fi
evidence_dir=${1:-$(mktemp -d "${TMPDIR:-/tmp}/stock-agent-host-proxy.XXXXXX")}
mkdir -p "$evidence_dir"
evidence_dir=$(cd "$evidence_dir" && pwd -P)
record() {
  local name=$1
  shift
  printf '%s\n' "$*" > "$evidence_dir/$name.command"
  local status=0
  "$@" > "$evidence_dir/$name.stdout" 2> "$evidence_dir/$name.stderr" || status=$?
  printf '%s\n' "$status" > "$evidence_dir/$name.exit"
}
record scutil-proxy scutil --proxy
record services networksetup -listallnetworkservices
record wifi-http networksetup -getwebproxy Wi-Fi
record wifi-https networksetup -getsecurewebproxy Wi-Fi
record wifi-socks networksetup -getsocksfirewallproxy Wi-Fi
record listeners lsof -nP -iTCP -sTCP:LISTEN
grep -Ei 'Shadowrocket|127\.0\.0\.1|localhost' "$evidence_dir/listeners.stdout" > "$evidence_dir/listeners.filtered" || true
record vpn scutil --nc list
record default-route route -n get default
# 使用生效的全局代理，不使用已禁用网络服务中的旧值，不从进程名推测端口。
python3 - "$evidence_dir" <<'PY'
import pathlib, re, sys
root = pathlib.Path(sys.argv[1])
raw = (root / 'scutil-proxy.stdout').read_text()
settings = dict(re.findall(r'^\s*(\w+)\s*:\s*(.*?)\s*$', raw, re.M))
def endpoint(prefix):
    if settings.get(prefix + 'Enable') != '1':
        return None
    host = settings.get(prefix + 'Proxy', '')
    port = settings.get(prefix + 'Port', '')
    if not re.fullmatch(r'[A-Za-z0-9.:-]+', host) or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError('INVALID_ENABLED_PROXY')
    authority = '[' + host + ']' if ':' in host else host
    return host, port, authority + ':' + port
valid = (root / 'scutil-proxy.exit').read_text().strip() == '0'
try:
    http, https, socks = (endpoint(p) for p in ('HTTP', 'HTTPS', 'SOCKS'))
except ValueError:
    http = https = socks = None
    settings = {}
    valid = False
selected = http or https or socks
mode = 'SYSTEM_HTTP_PROXY' if http else 'SYSTEM_HTTPS_PROXY' if https else 'SYSTEM_SOCKS_PROXY' if socks else 'UNKNOWN'
connected = re.search(r'\(Connected\)', (root / 'vpn.stdout').read_text())
tunnel_route = re.search(r'^\s*interface:\s*(utun\d+|tun\d+|ppp\d+)\s*$', (root / 'default-route.stdout').read_text(), re.M)
if not selected and valid and (connected or tunnel_route):
    mode = 'TUN_OR_VPN'
print('PROXY_MODE=' + mode)
print('LOCAL_PROXY_PORT=' + (selected[1] if selected else 'NONE'))
if selected:
    print('PROXY_HOST=' + selected[0])
    print('PROXY_PORT=' + selected[1])
if http or https:
    print('HTTP_PROXY_URL=http://' + (http or https)[2])
    print('HTTPS_PROXY_URL=http://' + (https or http)[2])
elif socks:
    print('ALL_PROXY_URL=socks5h://' + socks[2])
print('PROXY_EVIDENCE_DIR=' + str(root))
PY
