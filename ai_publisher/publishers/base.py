# publishers/base.py - 发布器抽象基类
#
# 所有平台发布器都继承此类。
# 提供：Cookie 读写、浏览器上下文初始化、统一的登录子进程启动。

import json
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, BrowserContext, Page

import config


class BasePublisher(ABC):

    # 子类必须设置的属性
    platform_key: str = ""       # 如 "xiaohongshu"
    platform_name: str = ""      # 如 "小红书"
    login_url: str = ""          # 扫码登录页 URL

    def __init__(self):
        self.cookie_path: Path = config.get_cookie_path(self.platform_key)

    # ─────────────────────────────────────────
    # Cookie 管理
    # ─────────────────────────────────────────

    def is_logged_in(self) -> bool:
        """Cookie 文件是否存在（不做有效性校验，发布失败时再处理）"""
        return self.cookie_path.exists()

    def load_cookies(self) -> Optional[list]:
        if not self.cookie_path.exists():
            return None
        return json.loads(self.cookie_path.read_text(encoding="utf-8"))

    def save_cookies(self, cookies: list):
        self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
        self.cookie_path.write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def clear_cookies(self):
        if self.cookie_path.exists():
            self.cookie_path.unlink()

    # ─────────────────────────────────────────
    # 浏览器上下文
    # ─────────────────────────────────────────

    def _new_context(self, playwright) -> BrowserContext:
        """创建带 Cookie 的浏览器上下文"""
        browser = playwright.chromium.launch(
            headless=config.BROWSER_HEADLESS,
            slow_mo=config.BROWSER_SLOW_MO,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )
        cookies = self.load_cookies()
        if cookies:
            context.add_cookies(cookies)
        return context

    # ─────────────────────────────────────────
    # 登录流程（子进程，非阻塞）
    # ─────────────────────────────────────────

    def start_login_subprocess(self):
        """
        启动独立子进程打开登录页，Streamlit 主进程不阻塞。
        子进程路径：publishers/{platform_key}.py  login
        """
        module_path = Path(__file__).parent / f"{self.platform_key}.py"
        subprocess.Popen(
            [sys.executable, str(module_path), "login"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def login_blocking(self):
        """
        同步登录（在子进程里直接调用）：
        打开浏览器 → 等用户扫码 → 保存 Cookie → 关闭浏览器
        只有 _wait_for_login 返回 True 才保存 Cookie，避免超时后空文件误判为已登录
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                slow_mo=300,
                args=["--no-sandbox"]
            )
            context = browser.new_context(locale="zh-CN")
            page = context.new_page()

            print(f"[{self.platform_name}] 正在打开登录页...")
            page.goto(self.login_url, wait_until="domcontentloaded")

            # 各平台可以覆盖此方法，处理特殊登录逻辑
            if self._wait_for_login(page, context):
                cookies = context.cookies()
                self.save_cookies(cookies)
                print(f"[{self.platform_name}] 登录成功，Cookie 已保存")
            else:
                print(f"[{self.platform_name}] 登录未完成，Cookie 未保存")
            browser.close()

    def _wait_for_login(self, page: Page, context: BrowserContext) -> bool:
        """
        等待用户完成登录。子类可以覆盖此方法检测特定元素。
        默认：等待用户按 Enter（终端运行时有效）
        返回 True 表示登录成功，False 表示失败/超时
        """
        try:
            input(f"\n请在浏览器中完成{self.platform_name}扫码登录，完成后在此按 Enter...\n")
            return True
        except (EOFError, OSError):
            print(f"\n无终端交互，无法等待用户确认，登录未完成")
            return False

    # ─────────────────────────────────────────
    # 发布接口（子类实现）
    # ─────────────────────────────────────────

    @abstractmethod
    def publish(self, content: dict, images: list[str]) -> dict:
        """
        发布内容。
        content: ai_results 中该平台的 dict，如 {"title": ..., "body": ..., "tags": ...}
        images: 本地图片路径列表
        返回：{"success": bool, "url": str|None, "error": str|None}
        """
        pass

    def _safe_publish(self, content: dict, images: list[str]) -> dict:
        """
        带重试的发布包装（最多3次）。
        """
        last_error = ""
        for attempt in range(1, 4):
            try:
                result = self.publish(content, images)
                if result.get("success"):
                    return result
                last_error = result.get("error", "未知错误")
            except Exception as e:
                last_error = str(e)
                print(f"[{self.platform_name}] 第{attempt}次发布失败：{last_error}")

        return {"success": False, "url": None, "error": f"重试3次仍失败：{last_error}"}

    # ─────────────────────────────────────────
    # 工具方法
    # ─────────────────────────────────────────

    @staticmethod
    def _fill_rich_text(page: Page, selector: str, text: str):
        """
        填充富文本编辑器（contenteditable div）。
        直接 fill() 在 contenteditable 上不工作，需要先 click() 再 type()。
        """
        el = page.locator(selector).first
        el.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        # 分段输入，处理换行
        for line in text.split("\n"):
            page.keyboard.type(line, delay=20)
            page.keyboard.press("Enter")

    @staticmethod
    def _upload_images(page: Page, file_input_selector: str, image_paths: list[str]):
        """上传多张图片到 file input"""
        valid = [p for p in image_paths if Path(p).exists()]
        if not valid:
            return
        page.locator(file_input_selector).set_input_files(valid)
