"""Windows 11 hourly activity reminder.

Only Python's standard library is required.  Run with:
    python hourly_reminder.py
"""

from __future__ import annotations

import csv
import ctypes
import json
import os
import subprocess
import sys
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

from holiday_calendar import is_china_legal_workday


APP_NAME = "Work Log"
DEFAULT_INTERVAL_SECONDS = 60 * 60
SCHEDULE_REMINDER_WINDOW = timedelta(minutes=30)
# Keep the original directory so upgrading never loses existing records/settings.
APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "HourlyReminder"
SETTINGS_FILE = APP_DATA_DIR / "settings.json"


def load_settings() -> dict[str, object]:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(settings: dict[str, object]) -> None:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def get_log_directory() -> Path:
    """Use the folder selected during installation, with a safe default."""
    selected_directory = load_settings().get("log_directory")
    if isinstance(selected_directory, str) and selected_directory:
        return Path(selected_directory)
    return APP_DATA_DIR


def get_log_file(when: datetime | None = None) -> Path:
    """Return this month's append-only log file; never replace old logs."""
    timestamp = when or datetime.now()
    return get_log_directory() / f"activity_log_{timestamp:%Y-%m}.csv"


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
        settings = load_settings()
        start_hour, start_minute = self._split_time(settings.get("start_time", "09:00"), "09:00")
        end_hour, end_minute = self._split_time(settings.get("end_time", "18:00"), "18:00")
        self.start_hour_var = tk.StringVar(value=start_hour)
        self.start_minute_var = tk.StringVar(value=start_minute)
        self.end_hour_var = tk.StringVar(value=end_hour)
        self.end_minute_var = tk.StringVar(value=end_minute)
        mode = settings.get("schedule_mode", "daily")
        self.schedule_mode_var = tk.StringVar(value=mode if mode in {"daily", "legal_workdays"} else "daily")
        stored_calendar = settings.get("holiday_calendar", {})
        self.holiday_calendar: dict[str, dict[str, bool]] = stored_calendar if isinstance(stored_calendar, dict) else {}
        self.decision_window: tk.Toplevel | None = None
        self.decision_opened_at: datetime | None = None
        self.start_prompted_date: str | None = None
        self.end_prompted_date: str | None = None

        self.root.title(APP_NAME)
        self.root.geometry("480x495")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)
        self._build_main_window()
        self._ensure_log_file()
        self._tick()

    def _build_main_window(self) -> None:
        frame = tk.Frame(self.root, padx=26, pady=24)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Work Log", font=("Microsoft YaHei UI", 20, "bold")).pack(anchor="w")
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
        self.autostart_var = tk.BooleanVar(value=self._startup_shortcut().exists())
        tk.Checkbutton(
            frame, text="开机自动启动", variable=self.autostart_var,
            command=self._toggle_autostart, font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(12, 0))
        schedule = tk.LabelFrame(frame, text="上下班时间（24 小时制）", padx=10, pady=8)
        schedule.pack(fill="x", pady=(12, 0))
        hours = tuple(f"{value:02d}" for value in range(24))
        minutes = tuple(f"{value:02d}" for value in range(60))

        def time_picker(row: int, label: str, hour: tk.StringVar, minute: tk.StringVar) -> None:
            tk.Label(schedule, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Spinbox(schedule, values=hours, textvariable=hour, width=3, state="readonly", wrap=True).grid(row=row, column=1, padx=(8, 2))
            tk.Label(schedule, text=":").grid(row=row, column=2)
            ttk.Spinbox(schedule, values=minutes, textvariable=minute, width=3, state="readonly", wrap=True).grid(row=row, column=3, padx=(2, 18))

        time_picker(0, "上班", self.start_hour_var, self.start_minute_var)
        time_picker(1, "下班", self.end_hour_var, self.end_minute_var)
        tk.Radiobutton(schedule, text="每天", variable=self.schedule_mode_var, value="daily").grid(row=0, column=4, sticky="w")
        tk.Radiobutton(schedule, text="仅法定工作日", variable=self.schedule_mode_var, value="legal_workdays").grid(row=1, column=4, sticky="w")
        tk.Button(schedule, text="保存时间", command=self._save_schedule).grid(row=0, column=5, rowspan=2, padx=(12, 0))
        tk.Label(
            schedule, text=self._holiday_calendar_status(),
            fg="#666666", font=("Microsoft YaHei UI", 8),
        ).grid(row=2, column=0, columnspan=6, sticky="w", pady=(6, 0))
        tk.Label(
            frame,
            text=(
                f"本月记录文件：{get_log_file()}\n"
                "旧版 activity_log.csv 会永久保留，不会在升级时删除。"
            ),
            fg="#666666",
            font=("Microsoft YaHei UI", 9), justify="left", wraplength=425,
        ).pack(anchor="w", pady=(18, 0))

    def _tick(self) -> None:
        now = datetime.now()
        self._check_work_schedule(now)
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

    @staticmethod
    def _parse_time(value: str) -> datetime.time | None:
        try:
            return datetime.strptime(value.strip(), "%H:%M").time()
        except ValueError:
            return None

    @staticmethod
    def _split_time(value: str, fallback: str) -> tuple[str, str]:
        parsed = HourlyReminder._parse_time(value)
        if parsed is None:
            parsed = datetime.strptime(fallback, "%H:%M").time()
        return f"{parsed.hour:02d}", f"{parsed.minute:02d}"

    def _selected_time(self, hour: tk.StringVar, minute: tk.StringVar) -> str:
        return f"{hour.get()}:{minute.get()}"

    def _save_schedule(self) -> None:
        start_text = self._selected_time(self.start_hour_var, self.start_minute_var)
        end_text = self._selected_time(self.end_hour_var, self.end_minute_var)
        start = self._parse_time(start_text)
        end = self._parse_time(end_text)
        if start is None or end is None or start >= end:
            messagebox.showwarning(
                APP_NAME, "请输入有效时间，例如 09:00 和 18:00；下班时间应晚于上班时间。",
                parent=self.root,
            )
            return
        settings = load_settings()
        settings["start_time"] = start_text
        settings["end_time"] = end_text
        settings["schedule_mode"] = self.schedule_mode_var.get()
        try:
            save_settings(settings)
        except OSError as error:
            messagebox.showerror(APP_NAME, f"无法保存上下班时间：\n{error}", parent=self.root)
            return
        self.start_prompted_date = None
        self.end_prompted_date = None
        self.status.config(text=f"上下班时间已保存：{settings['start_time']} - {settings['end_time']}")

    def _holiday_calendar_status(self) -> str:
        years = sorted(year for year, days in self.holiday_calendar.items() if isinstance(days, dict))
        if years:
            return "法定节假日与调休日历已下载：" + "、".join(years)
        return "尚未下载法定节假日日历；重新运行安装包并联网后可启用。"

    def _check_work_schedule(self, now: datetime) -> None:
        if self.prompt is not None or self.decision_window is not None:
            return
        if self.schedule_mode_var.get() == "legal_workdays":
            legal_workday = is_china_legal_workday(now.date(), self.holiday_calendar)
            if legal_workday is None:
                return
            if not legal_workday:
                return
        start_text = self._selected_time(self.start_hour_var, self.start_minute_var)
        end_text = self._selected_time(self.end_hour_var, self.end_minute_var)
        start = self._parse_time(start_text)
        end = self._parse_time(end_text)
        if start is None or end is None or start >= end:
            return
        today = now.date().isoformat()
        scheduled_start = now.replace(
            hour=start.hour, minute=start.minute, second=0, microsecond=0,
        )
        scheduled_end = now.replace(
            hour=end.hour, minute=end.minute, second=0, microsecond=0,
        )
        in_start_window = (
            scheduled_start - SCHEDULE_REMINDER_WINDOW <= now
            <= scheduled_start + SCHEDULE_REMINDER_WINDOW
        )
        in_end_window = (
            scheduled_end - SCHEDULE_REMINDER_WINDOW <= now
            <= scheduled_end + SCHEDULE_REMINDER_WINDOW
        )
        if not self.working and in_start_window and self.start_prompted_date != today:
            self.start_prompted_date = today
            self._show_schedule_decision(is_start=True, scheduled_time=start_text)
        elif self.working and in_end_window and self.end_prompted_date != today:
            self.end_prompted_date = today
            self._show_schedule_decision(is_start=False, scheduled_time=end_text)

    def _show_schedule_decision(self, is_start: bool, scheduled_time: str) -> None:
        window = tk.Toplevel(self.root)
        self.decision_window = window
        self.decision_opened_at = datetime.now()
        window.title("上班确认" if is_start else "下班确认")
        window.configure(bg="#f7f7f7")
        window.attributes("-fullscreen", True)
        window.attributes("-topmost", True)
        window.protocol("WM_DELETE_WINDOW", lambda: None)
        window.bind("<Alt-F4>", lambda _event: "break")
        body = tk.Frame(window, bg="#f7f7f7", padx=50, pady=45)
        body.pack(fill="both", expand=True)
        action = "开始上班" if is_start else "开始下班"
        tk.Label(body, text=f"现在是 {datetime.now().strftime('%H:%M')}", bg="#f7f7f7", font=("Microsoft YaHei UI", 15)).pack(anchor="w")
        tk.Label(body, text=f"已到设定{action}时间（{scheduled_time}）", bg="#f7f7f7", font=("Microsoft YaHei UI", 24, "bold")).pack(anchor="w", pady=(14, 8))
        tk.Label(body, text=f"是否{action}？", bg="#f7f7f7", font=("Microsoft YaHei UI", 17)).pack(anchor="w")
        elapsed = tk.Label(body, bg="#f7f7f7", fg="#b42318", font=("Microsoft YaHei UI", 11))
        elapsed.pack(anchor="w", pady=(12, 28))
        buttons = tk.Frame(body, bg="#f7f7f7")
        buttons.pack(anchor="w")

        def choose_yes() -> None:
            self._close_schedule_decision()
            if is_start:
                self._start_work()
            else:
                self._stop_work()

        def choose_no() -> None:
            self._close_schedule_decision()
            self.status.config(text="已跳过本次" + action + "确认；仍可在主界面手动操作。")

        tk.Button(buttons, text="是，" + action, command=choose_yes, bg="#1677ff", fg="white", width=16, pady=8).pack(side="left")
        tk.Button(buttons, text="暂不" + action, command=choose_no, width=16, pady=8).pack(side="left", padx=(12, 0))

        def update_waiting() -> None:
            if self.decision_window is not window or self.decision_opened_at is None:
                return
            waited = int((datetime.now() - self.decision_opened_at).total_seconds())
            minutes, seconds = divmod(waited, 60)
            elapsed.config(text=f"等待选择：{minutes:02d}:{seconds:02d}")
            window.after(1000, update_waiting)

        self._make_window_prominent(window)
        window.after(80, lambda: self._make_window_prominent(window))
        update_waiting()

    def _close_schedule_decision(self) -> None:
        if self.decision_window is not None:
            self.decision_window.destroy()
        self.decision_window = None
        self.decision_opened_at = None

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

    @staticmethod
    def _startup_shortcut() -> Path:
        return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{APP_NAME}.lnk"

    def _toggle_autostart(self) -> None:
        shortcut = self._startup_shortcut()
        if not self.autostart_var.get():
            try:
                shortcut.unlink(missing_ok=True)
            except OSError as error:
                self.autostart_var.set(True)
                messagebox.showerror(APP_NAME, f"无法取消开机启动：\n{error}", parent=self.root)
            return
        target = Path(sys.executable)
        arguments = "" if getattr(sys, "frozen", False) else f'"{Path(__file__).resolve()}"'
        # PowerShell does not reliably expose arguments appended after -Command
        # as $args on every Windows configuration.  Use literal, escaped paths.
        def ps_literal(value: str) -> str:
            return "'" + value.replace("'", "''") + "'"

        target_text = ps_literal(str(target))
        command = (
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut("
            f"{ps_literal(str(shortcut))});"
            f"$s.TargetPath={target_text};$s.Arguments={ps_literal(arguments)};"
            f"$s.WorkingDirectory={ps_literal(str(target.parent))};"
            f"$s.IconLocation={target_text}+',0';$s.Save()"
        )
        try:
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                check=True, creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError) as error:
            self.autostart_var.set(False)
            messagebox.showerror(APP_NAME, f"无法启用开机启动：\n{error}", parent=self.root)

    def _show_prompt(self, is_clock_out: bool = False) -> None:
        if self.prompt is not None:
            self._bring_to_front()
            return

        opened_at = datetime.now()
        period_started_at = self.period_started_at or opened_at
        window = tk.Toplevel(self.root)
        window.title("下班前填写" if is_clock_out else "请记录刚刚这一小时")
        window.configure(bg="#f7f7f7")
        # Fullscreen visual reminder.  Do not globally capture keyboard/mouse
        # input: the text field must remain usable and Windows controls stay safe.
        window.attributes("-fullscreen", True)
        window.attributes("-topmost", True)
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
        tk.Label(
            body,
            text=(
                f"本次填写时间段：{period_started_at.strftime('%Y-%m-%d %H:%M')} "
                f"至 {opened_at.strftime('%Y-%m-%d %H:%M')}"
            ),
            bg="#f7f7f7", fg="#444444", font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(8, 0))
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
            period_started_at, opened_at, window, text, elapsed, is_clock_out,
        )
        self.status.config(text="正在等待下班记录；保存后结束本次上班。" if is_clock_out else "正在等待填写；新的提醒已暂停。")
        self._make_window_prominent(window)
        # A minimized/behind main window must not keep the reminder hidden.
        window.after(80, lambda: self._make_window_prominent(window))
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
        log_file = get_log_file(now)
        try:
            self._ensure_log_file(log_file)
            with log_file.open("a", newline="", encoding="utf-8-sig") as file:
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

    def _ensure_log_file(self, log_file: Path | None = None) -> None:
        """Create only a missing monthly file; existing history is immutable."""
        target = log_file or get_log_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with target.open("w", newline="", encoding="utf-8-sig") as file:
                csv.writer(file).writerow(["记录周期开始", "提交时间", "这段时间做的事情"])

    def _bring_to_front(self) -> None:
        if self.prompt is not None:
            self.prompt.window.attributes("-topmost", True)
            self.prompt.window.lift()
            self.prompt.window.focus_force()

    @staticmethod
    def _make_window_prominent(window: tk.Toplevel) -> None:
        """Restore and show a reminder even if the app was in the background."""
        try:
            HWND_TOPMOST = -1
            SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW = 0x0002, 0x0001, 0x0040
            SW_RESTORE = 9
            window.deiconify()
            window.lift()
            window.update_idletasks()
            hwnd = window.winfo_id()
            user32 = ctypes.windll.user32
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetWindowPos(
                hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
            )
            user32.SetForegroundWindow(hwnd)
            window.focus_force()
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
