#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod runtime;

use runtime::RuntimeSupervisor;
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder, WindowEvent};

fn main() {
    tauri::Builder::default()
        .manage(RuntimeSupervisor::default())
        .setup(|app| {
            let supervisor = app.state::<RuntimeSupervisor>();
            supervisor
                .start(app.handle())
                .map_err(|error| std::io::Error::new(std::io::ErrorKind::Other, error))?;
            let url = WebviewUrl::External(
                supervisor
                    .launch_url()
                    .map_err(|error| std::io::Error::new(std::io::ErrorKind::Other, error))?
                    .parse()
                    .map_err(|_| {
                        std::io::Error::new(
                            std::io::ErrorKind::InvalidData,
                            "runtime endpoint is not a valid URL",
                        )
                    })?,
            );
            WebviewWindowBuilder::new(
                app,
                "main",
                url,
            )
            .title("StageMesh")
            .inner_size(1440.0, 960.0)
            .min_inner_size(1024.0, 700.0)
            .resizable(true)
            .build()?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, WindowEvent::Destroyed) {
                window.state::<RuntimeSupervisor>().shutdown();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running StageMesh desktop application");
}
