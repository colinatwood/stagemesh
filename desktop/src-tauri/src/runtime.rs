use serde::Serialize;
use std::fs::{self, File, OpenOptions};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::Manager;

const DATA_DIRECTORIES: &[&str] = &["sessions", "media", "preferences", "logs", "tmp"];

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

        let Some(executable) = resolve_runtime_executable(app) else {
            inner.status.state = "unavailable".into();
            inner.status.error = Some(
                "StageMesh runtime sidecar is not installed; set STAGEMESH_RUNTIME_EXECUTABLE or ship stagemesh-runtime beside the application".into(),
            );
            return Ok(());
        };

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
        let mut command = Command::new(&executable);
        command
            .args(["--host", "127.0.0.1", "--port", port_text.as_str()])
            .env("STAGEFORGE_DATA_DIR", &data_dir)
            .env("STAGEFORGE_FRONTEND_DIR", resource_dir.join("frontend"))
            .env("STAGEFORGE_RUNTIME_MODE", "desktop")
            .stdin(Stdio::null())
            .stdout(Stdio::from(stdout))
            .stderr(Stdio::from(stderr));

        let child = command.spawn().map_err(|error| {
            format!(
                "could not start StageMesh runtime {}: {error}",
                executable.display()
            )
        })?;
        let pid = child.id();
        inner.child = Some(child);
        inner.status = RuntimeStatus {
            state: "starting".into(),
            endpoint: Some(format!("http://127.0.0.1:{port}")),
            data_dir: data_dir.display().to_string(),
            executable: Some(executable.display().to_string()),
            pid: Some(pid),
            error: None,
        };
        Ok(())
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
            let _ = child.kill();
            let _ = child.wait();
        }
        if inner.status.state == "running" || inner.status.state == "starting" {
            inner.status.state = "stopped".into();
            inner.status.pid = None;
        }
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

fn resolve_runtime_executable(app: &tauri::AppHandle) -> Option<PathBuf> {
    if let Some(configured) = std::env::var_os("STAGEMESH_RUNTIME_EXECUTABLE") {
        let path = PathBuf::from(configured);
        if path.is_file() {
            return Some(path);
        }
    }

    let executable_name = if cfg!(windows) {
        "stagemesh-runtime.exe"
    } else {
        "stagemesh-runtime"
    };
    let resource_candidate = app
        .path()
        .resource_dir()
        .ok()
        .map(|dir| dir.join(executable_name));
    let application_candidate = std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(|dir| dir.join(executable_name)));
    resource_candidate
        .into_iter()
        .chain(application_candidate)
        .find(|path| path.is_file())
}

#[tauri::command]
pub fn runtime_status(supervisor: tauri::State<'_, RuntimeSupervisor>) -> Result<RuntimeStatus, String> {
    supervisor.status()
}

#[cfg(test)]
mod tests {
    use super::{prepare_data_layout, DATA_DIRECTORIES};
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
}
