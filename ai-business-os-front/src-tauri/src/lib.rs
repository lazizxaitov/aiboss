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
        let loaded = std::process::Command::new("/bin/launchctl")
            .args(["print", &service])
            .output()
            .map(|result| result.status.success())
            .unwrap_or(false);
        if !loaded {
            let path = format!("{home}/Library/LaunchAgents/{plist}");
            let _ = std::process::Command::new("/bin/launchctl")
                .args(["bootstrap", &domain, &path])
                .output();
        }
    }
}
