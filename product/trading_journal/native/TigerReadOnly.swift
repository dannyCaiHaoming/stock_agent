// Local AX bridge. Never sends screenshots, raw titles, account fields or descriptions.
import Foundation
import AppKit
import ApplicationServices
import CryptoKit

let bundleID = "com.itiger.TigerTrade-Mac"
let installedURL = URL(fileURLWithPath: "/Applications/Tiger Trade.app")
let allowedActions: Set<String> = ["probe", "inspect_layout", "open_app", "navigate_history", "read_history_view", "set_history_window", "read_next_page", "export_history"]
let navigationTargets: Set<String> = ["account_nav", "history", "statement_nav"]

// Labels are a recognition vocabulary, not a navigation profile. A mutation requires
// a profile recorded against the installed version and its observed controls.
let controlNames: [String: Set<String>] = [
    "account_nav": ["账户", "老虎账户", "Account", "Tiger Account"],
    "history": ["历史成交", "成交历史", "交易历史", "交易记录", "成交记录", "订单与成交", "Transactions", "Trade History", "Execution History"],
    "statement_nav": ["账单报表", "账单", "Statements", "Account Statements"],
    "order_history": ["订单历史", "历史订单", "Order History"],
    "sidebar_quotes": ["行情", "Quotes"],
    "sidebar_news": ["资讯", "News"],
    "sidebar_community": ["社区", "Community"],
    "sidebar_trade": ["交易", "Trade"],
    "start_date": ["开始日期", "起始日期", "Start Date", "From Date"],
    "end_date": ["结束日期", "截止日期", "End Date", "To Date"],
    "all_history": ["全部时间", "开户至今", "All Time", "Since Account Open"],
    "query": ["查询", "搜索", "Query", "Search"],
    "next_page": ["下一页", "Next Page", "Next"],
    "export": ["导出CSV", "导出 CSV", "Export CSV"],
    "save_name": ["另存为:", "另存为：", "Save As:", "Save As"],
    "save_confirm": ["存储", "保存", "Save"],
    "login": ["登录", "登入", "Log In", "Login"],
    "danger": ["买入", "卖出", "下单", "确认下单", "撤单", "改单", "行权", "交易解锁", "转账", "换汇", "Buy", "Sell", "Place Order", "Cancel Order", "Modify Order", "Exercise", "Unlock Trading", "Transfer", "Exchange Currency"]
]
let fieldNames: [String: Set<String>] = [
    "occurred_at": ["成交时间", "Execution Time", "Trade Time"],
    "symbol": ["证券代码", "股票代码", "合约代码", "代码", "Symbol", "Contract", "Code"],
    "side": ["买卖方向", "方向", "买卖", "交易方向", "Side", "Buy/Sell", "Direction"],
    "quantity": ["成交数量", "成交量", "Quantity", "Filled Quantity", "Filled Qty"],
    "price": ["成交价格", "成交价", "Price", "Execution Price", "Fill Price"],
    "commission": ["佣金", "Commission"],
    "fee": ["费用", "Fees"],
    "total_fees": ["总费用", "總費用", "Total Fees", "Total Fee"],
    "currency": ["币种", "Currency"],
    "asset_class": ["证券类型", "Asset Type", "Security Type"],
    "execution_id": ["成交编号", "Execution ID", "Trade ID"],
    "order_id": ["委托编号", "Order ID"],
    "market": ["市场", "Market", "Exchange"],
    "underlying": ["标的代码", "Underlying"],
    "expiry": ["到期日", "Expiry", "Expiration"],
    "strike": ["行权价", "Strike"],
    "option_right": ["期权类型", "Call/Put"],
    "multiplier": ["合约乘数", "Multiplier"],
    "position_effect": ["开平仓", "Position Effect"]
]
let requiredFields: Set<String> = ["occurred_at", "symbol", "side", "quantity", "price"]

struct SafeFailure: Error { let code: String }
enum NavigationStage: String {
    case requestValidated = "REQUEST_VALIDATED"
    case observedIdentity = "OBSERVED_IDENTITY_VERIFIED"
    case appActivation = "APP_ACTIVATION_CHECK"
    case refreshedIdentity = "REFRESHED_IDENTITY_VERIFIED"
    case geometry = "SIDEBAR_GEOMETRY_CHECK"
    case hit = "SIDEBAR_HIT_CHECK"
    case finalIdentity = "FINAL_IDENTITY_CHECK"
    case actionIssued = "NAVIGATION_ACTION_ISSUED"
    case postLayout = "POST_LAYOUT_READ"
    case complete = "COMPLETE"
}
struct NavigationAudit {
    var stage: NavigationStage = .requestValidated
    var appActivationRequested = false
    var navigationActionIssued = false
    var safeJSON: [String: Any] { ["stage": stage.rawValue, "app_activation_requested": appActivationRequested,
                                 "navigation_action_issued": navigationActionIssued] }
}
var navAudit: NavigationAudit?
var roleCache: [CFHashCode: [(AXUIElement, String)]] = [:]
var labelCache: [CFHashCode: [(AXUIElement, (String, String)?)]] = [:]
var sidebarValueProfileVerified = false
func fail(_ code: String) throws -> Never { throw SafeFailure(code: code) }
func noSymlinkComponents(_ url: URL) -> Bool {
    // Foundation standardization rewrites /private/var to /var on macOS, whereas
    // Python resolves the /var symlink in the opposite direction. Inspect actual
    // path components rather than treating those aliases as an identity proof.
    guard url.path.hasPrefix("/") else { return false }
    var current = ""
    for component in url.path.split(separator: "/") {
        if component == "." || component == ".." { return false }
        current += "/" + component
        guard let attributes = try? FileManager.default.attributesOfItem(atPath: current),
              attributes[.type] as? FileAttributeType != .typeSymbolicLink else { return false }
    }
    return true
}
func attribute(_ node: AXUIElement, _ name: String) -> CFTypeRef? {
    var value: CFTypeRef?
    return AXUIElementCopyAttributeValue(node, name as CFString, &value) == .success ? value : nil
}
func stringAttribute(_ node: AXUIElement, _ name: String) -> String? {
    attribute(node, name) as? String
}
func elements(_ node: AXUIElement, _ name: String) -> [AXUIElement] {
    attribute(node, name) as? [AXUIElement] ?? []
}
func recognizedLabel(_ node: AXUIElement) -> (String, String)? {
    let hash = CFHash(node)
    if let found = labelCache[hash]?.first(where: { CFEqual($0.0, node) }) { return found.1 }
    func cached(_ value: (String, String)?) -> (String, String)? {
        labelCache[hash, default: []].append((node, value)); return value
    }
    // Only exact known labels leave the process; no AXValue is accessed in
    // discovery. AXDescription is sometimes the native accessible button label.
    var labelAttributes = [kAXTitleAttribute, kAXDescriptionAttribute]
    // Only the positively identified fixed sidebar namespace may expose Value
    // or Help. A balance summary outside it is never read as a string value.
    let staticSafe = nodeRole(node) == "AXStaticText" && sidebarContext(node) != nil
    if staticSafe { labelAttributes += [kAXValueAttribute, kAXHelpAttribute] }
    for attributeName in labelAttributes {
        guard let title = stringAttribute(node, attributeName), title.count < 80 else { continue }
        let exact = title.trimmingCharacters(in: .whitespacesAndNewlines)
        for key in controlNames.keys.sorted() {
            // Value/Help are a fixed navigation vocabulary on known non-data
            // nodes only. Unknown strings are discarded without returning hashes.
            if [kAXValueAttribute, kAXHelpAttribute].contains(attributeName) &&
                !navigationTargets.union(["order_history", "sidebar_quotes", "sidebar_news", "sidebar_community", "sidebar_trade", "login", "danger"]).contains(key) { continue }
            // Buy/Sell in a historical data cell is not an actionable trading control.
            if key == "danger" && !["AXButton", "AXMenuItem", "AXMenuButton"].contains(nodeRole(node)) { continue }
            if controlNames[key]!.contains(exact) { return cached(("control:" + key, exact)) }
        }
        if ![kAXValueAttribute, kAXHelpAttribute].contains(attributeName) {
            for key in fieldNames.keys.sorted() { if fieldNames[key]!.contains(exact) { return cached(("field:" + key, exact)) } }
        }
    }
    return cached(nil)
}
func labelToken(_ node: AXUIElement) -> String? { recognizedLabel(node)?.0 }
func parentElement(_ node: AXUIElement) -> AXUIElement? {
    guard let parent = attribute(node, kAXParentAttribute), CFGetTypeID(parent) == AXUIElementGetTypeID() else { return nil }
    return unsafeBitCast(parent, to: AXUIElement.self)
}
func identityDescriptor(_ node: AXUIElement) -> [String: Any] {
    let ancestors = navigationAncestors(node)
    let chain = ancestors.nodes.map(nodeRole)
    let siblings = parentElement(node).map { elements($0, kAXChildrenAttribute).compactMap { labelToken($0) } } ?? []
    let identifier = stringAttribute(node, kAXIdentifierAttribute) ?? ""
    let hash = SHA256.hash(data: Data(identifier.utf8)).map { String(format: "%02x", $0) }.joined()
    let subrole = stringAttribute(node, kAXSubroleAttribute) ?? ""
    let safeSubroles: Set<String> = ["AXCloseButton", "AXMinimizeButton", "AXZoomButton", "AXToolbarButton", "AXTableRow", "AXUnknown"]
    return ["label_key": recognizedLabel(node)?.1 ?? "", "role": nodeRole(node),
            "subrole": safeSubroles.contains(subrole) ? subrole : "AXUnspecified",
            "identifier_hash": hash, "ancestor_roles": chain, "ancestor_chain_complete": ancestors.complete,
            "adjacent_known_categories": Array(Set(siblings)).sorted()]
}
func descriptorHash(_ descriptor: [String: Any]) -> String {
    let data = try! JSONSerialization.data(withJSONObject: descriptor, options: [.sortedKeys, .withoutEscapingSlashes])
    return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}
func nodeRole(_ node: AXUIElement) -> String {
    let hash = CFHash(node)
    if let found = roleCache[hash]?.first(where: { CFEqual($0.0, node) }) { return found.1 }
    let result = stringAttribute(node, kAXRoleAttribute) ?? "AXUnknown"
    let safe: Set<String> = ["AXApplication", "AXWindow", "AXSheet", "AXDialog", "AXGroup", "AXList", "AXImage", "AXButton", "AXMenuButton", "AXMenu", "AXMenuItem", "AXTable", "AXOutline", "AXRow", "AXColumn", "AXCell", "AXTextField", "AXStaticText", "AXPopUpButton", "AXCheckBox", "AXScrollArea", "AXWebArea", "AXTabGroup", "AXRadioButton", "AXSplitter", "AXToolbar", "AXUnknown"]
    let role = safe.contains(result) ? result : "AXOther"
    roleCache[hash, default: []].append((node, role))
    return role
}
struct Layout {
    let nodes: [AXUIElement]
    let roles: [String: Int]
    let tokens: [String: Int]
    let tokenRoles: [String: Int]
    let candidates: [[String: Any]]
    let truncated: Bool
    var safeJSON: [String: Any] { ["role_counts": roles, "recognized_controls": tokens, "recognized_control_roles": tokenRoles, "navigation_candidates": candidates, "truncated": truncated] }
}
// One layout snapshot owns its identity set. A hash only selects a bucket;
// equality decides identity, so hash collisions never hide another control.
struct LayoutSeen<Node> {
    private var buckets: [UInt: [Node]] = [:]
    func contains(_ node: Node, hash: UInt, equal: (Node, Node) -> Bool) -> Bool {
        buckets[hash]?.contains(where: { equal($0, node) }) ?? false
    }
    mutating func insert(_ node: Node, hash: UInt) { buckets[hash, default: []].append(node) }
}
struct NavigationAncestors<Node> {
    let nodes: [Node]
    let complete: Bool
}
func walkNavigationAncestors<Node>(_ node: Node, hash: (Node) -> UInt,
                                   equal: (Node, Node) -> Bool, parent: (Node) -> Node?) -> NavigationAncestors<Node> {
    var seen = LayoutSeen<Node>(), result: [Node] = []
    seen.insert(node, hash: hash(node))
    var current = parent(node)
    while let ancestor = current {
        let digest = hash(ancestor)
        if result.count >= 64 || seen.contains(ancestor, hash: digest, equal: equal) {
            return NavigationAncestors(nodes: result, complete: false)
        }
        seen.insert(ancestor, hash: digest)
        result.append(ancestor)
        current = parent(ancestor)
    }
    return NavigationAncestors(nodes: result, complete: true)
}
func navigationAncestors(_ node: AXUIElement) -> NavigationAncestors<AXUIElement> {
    walkNavigationAncestors(node, hash: { CFHash($0) }, equal: { CFEqual($0, $1) }, parent: parentElement)
}
func navigationEligible(role: String, ancestorRoles: [String], complete: Bool) -> Bool {
    let nodeRoles: Set<String> = ["AXButton", "AXMenuButton", "AXMenuItem", "AXRadioButton", "AXStaticText", "AXGroup"]
    let parentRoles: Set<String> = ["AXGroup", "AXList", "AXScrollArea", "AXWindow", "AXApplication", "AXToolbar", "AXTabGroup", "AXSplitter", "AXMenu"]
    return complete && nodeRoles.contains(role) && ancestorRoles.last == "AXApplication" &&
        ancestorRoles.filter { $0 == "AXApplication" }.count == 1 &&
        ancestorRoles.filter { $0 == "AXWindow" }.count == 1 &&
        ancestorRoles.allSatisfy { parentRoles.contains($0) }
}
func supportsPress(_ node: AXUIElement) -> Bool {
    var names: CFArray?
    return AXUIElementCopyActionNames(node, &names) == .success &&
        (names as? [String] ?? []).contains(kAXPressAction)
}
func axFrame(_ node: AXUIElement) -> CGRect? {
    guard let position = attribute(node, kAXPositionAttribute),
          let size = attribute(node, kAXSizeAttribute),
          CFGetTypeID(position) == AXValueGetTypeID(), CFGetTypeID(size) == AXValueGetTypeID() else { return nil }
    var origin = CGPoint.zero, dimensions = CGSize.zero
    guard AXValueGetValue(unsafeBitCast(position, to: AXValue.self), .cgPoint, &origin),
          AXValueGetValue(unsafeBitCast(size, to: AXValue.self), .cgSize, &dimensions) else { return nil }
    let frame = CGRect(origin: origin, size: dimensions)
    return finiteFrame(frame) ? frame : nil
}
func finiteFrame(_ frame: CGRect) -> Bool {
    [frame.minX, frame.minY, frame.width, frame.height].allSatisfy { $0.isFinite } &&
        frame.width > 0 && frame.height > 0 && frame.width <= 20000 && frame.height <= 20000
}
func sidebarGeometrySafe(label: CGRect, group: CGRect, window: CGRect) -> Bool {
    finiteFrame(label) && finiteFrame(group) && finiteFrame(window) && window.contains(group) && window.contains(label) &&
        group.contains(CGPoint(x: label.midX, y: label.midY)) && group.width <= 80 && group.height <= 120 &&
        group.minX >= window.minX && group.minX <= window.minX + 10
}
// The observed Group has no AXPress and exposes enabled=false as a structural
// container; the actual fixed sidebar Label and Image must both be enabled.
func sidebarEnabled(label: Bool?, image: Bool?) -> Bool { label == true && image == true }
func sidebarShapeSafe(ancestorRoles: [String], groupRoles: [String], innerRoles: [String], outerRoles: [String]) -> Bool {
    ancestorRoles == ["AXGroup", "AXList", "AXList", "AXScrollArea", "AXWindow", "AXApplication"] &&
        groupRoles.sorted() == ["AXImage", "AXStaticText"] && innerRoles.count == 7 &&
        innerRoles.allSatisfy { $0 == "AXGroup" } && outerRoles == ["AXList"]
}
struct SidebarContext {
    let label: AXUIElement
    let image: AXUIElement
    let group: AXUIElement
    let inner: AXUIElement
    let window: AXUIElement
    let app: AXUIElement
}
func sidebarContext(_ node: AXUIElement) -> SidebarContext? {
    guard sidebarValueProfileVerified, nodeRole(node) == "AXStaticText" else { return nil }
    let ancestors = navigationAncestors(node)
    guard ancestors.complete, ancestors.nodes.count == 6 else { return nil }
    let chain = ancestors.nodes, group = chain[0], inner = chain[1], outer = chain[2], window = chain[4], app = chain[5]
    let groupChildren = elements(group, kAXChildrenAttribute), rows = elements(inner, kAXChildrenAttribute)
    guard sidebarShapeSafe(ancestorRoles: chain.map(nodeRole), groupRoles: groupChildren.map(nodeRole),
                           innerRoles: rows.map(nodeRole), outerRoles: elements(outer, kAXChildrenAttribute).map(nodeRole)),
          elements(outer, kAXChildrenAttribute).first.map({ CFEqual($0, inner) }) == true,
          groupChildren.contains(where: { CFEqual($0, node) }), rows.contains(where: { CFEqual($0, group) }),
          rows.allSatisfy({ elements($0, kAXChildrenAttribute).map(nodeRole).sorted() == ["AXImage", "AXStaticText"] }) else { return nil }
    let windows = elements(app, kAXWindowsAttribute)
    var pid: pid_t = 0
    let main = NSRunningApplication.runningApplications(withBundleIdentifier: bundleID)
    guard windows.count == 1, CFEqual(windows[0], window), AXUIElementGetPid(app, &pid) == .success,
          main.count == 1, main[0].processIdentifier == pid,
          let running = NSRunningApplication(processIdentifier: pid), running.bundleIdentifier == bundleID,
          running.bundleURL?.standardizedFileURL == installedURL.standardizedFileURL,
          let labelFrame = axFrame(node), let groupFrame = axFrame(group), let windowFrame = axFrame(window),
          sidebarGeometrySafe(label: labelFrame, group: groupFrame, window: windowFrame),
          let image = groupChildren.first(where: { nodeRole($0) == "AXImage" }) else { return nil }
    return SidebarContext(label: node, image: image, group: group, inner: inner, window: window, app: app)
}
struct LayoutWalk<Node> {
    let nodes: [Node]
    let truncated: Bool
}
func orderedLayoutChildren<Node>(_ node: Node, role: (Node) -> String,
                                 windows: (Node) -> [Node], children: (Node) -> [Node]) -> [Node] {
    // AXWindows can expose the content independently of AXChildren. Keep every
    // remaining child (including menus and dangerous controls) in this snapshot.
    let ordinary = children(node)
    return role(node) == "AXApplication" ? windows(node) + ordinary : ordinary
}
func walkLayout<Node>(_ root: Node, hash: (Node) -> UInt, equal: (Node, Node) -> Bool,
                      children: (Node) -> [Node], maxNodes: Int = 8000, maxDepth: Int = 20,
                      duration: TimeInterval = 10,
                      now: () -> TimeInterval = { ProcessInfo.processInfo.systemUptime },
                      visit: (Node) -> Void) -> LayoutWalk<Node> {
    var seen = LayoutSeen<Node>(), stack: [(Node, Int)] = [(root, 0)], nodes: [Node] = []
    let deadline = now() + duration
    var truncated = false
    while let (node, depth) = stack.popLast() {
        let identityHash = hash(node)
        // Revisited nodes consume neither the finite budget nor candidate/count
        // slots and are never expanded again, even through another AX attribute.
        if seen.contains(node, hash: identityHash, equal: equal) { continue }
        if nodes.count >= maxNodes || now() > deadline { truncated = true; break }
        seen.insert(node, hash: identityHash)
        nodes.append(node)
        visit(node)
        let next = children(node)
        if depth < maxDepth {
            for child in next.reversed() { stack.append((child, depth + 1)) }
        } else if next.contains(where: { !seen.contains($0, hash: hash($0), equal: equal) }) {
            truncated = true
        }
    }
    return LayoutWalk(nodes: nodes, truncated: truncated)
}
func inspect(_ app: AXUIElement) -> Layout {
    // Cache only within this snapshot. Every post-action check obtains fresh labels.
    roleCache.removeAll(); labelCache.removeAll()
    let installed = try? metadata()
    sidebarValueProfileVerified = installed?["version"] as? String == "9.27.2" &&
        installed?["build"] as? String == "20260908205401"
    var roles: [String: Int] = [:], tokens: [String: Int] = [:], tokenRoles: [String: Int] = [:]
    var candidates: [[String: Any]] = []
    let walk = walkLayout(app, hash: { CFHash($0) }, equal: { CFEqual($0, $1) }, children: {
        orderedLayoutChildren($0, role: nodeRole,
                              windows: { elements($0, kAXWindowsAttribute) },
                              children: { elements($0, kAXChildrenAttribute) })
    }, visit: { node in
        let role = nodeRole(node)
        roles[role, default: 0] += 1
        if let token = labelToken(node) {
            tokens[token, default: 0] += 1
            tokenRoles[token + "@" + role, default: 0] += 1
            if ["control:account_nav", "control:history", "control:statement_nav"].contains(token) {
                var descriptor = identityDescriptor(node)
                descriptor["identity_hash"] = descriptorHash(descriptor)
                descriptor["category"] = token
                descriptor["eligible"] = navigationEligible(role: role,
                    ancestorRoles: descriptor["ancestor_roles"] as? [String] ?? [],
                    complete: descriptor["ancestor_chain_complete"] as? Bool == true)
                descriptor["supports_ax_press"] = supportsPress(node)
                candidates.append(descriptor)
            }
        }
    })
    if walk.truncated {
        candidates = candidates.map { candidate in var rejected = candidate; rejected["eligible"] = false; return rejected }
    }
    return Layout(nodes: walk.nodes, roles: roles, tokens: tokens, tokenRoles: tokenRoles, candidates: candidates, truncated: walk.truncated)
}
func metadata() throws -> [String: Any] {
    guard let bundle = Bundle(url: installedURL), bundle.bundleIdentifier == bundleID else { try fail("APP_NOT_INSTALLED") }
    return ["bundle_id": bundleID,
            "version": bundle.infoDictionary?["CFBundleShortVersionString"] as? String ?? "UNKNOWN",
            "build": bundle.infoDictionary?["CFBundleVersion"] as? String ?? "UNKNOWN",
            "ax_trusted": AXIsProcessTrusted(),
            "running": !NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).isEmpty]
}
func targetApp() throws -> AXUIElement {
    guard AXIsProcessTrusted() else { try fail("AX_PERMISSION_REQUIRED") }
    let matches = NSRunningApplication.runningApplications(withBundleIdentifier: bundleID)
    guard matches.count == 1, let target = matches.first, target.bundleURL?.standardizedFileURL == installedURL.standardizedFileURL else { try fail("APP_IDENTITY_UNCONFIRMED") }
    return AXUIElementCreateApplication(target.processIdentifier)
}
func profileVerified(_ request: [String: Any], _ layout: Layout) throws -> [String: Any] {
    guard let profile = request["profile"] as? [String: Any], profile["verified"] as? Bool == true,
          profile["bundle_id"] as? String == bundleID else { try fail("DESKTOP_PROFILE_UNVERIFIED") }
    let meta = try metadata()
    guard profile["version"] as? String == meta["version"] as? String,
          profile["build"] as? String == meta["build"] as? String else { try fail("APP_VERSION_CHANGED") }
    guard !layout.truncated, (layout.roles["AXWindow"] ?? 0) == 1,
          (layout.roles["AXSheet"] ?? 0) == 0, (layout.roles["AXDialog"] ?? 0) == 0,
          (layout.tokens["control:login"] ?? 0) == 0, (layout.tokens["control:danger"] ?? 0) == 0 else { try fail("PAGE_IDENTITY_UNCONFIRMED") }
    guard let signature = profile["page_signature"] as? [String], !signature.isEmpty,
          signature.allSatisfy({ $0.hasPrefix("control:") || $0.hasPrefix("field:") }),
          signature.allSatisfy({ token in
              if (layout.tokenRoles[token] ?? layout.tokens[token]) == 1 { return true }
              let pieces = token.split(separator: "@", maxSplits: 1).map(String.init)
              guard pieces[0].hasPrefix("control:"),
                    let expected = (profile["control_identity_hashes"] as? [String: String])?[String(pieces[0].dropFirst(8))] else { return false }
              return layout.candidates.filter {
                  $0["category"] as? String == pieces[0] && $0["identity_hash"] as? String == expected &&
                  (pieces.count == 1 || $0["role"] as? String == pieces[1])
              }.count == 1
          }) else { try fail("PAGE_SIGNATURE_MISMATCH") }
    return profile
}
func historyVerified(_ request: [String: Any], _ layout: Layout) throws -> [String: Any] {
    let profile = try profileVerified(request, layout)
    guard (layout.tokens["control:history"] ?? 0) == 1,
          requiredFields.allSatisfy({ (layout.tokens["field:" + $0] ?? 0) > 0 }) else { try fail("HISTORY_PAGE_UNCONFIRMED") }
    return profile
}
func navigateHistory(_ request: [String: Any], _ app: AXUIElement, _ current: Layout) throws -> Layout {
    var layout = current
    let profile = try profileVerified(request, layout)
    if requiredFields.allSatisfy({ (layout.tokens["field:" + $0] ?? 0) > 0 }) { return layout }
    if (layout.tokens["control:history"] ?? 0) == 0 {
        // The sole permitted intermediate navigation is the observed account tab.
        let account = try uniqueControl(layout, "account_nav", roles: ["AXButton", "AXMenuItem", "AXRadioButton"], profile: profile)
        try press(account)
        Thread.sleep(forTimeInterval: 0.3)
        layout = inspect(app)
        _ = try profileVerified(request, layout)
    }
    let history = try uniqueControl(layout, "history", roles: ["AXButton", "AXMenuItem", "AXRadioButton"], profile: profile)
    try press(history)
    Thread.sleep(forTimeInterval: 0.3)
    layout = inspect(app)
    _ = try historyVerified(request, layout)
    return layout
}
func uniqueControl(_ layout: Layout, _ token: String, roles: Set<String>, profile: [String: Any]? = nil) throws -> AXUIElement {
    var matches = layout.nodes.filter { labelToken($0) == "control:" + token && roles.contains(nodeRole($0)) }
    if ["account_nav", "history", "statement_nav"].contains(token) {
        // A column heading named Account is never a navigation tab.
        matches = matches.filter {
            let chain = identityDescriptor($0)["ancestor_roles"] as? [String] ?? []
            return Set(chain).isDisjoint(with: ["AXTable", "AXOutline", "AXRow", "AXCell"])
        }
    }
    if let expected = (profile?["control_identity_hashes"] as? [String: String])?[token] {
        matches = matches.filter { descriptorHash(identityDescriptor($0)) == expected }
    }
    guard matches.count == 1 else { try fail("CONTROL_IDENTITY_UNCONFIRMED") }
    return matches[0]
}
func enabled(_ node: AXUIElement) -> Bool { (attribute(node, kAXEnabledAttribute) as? Bool) == true }
func press(_ node: AXUIElement) throws {
    guard enabled(node), AXUIElementPerformAction(node, kAXPressAction as CFString) == .success else { try fail("CONTROL_ACTION_REJECTED") }
}
func navigationProof(_ request: [String: Any]) throws -> [String: Any] {
    guard let target = request["target"] as? String, navigationTargets.contains(target) else { try fail("NAVIGATION_TARGET_REJECTED") }
    guard let proof = request["nav_proof"] as? [String: Any],
          Set(proof.keys) == ["bundle_id", "version", "build", "identity_hash"],
          proof["bundle_id"] as? String == bundleID else { try fail("NAVIGATION_PROOF_INVALID") }
    for key in ["version", "build"] {
        guard let text = proof[key] as? String,
              text.range(of: #"^[A-Za-z0-9.+_-]{1,80}$"#, options: .regularExpression) != nil else { try fail("NAVIGATION_PROOF_INVALID") }
    }
    guard let digest = proof["identity_hash"] as? String,
          digest.range(of: #"^[a-f0-9]{64}$"#, options: .regularExpression) != nil else { try fail("NAVIGATION_PROOF_INVALID") }
    return proof
}
func navigationLayoutVerified(_ layout: Layout) throws {
    guard !layout.truncated, layout.roles["AXWindow"] == 1,
          (layout.roles["AXSheet"] ?? 0) == 0, (layout.roles["AXDialog"] ?? 0) == 0,
          (layout.tokens["control:login"] ?? 0) == 0, (layout.tokens["control:danger"] ?? 0) == 0 else { try fail("NAVIGATION_PAGE_UNCONFIRMED") }
}
func navigationNode(_ layout: Layout, target: String, proof: [String: Any]) throws -> AXUIElement {
    try navigationLayoutVerified(layout)
    let candidates = layout.candidates.filter { $0["category"] as? String == "control:" + target && $0["eligible"] as? Bool == true }
    guard candidates.count == 1, candidates[0]["identity_hash"] as? String == proof["identity_hash"] as? String else { try fail("NAVIGATION_IDENTITY_UNCONFIRMED") }
    let nodes = layout.nodes.filter { node in
        guard labelToken(node) == "control:" + target else { return false }
        let descriptor = identityDescriptor(node)
        return navigationEligible(role: nodeRole(node), ancestorRoles: descriptor["ancestor_roles"] as? [String] ?? [],
                                  complete: descriptor["ancestor_chain_complete"] as? Bool == true) &&
            descriptorHash(descriptor) == proof["identity_hash"] as? String
    }
    guard nodes.count == 1 else { try fail("NAVIGATION_IDENTITY_UNCONFIRMED") }
    let ancestry = navigationAncestors(nodes[0]), app = try targetApp()
    guard let ancestorApp = ancestry.nodes.last,
          let ancestorWindow = ancestry.nodes.first(where: { nodeRole($0) == "AXWindow" }) else { try fail("NAVIGATION_IDENTITY_UNCONFIRMED") }
    var targetPID: pid_t = 0, nodePID: pid_t = 0, ancestorPID: pid_t = 0
    let windows = elements(app, kAXWindowsAttribute)
    guard AXUIElementGetPid(app, &targetPID) == .success,
          AXUIElementGetPid(nodes[0], &nodePID) == .success,
          AXUIElementGetPid(ancestorApp, &ancestorPID) == .success,
          targetPID == nodePID, targetPID == ancestorPID,
          windows.count == 1, CFEqual(windows[0], ancestorWindow) else { try fail("NAVIGATION_IDENTITY_UNCONFIRMED") }
    return nodes[0]
}
func confirmFixedActivation(pid: pid_t, frontPID: () -> pid_t?, requestActivation: () -> Bool,
                            advance: () -> Void, now: () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }) -> Bool {
    if frontPID() == pid { return true }
    guard requestActivation() else { return false }
    let deadline = now() + 1
    while frontPID() != pid && now() < deadline { advance() }
    return frontPID() == pid
}
func activateFixedApp(_ app: AXUIElement) throws -> pid_t {
    var pid: pid_t = 0
    guard AXUIElementGetPid(app, &pid) == .success,
          let running = NSRunningApplication(processIdentifier: pid), running.bundleIdentifier == bundleID,
          running.bundleURL?.standardizedFileURL == installedURL.standardizedFileURL else { try fail("APP_ACTIVATION_UNVERIFIED") }
    guard confirmFixedActivation(pid: pid, frontPID: { NSWorkspace.shared.frontmostApplication?.processIdentifier },
          requestActivation: { navAudit?.appActivationRequested = true; return running.activate(options: []) },
          advance: { _ = RunLoop.current.run(mode: .default, before: Date(timeIntervalSinceNow: 0.05)) }) else { try fail("APP_ACTIVATION_UNVERIFIED") }
    return pid
}
func cgWindowBoundTo(_ window: AXUIElement, pid: pid_t, point: CGPoint) -> Bool {
    guard let frame = axFrame(window), frame.contains(point),
          let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] else { return false }
    let matches = windows.filter {
        guard ($0[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value == pid,
              ($0[kCGWindowLayer as String] as? NSNumber)?.intValue == 0,
              ($0[kCGWindowAlpha as String] as? NSNumber)?.doubleValue ?? 0 > 0,
              let bounds = $0[kCGWindowBounds as String] as? [String: Any],
              let cgFrame = CGRect(dictionaryRepresentation: bounds as CFDictionary) else { return false }
        return cgFrame == frame
    }
    return matches.count == 1
}
func strictBoolean(_ value: CFTypeRef?) -> Bool? {
    guard let value = value, CFGetTypeID(value) == CFBooleanGetTypeID() else { return nil }
    return CFBooleanGetValue(unsafeBitCast(value, to: CFBoolean.self))
}
func fixedWindowIdentity(role: String, count: Int, appPID: pid_t, windowPID: pid_t,
                         parentPID: pid_t, parentRoles: [String], complete: Bool) -> Bool {
    role == "AXWindow" && count == 1 && appPID > 0 && windowPID == appPID && parentPID == appPID &&
        complete && parentRoles == ["AXApplication"]
}
func verifiedOpenWindow(_ app: AXUIElement) throws -> AXUIElement {
    let windows = elements(app, kAXWindowsAttribute)
    guard windows.count == 1 else { try fail("WINDOW_IDENTITY_UNCONFIRMED") }
    let window = windows[0], ancestry = navigationAncestors(window)
    guard let parent = ancestry.nodes.last else { try fail("WINDOW_IDENTITY_UNCONFIRMED") }
    var appPID: pid_t = 0, windowPID: pid_t = 0, parentPID: pid_t = 0
    guard AXUIElementGetPid(app, &appPID) == .success, AXUIElementGetPid(window, &windowPID) == .success,
          AXUIElementGetPid(parent, &parentPID) == .success,
          fixedWindowIdentity(role: nodeRole(window), count: windows.count, appPID: appPID, windowPID: windowPID,
                              parentPID: parentPID, parentRoles: ancestry.nodes.map(nodeRole), complete: ancestry.complete),
          elements(parent, kAXWindowsAttribute).count == 1,
          elements(parent, kAXWindowsAttribute).first.map({ CFEqual($0, window) }) == true else { try fail("WINDOW_IDENTITY_UNCONFIRMED") }
    return window
}
func requestFixedWindowUnminimize(readMinimized: () -> Bool?, writable: () -> Bool,
                                  writeFalse: () -> Bool) throws -> Bool {
    guard let minimized = readMinimized() else { try fail("WINDOW_MINIMIZED_UNCONFIRMED") }
    if !minimized { return false }
    guard writable() else { try fail("WINDOW_RESTORE_NOT_PERMITTED") }
    guard writeFalse() else { try fail("WINDOW_RESTORE_REJECTED") }
    return true
}
func openedWindowVerified(minimized: Bool?, sameIdentity: Bool, frameMatchesCG: Bool,
                           visible: Bool, frontmost: Bool) -> Bool {
    minimized == false && sameIdentity && frameMatchesCG && visible && frontmost
}
func openFixedWindow(_ app: AXUIElement) throws -> [String: Any] {
    let installed = try metadata()
    guard installed["version"] as? String == "9.27.2", installed["build"] as? String == "20260908205401" else { try fail("WINDOW_PROFILE_UNVERIFIED") }
    let window = try verifiedOpenWindow(app)
    let restored = try requestFixedWindowUnminimize(readMinimized: { strictBoolean(attribute(window, kAXMinimizedAttribute)) },
        writable: {
            var settable: DarwinBoolean = false
            return AXUIElementIsAttributeSettable(window, kAXMinimizedAttribute as CFString, &settable) == .success && settable.boolValue
        }, writeFalse: {
            guard let same = try? verifiedOpenWindow(try targetApp()), CFEqual(same, window),
                  strictBoolean(attribute(same, kAXMinimizedAttribute)) == true else { return false }
            var settable: DarwinBoolean = false
            guard AXUIElementIsAttributeSettable(same, kAXMinimizedAttribute as CFString, &settable) == .success,
                  settable.boolValue else { return false }
            return AXUIElementSetAttributeValue(same, kAXMinimizedAttribute as CFString, kCFBooleanFalse) == .success
        })
    let pid = try activateFixedApp(try targetApp())
    let deadline = ProcessInfo.processInfo.systemUptime + 2
    repeat {
        let freshApp = try targetApp(), freshWindow = try verifiedOpenWindow(freshApp)
        guard CFEqual(freshWindow, window) else { try fail("WINDOW_IDENTITY_CHANGED") }
        let minimized = strictBoolean(attribute(freshWindow, kAXMinimizedAttribute))
        if let frame = axFrame(freshWindow) {
            let visible = cgWindowBoundTo(freshWindow, pid: pid, point: CGPoint(x: frame.midX, y: frame.midY))
            let frontmost = NSWorkspace.shared.frontmostApplication?.processIdentifier == pid
            if openedWindowVerified(minimized: minimized, sameIdentity: true,
                                    frameMatchesCG: visible && axFrame(freshWindow) == frame,
                                    visible: visible, frontmost: frontmost) {
                return ["restored_from_minimized": restored, "same_window_verified": true,
                        "not_minimized_verified": true, "onscreen_verified": true, "frontmost_verified": true]
            }
        }
        _ = RunLoop.current.run(mode: .default, before: Date(timeIntervalSinceNow: 0.05))
    } while ProcessInfo.processInfo.systemUptime < deadline
    try fail("WINDOW_OPEN_UNCONFIRMED")
}
func sidebarPeersVerified(_ context: SidebarContext) -> Bool {
    let tokens = elements(context.inner, kAXChildrenAttribute).compactMap { group in
        elements(group, kAXChildrenAttribute).first(where: { nodeRole($0) == "AXStaticText" }).flatMap(labelToken)
    }
    let required: Set<String> = ["control:sidebar_quotes", "control:sidebar_news", "control:sidebar_community", "control:account_nav", "control:sidebar_trade"]
    return required.allSatisfy { token in tokens.filter { $0 == token }.count == 1 }
}
func sidebarHitVerified(_ context: SidebarContext, point: CGPoint, pid: pid_t) -> Bool {
    let allowed = [context.group, context.label, context.image]
    for app in [context.app, AXUIElementCreateSystemWide()] {
        var hit: AXUIElement?
        guard AXUIElementCopyElementAtPosition(app, Float(point.x), Float(point.y), &hit) == .success, let node = hit,
              allowed.contains(where: { CFEqual($0, node) }) else { return false }
        var hitPID: pid_t = 0
        guard AXUIElementGetPid(node, &hitPID) == .success, hitPID == pid else { return false }
    }
    return true
}
func navigateOnly(_ request: [String: Any], app: AXUIElement, initial: Layout) throws -> [String: Any] {
    let proof = try navigationProof(request), target = request["target"] as! String, meta = try metadata()
    guard proof["version"] as? String == meta["version"] as? String,
          proof["build"] as? String == meta["build"] as? String else { try fail("APP_VERSION_CHANGED") }
    let node = try navigationNode(initial, target: target, proof: proof)
    navAudit?.stage = .observedIdentity
    let pressAvailable = supportsPress(node)
    let initialContext = pressAvailable ? nil : sidebarContext(node)
    var initialFrames: [CGRect] = []
    if !pressAvailable {
        // This fallback is only for the one actually observed account sidebar.
        guard target == "account_nav", meta["version"] as? String == "9.27.2",
              meta["build"] as? String == "20260908205401", let context = initialContext,
              sidebarPeersVerified(context), let label = axFrame(context.label), let group = axFrame(context.group),
              let window = axFrame(context.window) else { try fail("NAVIGATION_METHOD_UNVERIFIED") }
        initialFrames = [label, group, window]
    }
    navAudit?.stage = .appActivation
    let pid = try activateFixedApp(app)
    _ = try targetApp()
    let fresh = inspect(app), current = try navigationNode(fresh, target: target, proof: proof)
    navAudit?.stage = .refreshedIdentity
    let method: String
    if pressAvailable {
        guard supportsPress(current), enabled(current) else { try fail("NAVIGATION_METHOD_UNVERIFIED") }
        navAudit?.stage = .actionIssued; navAudit?.navigationActionIssued = true
        guard AXUIElementPerformAction(current, kAXPressAction as CFString) == .success else { try fail("CONTROL_ACTION_REJECTED") }
        method = "AX_PRESS"
    } else {
        navAudit?.stage = .geometry
        guard let context = sidebarContext(current), sidebarPeersVerified(context),
              let label = axFrame(context.label), let group = axFrame(context.group), let window = axFrame(context.window),
              initialFrames == [label, group, window], sidebarGeometrySafe(label: label, group: group, window: window),
              sidebarEnabled(label: attribute(context.label, kAXEnabledAttribute) as? Bool,
                             image: attribute(context.image, kAXEnabledAttribute) as? Bool) else { try fail("NAVIGATION_GEOMETRY_UNCONFIRMED") }
        let point = CGPoint(x: label.midX, y: label.midY)
        navAudit?.stage = .hit
        guard cgWindowBoundTo(context.window, pid: pid, point: point), sidebarHitVerified(context, point: point, pid: pid),
              CGPreflightPostEventAccess(), let source = CGEventSource(stateID: .combinedSessionState),
              let down = CGEvent(mouseEventSource: source, mouseType: .leftMouseDown, mouseCursorPosition: point, mouseButton: .left),
              let up = CGEvent(mouseEventSource: source, mouseType: .leftMouseUp, mouseCursorPosition: point, mouseButton: .left) else { try fail("NAVIGATION_HIT_UNCONFIRMED") }
        // All evidence is refreshed immediately before the adjacent fixed pair.
        navAudit?.stage = .finalIdentity
        let final = inspect(app)
        _ = try navigationNode(final, target: target, proof: proof)
        guard NSWorkspace.shared.frontmostApplication?.processIdentifier == pid,
              axFrame(context.label) == label, axFrame(context.group) == group, axFrame(context.window) == window,
              !supportsPress(context.group),
              sidebarEnabled(label: attribute(context.label, kAXEnabledAttribute) as? Bool,
                             image: attribute(context.image, kAXEnabledAttribute) as? Bool),
              cgWindowBoundTo(context.window, pid: pid, point: point), sidebarHitVerified(context, point: point, pid: pid) else { try fail("NAVIGATION_HIT_UNCONFIRMED") }
        down.flags = []; up.flags = []
        navAudit?.stage = .actionIssued; navAudit?.navigationActionIssued = true
        down.post(tap: .cghidEventTap); up.post(tap: .cghidEventTap)
        method = "VERIFIED_ACCOUNT_SIDEBAR_CLICK"
    }
    Thread.sleep(forTimeInterval: 0.3)
    navAudit?.stage = .postLayout
    var result = try metadata()
    result["layout"] = inspect(try targetApp()).safeJSON
    result["navigation"] = ["executed_category": target, "method": method]
    navAudit?.stage = .complete
    result["nav_audit"] = navAudit?.safeJSON
    return result
}
func safeCell(_ text: String, field: String) throws -> String {
    let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard value.count <= 120, !value.contains("\n"), !value.contains("\r") else { try fail("UNKNOWN_HISTORY_FORMAT") }
    if value.isEmpty { return value }
    var pattern: String
    switch field {
    case "quantity", "price", "commission", "fee", "total_fees", "strike", "multiplier": pattern = #"^[+-]?([0-9]+|[0-9]{1,3}(,[0-9]{3})+)(\.[0-9]+)?$"#
    case "occurred_at": pattern = #"^[0-9]{4}[-/][0-9]{2}[-/][0-9]{2}([ T][0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]+)?)?([+-][0-9]{2}:[0-9]{2}|Z)?)?$"#
    case "expiry": pattern = #"^[0-9]{4}[-/][0-9]{2}[-/][0-9]{2}$"#
    case "symbol", "underlying": pattern = #"^([0-9]{1,6}(\.[A-Za-z]{1,6})?|[A-Za-z][A-Za-z0-9._ /-]{0,63})$"#
    case "execution_id", "order_id": pattern = #"^[A-Za-z0-9._-]{1,64}$"#
    case "side": pattern = #"^(BUY|SELL|Buy|Sell|买入|卖出)$"#
    case "currency": pattern = #"^[A-Z]{3}$"#
    case "asset_class": pattern = #"^(STOCK|ETF|OPTION|Stock|Option|股票|期权|基金)$"#
    case "market": pattern = #"^[A-Za-z0-9._-]{1,16}$"#
    case "option_right": pattern = #"^(CALL|PUT|Call|Put|C|P|看涨|看跌)$"#
    case "position_effect": pattern = #"^(OPEN|CLOSE|BTO|STC|STO|BTC|Open|Close|开仓|平仓)$"#
    default: try fail("UNKNOWN_HISTORY_FIELD")
    }
    guard value.range(of: pattern, options: .regularExpression) != nil else { try fail("UNKNOWN_HISTORY_FORMAT") }
    return value
}
func cellText(_ cell: AXUIElement, field: String) -> String? {
    if let text = stringAttribute(cell, kAXValueAttribute) { return text }
    if ["quantity", "price", "commission", "fee", "total_fees", "strike", "multiplier"].contains(field),
       let number = attribute(cell, kAXValueAttribute) as? NSNumber { return number.stringValue }
    let readable = elements(cell, kAXChildrenAttribute).filter { ["AXStaticText", "AXTextField"].contains(nodeRole($0)) }
    if readable.count == 1 { return stringAttribute(readable[0], kAXValueAttribute) }
    return nil
}
func historyRows(_ layout: Layout) throws -> [String: Any] {
    var candidates: [(AXUIElement, [String])] = []
    for table in layout.nodes where ["AXTable", "AXOutline"].contains(nodeRole(table)) {
        let columns = elements(table, kAXColumnsAttribute)
        var fields: [String] = []
        for column in columns {
            let direct = labelToken(column)
            // Some native tables expose their column name as a header button.
            // Only exact known header labels are considered, never AXValue.
            let descendants = elements(column, kAXChildrenAttribute)
            let recognized = descendants.compactMap { labelToken($0) }.filter { $0.hasPrefix("field:") }
            let token = direct?.hasPrefix("field:") == true ? direct : (recognized.count == 1 ? recognized[0] : nil)
            guard let token = token, token.hasPrefix("field:") else { fields = []; break }
            fields.append(String(token.dropFirst(6)))
        }
        if requiredFields.isSubset(of: Set(fields)), Set(fields).count == fields.count { candidates.append((table, fields)) }
    }
    guard candidates.count == 1 else { try fail("HISTORY_TABLE_UNCONFIRMED") }
    let (table, fields) = candidates[0]
    let axRows = elements(table, kAXRowsAttribute)
    guard axRows.count <= 5000 else { try fail("PAGE_ROW_LIMIT") }
    var rows: [[String: String]] = []
    for row in axRows {
        let cells = elements(row, kAXChildrenAttribute)
        guard cells.count == fields.count else { try fail("UNKNOWN_HISTORY_FORMAT") }
        var result: [String: String] = [:]
        for (index, cell) in cells.enumerated() {
            // Values are accessed only after app/window/history/table/column validation.
            guard let text = cellText(cell, field: fields[index]) else { try fail("UNKNOWN_HISTORY_FORMAT") }
            result[fields[index]] = try safeCell(text, field: fields[index])
        }
        rows.append(result)
    }
    let serialized = try JSONSerialization.data(withJSONObject: rows, options: [.sortedKeys])
    let digest = SHA256.hash(data: serialized).map { String(format: "%02x", $0) }.joined()
    let nextNodes = layout.nodes.filter { labelToken($0) == "control:next_page" && nodeRole($0) == "AXButton" }
    let endProven = nextNodes.count == 1 && !enabled(nextNodes[0])
    return ["rows": rows, "row_count": rows.count, "page_hash": digest, "end_proven": endProven,
            "fields": fields, "source_kind": "AX_EXECUTION_DETAIL"]
}
func verifyFinancialRequest(_ request: [String: Any]) throws {
    guard let profile = request["profile"] as? [String: Any], let timezone = profile["source_timezone"] as? String,
          TimeZone(identifier: timezone) != nil else { try fail("SOURCE_TIMEZONE_UNVERIFIED") }
    guard let window = request["window"] as? [String: Any],
          let preset = window["preset"] as? String,
          ["week", "month", "half_year", "year", "lifetime", "custom"].contains(preset),
          let end = window["end"] as? String,
          end.range(of: #"^[0-9]{4}-[0-9]{2}-[0-9]{2}T.*(Z|[+-][0-9]{2}:[0-9]{2})$"#, options: .regularExpression) != nil,
          let queryEnd = window["query_end_date"] as? String,
          queryEnd.range(of: #"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"#, options: .regularExpression) != nil else { try fail("WINDOW_CHOICE_REQUIRED") }
    if let queryStart = window["query_start_date"] as? String {
        guard queryStart.range(of: #"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"#, options: .regularExpression) != nil,
              queryStart <= queryEnd else { try fail("INVALID_WINDOW") }
    } else if preset != "lifetime" { try fail("WINDOW_CHOICE_REQUIRED") }
    func parseInstant(_ text: String) -> Date? {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = parser.date(from: text) { return date }
        parser.formatOptions = [.withInternetDateTime]
        return parser.date(from: text)
    }
    let dates = DateFormatter(); dates.dateFormat = "yyyy-MM-dd"
    dates.timeZone = TimeZone(identifier: timezone); dates.locale = Locale(identifier: "en_US_POSIX")
    guard let cutoff = parseInstant(end), dates.string(from: cutoff) == queryEnd else { try fail("CLIENT_WINDOW_BOUNDARY_MISMATCH") }
    if let start = window["start"] as? String {
        guard let instant = parseInstant(start), instant <= cutoff,
              dates.string(from: instant) == window["query_start_date"] as? String else { try fail("CLIENT_WINDOW_BOUNDARY_MISMATCH") }
    } else if preset != "lifetime" { try fail("WINDOW_CHOICE_REQUIRED") }
    guard let rootText = request["private_root"] as? String,
          let expectedHash = request["guard_receipt"] as? String,
          expectedHash.range(of: #"^[a-f0-9]{64}$"#, options: .regularExpression) != nil else { try fail("ISOLATION_RECEIPT_REQUIRED") }
    let root = URL(fileURLWithPath: rootText)
    guard rootText.hasPrefix("/"), root.path.hasSuffix("/product/.private/trading-journal"),
          root.path == rootText, noSymlinkComponents(root) else { try fail("PRIVATE_ROOT_REJECTED") }
    let repository = root.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    let receipt = repository.appendingPathComponent(".codex-local/trading-journal-isolation.json")
    guard noSymlinkComponents(receipt),
          let attributes = try? FileManager.default.attributesOfItem(atPath: receipt.path),
          (attributes[.size] as? NSNumber)?.intValue ?? 65537 <= 65536,
          let bytes = try? Data(contentsOf: receipt),
          let proof = (try? JSONSerialization.jsonObject(with: bytes)) as? [String: Any],
          proof["status"] as? String == "VERIFIED",
          proof["repository_root"] as? String == repository.path else { try fail("ISOLATION_RECEIPT_REQUIRED") }
    let observedHash = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
    guard observedHash == expectedHash else { try fail("ISOLATION_RECEIPT_CHANGED") }
    for directory in [root, root.appendingPathComponent("sources", isDirectory: true)] {
        guard noSymlinkComponents(directory),
              let attrs = try? FileManager.default.attributesOfItem(atPath: directory.path),
              (attrs[.posixPermissions] as? NSNumber)?.intValue == 0o700,
              attrs[.type] as? FileAttributeType == .typeDirectory else { try fail("PRIVATE_ROOT_REJECTED") }
    }
}
func objectHash(_ value: Any) -> String {
    let bytes = try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
    return SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
}
func pageProof(_ request: [String: Any], _ page: [String: Any]) -> [String: Any] {
    ["window_hash": objectHash(request["window"]!), "profile_hash": objectHash(request["profile"]!),
     "page_hash": page["page_hash"]!, "query_refresh_verified": true, "scope_verified": true]
}
func verifyPageProof(_ request: [String: Any]) throws -> String {
    guard let proof = request["page_proof"] as? [String: Any],
          Set(proof.keys) == ["window_hash", "profile_hash", "page_hash", "query_refresh_verified", "scope_verified"],
          proof["window_hash"] as? String == objectHash(request["window"]!),
          proof["profile_hash"] as? String == objectHash(request["profile"]!),
          proof["query_refresh_verified"] as? Bool == true, proof["scope_verified"] as? Bool == true,
          let hash = proof["page_hash"] as? String,
          hash.range(of: #"^[a-f0-9]{64}$"#, options: .regularExpression) != nil else { try fail("PAGE_PROOF_UNVERIFIED") }
    return hash
}
func scopeIsCurrent(_ layout: Layout, _ request: [String: Any]) -> Bool {
    guard let window = request["window"] as? [String: Any] else { return false }
    if window["preset"] as? String == "lifetime", window["query_start_date"] == nil || window["query_start_date"] is NSNull {
        guard let all = try? uniqueControl(layout, "all_history", roles: ["AXButton", "AXRadioButton"]) else { return false }
        return (attribute(all, kAXSelectedAttribute) as? Bool) == true || (attribute(all, kAXValueAttribute) as? Bool) == true
    }
    guard let start = try? uniqueControl(layout, "start_date", roles: ["AXTextField"]),
          let end = try? uniqueControl(layout, "end_date", roles: ["AXTextField"]),
          let expectedStart = window["query_start_date"] as? String, let expectedEnd = window["query_end_date"] as? String else { return false }
    return stringAttribute(start, kAXValueAttribute)?.replacingOccurrences(of: "/", with: "-") == expectedStart &&
           stringAttribute(end, kAXValueAttribute)?.replacingOccurrences(of: "/", with: "-") == expectedEnd
}
func rowsInClientDates(_ page: [String: Any], _ request: [String: Any]) -> Bool {
    guard let rows = page["rows"] as? [[String: String]], let window = request["window"] as? [String: Any],
          let end = window["query_end_date"] as? String,
          let timezone = (request["profile"] as? [String: Any])?["source_timezone"] as? String,
          let zone = TimeZone(identifier: timezone) else { return false }
    let start = window["query_start_date"] as? String
    let formatter = DateFormatter(); formatter.dateFormat = "yyyy-MM-dd"; formatter.timeZone = zone
    formatter.locale = Locale(identifier: "en_US_POSIX")
    let iso = ISO8601DateFormatter()
    return rows.allSatisfy { row in
        guard let raw = row["occurred_at"] else { return false }
        let text = raw.replacingOccurrences(of: "/", with: "-")
        var day = String(text.prefix(10))
        let timestamp = text.replacingOccurrences(of: " ", with: "T")
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let fractional = iso.date(from: timestamp)
        iso.formatOptions = [.withInternetDateTime]
        if let instant = fractional ?? iso.date(from: timestamp) { day = formatter.string(from: instant) }
        return day <= end && (start == nil || day >= start!)
    }
}
struct RefreshTracker {
    let baseline: String
    let requireChange: Bool
    private(set) var samples = 0
    private var candidate = ""
    private var firstAt: TimeInterval = 0
    init(baseline: String, requireChange: Bool) { self.baseline = baseline; self.requireChange = requireChange }
    mutating func observe(hash: String, rangeVerified: Bool, at: TimeInterval) -> Bool {
        guard rangeVerified, requireChange ? hash != baseline : hash == baseline else {
            candidate = ""; samples = 0; return false
        }
        if candidate == hash { samples += 1 } else { candidate = hash; samples = 1; firstAt = at }
        return samples >= 2 && at - firstAt >= 0.4
    }
}
func stableHistoryPage(_ request: [String: Any], _ app: AXUIElement, baseline: String,
                       requireChange: Bool, failureCode: String) throws -> [String: Any] {
    let deadline = ProcessInfo.processInfo.systemUptime + 4
    var tracker = RefreshTracker(baseline: baseline, requireChange: requireChange)
    var rangeConfirmed = false
    while ProcessInfo.processInfo.systemUptime < deadline {
        try verifyFinancialRequest(request)
        let layout = inspect(app)
        _ = try historyVerified(request, layout)
        if scopeIsCurrent(layout, request) {
            let page = try historyRows(layout)
            let hash = page["page_hash"] as! String
            if rowsInClientDates(page, request) {
                rangeConfirmed = true
                if tracker.observe(hash: hash, rangeVerified: true, at: ProcessInfo.processInfo.systemUptime) {
                    try verifyFinancialRequest(request)
                    var result = page
                    result["page_proof"] = pageProof(request, page)
                    result["stable_observations"] = tracker.samples
                    return result
                }
            } else { _ = tracker.observe(hash: hash, rangeVerified: false, at: ProcessInfo.processInfo.systemUptime) }
        } else { _ = tracker.observe(hash: "", rangeVerified: false, at: ProcessInfo.processInfo.systemUptime) }
        Thread.sleep(forTimeInterval: 0.2)
    }
    try fail(rangeConfirmed ? failureCode : "QUERY_RANGE_UNCONFIRMED")
}
func validateRequest(_ request: [String: Any]) throws -> String {
    guard let action = request["action"] as? String, allowedActions.contains(action) else { try fail("ACTION_NOT_ALLOWED") }
    let knownKeys: Set<String> = ["action", "profile", "window", "destination", "private_root", "guard_receipt", "page_proof", "target", "nav_proof"]
    guard Set(request.keys).isSubset(of: knownKeys) else { try fail("ARGUMENT_NOT_ALLOWED") }
    if action == "navigate_history" {
        guard Set(request.keys) == ["action", "target", "nav_proof"] else { try fail("ARGUMENT_NOT_ALLOWED") }
        _ = try navigationProof(request)
    } else if ["probe", "inspect_layout", "open_app"].contains(action) {
        guard Set(request.keys) == ["action"] else { try fail("ARGUMENT_NOT_ALLOWED") }
    } else {
        var expected: Set<String> = ["action", "profile", "window", "private_root", "guard_receipt"]
        if action == "export_history" { expected.insert("destination") }
        if ["read_history_view", "read_next_page", "export_history"].contains(action) { expected.insert("page_proof") }
        guard Set(request.keys) == expected else { try fail("ARGUMENT_NOT_ALLOWED") }
        try verifyFinancialRequest(request)
        if ["read_history_view", "read_next_page", "export_history"].contains(action) { _ = try verifyPageProof(request) }
    }
    return action
}
func run(_ request: [String: Any]) throws -> [String: Any] {
    let action = try validateRequest(request)
    if action == "navigate_history" { navAudit = NavigationAudit() }
    var meta = try metadata()
    if action == "probe" { return meta }
    if action == "open_app" {
        guard AXIsProcessTrusted() else { try fail("AX_PERMISSION_REQUIRED") }
        // Fixed application URL only; empty options reuse the existing instance.
        // Opening also applies when it is already running with no visible window;
        // the fresh layout below reports the actual result without promising one.
        do { _ = try NSWorkspace.shared.launchApplication(at: installedURL, options: [], configuration: [:]) }
        catch { try fail("APP_OPEN_FAILED") }
        let app = try targetApp()
        let windowOpen = try openFixedWindow(app)
        meta = try metadata()
        meta["window_open"] = windowOpen
        meta["layout"] = inspect(try targetApp()).safeJSON
        return meta
    }
    let app = try targetApp()
    var layout = inspect(app)
    if action == "inspect_layout" { meta["layout"] = layout.safeJSON; return meta }
    if action == "navigate_history" { return try navigateOnly(request, app: app, initial: layout) }
    guard let profile = request["profile"] as? [String: Any],
          let allowed = profile["actions"] as? [String], allowed.contains(action) else { try fail("DESKTOP_PROFILE_UNVERIFIED") }
    if action == "read_history_view" {
        _ = try historyVerified(request, layout)
        let expectedHash = try verifyPageProof(request)
        return try stableHistoryPage(request, app, baseline: expectedHash, requireChange: false, failureCode: "PAGE_PROOF_CHANGED")
    }
    if action == "set_history_window" {
        // A verified history navigation control may be used before setting dates;
        // With a selected window and isolation proof, the old verified table is
        // hashed locally to witness refresh; its pre-query rows are not returned.
        layout = try navigateHistory(request, app, layout)
        _ = try historyVerified(request, layout)
        try verifyFinancialRequest(request)
        // This old-page hash stays in the isolated process and is used only as a
        // freshness witness. No pre-query rows leave the collector or are saved.
        let baseline = try historyRows(layout)["page_hash"] as! String
        if let window = request["window"] as? [String: Any], window["preset"] as? String == "lifetime",
           window["query_start_date"] == nil || window["query_start_date"] is NSNull {
            // The source's explicit All-Time control avoids inventing an account date.
            // Pagination and official inception reconciliation are still separate.
            let allTime = try uniqueControl(layout, "all_history", roles: ["AXButton", "AXRadioButton"])
            try press(allTime)
            let refreshed = try stableHistoryPage(request, app, baseline: baseline, requireChange: true, failureCode: "QUERY_REFRESH_UNVERIFIED")
            return ["window_set": true, "source_range": "ALL_TIME_VISIBLE", "account_start_known": false,
                    "page_proof": refreshed["page_proof"]!, "stable_observations": refreshed["stable_observations"]!]
        }
        guard let window = request["window"] as? [String: Any],
              let start = window["query_start_date"] as? String,
              let end = window["query_end_date"] as? String,
              [start, end].allSatisfy({ $0.range(of: #"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"#, options: .regularExpression) != nil }) else { try fail("CLIENT_WINDOW_UNSUPPORTED") }
        // All three controls must be present and uniquely identified before any write.
        let startNode = try uniqueControl(layout, "start_date", roles: ["AXTextField"])
        let endNode = try uniqueControl(layout, "end_date", roles: ["AXTextField"])
        let queryNode = try uniqueControl(layout, "query", roles: ["AXButton"])
        for node in [startNode, endNode] {
            var settable: DarwinBoolean = false
            guard enabled(node), AXUIElementIsAttributeSettable(node, kAXValueAttribute as CFString, &settable) == .success, settable.boolValue else { try fail("DATE_CONTROL_NOT_SETTABLE") }
        }
        guard enabled(queryNode) else { try fail("CONTROL_ACTION_REJECTED") }
        guard AXUIElementSetAttributeValue(startNode, kAXValueAttribute as CFString, start as CFString) == .success else { try fail("DATE_SETTING_FAILED") }
        _ = try historyVerified(request, inspect(app))
        guard AXUIElementSetAttributeValue(endNode, kAXValueAttribute as CFString, end as CFString) == .success else { try fail("DATE_SETTING_FAILED") }
        _ = try historyVerified(request, inspect(app))
        // Read-back is local and only compared to the expected dates, never returned.
        guard stringAttribute(startNode, kAXValueAttribute) == start, stringAttribute(endNode, kAXValueAttribute) == end else { try fail("DATE_READBACK_MISMATCH") }
        try press(queryNode)
        let refreshed = try stableHistoryPage(request, app, baseline: baseline, requireChange: true, failureCode: "QUERY_REFRESH_UNVERIFIED")
        return ["window_set": true, "page_proof": refreshed["page_proof"]!, "stable_observations": refreshed["stable_observations"]!]
    }
    _ = try historyVerified(request, layout)
    if action == "read_next_page" {
        let previousHash = try verifyPageProof(request)
        let previousPage = try historyRows(layout)
        guard scopeIsCurrent(layout, request), rowsInClientDates(previousPage, request),
              previousPage["page_hash"] as? String == previousHash else { try fail("PAGE_PROOF_CHANGED") }
        let next = try uniqueControl(layout, "next_page", roles: ["AXButton"])
        if !enabled(next) {
            var result = try stableHistoryPage(request, app, baseline: previousHash, requireChange: false, failureCode: "PAGE_PROOF_CHANGED")
            result["end_proven"] = true; result["terminal_without_page"] = true
            return result
        }
        try press(next)
        return try stableHistoryPage(request, app, baseline: previousHash, requireChange: true, failureCode: "PAGE_REFRESH_UNVERIFIED")
    }
    if action == "export_history" {
        let expectedHash = try verifyPageProof(request)
        _ = try stableHistoryPage(request, app, baseline: expectedHash, requireChange: false, failureCode: "PAGE_PROOF_CHANGED")
        layout = inspect(app)
        _ = try historyVerified(request, layout)
        guard scopeIsCurrent(layout, request) else { try fail("QUERY_RANGE_UNCONFIRMED") }
        guard let rootText = request["private_root"] as? String,
              let destinationText = request["destination"] as? String else { try fail("EXPORT_PATH_REJECTED") }
        let root = URL(fileURLWithPath: rootText)
        let destination = URL(fileURLWithPath: destinationText)
        let sourceDirectory = root.appendingPathComponent("sources", isDirectory: true)
        let rootMode = (try? FileManager.default.attributesOfItem(atPath: root.path)[.posixPermissions] as? NSNumber)?.intValue
        let sourceMode = (try? FileManager.default.attributesOfItem(atPath: sourceDirectory.path)[.posixPermissions] as? NSNumber)?.intValue
        guard root.path.hasSuffix("/product/.private/trading-journal"), rootMode == 0o700, sourceMode == 0o700,
              destination.deletingLastPathComponent().path == sourceDirectory.path,
              destination.lastPathComponent.range(of: #"^export-[a-f0-9]{32}\.csv$"#, options: .regularExpression) != nil,
              noSymlinkComponents(root), noSymlinkComponents(sourceDirectory),
              !FileManager.default.fileExists(atPath: destination.path) else { try fail("EXPORT_PATH_REJECTED") }
        let export = try uniqueControl(layout, "export", roles: ["AXButton"])
        try press(export)
        Thread.sleep(forTimeInterval: 0.3)
        let dialogLayout = inspect(app)
        let sheets = dialogLayout.nodes.filter { ["AXSheet", "AXDialog"].contains(nodeRole($0)) }
        guard sheets.count == 1, !dialogLayout.truncated,
              (dialogLayout.tokens["control:danger"] ?? 0) == 0 else { try fail("EXPORT_DESTINATION_NOT_VERIFIED") }
        let sheet = sheets[0]
        // A preselected folder must be explicitly exposed by the standard panel.
        // No Go-To-Folder shortcut or arbitrary filesystem/UI typing is available.
        let folder = stringAttribute(sheet, kAXURLAttribute) ?? stringAttribute(sheet, kAXDocumentAttribute)
        guard let folderText = folder, let folderURL = URL(string: folderText),
              folderURL.isFileURL, folderURL.standardizedFileURL.path == sourceDirectory.path else { try fail("EXPORT_DESTINATION_NOT_VERIFIED") }
        let safeDialog = inspect(sheet)
        let name = try uniqueControl(safeDialog, "save_name", roles: ["AXTextField"])
        let save = try uniqueControl(safeDialog, "save_confirm", roles: ["AXButton"])
        var settable: DarwinBoolean = false
        guard enabled(name), enabled(save),
              AXUIElementIsAttributeSettable(name, kAXValueAttribute as CFString, &settable) == .success,
              settable.boolValue else { try fail("EXPORT_DESTINATION_NOT_VERIFIED") }
        guard AXUIElementSetAttributeValue(name, kAXValueAttribute as CFString, destination.lastPathComponent as CFString) == .success,
              stringAttribute(name, kAXValueAttribute) == destination.lastPathComponent else { try fail("EXPORT_DESTINATION_NOT_VERIFIED") }
        // Validate app identity and same dialog immediately before saving.
        _ = try targetApp()
        guard (inspect(app).roles["AXSheet"] ?? 0) + (inspect(app).roles["AXDialog"] ?? 0) == 1 else { try fail("EXPORT_DESTINATION_NOT_VERIFIED") }
        try verifyFinancialRequest(request)
        try press(save)
        let deadline = ProcessInfo.processInfo.systemUptime + 3
        while !FileManager.default.fileExists(atPath: destination.path) && ProcessInfo.processInfo.systemUptime < deadline { Thread.sleep(forTimeInterval: 0.1) }
        guard FileManager.default.fileExists(atPath: destination.path), noSymlinkComponents(destination) else { try fail("EXPORT_FILE_MISSING") }
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: destination.path)
        let raw = try Data(contentsOf: destination)
        guard !raw.isEmpty, raw.count <= 100_000_000 else { try fail("EXPORT_FILE_INVALID") }
        let digest = SHA256.hash(data: raw).map { String(format: "%02x", $0) }.joined()
        // Raw CSV stays local; account columns are never sent through stdout.
        return ["source_hash": digest, "path": destination.path, "byte_count": raw.count,
                "source_kind": "OFFICIAL_CSV", "gaps": []]
    }
    try fail("ACTION_NOT_ALLOWED")
}

#if JOURNAL_WINDOW_OPEN_TEST
// Fixed-window policy runs without an installed application or any AX/CG call.
func windowIdentityFixture(role: String = "AXWindow", count: Int = 1, windowPID: pid_t = 42,
                           parentPID: pid_t = 42, parentRoles: [String] = ["AXApplication"], complete: Bool = true) -> Bool {
    fixedWindowIdentity(role: role, count: count, appPID: 42, windowPID: windowPID, parentPID: parentPID,
                        parentRoles: parentRoles, complete: complete)
}
func restoreRejected(_ minimized: Bool?, writable: Bool, code: String) -> Bool {
    var writes = 0
    do { _ = try requestFixedWindowUnminimize(readMinimized: { minimized }, writable: { writable }, writeFalse: { writes += 1; return true }); return false }
    catch let failure as SafeFailure { return failure.code == code && writes == 0 }
    catch { return false }
}
var windowPolicyResults: [String: Bool] = [
    "strict_true_bool": strictBoolean(kCFBooleanTrue) == true,
    "strict_false_bool": strictBoolean(kCFBooleanFalse) == false,
    "numeric_not_bool": strictBoolean(NSNumber(value: 1)) == nil,
    "string_not_bool": strictBoolean("false" as CFString) == nil,
    "unique_main_window": windowIdentityFixture(),
    "foreign_window_pid_rejected": !windowIdentityFixture(windowPID: 43),
    "foreign_parent_pid_rejected": !windowIdentityFixture(parentPID: 43),
    "multiple_windows_rejected": !windowIdentityFixture(count: 2),
    "non_window_role_rejected": !windowIdentityFixture(role: "AXDialog"),
    "incomplete_parent_rejected": !windowIdentityFixture(complete: false),
    "unknown_parent_rejected": !windowIdentityFixture(parentRoles: ["AXOther", "AXApplication"]),
    "unknown_minimized_stops_no_write": restoreRejected(nil, writable: true, code: "WINDOW_MINIMIZED_UNCONFIRMED"),
    "unwritable_stops_no_write": restoreRejected(true, writable: false, code: "WINDOW_RESTORE_NOT_PERMITTED"),
    "verified_post_restore": openedWindowVerified(minimized: false, sameIdentity: true, frameMatchesCG: true, visible: true, frontmost: true),
    "still_minimized_rejected": !openedWindowVerified(minimized: true, sameIdentity: true, frameMatchesCG: true, visible: true, frontmost: true),
    "unknown_post_minimized_rejected": !openedWindowVerified(minimized: nil, sameIdentity: true, frameMatchesCG: true, visible: true, frontmost: true),
    "changed_identity_rejected": !openedWindowVerified(minimized: false, sameIdentity: false, frameMatchesCG: true, visible: true, frontmost: true),
    "changed_frame_rejected": !openedWindowVerified(minimized: false, sameIdentity: true, frameMatchesCG: false, visible: true, frontmost: true),
    "offscreen_rejected": !openedWindowVerified(minimized: false, sameIdentity: true, frameMatchesCG: true, visible: false, frontmost: true),
    "not_frontmost_rejected": !openedWindowVerified(minimized: false, sameIdentity: true, frameMatchesCG: true, visible: true, frontmost: false),
]
do {
    var writableChecks = 0, writes = 0
    let skipped = try! requestFixedWindowUnminimize(readMinimized: { false }, writable: { writableChecks += 1; return true }, writeFalse: { writes += 1; return true })
    windowPolicyResults["already_unminimized_no_write"] = !skipped && writableChecks == 0 && writes == 0
    let requested = try! requestFixedWindowUnminimize(readMinimized: { true }, writable: { writableChecks += 1; return true }, writeFalse: { writes += 1; return true })
    windowPolicyResults["writable_minimized_requests_one_false"] = requested && writableChecks == 1 && writes == 1
    do {
        _ = try requestFixedWindowUnminimize(readMinimized: { true }, writable: { true }, writeFalse: { false })
        windowPolicyResults["write_failure_rejected"] = false
    } catch let failure as SafeFailure { windowPolicyResults["write_failure_rejected"] = failure.code == "WINDOW_RESTORE_REJECTED" }
    catch { windowPolicyResults["write_failure_rejected"] = false }
}
FileHandle.standardOutput.write(try! JSONSerialization.data(withJSONObject: windowPolicyResults, options: [.sortedKeys]))
#elseif JOURNAL_NAVIGATION_TEST
// Pure navigation policy fixtures. No application, AX or CG event access.
final class SyntheticAncestor {
    let id: Int
    var parent: SyntheticAncestor?
    init(_ id: Int) { self.id = id }
}
let fixedChain = ["AXGroup", "AXList", "AXList", "AXScrollArea", "AXWindow", "AXApplication"]
let labelRect = CGRect(x: 8, y: 407, width: 34, height: 26)
let groupRect = CGRect(x: 0, y: 372, width: 50, height: 60)
let windowRect = CGRect(x: 0, y: 20, width: 900, height: 700)
var navigationPolicyResults: [String: Bool] = [
    "fixed_sidebar_eligible": navigationEligible(role: "AXStaticText", ancestorRoles: fixedChain, complete: true),
    "data_table_same_label_rejected": !navigationEligible(role: "AXStaticText", ancestorRoles: ["AXCell", "AXRow", "AXTable", "AXWindow", "AXApplication"], complete: true),
    "outline_heading_button_rejected": !navigationEligible(role: "AXButton", ancestorRoles: ["AXColumn", "AXOutline", "AXWindow", "AXApplication"], complete: true),
    "input_subtree_rejected": !navigationEligible(role: "AXStaticText", ancestorRoles: ["AXTextField", "AXWindow", "AXApplication"], complete: true),
    "dialog_subtree_rejected": !navigationEligible(role: "AXButton", ancestorRoles: ["AXDialog", "AXWindow", "AXApplication"], complete: true),
    "incomplete_ancestry_rejected": !navigationEligible(role: "AXStaticText", ancestorRoles: fixedChain, complete: false),
    "multiple_window_chain_rejected": !navigationEligible(role: "AXButton", ancestorRoles: ["AXWindow", "AXWindow", "AXApplication"], complete: true),
    "unknown_ancestor_rejected": !navigationEligible(role: "AXButton", ancestorRoles: ["AXOther", "AXWindow", "AXApplication"], complete: true),
    "fixed_sidebar_shape_accepted": sidebarShapeSafe(ancestorRoles: fixedChain, groupRoles: ["AXImage", "AXStaticText"], innerRoles: Array(repeating: "AXGroup", count: 7), outerRoles: ["AXList"]),
    "mixed_sidebar_group_rejected": !sidebarShapeSafe(ancestorRoles: fixedChain, groupRoles: ["AXImage", "AXStaticText", "AXTextField"], innerRoles: Array(repeating: "AXGroup", count: 7), outerRoles: ["AXList"]),
    "extra_sidebar_row_rejected": !sidebarShapeSafe(ancestorRoles: fixedChain, groupRoles: ["AXImage", "AXStaticText"], innerRoles: Array(repeating: "AXGroup", count: 8), outerRoles: ["AXList"]),
    "extra_outer_list_rejected": !sidebarShapeSafe(ancestorRoles: fixedChain, groupRoles: ["AXImage", "AXStaticText"], innerRoles: Array(repeating: "AXGroup", count: 7), outerRoles: ["AXList", "AXList"]),
    "observed_geometry_accepted": sidebarGeometrySafe(label: labelRect, group: groupRect, window: windowRect),
    "off_window_geometry_rejected": !sidebarGeometrySafe(label: labelRect, group: groupRect, window: CGRect(x: 100, y: 20, width: 900, height: 700)),
    "wide_region_rejected": !sidebarGeometrySafe(label: labelRect, group: CGRect(x: 0, y: 372, width: 600, height: 60), window: windowRect),
    "right_side_region_rejected": !sidebarGeometrySafe(label: CGRect(x: 808, y: 407, width: 34, height: 26), group: CGRect(x: 800, y: 372, width: 50, height: 60), window: windowRect),
    "zero_frame_rejected": !sidebarGeometrySafe(label: .zero, group: groupRect, window: windowRect),
    "nonfinite_frame_rejected": !finiteFrame(CGRect(x: CGFloat.infinity, y: 0, width: 50, height: 60)),
    "sidebar_width_limit_rejected": !sidebarGeometrySafe(label: labelRect, group: CGRect(x: 0, y: 372, width: 81, height: 60), window: windowRect),
    "sidebar_offset_limit_rejected": !sidebarGeometrySafe(label: CGRect(x: 19, y: 407, width: 34, height: 26), group: CGRect(x: 11, y: 372, width: 50, height: 60), window: windowRect),
    "positive_enabled_accepted": sidebarEnabled(label: true, image: true),
    "missing_enabled_rejected": !sidebarEnabled(label: nil, image: true) && !sidebarEnabled(label: true, image: nil),
    "disabled_sidebar_rejected": !sidebarEnabled(label: false, image: true) && !sidebarEnabled(label: true, image: false),
    "observed_disabled_container_enabled_leaves_accepted": sidebarEnabled(label: true, image: true),
]
do {
    var activationCalls = 0, advances = 0
    let alreadyFront = confirmFixedActivation(pid: 1, frontPID: { 1 }, requestActivation: { activationCalls += 1; return true },
                                              advance: { advances += 1 }, now: { 0 })
    navigationPolicyResults["already_front_does_not_reactivate"] = alreadyFront && activationCalls == 0 && advances == 0
    var front: pid_t = 2, clock = 0.0
    let eventual = confirmFixedActivation(pid: 1, frontPID: { front }, requestActivation: { activationCalls += 1; return true },
        advance: { advances += 1; clock += 0.1; if advances == 3 { front = 1 } }, now: { clock })
    navigationPolicyResults["activation_once_advances_to_front"] = eventual && activationCalls == 1 && advances == 3
    activationCalls = 0; advances = 0; clock = 0
    let timedOut = confirmFixedActivation(pid: 1, frontPID: { 2 }, requestActivation: { activationCalls += 1; return true },
        advance: { advances += 1; clock += 0.5 }, now: { clock })
    navigationPolicyResults["activation_timeout_never_retries"] = !timedOut && activationCalls == 1 && advances == 2
    activationCalls = 0; advances = 0
    let refused = confirmFixedActivation(pid: 1, frontPID: { 2 }, requestActivation: { activationCalls += 1; return false },
                                         advance: { advances += 1 }, now: { 0 })
    navigationPolicyResults["activation_refusal_stops_once"] = !refused && activationCalls == 1 && advances == 0
    let audit = NavigationAudit(stage: .geometry, appActivationRequested: false, navigationActionIssued: false).safeJSON
    navigationPolicyResults["audit_fields_are_fixed"] = Set(audit.keys) == ["stage", "app_activation_requested", "navigation_action_issued"]
}
do {
    let first = SyntheticAncestor(1), second = SyntheticAncestor(2), last = SyntheticAncestor(3)
    first.parent = second; second.parent = last
    let complete = walkNavigationAncestors(first, hash: { _ in 1 }, equal: { $0.id == $1.id }, parent: { $0.parent })
    navigationPolicyResults["ancestor_hash_collisions_preserved"] = complete.complete && complete.nodes.map { $0.id } == [2, 3]
    last.parent = first
    navigationPolicyResults["ancestor_cycle_rejected"] = !walkNavigationAncestors(first, hash: { _ in 1 }, equal: { $0.id == $1.id }, parent: { $0.parent }).complete
    let chain = (0...65).map(SyntheticAncestor.init)
    for index in 0..<65 { chain[index].parent = chain[index + 1] }
    navigationPolicyResults["ancestor_depth_truncation_rejected"] = !walkNavigationAncestors(chain[0], hash: { UInt($0.id) }, equal: { $0.id == $1.id }, parent: { $0.parent }).complete
}
FileHandle.standardOutput.write(try! JSONSerialization.data(withJSONObject: navigationPolicyResults, options: [.sortedKeys]))
#elseif JOURNAL_LAYOUT_TEST
// A separate synthetic build runs the exact snapshot walker and ordering helper.
// No AX call, application lookup or installed-client metadata occurs in this mode.
final class SyntheticLayoutNode {
    let id: String
    let identityHash: UInt
    let role: String
    var children: [SyntheticLayoutNode] = []
    var windows: [SyntheticLayoutNode] = []
    init(_ id: String, hash: UInt = 1, role: String = "AXGroup") {
        self.id = id; self.identityHash = hash; self.role = role
    }
}
func syntheticWalk(_ root: SyntheticLayoutNode, maxNodes: Int = 8000,
                   maxDepth: Int = 20, now: () -> TimeInterval = { 0 }) -> [String: Any] {
    var counts: [String: Int] = [:]
    let walk = walkLayout(root, hash: { $0.identityHash }, equal: { $0.id == $1.id }, children: {
        orderedLayoutChildren($0, role: { $0.role }, windows: { $0.windows }, children: { $0.children })
    }, maxNodes: maxNodes, maxDepth: maxDepth, now: now, visit: {
        counts[$0.role, default: 0] += 1
    })
    return ["ids": walk.nodes.map { $0.id }, "role_counts": counts, "truncated": walk.truncated]
}
var traversalCases: [String: [String: Any]] = [:]
do {
    let app = SyntheticLayoutNode("app", role: "AXApplication"), menu = SyntheticLayoutNode("menu", role: "AXMenu")
    app.children = [menu]; menu.children = [app]
    traversalCases["cycle"] = syntheticWalk(app)
}
do {
    let root = SyntheticLayoutNode("root"), left = SyntheticLayoutNode("left"), right = SyntheticLayoutNode("right")
    let shared = SyntheticLayoutNode("shared", role: "AXButton")
    root.children = [left, right]; left.children = [shared]; right.children = [shared]
    traversalCases["shared"] = syntheticWalk(root)
}
do {
    let app = SyntheticLayoutNode("app", role: "AXApplication"), menu = SyntheticLayoutNode("menu", role: "AXMenu")
    let window = SyntheticLayoutNode("window", role: "AXWindow"), history = SyntheticLayoutNode("history", role: "AXButton")
    let danger = SyntheticLayoutNode("danger", role: "AXMenuItem"), login = SyntheticLayoutNode("login", role: "AXButton")
    app.windows = [window]; app.children = [menu, window]; window.children = [history]
    menu.children = [danger, login, app]
    traversalCases["windows_first_full_scan"] = syntheticWalk(app)
    traversalCases["windows_first_bounded"] = syntheticWalk(app, maxNodes: 2)
}
do {
    // Equal ids simulate distinct AX handles which CFEqual considers identical;
    // unrelated nodes intentionally share the same hash bucket.
    let root = SyntheticLayoutNode("root"), first = SyntheticLayoutNode("first", role: "AXButton")
    let equalHandle = SyntheticLayoutNode("first", role: "AXButton"), other = SyntheticLayoutNode("other", role: "AXMenuItem")
    root.children = [first, equalHandle, other]
    traversalCases["collisions_and_equal_handles"] = syntheticWalk(root)
    traversalCases["duplicate_at_node_budget"] = syntheticWalk(root, maxNodes: 3)
    traversalCases["genuine_node_budget"] = syntheticWalk(root, maxNodes: 2)
}
do {
    let chain = (0...20).map { SyntheticLayoutNode("depth-\($0)") }
    for index in 0..<20 { chain[index].children = [chain[index + 1]] }
    chain[20].children = [chain[0]]
    traversalCases["depth_only_seen_child"] = syntheticWalk(chain[0])
    chain[20].children.append(SyntheticLayoutNode("unvisited"))
    traversalCases["genuine_depth_budget"] = syntheticWalk(chain[0])
}
do {
    let root = SyntheticLayoutNode("root"), child = SyntheticLayoutNode("child")
    root.children = [child]
    var clock = [0.0, 0.0, 11.0]
    traversalCases["genuine_time_budget"] = syntheticWalk(root, now: { clock.removeFirst() })
}
FileHandle.standardOutput.write(try! JSONSerialization.data(withJSONObject: traversalCases, options: [.sortedKeys]))
#elseif JOURNAL_POLICY_TEST
// A separate test build exercises the production refresh tracker without any AX
// or installed-client access. This is not an action in the shipping JSON API.
func replay(_ observations: [(String, Bool, TimeInterval)], change: Bool = true) -> Bool {
    var tracker = RefreshTracker(baseline: "old", requireChange: change)
    return observations.contains { tracker.observe(hash: $0.0, rangeVerified: $0.1, at: $0.2) }
}
let results: [String: Bool] = [
    "unchanged_rejected": !replay([("old", true, 0), ("old", true, 1), ("old", true, 2)]),
    "late_refresh_accepted": replay([("old", true, 0), ("old", true, 1), ("new", true, 2), ("new", true, 2.5)]),
    "brief_stability_rejected": !replay([("new", true, 0), ("new", true, 0.2)]),
    "fluctuation_rejected": !replay([("new", true, 0), ("other", true, 1), ("new", true, 2)]),
    "unknown_range_rejected": !replay([("new", false, 0), ("new", false, 1)]),
    "range_reset_rejected": !replay([("new", true, 0), ("new", false, 1), ("new", true, 2)]),
    "bound_page_accepted": replay([("old", true, 0), ("old", true, 0.5)], change: false),
    "changed_bound_page_rejected": !replay([("new", true, 0), ("new", true, 1)], change: false),
]
FileHandle.standardOutput.write(try! JSONSerialization.data(withJSONObject: results, options: [.sortedKeys]))
#else
do {
    let data = FileHandle.standardInput.readDataToEndOfFile()
    guard data.count <= 65536, let request = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { try fail("INVALID_REQUEST") }
    #if JOURNAL_REQUEST_TEST
    // Executes the shipping request gate only, before installed metadata or UI.
    let result: [String: Any] = ["validated_action": try validateRequest(request)]
    #else
    let result = try run(request)
    #endif
    let output = try JSONSerialization.data(withJSONObject: ["ok": true, "result": result], options: [.sortedKeys])
    FileHandle.standardOutput.write(output)
} catch let failure as SafeFailure {
    var envelope: [String: Any] = ["ok": false, "code": failure.code]
    if let audit = navAudit { envelope["nav_audit"] = audit.safeJSON }
    let output = try! JSONSerialization.data(withJSONObject: envelope, options: [.sortedKeys])
    FileHandle.standardOutput.write(output)
    exit(2)
} catch {
    var envelope: [String: Any] = ["ok": false, "code": "NATIVE_BRIDGE_FAILED"]
    if let audit = navAudit { envelope["nav_audit"] = audit.safeJSON }
    FileHandle.standardOutput.write(try! JSONSerialization.data(withJSONObject: envelope, options: [.sortedKeys]))
    exit(2)
}
#endif
