"""Windows 11 hourly activity reminder.

Only Python's standard library is required.  Run with:
    python hourly_reminder.py
"""

from __future__ import annotations

import csv
import ctypes
import json
import os
import sys
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox


APP_NAME = "每小时记录"
DEFAULT_INTERVAL_SECONDS = 60 * 60
APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "HourlyReminder"
SETTINGS_FILE = APP_DATA_DIR / "settings.json"


def get_log_file() -> Path:
    """Use the folder selected during installation, with a safe default."""
    try:
        settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        selected_directory = settings.get("log_directory")
        if selected_directory:
            return Path(selected_directory) / "activity_log.csv"
    except (OSError, json.JSONDecodeError):
        pass
    return APP_DATA_DIR / "activity_log.csv"


LOG_FILE = get_log_file()


@dataclass
class Prompt:
    period_started_at: datetime
    opened_at: datetime
    window: tk.Toplevel
    text: tk.Text
    elapsed: tk.Label
    is_clock_out: bool


class HourlyReminder:
    def __init__(self, root: tk.Tk, interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> None:
        self.root = root
        self.interval_seconds = interval_seconds
        self.prompt: Prompt | None = None
        self.working = False
        self.next_due: datetime | None = None
        self.period_started_at: datetime | None = None

        self.root.title(APP_NAME)
        self.root.geometry("480x290")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)
        self._build_main_window()
        self._ensure_log_file()
        self._tick()

    def _build_main_window(self) -> None:
        frame = tk.Frame(self.root, padx=26, pady=24)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="每小时记录", font=("Microsoft YaHei UI", 20, "bold")).pack(anchor="w")
        self.status = tk.Label(frame, font=("Microsoft YaHei UI", 11), justify="left")
        self.status.pack(anchor="w", pady=(15, 20))
        buttons = tk.Frame(frame)
        buttons.pack(anchor="w")
        self.start_button = tk.Button(buttons, text="开始上班", command=self._start_work, width=14)
        self.start_button.pack(side="left")
        self.stop_button = tk.Button(buttons, text="开始下班", command=self._stop_work, width=14, state="disabled")
        self.stop_button.pack(side="left", padx=(10, 0))
        self.manual_button = tk.Button(frame, text="立即填写", command=self._show_prompt, width=14, state="disabled")
        self.manual_button.pack(anchor="w", pady=(10, 0))
        tk.Label(
            frame,
            text=f"记录文件：{LOG_FILE}",
            fg="#666666",
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", pady=(18, 0))

    def _tick(self) -> None:
        now = datetime.now()
        # An unanswered prompt deliberately blocks all later scheduled prompts.
        if self.working and self.prompt is None and self.next_due is not None and now >= self.next_due:
            self._show_prompt()
        if self.prompt is None:
            if self.working and self.next_due is not None:
                remaining = max(timedelta(), self.next_due - now)
                minutes, seconds = divmod(int(remaining.total_seconds()), 60)
                self.status.config(text=f"当前状态：上班中\n下一次提醒：{minutes:02d}:{seconds:02d} 后")
            else:
                self.status.config(text="当前状态：已下班\n点击“开始上班”后启动每小时提醒。")
        self.root.after(1000, self._tick)

    def _start_work(self) -> None:
        if self.working:
            return
        self.working = True
        self.period_started_at = datetime.now()
        self.next_due = self.period_started_at + timedelta(seconds=self.interval_seconds)
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.manual_button.config(state="normal")

    def _stop_work(self) -> None:
        if self.prompt is not None:
            messagebox.showwarning(APP_NAME, "请先填写并保存当前提醒，再开始下班。", parent=self.prompt.window)
            return
        self._show_prompt(is_clock_out=True)

    def _show_prompt(self, is_clock_out: bool = False) -> None:
        if self.prompt is not None:
            self._bring_to_front()
            return

        opened_at = datetime.now()
        window = tk.Toplevel(self.root)
        window.title("下班前填写" if is_clock_out else "请记录刚刚这一小时")
        window.configure(bg="#f7f7f7")
        # Fullscreen visual reminder.  Do not globally capture keyboard/mouse
        # input: the text field must remain usable and Windows controls stay safe.
        window.attributes("-fullscreen", True)
        window.attributes("-topmost", True)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._refuse_close)
        window.bind("<Alt-F4>", lambda _event: "break")

        body = tk.Frame(window, bg="#f7f7f7", padx=34, pady=28)
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text="下班前，请记录上次填写后到现在做了什么？" if is_clock_out else "这一个小时里，你做了什么？",
            bg="#f7f7f7",
            font=("Microsoft YaHei UI", 19, "bold"),
        ).pack(anchor="w")
        elapsed = tk.Label(body, bg="#f7f7f7", fg="#b42318", font=("Microsoft YaHei UI", 10))
        elapsed.pack(anchor="w", pady=(8, 18))
        text = tk.Text(body, height=10, font=("Microsoft YaHei UI", 12), wrap="word", undo=True)
        text.pack(fill="both", expand=True)
        text.focus_set()
        tk.Button(
            body, text="保存记录", command=self._save_prompt, bg="#1677ff", fg="white",
            activebackground="#0958d9", activeforeground="white", relief="flat",
            font=("Microsoft YaHei UI", 11, "bold"), padx=22, pady=8,
        ).pack(anchor="e", pady=(18, 0))

        self.prompt = Prompt(
            self.period_started_at or opened_at, opened_at, window, text, elapsed, is_clock_out,
        )
        self.status.config(text="正在等待下班记录；保存后结束本次上班。" if is_clock_out else "正在等待填写；新的提醒已暂停。")
        self._make_window_prominent(window)
        self._update_elapsed()

    def _update_elapsed(self) -> None:
        if self.prompt is None:
            return
        seconds = int((datetime.now() - self.prompt.opened_at).total_seconds())
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        prefix = "已等待"
        self.prompt.elapsed.config(text=f"{prefix} {hours:02d}:{minutes:02d}:{seconds:02d}，填写后才能继续。")
        self.root.after(1000, self._update_elapsed)

    def _save_prompt(self) -> None:
        if self.prompt is None:
            return
        activity = self.prompt.text.get("1.0", "end-1c").strip()
        if not activity:
            messagebox.showwarning(APP_NAME, "请先填写这一个小时做的事情。", parent=self.prompt.window)
            self.prompt.text.focus_set()
            return
        now = datetime.now()
        try:
            with LOG_FILE.open("a", newline="", encoding="utf-8-sig") as file:
                csv.writer(file).writerow([
                    self.prompt.period_started_at.isoformat(timespec="seconds"),
                    now.isoformat(timespec="seconds"),
                    activity,
                ])
        except OSError as error:
            messagebox.showerror(APP_NAME, f"无法写入记录文件：\n{error}", parent=self.prompt.window)
            return
        is_clock_out = self.prompt.is_clock_out
        self.prompt.window.destroy()
        self.prompt = None
        if is_clock_out:
            self.working = False
            self.next_due = None
            self.period_started_at = None
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")
            self.manual_button.config(state="disabled")
            self.status.config(text="下班记录已保存，提醒已暂停。")
        elif self.working:
            self.period_started_at = now
            self.next_due = now + timedelta(seconds=self.interval_seconds)
            self.status.config(text="已保存，下一小时后再提醒。")

    def _ensure_log_file(self) -> None:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not LOG_FILE.exists():
            with LOG_FILE.open("w", newline="", encoding="utf-8-sig") as file:
                csv.writer(file).writerow(["记录周期开始", "提交时间", "这段时间做的事情"])

    def _bring_to_front(self) -> None:
        if self.prompt is not None:
            self.prompt.window.attributes("-topmost", True)
            self.prompt.window.lift()
            self.prompt.window.focus_force()

    @staticmethod
    def _make_window_prominent(window: tk.Toplevel) -> None:
        # Keep it above normal Windows.  Tk's topmost flag is sufficient in most cases;
        # this explicit Windows call makes the intent more reliable on Windows 11.
        try:
            HWND_TOPMOST = -1
            SWP_NOMOVE, SWP_NOSIZE = 0x0002, 0x0001
            ctypes.windll.user32.SetWindowPos(window.winfo_id(), HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
        except (AttributeError, OSError):
            pass

    def _refuse_close(self) -> None:
        messagebox.showinfo(APP_NAME, "请填写并保存后关闭此窗口。", parent=self.prompt.window if self.prompt else self.root)

    def _quit(self) -> None:
        if self.prompt is not None:
            self._refuse_close()
            return
        self.root.destroy()

    @staticmethod
    def _center_window(window: tk.Toplevel) -> None:
        window.update_idletasks()
        width, height = 620, 420
        x = (window.winfo_screenwidth() - width) // 2
        y = (window.winfo_screenheight() - height) // 2
        window.geometry(f"{width}x{height}+{x}+{y}")


def get_interval_seconds() -> int:
    """Allow a short interval for development: `python hourly_reminder.py 10`."""
    if len(sys.argv) == 2:
        try:
            return max(1, int(sys.argv[1]))
        except ValueError:
            print("可选参数必须是间隔秒数，例如：python hourly_reminder.py 10", file=sys.stderr)
            raise SystemExit(2)
    return DEFAULT_INTERVAL_SECONDS


if __name__ == "__main__":
    app = tk.Tk()
    HourlyReminder(app, get_interval_seconds())
    app.mainloop()
