import os
import re
import sys
import time
import shutil
from pathlib import Path
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QTextBrowser, QProgressBar, QCheckBox, QFileDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor

# ---------------------------------------------------------
# 实用工具函数：字节转换
# ---------------------------------------------------------
def format_size(size_in_bytes):
    """将字节数转换为人类可读的格式 (KB, MB, GB)"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} PB"

# ---------------------------------------------------------
# 核心逻辑：文件过滤规则
# ---------------------------------------------------------
def should_delete_file(file_path, base_path):
    """
    判断单个文件是否需要被删除
    返回 True (需删除) 或 False (需保留)
    """
    try:
        rel_path = file_path.relative_to(base_path)
        parts = rel_path.parts
        name = file_path.name
        suffix = file_path.suffix.lower()

        # [1] 白名单：绝对保护核心文件 (优先匹配)
        if name.lower() in ['ini_xyr.dat']:
            return False
        if suffix in ['.py', '.sh', '.md']:
            return False

        # [2] 黑名单：清理 DATA 文件夹内的所有文件
        # 只要文件的任意上级目录包含 'data' (忽略大小写)，即判定为数据文件
        if any(p.lower() == 'data' for p in parts[:-1]):
            return True

        # [3] 黑名单：清理各类日志和输出冗余
        if suffix in ['.log', '.err', '.error', '.out']:
            return True

        # [4] 精细规则：处理 .dat 文件
        if suffix == '.dat':
            # 匹配带时间步的文件名，例如 result_10000.dat, output2000.dat
            # 正则解释: 匹配下划线+数字+.dat，或者直接数字+.dat结尾
            if re.search(r'_\d+\.dat$', name.lower()) or re.search(r'\d+\.dat$', name.lower()):
                return True
            else:
                # 不带时间步的 .dat 予以保留
                return False

        # [5] 默认处理：如果都不匹配，为了安全起见，默认保留
        return False

    except Exception:
        # 如果解析路径发生异常，保守起见不删除
        return False

# ---------------------------------------------------------
# 线程 1：扫描预演线程 (Dry-run Scanner)
# ---------------------------------------------------------
class ScannerThread(QThread):
    progress_update = pyqtSignal(int)
    log_update = pyqtSignal(str)
    scan_finished = pyqtSignal(list, int) # 返回 (待删除文件路径列表, 待释放总字节数)

    def __init__(self, target_dir):
        super().__init__()
        self.target_dir = Path(target_dir)

    def run(self):
        self.log_update.emit("[系统] 正在初始化扫描环境...")
        
        # 第一遍：快速统计文件总数，用于计算精确进度条
        self.log_update.emit("[系统] 正在评估目录规模...")
        total_files = sum(len(files) for _, _, files in os.walk(self.target_dir))
        
        if total_files == 0:
            self.log_update.emit("[警告] 目标目录为空或不存在。")
            self.scan_finished.emit([], 0)
            return

        self.log_update.emit(f"[系统] 发现总计 {total_files} 个文件，开始执行规则匹配...")
        
        files_to_delete = []
        total_freed_bytes = 0
        processed_files = 0
        
        # 为了防止 UI 频繁刷新导致卡顿，限制刷新频率
        last_update_time = time.time()

        # 第二遍：执行匹配逻辑
        for root, _, files in os.walk(self.target_dir):
            root_path = Path(root)
            for file in files:
                file_path = root_path / file
                processed_files += 1

                # 规则判断
                if should_delete_file(file_path, self.target_dir):
                    files_to_delete.append(file_path)
                    try:
                        total_freed_bytes += file_path.stat().st_size
                    except OSError:
                        pass # 忽略无法读取大小的文件

                # 控制进度条更新频率 (每 0.1 秒刷新一次)
                current_time = time.time()
                if current_time - last_update_time > 0.1 or processed_files == total_files:
                    progress_pct = int((processed_files / total_files) * 100)
                    self.progress_update.emit(progress_pct)
                    last_update_time = current_time

        self.log_update.emit("[成功] 目录扫描与预演完成。")
        self.scan_finished.emit(files_to_delete, total_freed_bytes)

# ---------------------------------------------------------
# 线程 2：物理清理线程 (Cleaner)
# ---------------------------------------------------------
class CleanerThread(QThread):
    progress_update = pyqtSignal(int)
    log_update = pyqtSignal(str)
    clean_finished = pyqtSignal(int, int) # 返回 (成功删除数, 失败数)

    def __init__(self, files_to_delete, target_dir):
        super().__init__()
        self.files_to_delete = files_to_delete
        self.target_dir = Path(target_dir)

    def run(self):
        total_tasks = len(self.files_to_delete)
        if total_tasks == 0:
            self.clean_finished.emit(0, 0)
            return

        success_count = 0
        fail_count = 0
        last_update_time = time.time()

        for i, file_path in enumerate(self.files_to_delete):
            try:
                # 核心：物理删除文件
                os.remove(file_path)
                success_count += 1
            except PermissionError:
                # 异常捕获：文件被占用
                self.log_update.emit(f"<font color='#F59E0B'>[警告] 权限拒绝或文件被占用，已跳过: {file_path.name}</font>")
                fail_count += 1
            except FileNotFoundError:
                fail_count += 1
            except Exception as e:
                self.log_update.emit(f"<font color='#F59E0B'>[警告] 删除失败 ({str(e)}): {file_path.name}</font>")
                fail_count += 1

            # 控制进度条更新频率
            current_time = time.time()
            if current_time - last_update_time > 0.1 or (i + 1) == total_tasks:
                progress_pct = int(((i + 1) / total_tasks) * 100)
                self.progress_update.emit(progress_pct)
                last_update_time = current_time

        # --- 新增逻辑：彻底铲除 DATA 文件夹及其子目录结构 ---
        self.log_update.emit("[系统] 正在清理 DATA 目录结构...")
        try:
            # 采用自下而上的遍历 (topdown=False) 确保能干净地删除嵌套文件夹
            for root, dirs, files in os.walk(self.target_dir, topdown=False):
                for d in dirs:
                    if d.lower() == 'data':
                        dir_path = Path(root) / d
                        try:
                            # 强制删除整个 DATA 文件夹
                            shutil.rmtree(dir_path)
                        except Exception:
                            pass
        except Exception:
            pass

        self.clean_finished.emit(success_count, fail_count)

# ---------------------------------------------------------
# 主窗口：UI 界面 (PyQt5)
# ---------------------------------------------------------
class ZDEMArchiverWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.files_to_delete_cache = [] # 缓存预演生成的待删除列表
        self.initUI()

    def initUI(self):
        self.setWindowTitle('ZDEM Archiver | 归档清理工具')
        self.resize(720, 560)
        
        # 居中显示
        screen = QApplication.primaryScreen().geometry()
        size = self.geometry()
        self.move((screen.width() - size.width()) // 2, (screen.height() - size.height()) // 2)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        # 增加内边距，提升留白和呼吸感
        layout.setContentsMargins(35, 30, 35, 30)
        layout.setSpacing(18)

        # 1. 顶部：路径选择
        path_layout = QHBoxLayout()
        path_label = QLabel("项目路径:")
        path_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("请选择 ZDEM 项目文件夹...")
        self.path_input.setReadOnly(True)
        self.path_input.setFixedHeight(36)
        
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.setObjectName("browse_btn")
        self.browse_btn.setFixedSize(85, 36)
        self.browse_btn.setCursor(Qt.PointingHandCursor)
        self.browse_btn.clicked.connect(self.browse_folder)
        
        path_layout.addWidget(path_label)
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.browse_btn)
        layout.addLayout(path_layout)

        # 2. 中部：日志区域 (带标题和清空按钮)
        log_header_layout = QHBoxLayout()
        log_label = QLabel("执行日志:")
        log_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        
        self.clear_log_btn = QPushButton("清空日志")
        self.clear_log_btn.setFixedSize(70, 26)
        self.clear_log_btn.setCursor(Qt.PointingHandCursor)
        self.clear_log_btn.clicked.connect(self.clear_logs)
        
        log_header_layout.addWidget(log_label)
        log_header_layout.addStretch()
        log_header_layout.addWidget(self.clear_log_btn)
        layout.addLayout(log_header_layout)

        self.log_browser = QTextBrowser()
        self.log_browser.setFont(QFont("Consolas", 10))
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
        self.dry_run_btn.setCursor(Qt.PointingHandCursor)
        self.dry_run_btn.clicked.connect(self.start_dry_run)
        
        self.clean_btn = QPushButton("一键清理")
        self.clean_btn.setFixedHeight(42)
        self.clean_btn.setEnabled(False)
        self.clean_btn.clicked.connect(self.start_clean)
        
        btn_layout.addWidget(self.dry_run_btn)
        btn_layout.addWidget(self.clean_btn)
        layout.addLayout(btn_layout)

        self.apply_stylesheet()

    def browse_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "选择 ZDEM 项目文件夹")
        if folder_path:
            self.path_input.setText(folder_path)
            self.clean_btn.setEnabled(False) # 路径改变，重置清理按钮状态
            self.clean_btn.setStyleSheet("")
            self.progress_bar.setValue(0)

    def append_log(self, text):
        """线程安全的日志添加，并自动滚动到底部"""
        self.log_browser.append(text)
        self.log_browser.moveCursor(QTextCursor.End)

    def clear_logs(self):
        self.log_browser.clear()
        self.append_log("[系统] 日志已清空，等待新指令。")

    def start_dry_run(self):
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

    def on_scan_finished(self, files_to_delete, total_freed_bytes):
        self.files_to_delete_cache = files_to_delete
        
        self.append_log("-" * 50)
        self.append_log("预演结果汇总：")
        self.append_log(f"  - 将删除文件数: {len(files_to_delete)} 个")
        self.append_log(f"  - 预计释放空间: <font color='#10B981'><b>{format_size(total_freed_bytes)}</b></font>")
        self.append_log("-" * 50)
        
        self.dry_run_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)

        if len(files_to_delete) > 0:
            self.append_log("<font color='#F59E0B'>[注意] 确认无误后，点击 [一键清理] 执行物理清除。</font>")
            self.clean_btn.setEnabled(True)
            self.clean_btn.setStyleSheet(self.get_active_clean_btn_style())
        else:
            self.append_log("[系统] 目标目录已优化，无需清理。")

    def start_clean(self):
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

    def on_clean_finished(self, success_count, fail_count):
        self.append_log(f"<font color='#10B981'><b>[成功] 数据净化完成。安全移除 {success_count} 个文件及对应 DATA 目录。</b></font>")
        if fail_count > 0:
            self.append_log(f"<font color='#F59E0B'>[警告] 另有 {fail_count} 个文件因权限保护被跳过。</font>")
        
        self.dry_run_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.clean_btn.setStyleSheet("") # 恢复禁用状态样式
        self.files_to_delete_cache = [] # 清空缓存

    # ---------------- UI 样式定义 (学术高级感) ----------------
    def apply_stylesheet(self):
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

    def get_active_clean_btn_style(self):
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
        
    def get_blue_progress_style(self):
        return """
        QProgressBar { border: none; background-color: #F1F5F9; border-radius: 4px; }
        QProgressBar::chunk { background-color: #0F172A; border-radius: 4px; }
        """
        
    def get_red_progress_style(self):
        return """
        QProgressBar { border: none; background-color: #F1F5F9; border-radius: 4px; }
        QProgressBar::chunk { background-color: #BE123C; border-radius: 4px; }
        """

if __name__ == '__main__':
    app = QApplication(sys.argv)
    # 优先使用 Segoe UI，提供极佳的英文和数字渲染，中文会自动回退到系统优雅字体
    app.setFont(QFont("Segoe UI", 9))
    window = ZDEMArchiverWindow()
    window.show()
    sys.exit(app.exec_())