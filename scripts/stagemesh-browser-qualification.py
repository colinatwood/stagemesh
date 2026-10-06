#!/usr/bin/env python3
"""Rendered StageMesh operator UI qualification using a real Chromium renderer.

The managed Chromium policy in some CI/container environments blocks direct loopback
navigation. This helper therefore serves the real StageMesh handler on loopback but
loads the production HTML/CSS/JavaScript with Playwright ``set_content`` and bridges
``fetch`` calls back to that real handler. This qualifies rendering, responsive layout,
keyboard focus, Chromium accessibility-tree semantics and client-side workflow behavior. It does *not* qualify browser-to-LAN
networking, TLS/IdP policy or actual assistive-technology interaction.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
SCRIPTS = ["app.js", "arrangement.js", "markers.js", "automation.js", "production.js", "recovery.js"]
VIEWPORTS = [(1440, 900), (1024, 768), (768, 1024), (390, 844)]


def _production_html() -> str:
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="/styles.css">', "")
    return re.sub(r'\s*<script src="/[^"]+"></script>', "", html)


def _bridge_fetch(local_base: str, payload: dict[str, Any]) -> dict[str, Any]:
    raw_url = str(payload.get("url") or "/")
    if raw_url.startswith(("http://", "https://")):
        parsed = urlsplit(raw_url)
        raw_url = parsed.path + (("?" + parsed.query) if parsed.query else "")
    if not raw_url.startswith("/"):
        raw_url = "/" + raw_url
    headers = {
        str(k): str(v)
        for k, v in dict(payload.get("headers") or {}).items()
        if str(k).lower() not in {"host", "origin", "referer", "content-length", "connection", "accept-encoding"}
    }
    body = payload.get("body")
    data = body.encode("utf-8") if isinstance(body, str) else None
    request = urllib.request.Request(
        local_base + raw_url,
        data=data,
        headers=headers,
        method=str(payload.get("method") or "GET"),
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            return {
                "status": response.status,
                "headers": dict(response.headers.items()),
                "body": base64.b64encode(raw).decode("ascii"),
            }
    except urllib.error.HTTPError as error:
        raw = error.read()
        return {
            "status": error.code,
            "headers": dict(error.headers.items()),
            "body": base64.b64encode(raw).decode("ascii"),
        }


def analyze_accessibility_tree(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    def prop(node: dict[str, Any], name: str) -> Any:
        for item in node.get("properties") or []:
            if item.get("name") == name:
                return (item.get("value") or {}).get("value")
        return None

    def role(node: dict[str, Any]) -> str:
        return str((node.get("role") or {}).get("value") or "")

    def name(node: dict[str, Any]) -> str:
        return str((node.get("name") or {}).get("value") or "").strip()

    exposed=[node for node in nodes if not node.get("ignored")]
    interactive={"button","link","spinbutton","textbox","checkbox","combobox"}
    unnamed=[role(node) for node in exposed if role(node) in interactive and not name(node)]
    ignored_focusable=[role(node) for node in nodes if node.get("ignored") and prop(node,"focusable") is True]
    names_by_role:dict[str,list[str]]={}
    for node in exposed:names_by_role.setdefault(role(node),[]).append(name(node))
    bpm=[node for node in exposed if role(node)=="spinbutton" and name(node).startswith("BPM")]
    checks={
        "mainLandmark":any(role(node)=="main" for node in exposed),
        "skipLink":any(role(node)=="link" and name(node)=="Skip to stage controls" and prop(node,"focusable") is True for node in exposed),
        "launcherPlayPause":any(role(node)=="button" and name(node)=="Play or pause" and prop(node,"focusable") is True for node in exposed),
        "launcherStop":any(role(node)=="button" and name(node)=="Stop" for node in exposed),
        "bpmControl":bool(bpm and prop(bpm[0],"focusable") is True and prop(bpm[0],"valuemin")==30 and prop(bpm[0],"valuemax")==300),
        "keyControl":any(role(node)=="combobox" and name(node).startswith("Key") and prop(node,"focusable") is True for node in exposed),
        "playerButtons":sum(1 for node in exposed if role(node)=="button" and any(player in name(node) for player in ("Alex","Sam","Maya","Jordan")))>=4,
        "liveRegions":sum(1 for node in exposed if role(node)=="status" and prop(node,"live")=="polite")>=3,
        "namedInteractiveControls":not unnamed,
        "noIgnoredFocusableNodes":not ignored_focusable,
    }
    failures=[key for key,value in checks.items() if not value]
    return {
        "passed":not failures,
        "checks":checks,
        "failures":failures,
        "exposedNodeCount":len(exposed),
        "interactiveNodeCount":sum(1 for node in exposed if role(node) in interactive),
        "liveRegionCount":sum(1 for node in exposed if role(node)=="status" and prop(node,"live")=="polite"),
        "unnamedInteractiveRoles":unnamed[:32],
        "ignoredFocusableRoles":ignored_focusable[:32],
    }


def qualify(chromium: str, screenshot_dir: Path | None = None) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright Python is required for rendered-browser qualification") from exc

    with tempfile.TemporaryDirectory(prefix="stagemesh-browser-") as state_dir:
        os.environ["STAGEMESH_DATA_DIR"] = state_dir
        sys.path.insert(0, str(ROOT / "backend"))
        from dev_server import StageMeshHandler  # pylint: disable=import-outside-toplevel

        server = ThreadingHTTPServer(("127.0.0.1", 0), StageMeshHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        local_base = f"http://127.0.0.1:{server.server_port}"
        try:
            html = _production_html()
            css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
            scripts = [(name, (FRONTEND / name).read_text(encoding="utf-8")) for name in SCRIPTS]
            results: list[dict[str, Any]] = []
            accessibility_reference: dict[str, Any] | None = None
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=chromium,
                    headless=True,
                    args=["--no-sandbox"],
                )
                try:
                    for width, height in VIEWPORTS:
                        page = browser.new_page(viewport={"width": width, "height": height})
                        errors: list[str] = []
                        page.on("pageerror", lambda error, sink=errors: sink.append(f"page: {error}"))
                        page.on(
                            "console",
                            lambda message, sink=errors: sink.append(f"console: {message.text}")
                            if message.type == "error"
                            else None,
                        )
                        page.expose_function(
                            "__stagemesh_bridge",
                            lambda payload, base=local_base: _bridge_fetch(base, payload),
                        )
                        page.set_content(html, wait_until="domcontentloaded")
                        page.add_style_tag(content=css)
                        page.evaluate(
                            """
                            (() => {
                              delete globalThis.EventSource;
                              const decode = (encoded) => Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0));
                              globalThis.fetch = async (input, init = {}) => {
                                const url = typeof input === "string" ? input : input.url;
                                const method = init.method || (typeof input === "string" ? "GET" : input.method) || "GET";
                                const headers = {};
                                const source = new Headers(init.headers || (typeof input === "string" ? {} : input.headers || {}));
                                for (const [key, value] of source.entries()) headers[key] = value;
                                const response = await globalThis.__stagemesh_bridge({url, method, headers, body: init.body ?? null});
                                return new Response(decode(response.body), {status: response.status, headers: response.headers});
                              };
                            })();
                            """
                        )
                        for _, source in scripts:
                            page.add_script_tag(content=source)
                        page.wait_for_timeout(1800)

                        title = page.title()
                        overflow_px = int(
                            page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                        )
                        launcher_visible = page.locator("#launcherPlay").is_visible() and page.locator("#launcherStop").is_visible()
                        player_count = page.locator("[data-player]").count()
                        launcher_status = page.locator("#launcherStatus").inner_text()
                        if title != "StageMesh":
                            errors.append(f"unexpected title: {title!r}")
                        if overflow_px > 0:
                            errors.append(f"horizontal overflow: {overflow_px}px")
                        if not launcher_visible:
                            errors.append("stage launcher controls are not visible")
                        if player_count < 4:
                            errors.append(f"expected at least four player nodes, got {player_count}")
                        if "Loading native sampler" in launcher_status:
                            errors.append("launcher did not finish initial render")

                        if width == 1440:
                            page.keyboard.press("Tab")
                            if "skipLink" not in page.evaluate("document.activeElement.className"):
                                errors.append("first keyboard focus is not the skip link")
                            page.keyboard.press("Enter")
                            if page.evaluate("document.activeElement.id") != "main-content":
                                errors.append("skip link did not focus the main stage controls")
                            page.locator('[data-player="alex"]').click()
                            page.wait_for_timeout(100)
                            if not page.locator("#monitorControls").is_visible():
                                errors.append("player selection did not reveal personal monitor controls")
                            if "Alex" not in page.locator("#playerTitle").inner_text():
                                errors.append("player selection did not render Alex's control heading")
                            page.locator("#bpm").fill("123")
                            page.locator("#bpm").dispatch_event("change")
                            page.wait_for_timeout(150)
                            if page.locator("#bpm").input_value() != "123":
                                errors.append("safe show-state BPM edit did not remain rendered")
                            cdp = page.context.new_cdp_session(page)
                            accessibility_reference = analyze_accessibility_tree(cdp.send("Accessibility.getFullAXTree")["nodes"])
                            cdp.detach()
                            if not accessibility_reference["passed"]:
                                errors.extend(f"accessibility tree: {item}" for item in accessibility_reference["failures"])

                        if screenshot_dir is not None:
                            screenshot_dir.mkdir(parents=True, exist_ok=True)
                            page.screenshot(
                                path=str(screenshot_dir / f"stagemesh-{width}x{height}.png"),
                                full_page=True,
                            )
                        results.append(
                            {
                                "viewport": {"width": width, "height": height},
                                "horizontalOverflowPx": overflow_px,
                                "launcherVisible": launcher_visible,
                                "playerCount": player_count,
                                "errors": errors,
                            }
                        )
                        page.close()
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    failures = [item for item in results if item["errors"]]
    return {
        "qualification": "rendered-browser-reference",
        "chromium": chromium,
        "viewports": results,
        "passed": not failures,
        "renderedWorkflowQualified": not failures,
        "responsiveReferenceQualified": not failures,
        "accessibilityTreeReferenceQualified": bool(accessibility_reference and accessibility_reference["passed"]),
        "accessibilityTree": accessibility_reference,
        "assistiveTechnologyQualified": False,
        "directBrowserLoopbackNetworkingQualified": False,
        "notes": [
            "Production HTML/CSS/JavaScript execute in real headless Chromium.",
            "Fetch calls are bridged to the real loopback StageMesh handler because this managed Chromium policy blocks direct loopback navigation.",
            "Chromium's accessibility tree is checked for landmarks, names, roles, focusability, bounded BPM semantics and polite live regions.",
            "This does not qualify screen readers, switch/voice control, TLS/IdP/firewall behavior, touch hardware or venue networking.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium", default=shutil.which("chromium") or "", help="Chromium/Chrome executable")
    parser.add_argument("--screenshots", type=Path, help="Optional directory for full-page qualification screenshots")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    if not args.chromium or not Path(args.chromium).is_file():
        parser.error("a Chromium executable is required (use --chromium)")
    report = qualify(args.chromium, args.screenshots)
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
