"""
日报填报工具 - GUI 主程序
打包命令见 build.bat
"""
import asyncio
import threading
import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"  # 屏蔽无关库提示
# 屏蔽 libpng iCCP 警告（tkinter 加载内置图标时触发，不影响功能）
import ctypes, sys
if sys.platform == "win32":
    try:
        ctypes.windll.kernel32.SetEnvironmentVariableW("LIBPNG_NO_WARNINGS", "1")
    except Exception:
        pass
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import date, timedelta
from typing import Optional
from playwright.async_api import async_playwright

# ===== 配置 =====
LOGIN_URL    = "https://ihub.testfarm.cn:8020/admin/login"
PROJECT_NAME = "万花筒工具平台"

DAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# ===== 日期工具 =====

def get_week_info(today: date = None):
    if today is None:
        today = date.today()
    year, month = today.year, today.month
    first_day = date(year, month, 1)
    days_to_mon = (7 - first_day.weekday()) % 7
    first_monday = first_day + timedelta(days=days_to_mon)
    if today < first_monday:
        return get_week_info(first_day - timedelta(days=1))
    week_index = (today - first_monday).days // 7
    week_monday = first_monday + timedelta(weeks=week_index)
    week_sunday = week_monday + timedelta(days=6)
    CN = ["一","二","三","四","五","六","七","八"]
    fmt = lambda d: f"{d.month}.{d.day}"
    return {
        "year_month": f"{year}{month:02d}",
        "year_month_label": f"{year}年{month}月",
        "week_label": f"第{CN[min(week_index,7)]}周({fmt(week_monday)}-{fmt(week_sunday)})",
    }

def get_day_label(today: date = None):
    return DAYS[(today or date.today()).weekday()]


# ===== 自动化核心 =====

async def submit_report(content: str, log_fn, email: str, password: str, today: date = None):
    """无头浏览器执行填报，log_fn 用于向 GUI 输出日志"""
    if today is None:
        today = date.today()

    wi = get_week_info(today)
    day_label = get_day_label(today)
    target_day = day_label          # e.g. "周五"

    def log(msg): log_fn(msg)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)   # 🔕 无界面
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        page.set_default_timeout(30000)

        try:
            # ---------- 登录 ----------
            log("🔐 正在登录...")
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            await page.locator("input[placeholder='邮箱']").fill(email)
            await page.locator("input[placeholder='密码']").fill(password)
            await page.locator("button.button.large.align-center.normal").click()
            await asyncio.sleep(5)
            log(f"✅ 登录成功")

            # ---------- 进入项目 ----------
            log("📂 导航到项目页面...")
            nav = page.locator(".el-menu-item:has-text('项目')")
            if await nav.count() > 0:
                await nav.click()
            else:
                await page.goto("https://ihub.testfarm.cn:8020/admin/new-work-item/project",
                                wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # ---------- 等待项目出现 ----------
            log(f"🔍 查找项目 '{PROJECT_NAME}'...")
            try:
                await page.locator(f"text={PROJECT_NAME}").first.wait_for(state="visible", timeout=15000)
            except:
                for _ in range(5):
                    await page.evaluate("window.scrollBy(0, 300)")
                    await asyncio.sleep(1)
                    try:
                        await page.locator(f"text={PROJECT_NAME}").first.wait_for(state="visible", timeout=3000)
                        break
                    except:
                        pass
                else:
                    log("❌ 未找到项目，请检查账号权限")
                    return False

            # ---------- 悬停 -> 查看工作项 ----------
            log("🖱 打开工作项...")
            project_node = page.locator(".el-tree-node").filter(has_text=PROJECT_NAME).first
            await project_node.hover()
            await asyncio.sleep(2)

            # 尝试点击 dropdown
            dropdown = project_node.locator(".el-dropdown, .el-dropdown-link").first
            if await dropdown.count() > 0 and await dropdown.is_visible():
                await dropdown.hover()
                await asyncio.sleep(1)

            clicked = await page.evaluate("""() => {
                for (const el of document.querySelectorAll('li,span,a,div,.el-dropdown-menu__item')) {
                    const t = el.textContent.trim();
                    if (t === '查看工作项' || (t.includes('查看工作项') && el.children.length === 0)) {
                        const r = el.getBoundingClientRect(), s = window.getComputedStyle(el);
                        if (r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden') {
                            (el.closest('li,a,[role="menuitem"]') || el).click();
                            return true;
                        }
                    }
                }
                return false;
            }""")
            if not clicked:
                log("❌ 无法打开工作项菜单")
                return False
            await asyncio.sleep(4)
            log("✅ 已进入工作项")

            # ---------- 展开树节点 ----------
            log(f"📅 展开 {wi['year_month_label']} / {wi['week_label']}...")
            tree_keywords = ["工具小组的日报", wi["year_month_label"], wi["week_label"]]

            for kw in tree_keywords:
                loc = page.locator(".el-tree-node__content").filter(has_text=kw).last
                try:
                    await loc.wait_for(state="visible", timeout=10000)
                    await loc.scroll_into_view_if_needed()
                    icon = loc.locator(".el-tree-node__expand-icon").first
                    if await icon.count() > 0:
                        cls = await icon.get_attribute("class") or ""
                        if "expanded" not in cls and "is-leaf" not in cls:
                            await icon.click()
                        else:
                            await loc.click()
                    else:
                        await loc.click()
                    await asyncio.sleep(2)
                    log(f"  ✅ 展开: {kw}")
                except Exception as e:
                    log(f"  ⚠ 展开失败 '{kw}': {e}")

            # ---------- 点击张宁节点 ----------
            log("👤 定位张宁日报节点...")
            target_loc = (page.locator(".el-tree-node__content")
                          .filter(has_text="张宁")
                          .filter(has_text=wi["year_month"])
                          .last)
            found = False
            try:
                await target_loc.wait_for(state="visible", timeout=10000)
                await target_loc.scroll_into_view_if_needed()
                await target_loc.click()
                found = True
            except:
                tree = page.locator(".el-tree").first
                if await tree.count() > 0:
                    for _ in range(5):
                        await tree.evaluate("el => el.parentElement.scrollBy(0,300)")
                        await asyncio.sleep(1)
                        if await target_loc.is_visible():
                            await target_loc.click()
                            found = True
                            break
            if not found:
                log("❌ 未找到张宁日报节点（可能本周尚未建单）")
                return False
            await asyncio.sleep(3)
            log(f"✅ 已进入日报页面")

            # ---------- 点击今日日报编辑 ----------
            log(f"✏️  点击 [{target_day}日报] 编辑...")
            clicked_edit = await page.evaluate("""(day) => {
                const h = [...document.querySelectorAll('*')].reverse()
                    .find(el => (el.textContent.trim()===day||el.textContent.trim()===day+'日报') && el.children.length===0);
                if (!h) return false;
                let c = h;
                for (let i=0; i<7; i++) {
                    if (!c.parentElement) break;
                    c = c.parentElement;
                    if (c.innerText?.includes('编辑') && c.innerText?.includes('预览')) {
                        const btn = [...c.querySelectorAll('button,span,a,div')]
                            .find(el => el.textContent.trim()==='编辑' && el.children.length===0);
                        if (btn) { (btn.closest('button,[role="button"]')||btn).click(); return true; }
                    }
                }
                return false;
            }""", target_day)

            if not clicked_edit:
                log(f"❌ 未找到 [{target_day}日报] 的编辑按钮")
                return False

            await asyncio.sleep(2)
            log("✅ 已进入编辑模式")

            # ---------- 写入内容 ----------
            log("📝 写入日报内容...")
            editor = page.locator("textarea:visible, .cm-content:visible, [contenteditable='true']:visible").first
            if await editor.count() == 0:
                log("❌ 未找到编辑器")
                return False

            await editor.click()
            await asyncio.sleep(0.5)
            await page.keyboard.press("Control+a")
            await asyncio.sleep(0.1)
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.1)
            await page.keyboard.type(content, delay=30)
            await asyncio.sleep(1)
            log("✅ 内容已输入")

            # ---------- 预览 ----------
            log("👁 切换预览...")
            await page.evaluate("""(day) => {
                const h = [...document.querySelectorAll('*')].reverse()
                    .find(el => (el.textContent.trim()===day||el.textContent.trim()===day+'日报') && el.children.length===0);
                let c = h;
                for (let i=0; i<7; i++) {
                    if (!c) break;
                    if (c.innerText?.includes('预览')) {
                        const btn = [...c.querySelectorAll('button,span,a,div')]
                            .find(el => el.textContent.trim()==='预览' && el.children.length===0);
                        if (btn) { (btn.closest('button,[role="button"]')||btn).click(); return true; }
                    }
                    c = c.parentElement;
                }
                return false;
            }""", target_day)
            await asyncio.sleep(2)

            # ---------- 保存 ----------
            log("💾 保存...")
            save_btn = page.locator("button").filter(has_text="保存").first
            if await save_btn.count() > 0:
                await save_btn.click()
                try:
                    confirm = page.locator("button").filter(has_text="确认").first
                    await confirm.wait_for(state="visible", timeout=3000)
                    await confirm.click()
                except:
                    try:
                        await page.locator("span").filter(has_text="确认").first.click(timeout=1000)
                    except:
                        pass
                await asyncio.sleep(3)
                log("🎉 提交成功！")
                return True
            else:
                log("⚠ 未找到保存按钮")
                return False

        except Exception as e:
            log(f"❌ 发生错误: {e}")
            return False
        finally:
            await browser.close()


# ===== GUI =====

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("日报填报工具")
        self.resizable(False, False)
        self._build_ui()
        self._update_date_label()

    def _build_ui(self):
        PAD = dict(padx=12, pady=6)

        # ── 顶部：系统日期 + 手动选择 ──────────────────────────
        info_frame = tk.Frame(self, bg="#f0f4ff")
        info_frame.pack(fill="x")

        self.date_label = tk.Label(info_frame, text="", bg="#f0f4ff",
                                   font=("微软雅黑", 10), anchor="w")
        self.date_label.pack(fill="x", padx=12, pady=(8, 2))

        pick_frame = tk.Frame(info_frame, bg="#f0f4ff")
        pick_frame.pack(fill="x", padx=12, pady=(0, 4))

        tk.Label(pick_frame, text="手动指定日期：", bg="#f0f4ff",
                 font=("微软雅黑", 9)).pack(side="left")

        today = date.today()
        self.var_year  = tk.IntVar(value=today.year)
        self.var_month = tk.IntVar(value=today.month)
        self.var_day   = tk.IntVar(value=today.day)

        tk.Spinbox(pick_frame, from_=2024, to=2099, width=6,
                   textvariable=self.var_year,  font=("微软雅黑", 9),
                   command=self._on_date_change).pack(side="left", padx=(0,2))
        tk.Label(pick_frame, text="年", bg="#f0f4ff", font=("微软雅黑", 9)).pack(side="left")
        tk.Spinbox(pick_frame, from_=1, to=12, width=4,
                   textvariable=self.var_month, font=("微软雅黑", 9),
                   command=self._on_date_change).pack(side="left", padx=(4,2))
        tk.Label(pick_frame, text="月", bg="#f0f4ff", font=("微软雅黑", 9)).pack(side="left")
        tk.Spinbox(pick_frame, from_=1, to=31, width=4,
                   textvariable=self.var_day,   font=("微软雅黑", 9),
                   command=self._on_date_change).pack(side="left", padx=(4,2))
        tk.Label(pick_frame, text="日", bg="#f0f4ff", font=("微软雅黑", 9)).pack(side="left")
        tk.Button(pick_frame, text="回到今天", font=("微软雅黑", 9),
                  relief="flat", bg="#dde8ff", cursor="hand2",
                  command=self._reset_to_today).pack(side="left", padx=(12,0))

        self.pick_label = tk.Label(info_frame, text="", bg="#f0f4ff",
                                   font=("微软雅黑", 9), fg="#555", anchor="w")
        self.pick_label.pack(fill="x", padx=12, pady=(0, 6))

        for var in (self.var_year, self.var_month, self.var_day):
            var.trace_add("write", lambda *_: self.after(300, self._on_date_change))

        # ── 账号密码 ───────────────────────────────────────────
        auth_frame = tk.LabelFrame(self, text="账号信息", font=("微软雅黑", 9),
                                   padx=8, pady=6)
        auth_frame.pack(fill="x", padx=12, pady=(4, 2))

        tk.Label(auth_frame, text="邮箱：", font=("微软雅黑", 9)).grid(
            row=0, column=0, sticky="e")
        self.email_var = tk.StringVar(value="XXXX")
        tk.Entry(auth_frame, textvariable=self.email_var, width=36,
                 font=("微软雅黑", 9)).grid(row=0, column=1, sticky="w", padx=(4,20))

        tk.Label(auth_frame, text="密码：", font=("微软雅黑", 9)).grid(
            row=0, column=2, sticky="e")
        self.pwd_var = tk.StringVar(value="XXXX")
        tk.Entry(auth_frame, textvariable=self.pwd_var, width=16,
                 show="●", font=("微软雅黑", 9)).grid(row=0, column=3, sticky="w")

        # ── 日报输入 ───────────────────────────────────────────
        tk.Label(self, text="今日工作内容（支持 Markdown）：",
                 font=("微软雅黑", 10, "bold")).pack(anchor="w", **PAD)

        # 输入区
        self.input_box = scrolledtext.ScrolledText(
            self, width=70, height=3, font=("Consolas", 11),
            wrap=tk.WORD, undo=True
        )
        self.input_box.pack(padx=12, pady=(0, 4))

        # 提示
        hint = ("提示：直接输入 Markdown 格式内容，例如：\n"
                "### 一体化日志填报自动化脚本: \n- 张宁：账号→日期→内容")
        tk.Label(self, text=hint, fg="#888", font=("微软雅黑", 9),
                 justify="left").pack(anchor="w", padx=12)

        # 按钮行
        btn_frame = tk.Frame(self)
        btn_frame.pack(fill="x", padx=12, pady=8)
        self.submit_btn = tk.Button(btn_frame, text="🚀  提交日报",
                                    font=("微软雅黑", 11, "bold"),
                                    bg="#4a7cff", fg="white", relief="flat",
                                    padx=20, pady=6, cursor="hand2",
                                    command=self._on_submit)
        self.submit_btn.pack(side="left")
        tk.Button(btn_frame, text="清空", font=("微软雅黑", 10),
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=lambda: self.input_box.delete("1.0", tk.END)
                  ).pack(side="left", padx=8)

        # 进度条（determinate 模式，单向增长）
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(self, mode="determinate", length=400,
                                        variable=self.progress_var, maximum=100)
        self.progress.pack(padx=12, pady=(0, 4))

        # 状态文字（替代弹窗）
        self.status_label = tk.Label(self, text="", font=("微软雅黑", 9))
        self.status_label.pack(anchor="w", padx=14, pady=(0, 2))

        # 日志区
        tk.Label(self, text="运行日志：", font=("微软雅黑", 9),
                 fg="#555").pack(anchor="w", padx=12)
        self.log_box = scrolledtext.ScrolledText(
            self, width=70, height=8, font=("Consolas", 9),
            state="disabled", bg="#1e1e1e", fg="#d4d4d4"
        )
        self.log_box.pack(padx=12, pady=(0, 12))

    def _get_selected_date(self) -> Optional[date]:
        """从 Spinbox 读取并校验日期，返回 date 对象或 None（非法时）"""
        try:
            y = self.var_year.get()
            m = self.var_month.get()
            d = self.var_day.get()
            return date(y, m, d)
        except Exception:
            return None

    def _reset_to_today(self):
        today = date.today()
        self.var_year.set(today.year)
        self.var_month.set(today.month)
        self.var_day.set(today.day)
        self._on_date_change()

    def _on_date_change(self, *_):
        """Spinbox 变化时同步更新提示标签"""
        d = self._get_selected_date()
        if d is None:
            self.pick_label.config(text="⚠ 日期无效", fg="red")
            return
        wi = get_week_info(d)
        dl = get_day_label(d)
        is_today = (d == date.today())
        tag = "（今天）" if is_today else ""
        self.pick_label.config(
            text=f"  → {dl}{tag}  {wi['year_month_label']} {wi['week_label']}  ｜  将写入：{dl}日报",
            fg="#4a7cff"
        )

    def _update_date_label(self):
        today = date.today()
        wi = get_week_info(today)
        dl = get_day_label(today)
        self.date_label.config(
            text=f"📅  系统日期：{today.strftime('%Y年%m月%d日')}  {dl}  ｜  "
                 f"{wi['year_month_label']} {wi['week_label']}"
        )
        self._on_date_change()   # 同步初始化手动选择提示

    def _log(self, msg: str):
        """线程安全写日志，同时推进进度条"""
        # 根据关键日志步骤映射进度值
        STEP_MAP = {
            "🔐": 5, "✅ 登录成功": 15, "📂": 20, "🔍": 28,
            "🖱": 35, "✅ 已进入工作项": 45, "📅": 52,
            "👤": 62, "✅ 已进入日报页面": 70, "✏️": 75,
            "✅ 已进入编辑模式": 82, "📝": 87, "✅ 内容已输入": 91,
            "👁": 94, "💾": 97, "🎉": 100,
        }
        def _inner():
            self.log_box.config(state="normal")
            self.log_box.insert(tk.END, msg + "\n")
            self.log_box.see(tk.END)
            self.log_box.config(state="disabled")
            for key, val in STEP_MAP.items():
                if key in msg:
                    cur = self.progress_var.get()
                    if val > cur:
                        self.progress_var.set(val)
                    break
        self.after(0, _inner)

    def _set_busy(self, busy: bool):
        def _inner():
            if busy:
                self.submit_btn.config(state="disabled", text="⏳  提交中...")
                self.progress_var.set(0)
                self.status_label.config(text="")
            else:
                self.submit_btn.config(state="normal", text="🚀  提交日报")
        self.after(0, _inner)

    def _set_status(self, ok: bool):
        def _inner():
            if ok:
                self.status_label.config(text="🎉 日报提交成功！", fg="#1a9c3e")
            else:
                self.status_label.config(text="❌ 提交失败，请查看日志", fg="#cc0000")
        self.after(0, _inner)

    def _on_submit(self):
        content = self.input_box.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("提示", "请先输入今日工作内容！")
            return

        # 清空日志
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.config(state="disabled")

        email    = self.email_var.get().strip()
        password = self.pwd_var.get().strip()
        if not email or not password:
            messagebox.showwarning("提示", "请填写邮箱和密码！")
            return

        selected = self._get_selected_date()
        if selected is None:
            messagebox.showwarning("提示", "日期无效，请检查手动选择的日期！")
            return

        self._set_busy(True)

        def _run():
            ok = asyncio.run(submit_report(content, self._log,
                                           email=email, password=password,
                                           today=selected))
            self._set_busy(False)
            self._set_status(ok)

        threading.Thread(target=_run, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
    # cd D:\MyPython\MyAI\yitihua
    # pyinstaller yitihua.spec
    # dist\yitihua.exe