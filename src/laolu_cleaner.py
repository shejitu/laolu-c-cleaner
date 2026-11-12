# -*- coding: utf-8 -*-
"""老卢系统盘清理 —— tkinter 主界面（标准库，零第三方依赖）"""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cleaner_core as core

APP = "老卢系统盘清理"
VER = "1.0.0"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP} v{VER}")
        self.geometry("860x620")
        self.minsize(760, 540)
        self._scan_results = {}     # key -> (size, [(path, size)])
        self._build()
        self.after(200, self.refresh_sysinfo)

    # ---------- 布局 ----------
    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self.tab_clean = ttk.Frame(nb)
        self.tab_big = ttk.Frame(nb)
        self.tab_privacy = ttk.Frame(nb)
        self.tab_sys = ttk.Frame(nb)
        nb.add(self.tab_clean, text=" 垃圾清理 ")
        nb.add(self.tab_big, text=" C盘瘦身 ")
        nb.add(self.tab_privacy, text=" 隐私清理 ")
        nb.add(self.tab_sys, text=" 系统信息 ")
        self._build_clean()
        self._build_big()
        self._build_privacy()
        self._build_sys()
        self.status = tk.Label(self, text="就绪 · 全部扫描清理均在本地进行，不联网", anchor="w",
                               bg="#f2f4f8", fg="#555")
        self.status.pack(fill="x", side="bottom")

    def _say(self, msg):
        self.status.config(text=msg)
        self.update_idletasks()

    # ---------- 页 1：垃圾清理 ----------
    def _build_clean(self):
        f = self.tab_clean
        top = ttk.Frame(f)
        top.pack(fill="x", padx=10, pady=8)
        ttk.Button(top, text="① 扫描", command=self.scan_all).pack(side="left")
        ttk.Button(top, text="② 清理选中项", command=self.clean_selected).pack(side="left", padx=8)
        self.lbl_total = ttk.Label(top, text="（先扫描）")
        self.lbl_total.pack(side="left", padx=12)

        cols = ("on", "name", "size", "desc")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=16)
        for cid, w, txt in [("on", 50, "选中"), ("name", 170, "项目"),
                            ("size", 100, "可清理"), ("desc", 460, "说明")]:
            self.tree.heading(cid, text=txt)
            self.tree.column(cid, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=4)
        self.tree.bind("<Button-1>", self._toggle_row)
        self.checked = {}

    def _toggle_row(self, ev):
        item = self.tree.identify_row(ev.y)
        col = self.tree.identify_column(ev.x)
        if item and (col == "#1" or True):   # 整行点击切换
            k = self.tree.item(item, "values")[0] if False else item
            # 用 iid 存 key
            key = item
            if key in self.checked and self._scan_results.get(key, (0, []))[0] > 0:
                self.checked[key] = not self.checked.get(key, True)
                self.tree.item(item, values=self._row_values(key))
                self._update_total()

    def _row_values(self, key):
        size, _ = self._scan_results.get(key, (0, []))
        t = next(x for x in core.TARGETS if x.key == key)
        mark = "☑" if self.checked.get(key, True) else "☐"
        return (mark, t.name, core.fmt_size(size) if size else "—", t.desc)

    def _update_total(self):
        total = sum(s for k, (s, _f) in self._scan_results.items()
                    if self.checked.get(k, True))
        self.lbl_total.config(text=f"选中合计：{core.fmt_size(total)}")

    def scan_all(self):
        def work():
            self._say("扫描中…")
            self._scan_results.clear()
            for t in core.TARGETS:
                s, found = core.scan_target(t)
                self._scan_results[t.key] = (s, found)
                self._say(f"扫描中… {t.name} {core.fmt_size(s)}")
            self.after(0, self._fill_tree)
        threading.Thread(target=work, daemon=True).start()

    def _fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        for t in core.TARGETS:
            s, _f = self._scan_results.get(t.key, (0, []))
            iid = self.tree.insert("", "end", iid=t.key, values=self._row_values(t.key))
            self.checked.setdefault(t.key, True)
            self.tree.item(iid, values=self._row_values(t.key))
        self._update_total()
        self._say("扫描完成。请核对列表后点「清理选中项」。")

    def clean_selected(self):
        keys = [k for k in self._scan_results if self.checked.get(k, True)
                and self._scan_results[k][0] > 0]
        if not keys:
            messagebox.showinfo(APP, "没有选中任何可清理项（先点「扫描」）。")
            return
        total = sum(self._scan_results[k][0] for k in keys)
        if not messagebox.askyesno(APP, f"确定清理 {len(keys)} 项，共约 {core.fmt_size(total)}？\n"
                                        "删除后无法恢复，请确认列表里没有还需要的东西。"):
            return

        def work():
            freed = 0
            for k in keys:
                t = next(x for x in core.TARGETS if x.key == k)
                sz, found = self._scan_results[k]
                self._say(f"清理 {t.name}…")
                done, fail = core.clean_target(t, found)
                freed += done
                if fail:
                    self._say(f"{t.name}：{fail} 个文件被占用跳过（正常现象）")
            self.after(0, lambda: self._after_clean(freed))
        threading.Thread(target=work, daemon=True).start()

    def _after_clean(self, freed):
        messagebox.showinfo(APP, f"清理完成，释放约 {core.fmt_size(freed)}。")
        self._say(f"清理完成，释放约 {core.fmt_size(freed)}。")
        self.scan_all()

    # ---------- 页 2：C盘瘦身 ----------
    def _build_big(self):
        f = self.tab_big
        top = ttk.Frame(f)
        top.pack(fill="x", padx=10, pady=8)
        ttk.Label(top, text="扫描 C 盘（系统盘）里占空间最大的目录与文件，供人工判断转移或删除：").pack(side="left")
        ttk.Button(top, text="分析", command=self.analyze_big).pack(side="left", padx=8)
        self.tree_big = ttk.Treeview(f, columns=("path", "size"), show="headings", height=18)
        for cid, w, txt in [("path", 640, "路径"), ("size", 150, "占用")]:
            self.tree_big.heading(cid, text=txt)
            self.tree_big.column(cid, width=w, anchor="w")
        self.tree_big.pack(fill="both", expand=True, padx=10, pady=4)
        ttk.Label(f, text="提示：只列出 ≥100 MB 的项。删除前请自己确认用途——本工具不代替你做判断。",
                  foreground="#a00").pack(anchor="w", padx=10)

    def analyze_big(self):
        root = "C:\\" if core.IS_WIN else "/"

        def work():
            self._say("分析磁盘占用…（大目录可能要几分钟）")
            items = core.top_items(root)
            self.after(0, lambda: self._fill_big(items))
        threading.Thread(target=work, daemon=True).start()

    def _fill_big(self, items):
        self.tree_big.delete(*self.tree_big.get_children())
        for p, s in items:
            self.tree_big.insert("", "end", values=(p, core.fmt_size(s)))
        self._say("分析完成。")

    # ---------- 页 3：隐私清理 ----------
    def _build_privacy(self):
        f = self.tab_privacy
        ttk.Label(f, text="清理使用痕迹（不影响任何文档与程序）：", padding=10).pack(anchor="w")
        ttk.Button(f, text="清除「最近使用文档」记录", command=self.priv_recent).pack(anchor="w", padx=20, pady=6)
        ttk.Label(f, text="说明：清空资源管理器「最近使用」的快捷方式列表，文件本身不受影响。",
                  foreground="#666").pack(anchor="w", padx=20)
        ttk.Button(f, text="清空回收站", command=self.priv_recycle).pack(anchor="w", padx=20, pady=14)
        ttk.Label(f, text="说明：等同右键回收站 → 清空。删了就找不回来。",
                  foreground="#666").pack(anchor="w", padx=20)

    def priv_recent(self):
        n = core.clean_recent_docs()
        messagebox.showinfo(APP, f"已清除 {n} 条最近使用记录。")

    def priv_recycle(self):
        if not messagebox.askyesno(APP, "确定清空回收站？删了就找不回来。"):
            return
        t = next(x for x in core.TARGETS if x.key == "recycle_bin")
        done, _fail = core.clean_target(t)
        messagebox.showinfo(APP, f"回收站已清空（释放约 {core.fmt_size(done)}）。")

    # ---------- 页 4：系统信息 ----------
    def _build_sys(self):
        f = self.tab_sys
        self.lbl_sys = tk.Label(f, text="", justify="left", anchor="nw", font=("Microsoft YaHei", 11))
        self.lbl_sys.pack(fill="both", expand=True, padx=20, pady=20)
        ttk.Button(f, text="刷新", command=self.refresh_sysinfo).pack(pady=6)

    def refresh_sysinfo(self):
        lines = [f"系统：{core.os_info()}", ""]
        for drv in (["C:\\"] if core.IS_WIN else ["/"]):
            u = core.disk_usage(drv)
            if u:
                pct = 100 * u["used"] / u["total"]
                lines.append(f"系统盘 {drv[0]}:  总 {core.fmt_size(u['total'])} · "
                             f"已用 {core.fmt_size(u['used'])}（{pct:.0f}%） · "
                             f"剩余 {core.fmt_size(u['free'])}")
        m = core.mem_info()
        if m:
            lines += ["", f"内存占用 {m['load_pct']}%："
                          f"总 {core.fmt_size(m['total'])} / 可用 {core.fmt_size(m['avail'])}",
                      "（提示：内存长期偏高时，重启浏览器等大内存程序比「一键加速」更有效——"
                      "本工具不承诺「加速」，只给事实。）"]
        self.lbl_sys.config(text="\n".join(lines))
        self.after(5000, self.refresh_sysinfo)


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
