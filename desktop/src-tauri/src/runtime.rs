use serde::Serialize;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use tauri::Manager;

const DATA_DIRECTORIES: &[&str] = &["sessions", "media", "preferences", "logs", "tmp"];
const READINESS_TIMEOUT: Duration = Duration::from_secs(15);

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeStatus {
    pub state: String,
    pub endpoint: Option<String>,
    pub data_dir: String,
    pub executable: Option<String>,
    pub pid: Option<u32>,
    pub error: Option<String>,
}

struct RuntimeInner {
    child: Option<Child>,
    status: RuntimeStatus,
    bootstrap_token: Option<String>,
    api_token: Option<String>,
    port: Option<u16>,
}

pub struct RuntimeSupervisor {
    inner: Mutex<RuntimeInner>,
}

impl Default for RuntimeSupervisor {
    fn default() -> Self {
        Self {
            inner: Mutex::new(RuntimeInner {
                child: None,
                status: RuntimeStatus {
                    state: "not-started".into(),
                    endpoint: None,
                    data_dir: String::new(),
                    executable: None,
                    pid: None,
                    error: None,
                },
                bootstrap_token: None,
                api_token: None,
                port: None,
            }),
        }
    }
}

impl RuntimeSupervisor {
    pub fn start(&self, app: &tauri::AppHandle) -> Result<(), String> {
        let data_dir = app
            .path()
            .app_data_dir()
            .map_err(|error| format!("could not resolve application data directory: {error}"))?;
        prepare_data_layout(&data_dir)?;

        let mut inner = self
            .inner
            .lock()
            .map_err(|_| "runtime supervisor lock is poisoned".to_string())?;
        inner.status.data_dir = data_dir.display().to_string();

        if inner.child.is_some() {
            return Ok(());
        }

        let Some(executable) = resolve_bundled_executable(app, "stagemesh-runtime") else {
            inner.status.state = "unavailable".into();
            inner.status.error = Some(
                "StageMesh runtime sidecar is not installed; set STAGEMESH_RUNTIME_EXECUTABLE or install a complete StageMesh package".into(),
            );
            return Err(inner.status.error.clone().unwrap_or_default());
        };
        let native_engine = resolve_bundled_executable(app, "stagemesh_engine").ok_or_else(|| {
            "StageMesh native engine is not installed; install a complete StageMesh package".to_string()
        })?;

        let listener = TcpListener::bind(("127.0.0.1", 0))
            .map_err(|error| format!("could not reserve local runtime port: {error}"))?;
        let port = listener
            .local_addr()
            .map_err(|error| format!("could not read local runtime port: {error}"))?
            .port();
        drop(listener);

        let log_path = data_dir.join("logs").join("runtime.log");
        let stdout = open_log(&log_path)?;
        let stderr = stdout
            .try_clone()
            .map_err(|error| format!("could not clone runtime log: {error}"))?;
        let resource_dir = app
            .path()
            .resource_dir()
            .map_err(|error| format!("could not resolve application resources: {error}"))?;

        let port_text = port.to_string();
        let api_token = random_token()?;
        let bootstrap_token = random_token()?;
        let mut command = Command::new(&executable);
        command
            .args(["--host", "127.0.0.1", "--port", port_text.as_str()])
            .env("STAGEMESH_DATA_DIR", &data_dir)
            .env("STAGEMESH_FRONTEND_DIR", resource_dir.join("frontend"))
            .env("STAGEMESH_RUNTIME_MODE", "desktop")
            .env("STAGEMESH_NATIVE_ENGINE", &native_engine)
            .env("STAGEMESH_REQUIRE_API_TOKEN", "1")
            .env("STAGEMESH_API_TOKEN", &api_token)
            .env("STAGEMESH_DESKTOP_SESSION_TOKEN", &bootstrap_token)
            .stdin(Stdio::null())
            .stdout(Stdio::from(stdout))
            .stderr(Stdio::from(stderr));

        let mut child = command.spawn().map_err(|error| {
            format!(
                "could not start StageMesh runtime {}: {error}",
                executable.display()
            )
        })?;
        let pid = child.id();
        inner.status = RuntimeStatus {
            state: "starting".into(),
            endpoint: Some(format!("http://127.0.0.1:{port}")),
            data_dir: data_dir.display().to_string(),
            executable: Some(executable.display().to_string()),
            pid: Some(pid),
            error: None,
        };
        if let Err(error) = wait_until_ready(&mut child, port, &api_token, READINESS_TIMEOUT) {
            let _ = child.kill();
            let _ = child.wait();
            inner.status.state = "failed".into();
            inner.status.pid = None;
            inner.status.error = Some(error.clone());
            return Err(error);
        }
        inner.status.state = "running".into();
        inner.child = Some(child);
        inner.bootstrap_token = Some(bootstrap_token);
        inner.api_token = Some(api_token);
        inner.port = Some(port);
        Ok(())
    }

    pub fn launch_url(&self) -> Result<String, String> {
        let inner = self
            .inner
            .lock()
            .map_err(|_| "runtime supervisor lock is poisoned".to_string())?;
        let endpoint = inner
            .status
            .endpoint
            .as_ref()
            .ok_or_else(|| "runtime endpoint is unavailable".to_string())?;
        let token = inner
            .bootstrap_token
            .as_ref()
            .ok_or_else(|| "desktop session is unavailable".to_string())?;
        Ok(format!("{endpoint}/app.html#stagemesh-session={token}"))
    }

    pub fn status(&self) -> Result<RuntimeStatus, String> {
        let mut inner = self
            .inner
            .lock()
            .map_err(|_| "runtime supervisor lock is poisoned".to_string())?;
        let child_state = inner
            .child
            .as_mut()
            .map(|child| child.try_wait().map_err(|error| error.to_string()));
        match child_state {
            Some(Ok(Some(exit))) => {
                inner.status.state = "exited".into();
                inner.status.pid = None;
                inner.status.error = Some(format!("runtime exited with {exit}"));
                inner.child = None;
                inner.bootstrap_token = None;
                inner.api_token = None;
                inner.port = None;
            }
            Some(Ok(None)) => inner.status.state = "running".into(),
            Some(Err(error)) => {
                inner.status.state = "unknown".into();
                inner.status.error = Some(format!("could not inspect runtime: {error}"));
            }
            None => {}
        }
        Ok(inner.status.clone())
    }

    pub fn shutdown(&self) {
        let Ok(mut inner) = self.inner.lock() else {
            return;
        };
        if let Some(mut child) = inner.child.take() {
            let graceful = match (inner.port.take(), inner.api_token.take()) {
                (Some(port), Some(api_token)) => request_graceful_shutdown(
                    &mut child,
                    port,
                    &api_token,
                    Duration::from_secs(2),
                ),
                _ => false,
            };
            if !graceful {
                let _ = child.kill();
            }
            let _ = child.wait();
        }
        if inner.status.state == "running" || inner.status.state == "starting" {
            inner.status.state = "stopped".into();
            inner.status.pid = None;
        }
        inner.bootstrap_token = None;
        inner.api_token = None;
        inner.port = None;
    }
}

impl Drop for RuntimeSupervisor {
    fn drop(&mut self) {
        self.shutdown();
    }
}

fn open_log(path: &Path) -> Result<File, String> {
    OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| format!("could not open runtime log {}: {error}", path.display()))
}

fn prepare_data_layout(root: &Path) -> Result<(), String> {
    fs::create_dir_all(root)
        .map_err(|error| format!("could not create application data directory: {error}"))?;
    for name in DATA_DIRECTORIES {
        fs::create_dir_all(root.join(name))
            .map_err(|error| format!("could not create application data directory {name}: {error}"))?;
    }
    Ok(())
}

fn resolve_bundled_executable(app: &tauri::AppHandle, base_name: &str) -> Option<PathBuf> {
    let configured_name = if base_name == "stagemesh-runtime" {
        "STAGEMESH_RUNTIME_EXECUTABLE"
    } else {
        "STAGEMESH_NATIVE_ENGINE_EXECUTABLE"
    };
    if let Some(configured) = std::env::var_os(configured_name) {
        let path = PathBuf::from(configured);
        if path.is_file() {
            return Some(path);
        }
    }

    let executable_name = if cfg!(windows) {
        format!("{base_name}.exe")
    } else {
        base_name.to_string()
    };
    let resource_candidate = app
        .path()
        .resource_dir()
        .ok()
        .map(|dir| dir.join(&executable_name));
    let application_candidate = std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(|dir| dir.join(&executable_name)));
    resource_candidate
        .into_iter()
        .chain(application_candidate)
        .find(|path| path.is_file())
}

fn random_token() -> Result<String, String> {
    let mut bytes = [0_u8; 32];
    getrandom::getrandom(&mut bytes)
        .map_err(|error| format!("could not generate desktop session token: {error}"))?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

fn wait_until_ready(
    child: &mut Child,
    port: u16,
    api_token: &str,
    timeout: Duration,
) -> Result<(), String> {
    let deadline = Instant::now() + timeout;
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    loop {
        if let Some(exit) = child
            .try_wait()
            .map_err(|error| format!("could not inspect StageMesh runtime: {error}"))?
        {
            return Err(format!("StageMesh runtime exited before readiness with {exit}"));
        }
        if Instant::now() >= deadline {
            return Err("StageMesh runtime did not become ready within 15 seconds".into());
        }
        if let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(250)) {
            let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
            let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));
            let request = format!(
                "GET /healthz HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nX-StageMesh-API-Token: {api_token}\r\nConnection: close\r\n\r\n"
            );
            if stream.write_all(request.as_bytes()).is_ok() {
                let mut response = [0_u8; 256];
                if let Ok(count) = stream.read(&mut response) {
                    let head = String::from_utf8_lossy(&response[..count]);
                    if head.starts_with("HTTP/1.1 200 ") || head.starts_with("HTTP/1.0 200 ") {
                        return Ok(());
                    }
                }
            }
        }
        thread::sleep(Duration::from_millis(100));
    }
}

fn request_graceful_shutdown(
    child: &mut Child,
    port: u16,
    api_token: &str,
    timeout: Duration,
) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(250)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));
    let request = format!(
        "POST /api/v1/desktop/shutdown HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nX-StageMesh-API-Token: {api_token}\r\nContent-Type: application/json\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{{}}"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut response = [0_u8; 512];
    let Ok(count) = stream.read(&mut response) else {
        return false;
    };
    let head = String::from_utf8_lossy(&response[..count]);
    if !head.starts_with("HTTP/1.1 202 ") && !head.starts_with("HTTP/1.0 202 ") {
        return false;
    }
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        match child.try_wait() {
            Ok(Some(_)) => return true,
            Ok(None) => thread::sleep(Duration::from_millis(50)),
            Err(_) => return false,
        }
    }
    false
}

#[tauri::command]
pub fn runtime_status(supervisor: tauri::State<'_, RuntimeSupervisor>) -> Result<RuntimeStatus, String> {
    supervisor.status()
}

#[cfg(test)]
mod tests {
    use super::{prepare_data_layout, random_token, DATA_DIRECTORIES};
    use std::fs;

    #[test]
    fn data_layout_is_portable_and_complete() {
        let root = std::env::temp_dir().join(format!("stagemesh-runtime-layout-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        prepare_data_layout(&root).expect("data layout should be created");
        assert!(root.is_dir());
        for name in DATA_DIRECTORIES {
            assert!(root.join(name).is_dir(), "missing {name}");
        }
        fs::remove_dir_all(root).expect("test data should be removable");
    }

    #[test]
    fn desktop_tokens_are_random_hex_credentials() {
        let first = random_token().expect("first token");
        let second = random_token().expect("second token");
        assert_eq!(first.len(), 64);
        assert!(first.bytes().all(|byte| byte.is_ascii_hexdigit()));
        assert_ne!(first, second);
    }
}
