"""Per-user installer for the standalone Work Log executable."""

from __future__ import annotations

import os
import json
import locale
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from holiday_calendar import download_china_holiday_year


APP_NAME = "Work Log"
LEGACY_APP_NAME = "每小时记录"


def bundled_file(name: str) -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / name


def create_shortcut(shortcut: Path, target: Path) -> None:
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


def create_start_menu_shortcut(target: Path) -> None:
    start_menu = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    create_shortcut(start_menu / f"{APP_NAME}.lnk", target)


def create_startup_shortcut(target: Path) -> None:
    startup = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    create_shortcut(startup / f"{APP_NAME}.lnk", target)


def main() -> None:
    root = tk.Tk()
    root.title("Work Log — 安装向导")
    root.resizable(False, False)
    root.geometry("590x445")
    app_dir = Path(os.environ["LOCALAPPDATA"]) / "HourlyReminder"
    target = app_dir / "WorkLog.exe"
    source = bundled_file("WorkLog.exe")
    default_log_directory = app_dir
    selected_directory = tk.StringVar(value=str(default_log_directory))

    container = ttk.Frame(root, padding=28)
    container.pack(fill="both", expand=True)
    ttk.Label(container, text="安装 Work Log", font=("Microsoft YaHei UI", 19, "bold")).pack(anchor="w")
    ttk.Label(
        container,
        text="软件会在您开始上班后按时提醒您填写工作内容。\n程序仅安装在当前 Windows 用户的本机目录中。",
        font=("Microsoft YaHei UI", 10),
        justify="left",
    ).pack(anchor="w", pady=(12, 24))

    locale_name = (locale.getlocale()[0] or "").upper()
    detected_region = "中国大陆" if locale_name.endswith("_CN") else "未识别（将使用中国大陆日历）"
    holiday_download_var = tk.BooleanVar(value=True)
    holiday_box = ttk.LabelFrame(container, text="法定工作日提醒", padding=9)
    holiday_box.pack(fill="x", pady=(0, 16))
    ttk.Label(holiday_box, text=f"系统地区：{detected_region}").pack(anchor="w")
    ttk.Checkbutton(
        holiday_box,
        text="联网下载当年和下一年法定节假日、调休工作日日历",
        variable=holiday_download_var,
    ).pack(anchor="w", pady=(5, 0))
    ttk.Label(
        holiday_box,
        text="需要互联网；未下载时，“仅法定工作日”功能不可用。",
        foreground="#9a6700",
    ).pack(anchor="w", pady=(4, 0))

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
        holiday_calendar: dict[str, dict[str, bool]] = {}
        if holiday_download_var.get():
            try:
                status.configure(text="正在联网下载法定节假日日历…")
                root.update_idletasks()
                current_year = datetime.now().year
                for year in (current_year, current_year + 1):
                    holiday_calendar[str(year)] = download_china_holiday_year(year)
            except (OSError, ValueError) as error:
                messagebox.showwarning(
                    "节假日日历下载失败",
                    f"无法下载法定节假日日历：\n{error}\n\n"
                    "请检查网络后重试；或取消勾选联网日历以安装基础功能。",
                    parent=root,
                )
                install_button.configure(state="normal")
                browse_button.configure(state="normal")
                status.configure(text="")
                return
        elif not messagebox.askyesno(
            "法定工作日功能不可用",
            "未联网下载节假日日历，“仅法定工作日”功能将不可用。\n\n仍要继续安装吗？",
            parent=root,
        ):
            install_button.configure(state="normal")
            browse_button.configure(state="normal")
            status.configure(text="")
            return
        try:
            app_dir.mkdir(parents=True, exist_ok=True)
            log_directory.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            settings_file = app_dir / "settings.json"
            try:
                settings = json.loads(settings_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                settings = {}
            settings["log_directory"] = str(log_directory)
            if holiday_calendar:
                settings["holiday_calendar"] = holiday_calendar
                settings["holiday_calendar_region"] = "CN"
                settings["holiday_calendar_updated_at"] = datetime.now().isoformat(timespec="seconds")
            settings_file.write_text(
                json.dumps(settings, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            create_start_menu_shortcut(target)
            start_menu = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            legacy_start_menu = start_menu / f"{LEGACY_APP_NAME}.lnk"
            legacy_startup = start_menu / "Startup" / f"{LEGACY_APP_NAME}.lnk"
            had_legacy_autostart = legacy_startup.exists()
            legacy_start_menu.unlink(missing_ok=True)
            legacy_startup.unlink(missing_ok=True)
            if had_legacy_autostart:
                create_startup_shortcut(target)
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
