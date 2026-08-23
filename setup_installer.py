"""Per-user installer for the standalone HourlyReminder executable."""

from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox


APP_NAME = "每小时记录"


def bundled_file(name: str) -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / name


def create_start_menu_shortcut(target: Path) -> None:
    start_menu = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    shortcut = start_menu / f"{APP_NAME}.lnk"
    command = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($args[0]);"
        "$s.TargetPath=$args[1];$s.WorkingDirectory=$args[2];"
        "$s.Description='每小时活动记录提醒';$s.Save()"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command,
         str(shortcut), str(target), str(target.parent)],
        check=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    app_dir = Path(os.environ["LOCALAPPDATA"]) / "HourlyReminder"
    target = app_dir / "HourlyReminder.exe"
    source = bundled_file("HourlyReminder.exe")
    default_log_directory = app_dir
    selected_directory = filedialog.askdirectory(
        parent=root,
        title="选择活动记录保存位置",
        initialdir=default_log_directory,
        mustexist=False,
    )
    if not selected_directory:
        root.destroy()
        return
    log_directory = Path(selected_directory)
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
        root.destroy()
        raise SystemExit(1)
    subprocess.Popen([str(target)], cwd=app_dir)
    messagebox.showinfo("安装完成", f"{APP_NAME} 已安装并启动。\n\n记录保存在：\n{log_directory / 'activity_log.csv'}", parent=root)
    root.destroy()


if __name__ == "__main__":
    main()
