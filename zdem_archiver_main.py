import os
import re
import sys
import time
import shutil
from pathlib import Path
from typing import Optional, Any, Union, cast
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QTextBrowser, QProgressBar, QFileDialog,
                             QDialog, QListWidget, QListWidgetItem, QAbstractItemView)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5 import QtCore, QtGui

# ---------------------------------------------------------
# 实用工具函数：字节转换
# ---------------------------------------------------------
def format_size(size_in_bytes: float) -> str:
    """将字节数转换为人类可读的格式 (KB, MB, GB)"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} PB"

# ---------------------------------------------------------
# 核心逻辑：文件过滤规则
# ---------------------------------------------------------
def should_delete_file(file_path: Path, base_path: Path) -> Optional[str]:
    """
    判断单个文件是否需要被删除。
    返回命中的规则名称 (str) 或 None (不删除)。
    """
    try:
        rel_path = file_path.relative_to(base_path)
        parts = rel_path.parts
        name = file_path.name
        suffix = file_path.suffix.lower()

        # [1] 白名单：绝对保护核心文件 (优先匹配)
        if name.lower() in ['ini_xyr.dat']:
            return None
        if suffix in ['.py', '.sh', '.md']:
            return None

        # [1b] IDE 和编译缓存目录 — 整个目录都是垃圾
        ide_junk_dirs = {'__pycache__', '.idea', '.vscode', '.cursor', '.superdesign'}
        if any(p in ide_junk_dirs for p in parts):
            return 'IDE/编译缓存'

        # [2] 黑名单：清理包含特定关键字的目录或文件名
        # 匹配关键字：data, datass, result (忽略大小写)
        # 只要文件的任意上级目录包含这些关键字，或者文件名本身匹配，即判定为清理对象
        deletion_keywords = ['data', 'datass', 'result']
        
        # 检查目录路径
        if any(any(kw in p.lower() for kw in deletion_keywords) for p in parts[:-1]):
            return '数据/结果目录清理'
            
        # 检查文件名本身 (包含针对 datass, result 等特定名称的精确或模糊匹配)
        if any(kw in name.lower() for kw in deletion_keywords):
            # 排除掉那些在白名单中已经处理过的情况
            return '数据/结果冗余文件'

        # [3] 黑名单：清理各类日志和输出冗余
        if suffix in ['.log', '.err', '.error', '.out']:
            return '日志/错误文件'
            
        # [3b] GMT 配置文件清理
        if name.lower() in ['gmt.conf', 'gmt.history']:
            return 'GMT 配置文件'

        # [3c] 系统垃圾和无用文件
        if name.lower() in ['thumbs.db', 'desktop.ini', '.ds_store']:
            return '系统缓存文件'
        if suffix in ['.pyc', '.lnk', '.mdc', '.css']:
            return '无用缓存/配置'

        # [3d] GIF 动画文件 — 可重新生成的后处理产物
        if suffix == '.gif':
            return 'GIF 动画'

        # [4] 精细规则：处理 .dat 文件
        if suffix == '.dat':
            # 匹配带时间步的文件名，例如 result_10000.dat, output2000.dat
            # 正则解释: 匹配下划线+数字+.dat，或者直接数字+.dat结尾
            if re.search(r'_\d+\.dat$', name.lower()) or re.search(r'\d+\.dat$', name.lower()):
                return '时间步 .dat'
            else:
                # 不带时间步的 .dat 予以保留
                return None

        # [5] 图像文件清理规则 (仅针对常见图像格式)
        if suffix in ['.jpg', '.jpeg', '.png', '.bmp']:
            stem = file_path.stem.lower()
            # [5a] 莫尔圆输出图：文件名以 mohr 开头
            if stem.startswith('mohr'):
                return '莫尔圆图片'
            # [5b] 应力-应变输出图：文件名以 strain_stress 开头
            if stem.startswith('strain_stress'):
                return '应力-应变图片'
            # [5c] 时间步快照图：文件名（去掉括号后）含有连续 5 位以上数字序列
            # 匹配形如 all_0000600997、all_0000600997 (2) 这类文件名
            if re.search(r'\d{5,}', stem):
                return '时间步图片'

        # [6] 默认处理：如果都不匹配，为了安全起见，默认保留
        return None
    except Exception:
        # 如果解析路径发生异常，保守起见不删除
        return None

# ---------------------------------------------------------
# 线程 1：扫描预演线程 (Dry-run Scanner)
# ---------------------------------------------------------
class ScannerThread(QThread): # type: ignore
    progress_update: pyqtSignal = pyqtSignal(int) # type: ignore
    log_update: pyqtSignal = pyqtSignal(str) # type: ignore
    scan_finished: pyqtSignal = pyqtSignal(object) # type: ignore

    def __init__(self, target_dir: Union[str, Path]) -> None:
        super().__init__()
        self.target_dir: Path = Path(target_dir)

    def run(self) -> None:
        self.log_update.emit("[系统] 正在初始化扫描环境...")
        
        # 第一遍：快速统计文件总数，用于计算精确进度条
        self.log_update.emit("[系统] 正在评估目录规模...")
        total_files = sum(len(files_list) for _, _, files_list in os.walk(self.target_dir))
        
        if total_files == 0:
            self.log_update.emit("[警告] 目标目录为空或不存在。")
            self.scan_finished.emit({
                'files_to_delete': [],
                'total_freed_bytes': 0,
                'rule_stats': {},
            })
            return

        self.log_update.emit(f"[系统] 发现总计 {total_files} 个文件，开始执行规则匹配...")
        
        files_to_delete = []
        total_freed_bytes = 0
        processed_files = 0
        # 按规则分类统计：{ 规则名: {'count': 文件数, 'bytes': 字节数} }
        rule_stats = {}
        
        # 为了防止 UI 频繁刷新导致卡顿，限制刷新频率
        last_update_time = time.time()

        # 第二遍：执行匹配逻辑
        for root, _, files_list in os.walk(self.target_dir):
            root_path = Path(root)
            for file in files_list:
                file_path = root_path / file
                processed_files += 1

                # 规则判断：返回规则名或 None
                rule = should_delete_file(file_path, self.target_dir)
                if rule:
                    try:
                        fsize = file_path.stat().st_size
                    except OSError:
                        fsize = 0
                    
                    # 存储 (路径, 大小, 规则)
                    files_to_delete.append((file_path, fsize, rule))
                    
                    total_freed_bytes += fsize
                    # 按规则名累加统计
                    if rule not in rule_stats:
                        rule_stats[rule] = {'count': 1, 'bytes': fsize}
                    else:
                        rule_stats[rule]['count'] += 1
                        rule_stats[rule]['bytes'] += fsize

                # 控制进度条更新频率 (每 0.1 秒刷新一次)
                current_time = time.time()
                if current_time - last_update_time > 0.1 or processed_files == total_files:
                    progress_pct = int((processed_files / total_files) * 100)
                    self.progress_update.emit(progress_pct)
                    last_update_time = current_time

        self.log_update.emit("[成功] 目录扫描与预演完成。")
        self.scan_finished.emit({
            'files_to_delete': files_to_delete,
            'total_freed_bytes': total_freed_bytes,
            'rule_stats': rule_stats,
        })

# ---------------------------------------------------------
# 线程 2：物理清理线程 (Cleaner)
# ---------------------------------------------------------
class CleanerThread(QThread): # type: ignore
    progress_update: pyqtSignal = pyqtSignal(int) # type: ignore
    log_update: pyqtSignal = pyqtSignal(str) # type: ignore
    clean_finished: pyqtSignal = pyqtSignal(object, object) # type: ignore

    def __init__(self, files_to_delete: list[tuple[Path, float, str]], target_dir: Union[str, Path]) -> None:
        super().__init__()
        self.files_to_delete: list[tuple[Path, float, str]] = files_to_delete
        self.target_dir: Path = Path(target_dir)
        self.is_interrupted: bool = False

    def run(self) -> None:
        total_tasks = len(self.files_to_delete)
        if total_tasks == 0:
            self.clean_finished.emit(0, 0)
            return

        success_count = 0
        fail_count = 0
        last_update_time = time.time()

        for i, item in enumerate(self.files_to_delete):
            if self.is_interrupted:
                break
            
            # --- 类型安全转换逻辑 ---
            # 无论 item 是 (path, size, rule) 还是单独的 path，都提取出真正的路径对象
            file_path: Optional[Path] = None
            try:
                if isinstance(item, (list, tuple)) and len(item) > 0:
                    potential_path = item[0]
                else:
                    potential_path = item
                
                # 统一转为 Path 确保拥有 .exists() 和 .name 属性
                file_path = Path(str(potential_path))
                
                if file_path.exists():
                    os.remove(file_path)
                    success_count += 1
            except PermissionError:
                f_name = file_path.name if file_path else "未知文件"
                self.log_update.emit(f"<font color='#F59E0B'>[权限拒绝] 已跳过: {f_name}</font>")
                fail_count += 1
            except Exception as e:
                f_name = file_path.name if file_path else "错误项"
                self.log_update.emit(f"<font color='#F59E0B'>[删除失败] {f_name}: {str(e)}</font>")
                fail_count += 1

            # 控制进度条更新频率
            current_time = time.time()
            if current_time - last_update_time > 0.1 or (i + 1) == total_tasks:
                progress_pct = int(((i + 1) / total_tasks) * 100)
                self.progress_update.emit(progress_pct)
                last_update_time = current_time

        # --- 彻底铲除数据/结果文件夹 + IDE 缓存目录 ---
        self.log_update.emit("[系统] 正在清理数据与结果目录结构...")
        try:
            # 子串匹配：只要文件夹名包含关键字就清理
            dir_keywords = ['data', 'datass', 'result']
            # 精确匹配：IDE/编译缓存目录名完全一致才清理
            ide_junk_dirs = {'__pycache__', '.idea', '.vscode', '.cursor', '.superdesign'}
            # 采用自下而上的遍历 (topdown=False) 确保能干净地删除嵌套文件夹
            for root, dirs, _ in os.walk(self.target_dir, topdown=False):
                for d in dirs:
                    d_lower = d.lower()
                    should_remove = False
                    # 数据/结果目录：子串匹配
                    if any(kw in d_lower for kw in dir_keywords):
                        should_remove = True
                    # IDE 缓存目录：精确匹配
                    if d in ide_junk_dirs:
                        should_remove = True
                    if should_remove:
                        dir_path = Path(root) / d
                        try:
                            shutil.rmtree(dir_path)
                        except Exception:
                            pass
        except Exception:
            pass

        self.clean_finished.emit(success_count, fail_count)

# ---------------------------------------------------------
# 空文件夹扫描工具
# ---------------------------------------------------------
def find_empty_dirs(root_path: Union[str, Path]) -> list[Path]:
    """
    深度扫描真正的空文件夹。
    逻辑：自底向上，确保完全没有任何实体（文件或非空子目录）的目录才被列入。
    """
    empty_dirs: list[Path] = []
    root_path = Path(root_path)

    # 定义极其严格的保护后缀：只要目录包含这些，绝不视为“空”
    protected_exts = {'.py', '.sh', '.md', '.docx', '.pptx', '.pdf', '.xlsx', '.xls', '.doc', '.caj', '.cdr'}

    for dirpath, _, filenames in os.walk(root_path, topdown=False):
        current = Path(dirpath)
        if current == root_path:
            continue

        # 核心防御 1：如果 filenames 里有任何东西，绝对不是空的
        if filenames:
            # 进一步检查是否有受保护的资产（双重保险）
            if any(Path(f).suffix.lower() in protected_exts for f in filenames):
                continue
            # 就算是黑名单里的文件还没删干净，也不触发“空文件夹”逻辑，交给主清理流程
            continue

        # 核心防御 2：使用 os.scandir 检查，确保没有任何隐藏实体
        try:
            is_empty = True
            with os.scandir(current) as it:
                for entry in it:
                    # 如果有任何文件，不为空
                    if entry.is_file():
                        is_empty = False
                        break
                    # 如果有文件夹，但该文件夹没被列入待删的 empty_dirs，说明它还有内容
                    if entry.is_dir():
                        if Path(entry.path) not in empty_dirs:
                            is_empty = False
                            break
            
            if is_empty:
                # 检查目录名是否在保护列表中（防止破坏某些带结构的空项目）
                if current.name.lower() in ['important_data', 'keep', 'final_results', '不要删']:
                    continue
                empty_dirs.append(current)
        except (PermissionError, OSError):
            continue

    # 深度排序
    empty_dirs.sort(key=lambda p: len(p.parts), reverse=True)
    return empty_dirs


# ---------------------------------------------------------
# 空文件夹清理对话框
# ---------------------------------------------------------
class EmptyFolderDialog(QDialog):
    """可勾选的空文件夹列表对话框"""
    list_widget: QListWidget

    def __init__(self, empty_dirs: list[Path], base_path: Union[str, Path], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.empty_dirs: list[Path] = empty_dirs
        self.base_path: Path = Path(base_path)
        self.setWindowTitle('空文件夹清理')
        self.resize(600, 420)
        self.initUI()

    def initUI(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        # 标题
        title = QLabel(f"发现 {len(self.empty_dirs)} 个空文件夹")
        title.setFont(QtGui.QFont("Segoe UI", 12, QtGui.QFont.Bold)) # type: ignore
        title.setStyleSheet("color: #1E293B;")
        layout.addWidget(title)

        hint = QLabel("勾选你需要删除的空文件夹，取消勾选的将被保留：")
        hint.setFont(QtGui.QFont("Segoe UI", 9)) # type: ignore
        hint.setStyleSheet("color: #64748B;")
        layout.addWidget(hint)

        # 可勾选列表
        self.list_widget = QListWidget()
        self.list_widget.setFont(QtGui.QFont("Consolas", 9)) # type: ignore
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection) # type: ignore
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                padding: 6px;
            }
            QListWidget::item {
                padding: 4px 2px;
                border-bottom: 1px solid #F1F5F9;
            }
        """)

        for d in self.empty_dirs:
            try:
                rel = d.relative_to(self.base_path)
            except ValueError:
                rel = d
            # 改进显示：如果路径太深，只取最后几段，并把完整路径显示在鼠标悬停提示中
            full_rel_str = str(rel)
            if len(full_rel_str) > 75:
                display_str = "..." + full_rel_str[-72:]
            else:
                display_str = full_rel_str

            item = QListWidgetItem(display_str)
            item.setToolTip(f"完整路径: {d}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable) # type: ignore
            item.setCheckState(Qt.Checked) # type: ignore
            item.setData(Qt.UserRole, str(d)) # type: ignore
            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        # 全选/全不选 按钮行
        select_layout = QHBoxLayout()
        select_all_btn = QPushButton("全选")
        select_all_btn.setFixedSize(70, 28)
        select_all_btn.setCursor(Qt.PointingHandCursor) # type: ignore
        select_all_btn.clicked.connect(self._select_all)
        select_all_btn.setStyleSheet("""
            QPushButton { background-color: #F1F5F9; color: #475569;
                          border: 1px solid #E2E8F0; border-radius: 6px;
                          font-size: 12px; }
            QPushButton:hover { background-color: #E2E8F0; }
        """)

        deselect_all_btn = QPushButton("全不选")
        deselect_all_btn.setFixedSize(70, 28)
        deselect_all_btn.setCursor(Qt.PointingHandCursor) # type: ignore
        deselect_all_btn.clicked.connect(self._deselect_all)
        deselect_all_btn.setStyleSheet(select_all_btn.styleSheet())

        select_layout.addWidget(select_all_btn)
        select_layout.addWidget(deselect_all_btn)
        select_layout.addStretch()
        layout.addLayout(select_layout)

        # 确认/取消 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(14)

        cancel_btn = QPushButton("跳过")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setCursor(Qt.PointingHandCursor) # type: ignore
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("""
            QPushButton { background-color: #F1F5F9; color: #475569;
                          border: 1px solid #E2E8F0; border-radius: 8px;
                          font-weight: 600; font-size: 13px; }
            QPushButton:hover { background-color: #E2E8F0; color: #1E293B; }
        """)

        confirm_btn = QPushButton("删除选中的空文件夹")
        confirm_btn.setFixedHeight(36)
        confirm_btn.setCursor(Qt.PointingHandCursor) # type: ignore
        confirm_btn.clicked.connect(self.accept)
        confirm_btn.setStyleSheet("""
            QPushButton { background-color: #0F172A; color: white;
                          border-radius: 8px; border: none;
                          font-weight: 600; font-size: 13px;
                          letter-spacing: 1px; }
            QPushButton:hover { background-color: #1E293B; }
        """)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(confirm_btn)
        layout.addLayout(btn_layout)

        # 对话框整体样式
        self.setStyleSheet("QDialog { background-color: #FFFFFF; }")

    def _select_all(self) -> None:
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item:
                item.setCheckState(Qt.Checked) # type: ignore

    def _deselect_all(self) -> None:
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item:
                item.setCheckState(Qt.Unchecked) # type: ignore

    def get_selected_dirs(self) -> list[Path]:
        """返回用户勾选的文件夹路径列表"""
        selected: list[Path] = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item and item.checkState() == Qt.Checked: # type: ignore
                selected.append(Path(str(item.data(Qt.UserRole)))) # type: ignore
        return selected


# ---------------------------------------------------------
# 主窗口：UI 界面 (PyQt5)
# ---------------------------------------------------------
class ZDEMArchiverWindow(QMainWindow):
    path_input: QLineEdit
    browse_btn: QPushButton
    log_browser: QTextBrowser
    clear_log_btn: QPushButton
    progress_bar: QProgressBar
    dry_run_btn: QPushButton
    clean_btn: QPushButton
    scanner_thread: ScannerThread
    cleaner_thread: CleanerThread

    def __init__(self) -> None:
        super().__init__()
        self.files_to_delete_cache: list[tuple[Path, float, str]] = [] # 缓存预演生成的待删除列表
        self.initUI()

    def initUI(self) -> None:
        self.setWindowTitle('ZDEM Archiver | 归档清理工具')
        self.resize(720, 560)
        
        # 居中显示
        primary_screen = QApplication.primaryScreen()
        if primary_screen:
            screen_geo = primary_screen.geometry()
            size = self.geometry()
            self.move((screen_geo.width() - size.width()) // 2, (screen_geo.height() - size.height()) // 2)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        # 增加内边距，提升留白和呼吸感
        layout.setContentsMargins(35, 30, 35, 30)
        layout.setSpacing(18)

        # 1. 顶部：路径选择
        path_layout = QHBoxLayout()
        path_label = QLabel("项目路径:")
        path_label.setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Bold)) # type: ignore
        
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("请选择 ZDEM 项目文件夹...")
        self.path_input.setReadOnly(True)
        self.path_input.setFixedHeight(36)
        
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.setObjectName("browse_btn")
        self.browse_btn.setFixedSize(85, 36)
        self.browse_btn.setCursor(Qt.PointingHandCursor) # type: ignore
        self.browse_btn.clicked.connect(self.browse_folder)
        
        path_layout.addWidget(path_label)
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.browse_btn)
        layout.addLayout(path_layout)

        # 2. 中部：日志区域 (带标题和清空按钮)
        log_header_layout = QHBoxLayout()
        log_label = QLabel("执行日志:")
        log_label.setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Bold)) # type: ignore
        
        self.clear_log_btn = QPushButton("清空日志")
        self.clear_log_btn.setFixedSize(70, 26)
        self.clear_log_btn.setCursor(Qt.PointingHandCursor) # type: ignore
        self.clear_log_btn.clicked.connect(self.clear_logs)
        
        log_header_layout.addWidget(log_label)
        log_header_layout.addStretch()
        log_header_layout.addWidget(self.clear_log_btn)
        layout.addLayout(log_header_layout)

        self.log_browser = QTextBrowser()
        self.log_browser.setFont(QtGui.QFont("Consolas", 10)) # type: ignore
        layout.addWidget(self.log_browser)
        self.append_log("ZDEM Archiver 归档清理核心已就绪。")
        self.append_log("等待指定目标路径。点击 [扫描预演] 开始安全检索。")

        # 3. 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8) # 略微增加高度以配合全圆角
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        # 4. 底部：操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(20)
        
        self.dry_run_btn = QPushButton("扫描预演")
        self.dry_run_btn.setFixedHeight(42)
        self.dry_run_btn.setCursor(Qt.PointingHandCursor) # type: ignore
        self.dry_run_btn.clicked.connect(self.start_dry_run)
        
        self.clean_btn = QPushButton("一键清理")
        self.clean_btn.setFixedHeight(42)
        self.clean_btn.setEnabled(False)
        self.clean_btn.clicked.connect(self.start_clean)
        
        btn_layout.addWidget(self.dry_run_btn)
        btn_layout.addWidget(self.clean_btn)
        layout.addLayout(btn_layout)

        self.apply_stylesheet()

    def browse_folder(self) -> None:
        folder_path = QFileDialog.getExistingDirectory(self, "选择 ZDEM 项目文件夹")
        if folder_path:
            self.path_input.setText(folder_path)
            self.clean_btn.setEnabled(False) # 路径改变，重置清理按钮状态
            self.clean_btn.setStyleSheet("")
            self.progress_bar.setValue(0)

    def append_log(self, text: str) -> None:
        """线程安全的日志添加，并自动滚动到底部"""
        self.log_browser.append(text)
        self.log_browser.moveCursor(QtGui.QTextCursor.End) # type: ignore

    def clear_logs(self) -> None:
        self.log_browser.clear()
        self.append_log("[系统] 日志已清空，等待新指令。")

    def start_dry_run(self) -> None:
        target_dir = self.path_input.text()
        if not target_dir or not os.path.exists(target_dir):
            self.append_log("<font color='#EF4444'>[错误] 请先选择有效的项目路径！</font>")
            return
            
        self.append_log("<br/><b>[指令] 启动预演扫描...</b>")
        self.dry_run_btn.setEnabled(False)
        self.clean_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(self.get_blue_progress_style())

        # 启动扫描后台线程
        self.scanner_thread = ScannerThread(target_dir)
        self.scanner_thread.progress_update.connect(self.progress_bar.setValue)
        self.scanner_thread.log_update.connect(self.append_log)
        self.scanner_thread.scan_finished.connect(self.on_scan_finished)
        self.scanner_thread.start()

    def on_scan_finished(self, result: dict[str, object]) -> None:
        files_to_delete: list[tuple[Path, float, str]] = cast(list, result['files_to_delete']) # type: ignore
        total_freed_bytes: float = cast(float, result['total_freed_bytes'])
        rule_stats: dict[str, dict[str, Any]] = cast(dict, result['rule_stats']) # type: ignore

        # 缓存扫描结果供正式清理使用
        self.files_to_delete_cache = files_to_delete
        
        self.append_log("<br/>" + "━" * 50)
        self.append_log("<font color='#1E293B' size='4'><b>🔍 预演预警：详细删除清单 (Physical Purge Preview)</b></font>")
        self.append_log("━" * 50)
        
        if not files_to_delete:
            self.append_log("<font color='#10B981'><b>[通知] 目录状态良好，未发现符合清理规则的冗余文件。</b></font>")
            self.dry_run_btn.setEnabled(True)
            self.browse_btn.setEnabled(True)
            return

        # --- 1. 按规则分类展示文件的详细路径 ---
        self.append_log("<b>[详细路径审查 - 仅显示部分代表项]:</b>")
        
        # 按规则对文件进行分组展示
        grouped_files: dict[str, list[tuple[Path, float]]] = {}
        target_base = self.path_input.text()
        
        for item in files_to_delete:
            try:
                if isinstance(item, (list, tuple)) and len(item) >= 3:
                    fp, sz, rule = Path(str(item[0])), float(item[1]), str(item[2])
                elif isinstance(item, Path):
                    fp, sz, rule = item, 0.0, "归档归类项"
                else:
                    fp, sz, rule = Path(str(item)), 0.0, "未知属性项"
            except (IndexError, TypeError, ValueError):
                fp, sz, rule = Path(str(item)), 0.0, "解析错误项"

            if rule not in grouped_files:
                grouped_files[rule] = []
            grouped_files[rule].append((fp, sz))
            
        target_base = self.path_input.text()
        
        for rule_name in sorted(grouped_files.keys()):
            items = grouped_files[rule_name]
            # 根据规则赋予不同颜色以便区分
            group_color = "#334155" # 缺省
            if '数据' in rule_name or '结果' in rule_name: group_color = "#2563EB" # 蓝
            if 'IDE' in rule_name or '缓存' in rule_name: group_color = "#7C3AED" # 紫
            if 'GIF' in rule_name: group_color = "#BE185D" # 艳红
            
            self.append_log(f"<br/><font color='{group_color}'><b>▶ 【{rule_name}】共 {len(items)} 个项:</b></font>")
            
            # 显示上限限制，防止日志太多导致 UI 卡顿
            LIMIT = 300 
            for i, (fp, sz) in enumerate(items):
                if i >= LIMIT:
                    self.append_log(f"   <font color='#94A3B8'><i>... (此项下省略其余 {len(items) - LIMIT} 个同类文件路径)</i></font>")
                    break
                try:
                    rel_path = Path(fp).relative_to(target_base)
                except:
                    rel_path = Path(fp).name
                self.append_log(f"   <font color='#64748B' size='2'>[{format_size(sz)}] {rel_path}</font>")

        # --- 2. 摘要汇总展示 ---
        self.append_log("<br/>" + "─" * 40)
        self.append_log("<b>📊 空间释放汇总 (按规则计):</b>")
        
        # 排序：按字节数降序
        sorted_rules = sorted(rule_stats.items(), key=lambda x: x[1]['bytes'], reverse=True)
        for rule_name, stats in sorted_rules:
            count = stats['count']
            size_str = format_size(stats['bytes'])
            self.append_log(f"  • {rule_name:<12s}: 待删除 <b>{count:>5d}</b> 个，共 <b>{size_str}</b>")
        
        self.append_log("─" * 40)
        final_summary = (
            f"<font color='#0F172A'><b>总预定释放:</b> "
            f"<b>{len(files_to_delete)}</b> 文件 / "
            f"<font color='#EF4444'><b>{format_size(total_freed_bytes)}</b></font></font>"
        )
        self.append_log(final_summary)
        
        # 风险提示
        self.append_log("<br/><font color='#EF4444'><b>⚠️ 注意：本清理操作为【物理永久删除】，不进入回收站。</b></font>")
        self.append_log("<font color='#1E293B'>请确保上述列表中的文件不再需要，确认无误后点击下方 [一键清理]。</font>")
        self.append_log("━" * 50 + "<br/>")

        self.clean_btn.setEnabled(True)
        self.clean_btn.setStyleSheet(self.get_active_clean_btn_style())
        self.dry_run_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)

    def start_clean(self) -> None:
        if not self.files_to_delete_cache:
            return

        target_dir = self.path_input.text()
        self.append_log("<br/><font color='#EF4444'><b>[指令] 正在执行物理清除，请勿中断进程...</b></font>")
        self.dry_run_btn.setEnabled(False)
        self.clean_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(self.get_red_progress_style())

        # 启动清理后台线程
        self.cleaner_thread = CleanerThread(self.files_to_delete_cache, target_dir)
        self.cleaner_thread.progress_update.connect(self.progress_bar.setValue)
        self.cleaner_thread.log_update.connect(self.append_log)
        self.cleaner_thread.clean_finished.connect(self.on_clean_finished)
        self.cleaner_thread.start()

    def on_clean_finished(self, success_count: float, fail_count: float) -> None:
        self.append_log(f"<font color='#10B981'><b>[成功] 数据净化完成。安全移除 {int(success_count)} 个文件及对应 DATA 目录。</b></font>")
        if fail_count > 0:
            self.append_log(f"<font color='#F59E0B'>[警告] 另有 {int(fail_count)} 个文件因权限保护被跳过。</font>")
        
        self.dry_run_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.clean_btn.setStyleSheet("") # 恢复禁用状态样式
        self.files_to_delete_cache = [] # 清空缓存

        # === 空文件夹清理 ===
        target_dir = self.path_input.text()
        if target_dir and os.path.exists(target_dir):
            self.append_log("<br/>[系统] 正在扫描残留空文件夹...")
            empty_dirs = find_empty_dirs(target_dir)

            if empty_dirs:
                self.append_log(f"<font color='#F59E0B'>[发现] 检测到 {len(empty_dirs)} 个空文件夹，等待用户确认。</font>")
                dialog = EmptyFolderDialog(empty_dirs, target_dir, parent=self)
                if dialog.exec_() == QDialog.Accepted: # type: ignore
                    selected = dialog.get_selected_dirs()
                    if selected:
                        removed = 0
                        for d in selected:
                            try:
                                # 用 rmtree 确保即使有隐藏文件也能删除
                                if d.exists():
                                    shutil.rmtree(d)
                                    removed += 1
                            except Exception as e:
                                self.append_log(f"<font color='#F59E0B'>[警告] 无法删除: {d.name} ({e})</font>")
                        self.append_log(f"<font color='#10B981'><b>[成功] 已清理 {removed} 个空文件夹。</b></font>")
                    else:
                        self.append_log("[系统] 未选中任何空文件夹，已跳过。")
                else:
                    self.append_log("[系统] 用户跳过空文件夹清理。")
            else:
                self.append_log("<font color='#10B981'>[系统] 未发现残留空文件夹，目录结构整洁。</font>")

    # ---------------- UI 样式定义 (学术高级感) ----------------
    def apply_stylesheet(self) -> None:
        qss = """
        QMainWindow { 
            background-color: #FFFFFF; 
        }
        QLabel { 
            color: #1E293B; 
        }
        QLineEdit {
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 0 12px;
            background-color: #F8FAFC;
            color: #334155;
            font-size: 13px;
        }
        QLineEdit:focus {
            border: 1px solid #94A3B8;
            background-color: #FFFFFF;
        }
        QTextBrowser {
            background-color: #0F172A;
            color: #F8FAFC;
            border-radius: 12px;
            padding: 14px;
            border: 1px solid #E2E8F0;
            line-height: 1.6;
            selection-background-color: #3B82F6;
        }
        QPushButton {
            font-family: "Segoe UI", "Microsoft YaHei";
            font-weight: 600;
            font-size: 13px;
            border-radius: 8px;
            border: none;
        }
        QPushButton#browse_btn {
            background-color: #F1F5F9;
            color: #475569;
            border: 1px solid #E2E8F0;
            font-weight: normal;
        }
        QPushButton#browse_btn:hover { background-color: #E2E8F0; color: #1E293B; }
        
        QPushButton#dry_run {
            background-color: #0F172A;
            color: white;
            letter-spacing: 1px;
        }
        QPushButton#dry_run:hover { background-color: #1E293B; }
        QPushButton#dry_run:disabled { background-color: #F1F5F9; color: #94A3B8; }
        
        QPushButton#clear_btn {
            background-color: transparent;
            color: #94A3B8;
            font-size: 12px;
            font-weight: normal;
            border: 1px solid transparent;
        }
        QPushButton#clear_btn:hover { color: #475569; text-decoration: underline; }
        """
        self.setStyleSheet(qss)
        self.dry_run_btn.setObjectName("dry_run")
        self.clear_log_btn.setObjectName("clear_btn")

    def get_active_clean_btn_style(self) -> str:
        return """
        QPushButton {
            background-color: #BE123C; /* 勃艮第红，克制的高级警示色 */
            color: white;
            font-family: "Segoe UI", "Microsoft YaHei";
            font-weight: 600;
            font-size: 13px;
            border-radius: 8px;
            border: none;
            letter-spacing: 1px;
        }
        QPushButton:hover { background-color: #9F1239; }
        """
        
    def get_blue_progress_style(self) -> str:
        return """
        QProgressBar { border: none; background-color: #F1F5F9; border-radius: 4px; }
        QProgressBar::chunk { background-color: #0F172A; border-radius: 4px; }
        """
        
    def get_red_progress_style(self) -> str:
        return """
        QProgressBar { border: none; background-color: #F1F5F9; border-radius: 4px; }
        QProgressBar::chunk { background-color: #BE123C; border-radius: 4px; }
        """

if __name__ == '__main__':
    app = QApplication(sys.argv)
    # 优先使用 Segoe UI，提供极佳的英文和数字渲染，中文会自动回退到系统优雅字体
    app.setFont(QtGui.QFont("Segoe UI", 9)) # type: ignore
    window = ZDEMArchiverWindow()
    window.show()
    sys.exit(app.exec_())