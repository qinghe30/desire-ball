import tkinter as tk
from tkinter import messagebox
import json
import os
import sys
import winsound
import math
import urllib.request
import urllib.error
from datetime import datetime

# ---------- 飞书反馈 Webhook ----------
FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/214ebe5a-96d1-4bd8-9e2b-6763e1b63d98"

def send_feedback_to_feishu(content, email=""):
    """通过飞书机器人 Webhook 发送反馈"""
    try:
        payload = {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": "DesireBall 用户反馈"},
                    "template": "blue"
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": content
                        }
                    },
                    {"tag": "hr"},
                    {
                        "tag": "note",
                        "elements": [
                            {"tag": "plain_text", "content": f"邮箱: {email if email else '未填写'}  |  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
                        ]
                    }
                ]
            }
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            FEISHU_WEBHOOK,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("code", 0) == 0
    except Exception as e:
        print("反馈发送失败:", e)
        return False

# ---------- 配置持久化 ----------
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config():
    default = {"interval_minutes": 5, "auto_start": False}
    if not os.path.exists(CONFIG_PATH):
        return default
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in default.items():
            cfg.setdefault(k, v)
        # 防御性范围校验：interval_minutes 限制在 1-60 分钟
        mins = cfg.get("interval_minutes")
        if not isinstance(mins, int) or mins < 1 or mins > 60:
            cfg["interval_minutes"] = 5
        return cfg
    except:
        return default

def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# ---------- 开机自启 ----------
def set_auto_start(enable):
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "DesireBall"
    if getattr(sys, 'frozen', False):
        exe_path = sys.executable
    else:
        pythonw = sys.executable.replace("python.exe", "pythonw.exe")
        exe_path = f'"{pythonw}" "{os.path.abspath(__file__)}"'
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print("开机自启设置失败:", e)

def is_auto_start():
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "DesireBall"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(key, app_name)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except:
        return False

# ---------- 主应用 ----------
class DesireBall:
    def __init__(self):
        self.config = load_config()
        self.root = tk.Tk()
        self.root.withdraw()

        self.ball_size = 64
        self.ball = tk.Toplevel(self.root)
        self.ball.overrideredirect(True)
        self.ball.attributes("-topmost", True)
        self.transparent_color = "#010101"
        self.ball.wm_attributes("-transparentcolor", self.transparent_color)
        self.ball.geometry(f"{self.ball_size}x{self.ball_size}+{self.root.winfo_screenwidth()-90}+{self.root.winfo_screenheight()//2}")
        self.ball.configure(bg=self.transparent_color)

        self.canvas = tk.Canvas(self.ball, width=self.ball_size, height=self.ball_size,
                                bg=self.transparent_color, highlightthickness=0)
        self.canvas.pack()

        self.draw_ball()

        self.canvas.bind("<Button-3>", self.show_context_menu)
        self.canvas.bind("<ButtonPress-1>", self.start_move)
        self.canvas.bind("<B1-Motion>", self.do_move)
        self.canvas.bind("<ButtonRelease-1>", self.end_move)

        self.popup_win = None
        self.popup_canvas = None
        self.option_items = []

        self.timer_job = None
        self.schedule_next_pop()

        # 标记当前 popup 是否由定时器自动触发，决定关闭后是否重置定时器
        self.is_auto_popup = False
        # 悬浮球呼吸动画状态
        self._breathing_scale = 1.0
        self._breathing_phase = 0.0
        self._breathing_paused = False
        self.start_breathing()

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="设置频率", command=self.set_interval)
        self.auto_start_var = tk.BooleanVar(value=self.config.get("auto_start", False))
        self.menu.add_checkbutton(label="开机自启", variable=self.auto_start_var, command=self.toggle_auto_start)
        self.menu.add_separator()
        self.menu.add_command(label="反馈建议", command=self.open_feedback_dialog)
        self.menu.add_separator()
        self.menu.add_command(label="退出", command=self.quit_app)

        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)

    # ---------- 悬浮球绘制与交互 ----------
    def draw_ball(self):
        self.canvas.delete("all")
        cx = cy = self.ball_size // 2
        r0 = self.ball_size // 2 - 4
        # 呼吸缩放系数（外部动画循环更新，未启动时默认 1.0）
        s = getattr(self, '_breathing_scale', 1.0)
        r = r0 * s

        # 玻璃态渐变：外层亮蓝高光
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                fill="#E0EBFF", outline="", tags="clickable")
        # 中层渐变
        self.canvas.create_oval(cx - r*0.9, cy - r*0.9, cx + r*0.9, cy + r*0.9,
                                fill="#8AB4F8", outline="", tags="clickable")
        # 中心主色
        self.canvas.create_oval(cx - r*0.75, cy - r*0.75, cx + r*0.75, cy + r*0.75,
                                fill="#007AFF", outline="", tags="clickable")
        # 顶部高光条
        self.canvas.create_oval(cx - r*0.6, cy - r*0.8, cx + r*0.6, cy + r*0.1,
                                fill="#5EACFF", outline="", tags="clickable")

        # 中心双白色胶囊眼睛（参考参考图样式）
        eye_w = 6 * s
        eye_h = 16 * s
        eye_spacing = 10 * s
        eye_r = eye_w / 2
        # 左眼
        x1, y1 = cx - eye_spacing/2 - eye_w, cy - eye_h/2
        x2, y2 = cx - eye_spacing/2, cy + eye_h/2
        self.canvas.create_oval(x1, y1, x1+eye_w, y1+eye_w, fill="white", outline="", tags="clickable")
        self.canvas.create_oval(x1, y2-eye_w, x1+eye_w, y2, fill="white", outline="", tags="clickable")
        self.canvas.create_rectangle(x1, y1+eye_r, x1+eye_w, y2-eye_r, fill="white", outline="", tags="clickable")
        # 右眼
        x1, y1 = cx + eye_spacing/2, cy - eye_h/2
        x2, y2 = cx + eye_spacing/2 + eye_w, cy + eye_h/2
        self.canvas.create_oval(x1, y1, x1+eye_w, y1+eye_w, fill="white", outline="", tags="clickable")
        self.canvas.create_oval(x1, y2-eye_w, x1+eye_w, y2, fill="white", outline="", tags="clickable")
        self.canvas.create_rectangle(x1, y1+eye_r, x1+eye_w, y2-eye_r, fill="white", outline="", tags="clickable")

        self.canvas.tag_bind("clickable", "<Button-1>", self.on_ball_click)

    def start_move(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self._drag_x = event.x
        self._drag_y = event.y
        self._pause_breathing()

    def do_move(self, event):
        dx = event.x - self._drag_x
        dy = event.y - self._drag_y
        new_x = self.ball.winfo_x() + dx
        new_y = self.ball.winfo_y() + dy
        # 拖动时先隐藏窗口再移动，避免残影
        self.ball.withdraw()
        self.ball.geometry(f"+{new_x}+{new_y}")
        self.ball.deiconify()
        self._drag_x = event.x
        self._drag_y = event.y
        if self.popup_win and self.popup_win.winfo_exists():
            self.update_popup_position()

    def end_move(self, event):
        self._resume_breathing()
        # 判断是否真正发生了点击（全程拖动距离 < 3px），是则才打开弹窗
        if hasattr(self, '_drag_start_x'):
            total_dx = abs(event.x - self._drag_start_x)
            total_dy = abs(event.y - self._drag_start_y)
            if total_dx <= 3 and total_dy <= 3:
                self.is_auto_popup = False
                self.open_popup()

    def show_context_menu(self, event):
        self.menu.tk_popup(event.x_root, event.y_root)

    def on_ball_click(self, event):
        # 仅处理弹窗已打开时点击关闭，打开弹窗的逻辑在 end_move 中判断
        if self.popup_win and self.popup_win.winfo_exists():
            self.close_popup()

    # ---------- 通用定位方法 ----------
    def calc_position_relative_to_ball(self, popup_w, popup_h):
        """根据悬浮球位置计算窗口坐标"""
        bx = self.ball.winfo_x()
        by = self.ball.winfo_y()
        ball_w = self.ball_size
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        x = bx + ball_w + 10
        y = by - 10
        if x + popup_w > screen_w:
            x = bx - popup_w - 10
        if x < 0:
            x = 10
        if x + popup_w > screen_w:
            x = screen_w - popup_w - 10
        if y + popup_h > screen_h:
            y = screen_h - popup_h - 10
        if y < 0:
            y = 10
        return x, y

    def update_popup_position(self):
        if self.popup_win and self.popup_win.winfo_exists():
            x, y = self.calc_position_relative_to_ball(240, 200)  # 弹窗固定尺寸
            self.popup_win.geometry(f"+{x}+{y}")

    # ---------- 提问弹窗 ----------
    def open_popup(self):
        if self.popup_win and self.popup_win.winfo_exists():
            return

        self.popup_win = tk.Toplevel(self.ball)
        self.popup_win.overrideredirect(True)
        self.popup_win.attributes("-topmost", True)
        self.popup_win.configure(bg=self.transparent_color)
        self.popup_win.wm_attributes("-transparentcolor", self.transparent_color)

        popup_w, popup_h = 240, 200
        x, y = self.calc_position_relative_to_ball(popup_w, popup_h)
        self.popup_win.geometry(f"{popup_w}x{popup_h}+{x}+{y}")

        self.popup_canvas = tk.Canvas(self.popup_win, width=popup_w, height=popup_h,
                                      bg=self.transparent_color, highlightthickness=0)
        self.popup_canvas.pack()

        r = 20
        self.popup_canvas.create_rounded_rect = self._create_rounded_rect
        self.popup_canvas.create_rounded_rect(5, 5, popup_w-5, popup_h-5, r,
                                              fill="white", outline="#E5E5EA", width=1)
        self.popup_canvas.create_text(popup_w//2, 35, text="这一秒是什么想要",
                                      font=("微软雅黑", 12, "bold"), fill="#1C1C1E")

        options = ["控制", "认同", "安全"]
        btn_w, btn_h = 200, 36
        start_y = 70
        self.option_items = []
        for idx, opt in enumerate(options):
            y_center = start_y + idx * 45
            x1, y1 = (popup_w - btn_w)//2, y_center - btn_h//2
            x2, y2 = x1 + btn_w, y1 + btn_h
            btn_bg = self.popup_canvas.create_rounded_rect(
                x1, y1, x2, y2, radius=18, fill="#F5F5F7", outline="#E5E5EA", width=1)
            btn_text = self.popup_canvas.create_text(popup_w//2, y_center, text=opt,
                                                     font=("微软雅黑", 11), fill="#007AFF")
            self.option_items.append((btn_bg, btn_text, opt))
            self.popup_canvas.tag_bind(btn_bg, "<Button-1>", lambda e, o=opt: self.select_option(o))
            self.popup_canvas.tag_bind(btn_text, "<Button-1>", lambda e, o=opt: self.select_option(o))

        self.popup_win.lift()
        self.popup_win.focus_force()

    def _create_rounded_rect(self, x1, y1, x2, y2, radius=25, **kwargs):
        points = [x1+radius, y1, x1+radius, y1, x2-radius, y1, x2-radius, y1,
                  x2, y1, x2, y1+radius, x2, y1+radius, x2, y2-radius,
                  x2, y2-radius, x2, y2, x2-radius, y2, x2-radius, y2,
                  x1+radius, y2, x1+radius, y2, x1, y2, x1, y2-radius,
                  x1, y2-radius, x1, y1+radius, x1, y1+radius, x1, y1]
        return self.popup_canvas.create_polygon(points, smooth=True, **kwargs)

    def select_option(self, option):
        for bg_id, text_id, opt_text in self.option_items:
            self.popup_canvas.tag_unbind(bg_id, "<Button-1>")
            self.popup_canvas.tag_unbind(text_id, "<Button-1>")
            if opt_text == option:
                self.popup_canvas.itemconfig(bg_id, fill="#007AFF", outline="#007AFF")
                self.popup_canvas.itemconfig(text_id, fill="white")
                coords = self.popup_canvas.coords(text_id)
                if coords:
                    cx, cy = coords[0], coords[1]
                    arrow_x = cx - 70
                    self.popup_canvas.create_line(arrow_x-4, cy-6, arrow_x+4, cy, fill="white", width=2.5)
                    self.popup_canvas.create_line(arrow_x+4, cy, arrow_x-4, cy+6, fill="white", width=2.5)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 选择了: {option}")
        if self.is_auto_popup:
            self.root.after(600, self.close_popup_and_reset)
        else:
            self.root.after(600, self.close_popup)
        self.is_auto_popup = False

    def close_popup_and_reset(self):
        self.close_popup()
        self.schedule_next_pop()

    def close_popup(self):
        if self.popup_win:
            self.popup_win.destroy()
            self.popup_win = None
            self.popup_canvas = None
        self.option_items = []

    # ---------- 呼吸动画 ----------
    def start_breathing(self):
        self._breath_job = self.root.after(50, self._animate_breath)

    def _animate_breath(self):
        if not getattr(self, '_breathing_paused', False):
            self._breathing_scale = 1.0 + 0.04 * math.sin(self._breathing_phase * 2 * math.pi)
            self._breathing_phase = (self._breathing_phase + 0.05) % 1.0
            self.draw_ball()
        self._breath_job = self.root.after(50, self._animate_breath)

    def _pause_breathing(self):
        self._breathing_paused = True

    def _resume_breathing(self):
        self._breathing_paused = False

    # ---------- 定时器 ----------
    def schedule_next_pop(self):
        if self.timer_job:
            self.root.after_cancel(self.timer_job)
        interval = self.config.get("interval_minutes", 5) * 60 * 1000
        self.timer_job = self.root.after(interval, self.timed_pop)

    def timed_pop(self):
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
        if self.popup_win and self.popup_win.winfo_exists():
            self.schedule_next_pop()
            return
        self.is_auto_popup = True
        self.open_popup()

    # ---------- 设置窗口 ----------
    def set_interval(self):
        dialog = tk.Toplevel(self.ball)
        dialog.title("设置频率")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        dw, dh = 260, 120
        x, y = self.calc_position_relative_to_ball(dw, dh)
        dialog.geometry(f"{dw}x{dh}+{x}+{y}")

        tk.Label(dialog, text="弹出间隔（分钟）：", font=("微软雅黑", 10)).pack(pady=(20,5))
        entry_var = tk.StringVar(value=str(self.config.get("interval_minutes", 5)))
        entry = tk.Entry(dialog, textvariable=entry_var, width=10, font=("微软雅黑", 10))
        entry.pack()

        def save_interval():
            try:
                mins = int(entry_var.get())
                if mins < 1 or mins > 60:
                    raise ValueError
                self.config["interval_minutes"] = mins
                save_config(self.config)
                self.schedule_next_pop()
                dialog.destroy()
            except:
                messagebox.showerror("错误", "请输入 1-60 之间的整数", parent=dialog)

        btn = tk.Button(dialog, text="保存", command=save_interval, bg="#007AFF", fg="white")
        btn.pack(pady=10)

    def toggle_auto_start(self):
        enable = self.auto_start_var.get()
        self.config["auto_start"] = enable
        save_config(self.config)
        set_auto_start(enable)

    # ---------- 反馈窗口 ----------
    def open_feedback_dialog(self):
        dialog = tk.Toplevel(self.ball)
        dialog.title("反馈建议")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        dw, dh = 340, 280
        x, y = self.calc_position_relative_to_ball(dw, dh)
        dialog.geometry(f"{dw}x{dh}+{x}+{y}")

        tk.Label(dialog, text="您的意见或建议", font=("微软雅黑", 10, "bold")).pack(pady=(15,5))
        text_var = tk.Text(dialog, width=36, height=7, font=("微软雅黑", 9),
                           wrap="word", relief="solid", bd=1)
        text_var.pack(padx=15)
        text_var.focus()

        tk.Label(dialog, text="邮箱（选填，方便我们回复您）", font=("微软雅黑", 8)).pack(pady=(8,2))
        email_var = tk.StringVar()
        tk.Entry(dialog, textvariable=email_var, width=36, font=("微软雅黑", 9)).pack()

        def submit_feedback():
            content = text_var.get("1.0", "end").strip()
            if not content:
                messagebox.showwarning("提示", "请填写反馈内容", parent=dialog)
                return
            email = email_var.get().strip()
            success = send_feedback_to_feishu(content, email)
            if success:
                messagebox.showinfo("感谢", "反馈已提交，感谢您的建议！", parent=dialog)
                dialog.destroy()
            else:
                messagebox.showerror("错误", "反馈发送失败，请检查网络连接", parent=dialog)

        btn = tk.Button(dialog, text="提交反馈", command=submit_feedback,
                        bg="#007AFF", fg="white", font=("微软雅黑", 10))
        btn.pack(pady=12)

    def quit_app(self):
        if self.timer_job:
            self.root.after_cancel(self.timer_job)
        if getattr(self, '_breath_job', None):
            self.root.after_cancel(self._breath_job)
        save_config(self.config)
        self.root.quit()
        self.root.destroy()
        sys.exit(0)

    def run(self):
        current_auto = is_auto_start()
        self.auto_start_var.set(current_auto)
        self.config["auto_start"] = current_auto
        save_config(self.config)
        self.root.mainloop()

if __name__ == "__main__":
    app = DesireBall()
    app.run()