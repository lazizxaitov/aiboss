#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

pub fn run() {
    bootstrap_services();
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running AI Business OS");
}

fn bootstrap_services() {
    let Ok(uid) = std::process::Command::new("/usr/bin/id").arg("-u").output() else {
        return;
    };
    let uid = String::from_utf8_lossy(&uid.stdout).trim().to_owned();
    if uid.is_empty() {
        return;
    }
    let domain = format!("gui/{uid}");
    let home = std::env::var("HOME").unwrap_or_default();
    for (label, plist) in [
        ("com.aiboss.frontend", "com.aiboss.frontend.plist"),
        ("com.aiboss.backend", "com.aiboss.backend.plist"),
    ] {
        let service = format!("{domain}/{label}");
        let service_status = std::process::Command::new("/bin/launchctl")
            .args(["print", &service])
            .output()
            .ok();
        let loaded = service_status.as_ref().map(|result| result.status.success()).unwrap_or(false);
        let running = service_status
            .as_ref()
            .map(|result| {
                let output = String::from_utf8_lossy(&result.stdout);
                output.contains("state = running") || output.contains("pid = ")
            })
            .unwrap_or(false);
        if !loaded {
            let paths = [
                format!("{home}/Library/LaunchAgents/{plist}"),
                format!("{home}/Projects/aiboss/{plist}"),
                format!("/Library/LaunchAgents/{plist}"),
            ];
            for path in paths {
                if !std::path::Path::new(&path).exists() {
                    continue;
                }
                let bootstrapped = std::process::Command::new("/bin/launchctl")
                    .args(["bootstrap", &domain, &path])
                    .output()
                    .map(|result| result.status.success())
                    .unwrap_or(false);
                if !bootstrapped {
                    let _ = std::process::Command::new("/bin/launchctl")
                        .args(["load", &path])
                        .output();
                }
                break;
            }
        }
        // Do not restart healthy services when the user merely reopens Tauri.
        // A stopped job is started, while an explicit restart uses the backend
        // system-control endpoint and intentionally uses kickstart -k.
        if !running {
            let _ = std::process::Command::new("/bin/launchctl")
                .args(["kickstart", "-k", &service])
                .output();
        }
    }
}
