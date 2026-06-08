<div align="center">

# ZDEM Archiver · 数据归档清理工具

**Data Purge Utility for Z-Discrete Element Method (ZDEM) Simulations**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)](zdem_archiver_main.py)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)](https://github.com/Phoenix0531-sudo/ZDEM_Archiver/releases)
[![GitHub release](https://img.shields.io/github/v/release/Phoenix0531-sudo/ZDEM_Archiver?include_prereleases)](https://github.com/Phoenix0531-sudo/ZDEM_Archiver/releases)

</div>

---

## 项目简介 | Overview

在运行 ZDEM 离散元数值模拟时，随着迭代步数的增加，项目目录下通常会生成海量的碎片化 Data 文件及冗余计算日志，造成极大的磁盘空间开销。手动清理不仅低效，且极易误删关键源文件。

ZDEM Archiver 是专为此场景开发的本地化 GUI 归档清理工具。它采用严格的黑白名单正则匹配机制，能够安全、高效地一键剥离冗余输出数据，同时绝对保护核心源代码与初始配置参数的完整性，确保模型后续的 **100% 可复现性**。

> During ZDEM (Z-Discrete Element Method) simulations, each iteration generates massive fragmented Data files and redundant logs, consuming enormous disk space. Manual cleanup is inefficient and risks deleting critical source files.
>
> **ZDEM Archiver** is a native GUI purging utility built specifically for this problem. With rigorous whitelist/blacklist regex matching, it safely strips redundant output data in one click while preserving core source code and configuration files — guaranteeing **100% reproducibility** of your models.

---

## 技术特性 | Technical Highlights

| 特性 | Feature | 说明 |
|------|---------|------|
| **异步非阻塞 UI** | Async Non-blocking UI | 基于 QThread 的后台扫描与清理线程，处理百万级碎片文件时界面保持流畅 |
| **详细路径预演** | Detailed Path Preview | 物理删除前分类审查所有待删文件，用蓝（数据）/紫（缓存）/红（GIF）醒目标注 |
| **Fail-safe 容错** | Fail-safe Tolerance | `os.remove` 由 try-except 包裹，遇权限锁定文件自动跳过并告警 |
| **Dry-run 防御** | Dry-run Safeguard | 清理按钮默认禁用，强制用户审查清单与容量后方可执行 |
| **空文件夹探测** | Empty Folder Detection | 清理完毕自动递归扫描空目录，内置资产保护算法，仅弹出真正冗余的空文件夹供勾选删除 |

---

## 核心清理逻辑 | Data Retention Policy

> 过滤引擎严格遵循以下规则。所有物理删除操作前，均须经过 Dry-run 预演确认。
>
> The filtering engine strictly follows the rules below. Every deletion requires a Dry-run preview first.

### 白名单 · Whitelist — 强制保留 · Protected

| 类别 | Category | 规则 Rule |
|------|----------|-----------|
| 初始配置文件 | Initial config | `ini_xyr.dat` |
| 源码与文档 | Source & docs | `*.py`, `*.sh`, `*.md` |
| 非过程性数据 | Non-procedural data | 不包含时间步特征的 `.dat` 文件（如 `output.dat`） |

### 黑名单 · Blacklist — 强制清除 · Removable

| 类别 | Category | 规则 Rule |
|------|----------|-----------|
| 过程性日志 | Log files | `*.log`, `*.err`, `*.error`, `*.out` |
| 时间步数据流 | Timestep data | 匹配 `_\d+\.dat$` 或 `\d+\.dat$` 的文件 |
| 模拟结果图 | Result images | 莫尔圆（`mohr*`）、应力-应变曲线（`strain_stress*`）、时间步快照（文件名含 5 位以上数字） |
| GIF 动画 | GIF animations | 所有 `.gif` 文件 |
| DATA 目录池 | DATA folders | 名为 `DATA`（忽略大小写）目录下的所有文件，清理后目录结构由 `shutil.rmtree` 彻底移除 |
| IDE/系统缓存 | IDE/OS cache | `__pycache__`、`.idea`、`.vscode`、`.cursor`、`.superdesign` 等目录；`Thumbs.db`、`desktop.ini`、`.DS_Store` 等系统缓存 |
| 无用编译产物 | Build artifacts | `.pyc`、`.lnk`、`.mdc`、`.css` |

### 空文件夹清理 · Post-Purge

清理完成后自动扫描残留空文件夹，弹出可勾选的交互式对话框，用户可选择性删除不再需要的空目录。

> After cleanup, the tool scans for empty directories and presents an interactive checklist dialog for selective removal.

---

## 获取与使用 | Download & Usage

为方便课题组使用，本项目提供预编译独立可执行文件（`.exe`），**无需安装 Python 或任何依赖**。

> Pre-compiled standalone executables are available — **no Python or dependencies required**.

1. **下载** | Download：访问 [Releases 页面](https://github.com/Phoenix0531-sudo/ZDEM_Archiver/releases)，下载最新 `zdem_archiver_main.exe`
2. **运行** | Run：双击即可启动 GUI
3. **选择目录** | Select folder：浏览并选择 ZDEM 项目根目录
4. **扫描预演** | Dry-run：点击 `[扫描预演]` 审查待删文件清单
5. **一键清理** | Purge：确认无误后点击 `[一键清理]`
6. **空文件夹处理** | Empty folders：按需勾选删除空目录

---

## 开发者指南 | Developer Guide

> 从源码编译前，请务必创建纯净的隔离环境，避免生成的 `.exe` 因重型科学计算库而过度膨胀。
>
> Before building from source, create a clean isolated environment to avoid bloating the `.exe` with heavy scientific libraries.

```bash
# 1. 创建纯净环境 | Create clean env
conda create -n zdem_pack python=3.9 -y
conda activate zdem_pack

# 2. 仅安装必要依赖 | Minimal dependencies
pip install PyQt5 pyinstaller

# 3. 编译 | Build standalone executable
pyinstaller --onefile --noconsole zdem_archiver_main.py
```

---

## 引用 | Citation

If you use ZDEM Archiver in your research, please cite it as:

```bibtex
@software{zdem_archiver2026,
  author    = {Phoenix0531-sudo},
  title     = {{ZDEM Archiver}: Data Purge Utility for ZDEM Numerical Simulations},
  year      = {2026},
  url       = {https://github.com/Phoenix0531-sudo/ZDEM_Archiver},
  version   = {1.0.0},
  license   = {MIT}
}
```

A `CITATION.cff` file is included in the repository for automated citation via GitHub's "Cite this repository" feature.

---

## 许可证 | License

This project is open-sourced under the **MIT License**. See [LICENSE](LICENSE) for details.

---

<div align="center">

**Made for the ZDEM research community**

</div>
