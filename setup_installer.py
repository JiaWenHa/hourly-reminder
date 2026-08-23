"""Per-user installer for the standalone HourlyReminder executable."""

from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_NAME = "每小时记录"


def bundled_file(name: str) -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / name


def create_start_menu_shortcut(target: Path) -> None:
    start_menu = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    shortcut = start_menu / f"{APP_NAME}.lnk"
    # Do not pass paths as trailing -Command arguments: that convention is
    # inconsistent across PowerShell versions.  Embed quoted string literals
    # in the script instead, so the installer also works on Windows 11.
    def ps_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    target_text = ps_literal(str(target))
    command = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut("
        f"{ps_literal(str(shortcut))});"
        f"$s.TargetPath={target_text};$s.WorkingDirectory={ps_literal(str(target.parent))};"
        f"$s.IconLocation={target_text}+',0';"
        "$s.Description='每小时活动记录提醒';$s.Save()"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        check=True, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True, text=True,
    )


def main() -> None:
    root = tk.Tk()
    root.title("每小时记录 — 安装向导")
    root.resizable(False, False)
    root.geometry("590x365")
    app_dir = Path(os.environ["LOCALAPPDATA"]) / "HourlyReminder"
    target = app_dir / "HourlyReminder.exe"
    source = bundled_file("HourlyReminder.exe")
    default_log_directory = app_dir
    selected_directory = tk.StringVar(value=str(default_log_directory))

    container = ttk.Frame(root, padding=28)
    container.pack(fill="both", expand=True)
    ttk.Label(container, text="安装 每小时记录", font=("Microsoft YaHei UI", 19, "bold")).pack(anchor="w")
    ttk.Label(
        container,
        text="软件会在您开始上班后按时提醒您填写工作内容。\n程序仅安装在当前 Windows 用户的本机目录中。",
        font=("Microsoft YaHei UI", 10),
        justify="left",
    ).pack(anchor="w", pady=(12, 24))

    ttk.Label(container, text="活动记录保存位置：", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
    directory_frame = ttk.Frame(container)
    directory_frame.pack(fill="x", pady=(7, 4))
    ttk.Entry(directory_frame, textvariable=selected_directory, state="readonly").pack(side="left", fill="x", expand=True)

    def choose_directory() -> None:
        choice = filedialog.askdirectory(
            parent=root,
            title="选择活动记录保存位置",
            initialdir=selected_directory.get(),
            mustexist=False,
        )
        if choice:
            selected_directory.set(choice)

    ttk.Button(directory_frame, text="浏览…", command=choose_directory).pack(side="left", padx=(10, 0))
    ttk.Label(
        container,
        text="工作记录会按时间顺序写入此文件夹中的 activity_log.csv。",
        foreground="#555555",
    ).pack(anchor="w", pady=(0, 25))

    button_frame = ttk.Frame(container)
    button_frame.pack(side="bottom", fill="x")
    status = ttk.Label(button_frame, text="")
    status.pack(side="left")

    def install() -> None:
        log_directory = Path(selected_directory.get())
        if not selected_directory.get().strip():
            messagebox.showwarning("请选择位置", "请选择活动记录的保存位置。", parent=root)
            return
        install_button.configure(state="disabled")
        browse_button.configure(state="disabled")
        status.configure(text="正在安装，请稍候…")
        root.update_idletasks()
        try:
            app_dir.mkdir(parents=True, exist_ok=True)
            log_directory.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            (app_dir / "settings.json").write_text(
                json.dumps({"log_directory": str(log_directory)}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            create_start_menu_shortcut(target)
        except (OSError, subprocess.SubprocessError) as error:
            messagebox.showerror("安装失败", f"无法安装 {APP_NAME}：\n{error}", parent=root)
            install_button.configure(state="normal")
            browse_button.configure(state="normal")
            status.configure(text="")
            return
        subprocess.Popen([str(target)], cwd=app_dir)
        messagebox.showinfo("安装完成", f"{APP_NAME} 已安装并启动。\n\n记录保存在：\n{log_directory / 'activity_log.csv'}", parent=root)
        root.destroy()

    install_button = ttk.Button(button_frame, text="立即安装", command=install)
    install_button.pack(side="right")
    ttk.Button(button_frame, text="取消", command=root.destroy).pack(side="right", padx=(0, 10))
    browse_button = directory_frame.winfo_children()[-1]
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
