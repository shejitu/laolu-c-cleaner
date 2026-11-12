# -*- coding: utf-8 -*-
"""
老卢系统盘清理 —— 扫描与清理核心
设计原则（docs/净室研究记录.md）：白名单删、先展示后确认、全本地无网络。
跨平台注意：核心逻辑用 pathspec 描述，Linux 下也能跑测试（回退到 /tmp 等）。
"""
import os
import sys
import shutil
import glob
import ctypes
import platform
from dataclasses import dataclass, field

IS_WIN = platform.system() == "Windows"


def home():
    return os.path.expanduser("~")


def windows_dir():
    return os.environ.get("SystemRoot", r"C:\Windows") if IS_WIN else "/tmp"


@dataclass
class CleanTarget:
    """一个可清理项：一个目录/文件通配模式集合 + 说明。"""
    key: str                 # 稳定 id（存配置用）
    name: str                # 界面显示名
    desc: str                # 说明（安全原因）
    paths: list = field(default_factory=list)   # 参与扫描的目录
    patterns: list = field(default_factory=list)  # 目录内匹配的相对通配（空 = 整目录内容）
    risk: str = "低"          # 低 / 中

    def __str__(self):
        return self.name


def _targets():
    win = windows_dir()
    tmp = os.environ.get("TEMP", os.environ.get("TMP", "/tmp"))
    locals_low = os.path.join(home(), "AppData", "Local")
    roaming = os.path.join(home(), "AppData", "Roaming")
    t = []
    if IS_WIN:
        t += [
            CleanTarget("user_temp", "用户临时文件", "当前用户 TEMP 目录，程序运行残留，公认安全",
                        [tmp], risk="低"),
            CleanTarget("sys_temp", "系统临时文件", "Windows\\Temp，系统更新/安装残留",
                        [os.path.join(win, "Temp")], risk="低"),
            CleanTarget("prefetch", "预读取缓存", "Windows\\Prefetch，可安全清空，系统会自动重建",
                        [os.path.join(win, "Prefetch")], risk="低"),
            CleanTarget("thumb", "缩略图缓存", "资源管理器缩略图缓存，清掉后首次打开文件夹稍慢",
                        [os.path.join(locals_low, "Microsoft", "Windows", "Explorer")],
                        patterns=["thumbcache_*.db"], risk="低"),
            CleanTarget("dxcache", "DirectX 着色器缓存",
                        [os.path.join(locals_low, "D3DSCache")], risk="低",
                        desc="游戏/图形程序着色器缓存，清掉后首次启动稍慢"),
            CleanTarget("win_update_dl", "Windows 更新下载缓存",
                        [os.path.join(win, "SoftwareDistribution", "Download")], risk="中",
                        desc="已装更新的安装包残留，清掉后不影响已装更新"),
            CleanTarget("recycle_bin", "回收站", "清空回收站（删除前请确认里面没有要找回的文件）",
                        ["$Recycle.Bin"], risk="中", desc="见上"),
            CleanTarget("crashdump", "崩溃转储与内存转储",
                        [os.path.join(locals_low, "CrashDumps"), os.path.join(win, "Minidump"),
                         os.path.join(win, "MEMORY.DMP")], risk="低",
                        desc="程序崩溃记录，排查过问题就没用了"),
            CleanTarget("win_old", "Windows.old（旧系统备份）",
                        [r"C:\Windows.old"], risk="中",
                        desc="升过级的旧系统整个备份，确认不需要回退再删"),
        ]
        # 各浏览器/应用缓存（只删 Cache 目录，不碰书签密码）
        for brand, sub in [
            ("Edge", os.path.join(locals_low, "Microsoft", "Edge", "User Data")),
            ("Chrome", os.path.join(locals_low, "Google", "Chrome", "User Data")),
        ]:
            t.append(CleanTarget(f"{brand.lower()}_cache", f"{brand} 浏览器缓存",
                                 f"网页缓存图片与脚本，不碰书签/密码/历史记录",
                                 [os.path.join(sub, "*", "Cache"),
                                  os.path.join(sub, "*", "Code Cache"),
                                  os.path.join(sub, "*", "GPUCache")],
                                 patterns=["*"], risk="低"))
    else:
        # 非 Windows（开发自测）：/tmp 与用户缓存
        t += [
            CleanTarget("user_temp", "临时文件", "POSIX /tmp", [tmp], risk="低"),
            CleanTarget("user_cache", "用户缓存", "~/.cache", [os.path.join(home(), ".cache")],
                        patterns=["*"], risk="低"),
        ]
    return t


TARGETS = _targets()


def dir_size(path):
    total = 0
    try:
        for root, _dirs, files in os.walk(path, onerror=lambda e: None):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def scan_target(t: CleanTarget):
    """返回 (可清理字节数, 详情列表 [(路径, 大小)])"""
    found = []
    for p in t.paths:
        if not os.path.isabs(p) and IS_WIN:
            # 相对路径（如回收站 $Recycle.Bin）按盘符展开
            for drv in _drive_letters():
                full = os.path.join(drv + "\\", p)
                _scan_one(t, full, found)
            continue
        _scan_one(t, p, found)
    return sum(s for _p, s in found), found


def _scan_one(t, p, found):
    if os.path.isfile(p):
        try:
            found.append((p, os.path.getsize(p)))
        except OSError:
            pass
        return
    if not os.path.isdir(p):
        return
    if t.patterns:
        for pat in t.patterns:
            for hit in glob.glob(os.path.join(p, pat)):
                if os.path.isfile(hit):
                    try:
                        found.append((hit, os.path.getsize(hit)))
                    except OSError:
                        pass
                elif os.path.isdir(hit):
                    found.append((hit, dir_size(hit)))
    else:
        for entry in os.listdir(p) if os.access(p, os.R_OK) else []:
            ep = os.path.join(p, entry)
            try:
                if os.path.isfile(ep):
                    found.append((ep, os.path.getsize(ep)))
                else:
                    found.append((ep, dir_size(ep)))
            except OSError:
                pass


def _drive_letters():
    if IS_WIN:
        return [d for d in "CDEFGH" if os.path.exists(f"{d}:\\")]
    return []


def clean_target(t: CleanTarget, found=None, progress=None):
    """删除扫描出的条目。found 缺省时先扫一遍。返回 (成功字节数, 失败条数)。"""
    if found is None:
        _sz, found = scan_target(t)
    done = 0
    fail = 0
    for p, _s in found:
        try:
            if os.path.isfile(p):
                os.remove(p)
            else:
                shutil.rmtree(p, ignore_errors=True)
            done += _s
        except OSError:
            fail += 1
        if progress:
            progress(p, done)
    return done, fail


# ---------- 大文件分析（C 盘瘦身对应功能） ----------

def top_items(root, limit=15, min_size_mb=100):
    """root 下一级里占用最大的目录/文件。"""
    items = []
    try:
        for e in os.listdir(root):
            ep = os.path.join(root, e)
            try:
                s = os.path.getsize(ep) if os.path.isfile(ep) else dir_size(ep)
            except OSError:
                continue
            if s >= min_size_mb * 1024 * 1024:
                items.append((ep, s))
    except OSError:
        pass
    items.sort(key=lambda x: -x[1])
    return items[:limit]


# ---------- 隐私痕迹 ----------

PRIVACY_ITEMS = [
    ("recent_docs", "最近使用文档记录", "资源管理器「最近使用」列表（Recent 目录快捷方式）"),
    ("run_history", "运行对话框历史", "注册表 RunMRU（v1.0 展示位置，清理按钮调用 reg 命令）"),
    ("recycle", "回收站", "同垃圾清理里的回收站项"),
]


def recent_docs_paths():
    p = os.path.join(home(), "AppData", "Roaming",
                     "Microsoft", "Windows", "Recent")
    return [p] if os.path.isdir(p) else []


def clean_recent_docs():
    done = 0
    for p in recent_docs_paths():
        for f in glob.glob(os.path.join(p, "*.lnk")) + glob.glob(os.path.join(p, "*.automaticDestinations-ms")):
            try:
                os.remove(f)
                done += 1
            except OSError:
                pass
    return done


# ---------- 系统信息 ----------

def disk_usage(drive="C:\\" if IS_WIN else "/"):
    try:
        t, u, f = shutil.disk_usage(drive)
        return {"total": t, "used": u, "free": f}
    except OSError:
        return None


def mem_info():
    """无 psutil 依赖：Windows 用 GlobalMemoryStatusEx，POSIX 读 /proc/meminfo。"""
    if IS_WIN:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        try:
            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return {"load_pct": st.dwMemoryLoad, "total": st.ullTotalPhys, "avail": st.ullAvailPhys}
        except OSError:
            return None
    try:
        d = {}
        for line in open("/proc/meminfo"):
            k, v = line.split(":")
            d[k.strip()] = int(v.strip().split()[0]) * 1024
        return {"load_pct": round(100 * (1 - d["MemAvailable"] / d["MemTotal"])),
                "total": d["MemTotal"], "avail": d["MemAvailable"]}
    except (OSError, KeyError, ValueError):
        return None


def os_info():
    return f"{platform.system()} {platform.release()}（{platform.machine()}）"


def fmt_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
