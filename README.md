# ZDEM Archiver | Data Purge Utility

> A robust, multi-threaded data archiving and purging utility for Z-Discrete Element Method (ZDEM) numerical simulations.

## 1. 简介 | Introduction

在运行 ZDEM 离散元数值模拟时，随着迭代步数的增加，项目目录下通常会生成海量的碎片化 Data 文件及冗余的计算日志，造成极大的磁盘空间开销。

**ZDEM Archiver** 是专为此痛点开发的本地化 GUI 归档工具。它采用严格的黑白名单正则匹配机制，旨在安全、高效地一键剥离冗余输出数据，同时绝对保证核心源代码（控制流）与初始配置参数的完整性，确保模型后续的 100% 可复现性。

## 2. 核心清理逻辑 | Data Retention Policy

本工具的过滤引擎严格遵循以下逻辑。任何执行物理删除前的操作，均须经过 Dry-run（预演扫描）确认。

### 白名单 (Whitelist - 强制保留)

核心控制流与配置文件将受到绝对保护：

* **初始配置文件**：`ini_xyr.dat`
* **所有源码与说明文件**：`*.py`, `*.sh`, `*.md`
* **非过程性数据文件**：不带有步数时间戳特征的 `.dat` 文件（如 `output.dat`）。

### 黑名单 (Blacklist - 强制清除)

冗余的过程性数据与日志将被标记为待删除：

* **过程性日志**：`*.log`, `*.err`, `*.error`, `*.out`
* **时间步数据流**：匹配正则表达式 `(_\d+\.dat$)|(\d+\.dat$)` 的文件（如 `result_10000.dat`, `output2000.dat`）。
* **图像结果图**：识别并清理模拟过程中产生的可视化图件（`.jpg`, `.png`, `.bmp`），包括：
    * **莫尔圆**：以 `mohr` 开头的文件。
    * **应力应变曲线**：以 `strain_stress` 开头的文件。
    * **快照序列**：文件名中包含 5 位及以上连续数字的时间步快照（如 `all_0000600997.jpg`）。
* **GIF 动画文件**：所有 `.gif` 动画文件（后处理输出产物，可重新生成）。
* **数据存放池 (DATA)**：任何位于名为 `DATA`（忽略大小写）目录下的文件均被视为输出数据。在文件清理完毕后，底层的 `DATA` 空壳目录结构将被 `shutil.rmtree` 彻底摧毁。
* **IDE/编译缓存目录**：`__pycache__`、`.idea`、`.vscode`、`.cursor`、`.superdesign` 等 IDE 生成的缓存和配置目录将被整体清除。
* **系统垃圾文件**：`Thumbs.db`、`desktop.ini`、`.DS_Store` 等操作系统缓存文件。
* **无用缓存/配置**：`.pyc`（Python 编译缓存）、`.lnk`（Windows 快捷方式）、`.mdc`（IDE 规则文件）、`.css`（IDE 主题文件）。

### 空文件夹清理 (Post-Purge)

清理完成后，工具将**自动扫描残留的空文件夹**。若检测到空目录，将弹出可勾选的交互式对话框，用户可选择性删除不再需要的空目录结构，确保项目目录彻底整洁。

## 3. 技术特性 | Technical Highlights

* **异步非阻塞 UI (QThread)**：后台采用独立的扫描与清理线程，在处理 1,000,000+ 级别碎文件时，前端界面保持流畅响应。
* **详细路径预演 (New)**：在物理删除前，可分类审查所有待删除文件的详细路径清单。预演窗口会以醒目颜色分类标注结果数据（蓝色）、编译缓存（紫色）及 GIF 动画（红色），透明度极高。
* **Fail-safe 容错机制**：底层 `os.remove` 操作由 `try-except` 包裹。遭遇外部程序锁定或无权限访问的文件将自动跳过并告警，防止清理进程崩溃。
* **Dry-run 防御机制**：物理清除按钮默认禁选，强制要求用户审查详细路径清单与容量后方可一键清理，最大限度降低误删可能。
* **空文件夹资产探测**：清理完毕后递归扫描目录。内置资产保护算法会探测并保护 `.py`, `.docx`, `.pptx`, `.md` 等原始资料目录，仅弹出真正的冗余空目录供交互式勾选删除。

## 4. 获取与使用 | Download & Usage

为方便课题组内部及相关科研人员使用，本项目已提供预编译的独立可执行文件（`.exe`），**使用者无需安装 Python 或任何依赖环境**。

* **获取程序**：访问本项目的 GitHub Releases 页面，下载最新版本的 `zdem_archiver_main.exe`。
* **独立运行**：将下载的文件放置于任意目录，双击运行即可启动 GUI 界面。
* **执行清理**：在界面中选取待归档的 ZDEM 项目根目录，依次执行 `[扫描预演]` 与 `[一键清理]`。
* **空文件夹处理**：清理完成后自动弹出空文件夹列表，勾选需删除的条目后确认即可。

## 5. 开发者编译指南 | For Developers

若需从源码修改规则并重新编译可执行文件，请务必遵循"纯净环境隔离"规范。严禁在主科研环境（如包含 PyTorch/SciPy 等重型计算库的环境）中直接执行 PyInstaller 打包，以免导致生成的 `.exe` 体积过度膨胀。

```bash
# 1. 创建并激活极简隔离环境
conda create -n zdem_pack python=3.9 -y
conda activate zdem_pack

# 2. 仅安装 GUI 与打包工具依赖
pip install PyQt5 pyinstaller

# 3. 编译单文件无控制台版本
pyinstaller --onefile --noconsole zdem_archiver_main.py