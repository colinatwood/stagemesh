#!/usr/bin/env python3
"""Verify the frozen desktop runtime, native engine, and authenticated UI handshake."""
from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time


def request(
    port: int,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    body = response.read()
    result = response.status, dict(response.getheaders()), body
    connection.close()
    return result


def stop_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def start_runtime(
    runtime: Path,
    port: int,
    environment: dict[str, str],
    log,
) -> subprocess.Popen:
    return subprocess.Popen(
        [str(runtime), "--host", "127.0.0.1", "--port", str(port)],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
    )


def wait_until_ready(
    process: subprocess.Popen,
    port: int,
    api_token: str,
) -> dict:
    deadline = time.monotonic() + 15
    health = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"runtime exited before readiness with {process.returncode}"
            )
        try:
            health = request(
                port,
                "GET",
                "/healthz",
                {"X-StageMesh-API-Token": api_token},
            )
            if health[0] == 200:
                break
        except OSError:
            pass
        time.sleep(0.1)
    if health is None or health[0] != 200:
        raise RuntimeError("runtime did not become ready within 15 seconds")
    health_payload = json.loads(health[2])
    if not health_payload.get("ok"):
        raise RuntimeError("runtime health payload is not healthy")
    return health_payload


def request_graceful_shutdown(
    process: subprocess.Popen,
    port: int,
    api_token: str,
) -> None:
    shutdown_status, _, shutdown_body = request(
        port,
        "POST",
        "/api/v1/desktop/shutdown",
        {
            "Content-Type": "application/json",
            "X-StageMesh-API-Token": api_token,
        },
        b"{}",
    )
    shutdown_payload = json.loads(shutdown_body)
    if shutdown_status != 202 or shutdown_payload.get("status") != "stopping":
        raise RuntimeError(
            f"desktop runtime rejected graceful shutdown: {shutdown_payload}"
        )
    try:
        return_code = process.wait(timeout=5)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "desktop runtime did not exit after graceful shutdown"
        ) from exc
    if return_code != 0:
        raise RuntimeError(
            f"desktop runtime exited with {return_code} after graceful shutdown"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--native-engine", required=True, type=Path)
    parser.add_argument("--frontend", required=True, type=Path)
    args = parser.parse_args()

    runtime = args.runtime.resolve()
    native_engine = args.native_engine.resolve()
    frontend = args.frontend.resolve()
    for name, path in (("runtime", runtime), ("native engine", native_engine)):
        if not path.is_file():
            parser.error(f"{name} does not exist: {path}")
    if not (frontend / "app.html").is_file():
        parser.error(f"frontend app is missing: {frontend}")

    api_token = secrets.token_hex(32)
    bootstrap_token = secrets.token_hex(32)

    with tempfile.TemporaryDirectory(prefix="stagemesh-desktop-smoke-") as temporary:
        root = Path(temporary)
        log_path = root / "runtime.log"
        environment = os.environ.copy()
        environment.update({
            "STAGEMESH_DATA_DIR": str(root / "data"),
            "STAGEMESH_FRONTEND_DIR": str(frontend),
            "STAGEMESH_RUNTIME_MODE": "desktop",
            "STAGEMESH_NATIVE_ENGINE": str(native_engine),
            "STAGEMESH_REQUIRE_API_TOKEN": "1",
            "STAGEMESH_API_TOKEN": api_token,
            "STAGEMESH_DESKTOP_SESSION_TOKEN": bootstrap_token,
        })

        # Prove a packaged runtime fails closed when its selected loopback port
        # is stolen, cleans up its native child, and can recover using the same
        # data directory once the port becomes available.
        collision_log_path = root / "runtime-port-collision.log"
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            reservation.listen(1)
            port = reservation.getsockname()[1]
            with collision_log_path.open("wb") as collision_log:
                collision = start_runtime(runtime, port, environment, collision_log)
                try:
                    try:
                        collision_code = collision.wait(timeout=15)
                    except subprocess.TimeoutExpired as exc:
                        raise RuntimeError(
                            "runtime did not fail closed on a reserved loopback port"
                        ) from exc
                    if collision_code == 0:
                        raise RuntimeError(
                            "runtime reported success while its loopback port was unavailable"
                        )
                finally:
                    stop_process_tree(collision)
        collision_details = collision_log_path.read_text(
            encoding="utf-8", errors="replace"
        )
        if api_token in collision_details or bootstrap_token in collision_details:
            raise RuntimeError("runtime port-collision log exposed a desktop credential")

        with log_path.open("wb") as log:
            process = start_runtime(runtime, port, environment, log)
            try:
                wait_until_ready(process, port, api_token)

                native_status, _, native_body = request(port, "GET", "/api/v1/native", {
                    "X-StageMesh-API-Token": api_token,
                })
                native_payload = json.loads(native_body)
                if native_status != 200 or not native_payload.get("available"):
                    raise RuntimeError(f"native engine is unavailable: {native_payload}")

                session_status, session_headers, _ = request(port, "POST", "/desktop/session", {
                    "X-StageMesh-Desktop-Token": bootstrap_token,
                })
                cookie = session_headers.get("Set-Cookie", "")
                if session_status != 200 or "HttpOnly" not in cookie or "SameSite=Strict" not in cookie:
                    raise RuntimeError("desktop session cookie was not established securely")
                cookie_value = cookie.split(";", 1)[0]
                cookie_status, _, _ = request(port, "GET", "/healthz", {"Cookie": cookie_value})
                if cookie_status != 200:
                    raise RuntimeError("desktop session cookie did not authorize the API")

                app_status, app_headers, app_body = request(port, "GET", "/app.html")
                if app_status != 200 or not app_headers.get("Content-Type", "").startswith("text/html"):
                    raise RuntimeError("packaged frontend was not served")
                if b"StageMesh" not in app_body:
                    raise RuntimeError("packaged frontend content is invalid")

                template_body = json.dumps({
                    "name": "Desktop restart persistence",
                    "objects": [{
                        "label": "Packaged marker",
                        "x": 50,
                        "y": 50,
                    }],
                }).encode("utf-8")
                template_status, _, template_response_body = request(
                    port,
                    "POST",
                    "/api/v1/templates",
                    {
                        "Content-Type": "application/json",
                        "X-StageMesh-API-Token": api_token,
                    },
                    template_body,
                )
                template_payload = json.loads(template_response_body)
                template_id = template_payload.get("templateId")
                template_objects = template_payload.get("objects")
                if (
                    template_status != 201
                    or not isinstance(template_id, str)
                    or not template_id
                    or template_payload.get("revision") != 1
                    or template_payload.get("state") != "draft"
                    or not isinstance(template_objects, list)
                    or len(template_objects) != 1
                    or not isinstance(template_objects[0], dict)
                    or template_objects[0].get("label") != "Packaged marker"
                    or template_objects[0].get("x") != 50
                    or template_objects[0].get("y") != 50
                ):
                    raise RuntimeError(
                        f"packaged runtime did not create a template: {template_payload}"
                    )

                request_graceful_shutdown(process, port, api_token)
                process = start_runtime(runtime, port, environment, log)
                wait_until_ready(process, port, api_token)

                restored_status, _, restored_body = request(
                    port,
                    "GET",
                    f"/api/v1/templates/{template_id}",
                    {"X-StageMesh-API-Token": api_token},
                )
                restored_payload = json.loads(restored_body)
                if (
                    restored_status != 200
                    or restored_payload.get("templateId") != template_id
                    or restored_payload.get("name") != "Desktop restart persistence"
                    or restored_payload.get("revision") != 1
                    or restored_payload.get("state") != "draft"
                    or restored_payload.get("objects") != template_objects
                ):
                    raise RuntimeError(
                        "packaged runtime did not preserve the template across restart: "
                        f"{restored_payload}"
                    )

                request_graceful_shutdown(process, port, api_token)
            except Exception as exc:
                log.flush()
                details = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                raise RuntimeError(f"{exc}\nRuntime log:\n{details}") from exc
            finally:
                stop_process_tree(process)
    print(
        "Desktop runtime smoke passed, including persistence restart; "
        "physical hardware was not activated or qualified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
