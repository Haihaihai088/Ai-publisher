# tests/test_task_manager.py — 任务状态机 CRUD + 锁机制测试
import os
import sys
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "ai_publisher"))

# Mock dotenv 避免需要安装依赖（必须在 import config 前注入）
sys.modules["dotenv"] = MagicMock()

from config import TaskStatus, PublishStatus


class TestTaskManager(unittest.TestCase):
    """测试 task_manager 的核心 CRUD 操作，使用临时目录隔离"""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.tasks_dir = Path(cls.tmpdir.name)

        import task_manager
        # task_manager 内部有 `from config import TASKS_DIR` 的本地引用,
        # 直接替换本地引用
        cls._patcher = patch.object(task_manager, "TASKS_DIR", cls.tasks_dir)
        cls._patcher.start()
        cls.tm = task_manager

    @classmethod
    def tearDownClass(cls):
        cls._patcher.stop()
        cls.tmpdir.cleanup()

    def test_create_task(self):
        task = self.tm.create_task("测试内容", ["xiaohongshu", "zhihu"], [])
        self.assertEqual(task["original_content"], "测试内容")
        self.assertEqual(task["status"], "created")
        self.assertEqual(task["platforms"], ["xiaohongshu", "zhihu"])
        self.assertIsNotNone(task["id"])
        self.assertEqual(len(task["id"]), 8)

        # 验证文件已持久化
        path = self.tasks_dir / f"{task['id']}.json"
        self.assertTrue(path.exists())

    def test_load_task_not_found(self):
        result = self.tm.load_task("nonexistent")
        self.assertIsNone(result)

    def test_load_save_cycle(self):
        task = self.tm.create_task("持久化测试", ["zhihu"], [])
        loaded = self.tm.load_task(task["id"])
        self.assertEqual(loaded["original_content"], "持久化测试")
        self.assertEqual(loaded["id"], task["id"])

    def test_update_status(self):
        task = self.tm.create_task("状态更新测试", ["tieba"], [])
        self.tm.update_status(task["id"], "analyzing")
        loaded = self.tm.load_task(task["id"])
        self.assertEqual(loaded["status"], "analyzing")

    def test_update_status_with_error(self):
        task = self.tm.create_task("错误测试", ["wechat"], [])
        self.tm.update_status(task["id"], "failed", error="网络错误")
        loaded = self.tm.load_task(task["id"])
        self.assertEqual(loaded["status"], "failed")
        self.assertEqual(loaded["error"], "网络错误")

    def test_update_ai_results(self):
        task = self.tm.create_task("AI测试内容", ["xiaohongshu"], [])
        analysis = {"topic": "测试", "keywords": ["a", "b"]}
        ai_results = {"xiaohongshu": {"title": "标题", "body": "正文", "tags": []}}
        self.tm.update_ai_results(task["id"], analysis, ai_results)
        loaded = self.tm.load_task(task["id"])
        self.assertEqual(loaded["status"], "pending_review")
        self.assertIsNotNone(loaded["analysis"])
        self.assertIsNotNone(loaded["ai_results"])

    def test_approve_platform(self):
        task = self.tm.create_task("审核测试", ["xiaohongshu"], [])
        # approve_platform 需要 ai_results 已存在
        self.tm.update_ai_results(task["id"],
                                   {"topic": "x"},
                                   {"xiaohongshu": {"title": "原标题", "body": "", "tags": []}})
        self.tm.approve_platform(task["id"], "xiaohongshu",
                                  edited_content={"title": "修改后标题"})
        loaded = self.tm.load_task(task["id"])
        self.assertEqual(loaded["review"]["xiaohongshu"], "approved")
        self.assertEqual(loaded["ai_results"]["xiaohongshu"]["title"], "修改后标题")

    def test_reject_platform(self):
        task = self.tm.create_task("拒绝测试", ["zhihu"], [])
        self.tm.reject_platform(task["id"], "zhihu")
        loaded = self.tm.load_task(task["id"])
        self.assertEqual(loaded["review"]["zhihu"], "rejected")

    def test_set_platform_extra_field(self):
        task = self.tm.create_task("贴吧测试", ["tieba"], [])
        # 先要有 ai_results
        self.tm.update_ai_results(task["id"],
                                   {"topic": "x"},
                                   {"tieba": {"title": "", "body": "", "tags": []}})
        self.tm.set_platform_extra_field(task["id"], "tieba", "tieba_selected", "数码")
        loaded = self.tm.load_task(task["id"])
        self.assertEqual(loaded["ai_results"]["tieba"]["tieba_selected"], "数码")

    def test_update_publish_result_success(self):
        task = self.tm.create_task("发布测试", ["zhihu"], [])
        self.tm.update_publish_result(task["id"], "zhihu", "success",
                                       url="https://example.com/article")
        loaded = self.tm.load_task(task["id"])
        self.assertEqual(loaded["publish_results"]["zhihu"]["status"], "success")
        self.assertEqual(loaded["publish_results"]["zhihu"]["url"], "https://example.com/article")
        self.assertEqual(loaded["status"], "completed")

    def test_update_publish_result_failed(self):
        task = self.tm.create_task("发布失败测试", ["xiaohongshu"], [])
        self.tm.update_publish_result(task["id"], "xiaohongshu", "failed",
                                       error="网络超时")
        loaded = self.tm.load_task(task["id"])
        self.assertEqual(loaded["status"], "failed")
        self.assertEqual(loaded["publish_results"]["xiaohongshu"]["error"], "网络超时")

    def test_delete_task(self):
        task = self.tm.create_task("删除测试", ["zhihu"], [])
        path = self.tasks_dir / f"{task['id']}.json"
        self.assertTrue(path.exists())
        self.tm.delete_task(task["id"])
        self.assertFalse(path.exists())

    def test_is_all_approved(self):
        task = self.tm.create_task("全通过测试", ["xiaohongshu", "zhihu"], [])
        self.assertFalse(self.tm.is_all_approved(task))
        task["review"]["xiaohongshu"] = "approved"
        task["review"]["zhihu"] = "approved"
        self.assertTrue(self.tm.is_all_approved(task))

    def test_load_all_tasks(self):
        # 清空之前的测试文件
        for f in self.tasks_dir.glob("*.json"):
            f.unlink()
        self.tm.create_task("任务A", ["zhihu"], [])
        self.tm.create_task("任务B", ["tieba"], [])
        all_tasks = self.tm.load_all_tasks()
        self.assertEqual(len(all_tasks), 2)

    def test_atomic_write(self):
        task = self.tm.create_task("原子写入测试", ["zhihu"], [])
        path = self.tasks_dir / f"{task['id']}.json"
        content_before = path.read_text(encoding="utf-8")
        self.assertIn("原子写入测试", content_before)
        # tmp 文件应该已被 rename，不应存在
        tmp_path = path.with_suffix(".tmp")
        self.assertFalse(tmp_path.exists())

    def test_lock_prevents_concurrent_access(self):
        """验证锁机制存在且可获取/释放"""
        task = self.tm.create_task("锁测试", ["zhihu"], [])
        lock_path = self.tasks_dir / f"{task['id']}.lock"
        self.assertFalse(lock_path.exists())  # 锁在使用后已释放

        # 手动模拟锁占用
        import time
        lock_path.write_text("blocked")
        t0 = time.time()
        # 尝试在锁占用时读取（load_task 不加锁，应该能读）
        loaded = self.tm.load_task(task["id"])
        self.assertIsNotNone(loaded)
        lock_path.unlink()

    def test_create_task_generates_unique_ids(self):
        ids = set()
        for _ in range(10):
            task = self.tm.create_task("唯一ID测试", ["zhihu"], [])
            ids.add(task["id"])
        self.assertEqual(len(ids), 10)


if __name__ == "__main__":
    unittest.main()
