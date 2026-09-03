# Work Log (Windows 11)

[English](#english) | [中文](#中文)

## 中文

Work Log 是一个 Windows 11 桌面工作记录与提醒工具。开始上班后，它会按设定时间提醒你记录工作内容，并在下班时要求完成最后一段工作记录。

### 安装与运行

1. 双击 [dist\WorkLogSetup.exe](dist/WorkLogSetup.exe)。
2. 安装时选择活动记录保存位置；默认会联网下载中国大陆当年与下一年的法定节假日、调休工作日日历。
3. 安装完成后，从开始菜单打开 **Work Log**。

安装包内置 Python 运行环境，目标电脑不需要另行安装 Python。

### 功能

- 点击“开始上班”后，每小时全屏提醒填写这段时间做了什么。
- 可用滚动框设定上班、下班时间；仅在设定时间前后 30 分钟内全屏询问是否开始上班或下班。
- 支持“每天”或“仅法定工作日”计划。后者使用安装时保存的中国大陆节假日、调休日历；未下载日历时不可用。
- 选择下班后，必须填写从上次记录到下班这段时间的内容，保存后才会结束当天提醒。
- 全屏提示会显示应填写的时间段和等待时长；未填写时不会创建新的后续提醒。
- 可在主界面启用“开机自动启动”。
- 新记录按时间顺序追加到所选目录的 `activity_log_YYYY-MM.csv`。旧版 `activity_log.csv` 与所有历史月度记录都会保留；重新安装或升级不会删除或覆盖已有记录。

### 安全说明

提示窗口会置顶和全屏显示，但不会全局拦截键盘鼠标。Windows 安全界面、任务管理器及其他系统控制始终可用。

### 从源码测试

确认已安装 Python 3 后，在项目目录运行：

```powershell
python hourly_reminder.py
```

可传入秒数来缩短每小时提醒间隔，例如每 10 秒提醒一次：

```powershell
python hourly_reminder.py 10
```

---

<a id="english"></a>

## English

Work Log is a Windows 11 desktop work-log and reminder app. Once a work session starts, it prompts you to record your activity at scheduled intervals and requires a final entry when you finish work.

### Install and run

1. Run [dist\WorkLogSetup.exe](dist/WorkLogSetup.exe).
2. Choose where to store activity records. By default, the installer downloads and saves the current and next year's Mainland China public-holiday and make-up-workday calendar.
3. Open **Work Log** from the Start menu after installation.

The installer bundles its Python runtime, so the target computer does not need Python installed.

### Features

- After selecting **Start Work**, receive a full-screen prompt every hour to record what you did.
- Set start and end times with hour/minute spin controls; full-screen confirmation appears only within 30 minutes before or after each scheduled time.
- Choose **Every day** or **Legal workdays only**. The latter uses the Mainland China holiday and make-up-workday calendar saved during installation, and is unavailable when that calendar was not downloaded.
- Choosing to finish work requires a final activity entry covering the period since the previous record.
- Prompts show the requested time range and how long they have been waiting. An unanswered prompt prevents later reminders from being created.
- Enable or disable launch at Windows sign-in from the main window.
- Entries are appended in chronological order to monthly `activity_log_YYYY-MM.csv` files in the selected folder. Legacy `activity_log.csv` and all historical monthly files are preserved: reinstalling or upgrading never deletes or overwrites records.

### Safety

Prompts are full-screen and topmost, but they do not globally capture the keyboard or mouse. Windows security controls, Task Manager, and other system controls remain available.

### Run from source

With Python 3 installed, run the following in the project directory:

```powershell
python hourly_reminder.py
```

For a short test interval, pass a number of seconds. For example, this prompts every 10 seconds:

```powershell
python hourly_reminder.py 10
```
