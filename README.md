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
* **数据存放池 (DATA)**：任何位于名为 `DATA`（忽略大小写）目录下的文件均被视为输出数据。在文件清理完毕后，底层的 `DATA` 空壳目录结构将被 `shutil.rmtree` 彻底摧毁。

## 3. 技术特性 | Technical Highlights

* **异步非阻塞 UI (QThread)**：后台采用独立的扫描与清理线程，在处理 100,000+ 级别碎文件时，前端界面保持流畅响应。
* **Fail-safe 容错机制**：底层 `os.remove` 操作由 `try-except` 包裹。遭遇外部程序锁定或无权限访问的文件（PermissionError）将自动跳过并告警，防止清理进程崩溃。
* **Dry-run 防御机制**：物理清除按钮（Purge）默认处于不可交互状态，强制要求用户审查预演容量清单后方可激活。

## 4. 获取与使用 | Download & Usage

为方便课题组内部及相关科研人员使用，本项目已提供预编译的独立可执行文件（`.exe`），**使用者无需安装 Python 或任何依赖环境**。

* **获取程序**：访问本项目的 GitHub Releases 页面，下载最新版本的 `zdem_archiver_main.exe`。
* **独立运行**：将下载的文件放置于任意目录，双击运行即可启动 GUI 界面。
* **执行清理**：在界面中选取待归档的 ZDEM 项目根目录，依次执行 `[扫描预演]` 与 `[一键清理]`。

## 5. 开发者编译指南 | For Developers

若需从源码修改规则并重新编译可执行文件，请务必遵循“纯净环境隔离”规范。严禁在主科研环境（如包含 PyTorch/SciPy 等重型计算库的环境）中直接执行 PyInstaller 打包，以免导致生成的 `.exe` 体积过度膨胀。

```bash
# 1. 创建并激活极简隔离环境
conda create -n zdem_pack python=3.9 -y
conda activate zdem_pack

# 2. 仅安装 GUI 与打包工具依赖
pip install PyQt5 pyinstaller

# 3. 编译单文件无控制台版本
pyinstaller --onefile --noconsole zdem_archiver_main.py