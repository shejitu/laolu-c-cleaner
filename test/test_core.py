# -*- coding: utf-8 -*-
"""核心逻辑自测（无需 GUI、无危险操作：只对临时沙箱目录）"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import cleaner_core as core


class TestCleaner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="laolu_test_")
        # 造垃圾：tmp 下 3 个文件 + 1 个子目录
        for i in range(3):
            p = os.path.join(self.tmp, f"junk{i}.tmp")
            with open(p, "wb") as f:
                f.write(b"x" * 100)
        sub = os.path.join(self.tmp, "sub")
        os.mkdir(sub)
        with open(os.path.join(sub, "deep.log"), "wb") as f:
            f.write(b"y" * 500)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_scan_counts(self):
        t = core.CleanTarget("k", "k", "test", [self.tmp])
        size, found = core.scan_target(t)
        self.assertEqual(len(found), 4)
        self.assertEqual(size, 800)

    def test_clean_removes_and_reports(self):
        t = core.CleanTarget("k", "k", "test", [self.tmp])
        _s, found = core.scan_target(t)
        done, fail = core.clean_target(t, found)
        self.assertEqual(done, 800)
        self.assertEqual(fail, 0)
        self.assertEqual(os.listdir(self.tmp), [])

    def test_patterns(self):
        # 只清 *.tmp，*.log 不动
        t = core.CleanTarget("k", "k", "test", [self.tmp], patterns=["*.tmp"])
        size, found = core.scan_target(t)
        self.assertEqual(len(found), 3)
        self.assertEqual(size, 300)
        core.clean_target(t, found)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "sub", "deep.log")))

    def test_fmt_size(self):
        self.assertEqual(core.fmt_size(0), "0 B")
        self.assertEqual(core.fmt_size(512), "512 B")
        self.assertEqual(core.fmt_size(2048), "2.0 KB")
        self.assertEqual(core.fmt_size(5 * 1024 ** 3), "5.0 GB")

    def test_targets_unique_keys(self):
        keys = [t.key for t in core.TARGETS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(t.name and t.desc for t in core.TARGETS))

    def test_top_items_min_size(self):
        big = os.path.join(self.tmp, "big.bin")
        with open(big, "wb") as f:
            f.write(b"z" * (200 * 1024 * 1024 // 10))   # 20MB，超过 min 阈值传参
        items = core.top_items(self.tmp, min_size_mb=10)
        self.assertTrue(any(p == big for p, _s in items))
        os.remove(big)

    def test_disk_usage(self):
        u = core.disk_usage("/" if not core.IS_WIN else "C:\\")
        self.assertIsNotNone(u)
        self.assertGreater(u["total"], 0)

    def test_mem_info(self):
        m = core.mem_info()
        self.assertIsNotNone(m)
        self.assertTrue(0 <= m["load_pct"] <= 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
