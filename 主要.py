# -*- coding: utf-8 -*-
import sys
import os
import subprocess
import shutil
import threading
import queue
import time
from pathlib import Path

# ---------- 自定义异常捕获（防止闪退） ----------
def show_error_and_exit(title, message):
    """用图形窗口显示错误并退出"""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except:
        # 如果连tkinter都用不了，则输出到控制台
        print(f"{title}: {message}")
        input("按回车键退出...")
    sys.exit(1)

# 全局异常钩子
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    show_error_and_exit("程序崩溃", f"发生未捕获的异常:\n{exc_value}")
sys.excepthook = handle_exception

# ---------- 自动安装依赖（带镜像、进度提示） ----------
def install_dependencies():
    required = {
        'tkinterdnd2': 'tkinterdnd2',
        'py7zr': 'py7zr',
        'rarfile': 'rarfile',
        'unrar': 'unrar'
    }
    missing = []
    for module, package in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if not missing:
        return

    # 显示提示窗口
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("安装依赖", "首次运行需要下载一些组件，请稍候...\n如果长时间无响应，可能是网络较慢，请手动安装。")
        root.destroy()
    except:
        pass

    mirrors = [
        'https://pypi.tuna.tsinghua.edu.cn/simple',
        'https://mirrors.aliyun.com/pypi/simple/',
        'https://pypi.douban.com/simple/',
        ''   # 官方源
    ]
    success = False
    for mirror in mirrors:
        try:
            cmd = [sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--timeout=60']
            if mirror:
                cmd += ['-i', mirror]
            cmd += missing
            print(f"正在尝试镜像: {mirror if mirror else '默认源'}")
            # 不静默，让用户可以看到进度
            subprocess.check_call(cmd)
            success = True
            break
        except Exception as e:
            print(f"安装失败: {e}")
            continue

    if not success:
        show_error_and_exit(
            "依赖安装失败",
            f"自动安装失败，请手动打开命令行执行以下命令：\npip install {' '.join(missing)}\n\n"
            "可以使用国内镜像加速：\npip install -i https://pypi.tuna.tsinghua.edu.cn/simple {' '.join(missing)}"
        )

install_dependencies()

# 现在可以安全导入这些库
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinterdnd2 as tkdnd
import py7zr
import rarfile
import zipfile
import tarfile

# ---------- 毛玻璃效果（仅Windows） ----------
def enable_glass(hwnd):
    if os.name != 'nt':
        return
    try:
        import ctypes
        from ctypes import wintypes
        margins = wintypes.MARGINS(-1, -1, -1, -1)
        ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
    except Exception:
        pass

# ---------- 主窗口 ----------
class NBUnzipApp(tkdnd.Tk):
    def __init__(self):
        super().__init__()
        self.title("牛B免费解压缩")
        self.geometry("800x520")
        self.configure(bg='#000000')
        self.resizable(False, False)
        
        # 毛玻璃
        self.update_idletasks()
        hwnd = self.winfo_id()
        if os.name == 'nt':
            try:
                import ctypes
                parent = ctypes.windll.user32.GetParent(hwnd)
                enable_glass(parent)
            except:
                pass
        
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.style.configure('TFrame', background='#1E1E1E')
        self.style.configure('TLabel', background='#1E1E1E', foreground='#E0E0E0', font=('微软雅黑', 11))
        self.style.configure('TButton', font=('微软雅黑', 10), padding=6)
        self.style.configure('TLabelframe', background='#1E1E1E', foreground='#FFFFFF')
        self.style.configure('TLabelframe.Label', background='#1E1E1E', foreground='#FFFFFF', font=('微软雅黑', 12, 'bold'))
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.unzip_paths = []
        self.zip_folder_path = None
        self.queue = queue.Queue()
        
        self.build_ui()
        self.process_queue()

    # 以下全部是原界面代码，保持不变
    def build_ui(self):
        main_frame = tk.Frame(self, bg='#000000')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        title_frame = tk.Frame(main_frame, bg='#000000')
        title_frame.pack(fill=tk.X, pady=(0, 15))
        title_label = tk.Label(title_frame, text="🐮 牛B免费解压缩", font=('微软雅黑', 24, 'bold'), fg='white', bg='#000000')
        title_label.pack(side=tk.LEFT, padx=10)
        
        panes = tk.Frame(main_frame, bg='#000000')
        panes.pack(fill=tk.BOTH, expand=True)
        
        # 解压面板
        unzip_frame = ttk.Labelframe(panes, text="📂 解压文件", padding=15)
        unzip_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        self.unzip_drop_area = tk.Label(unzip_frame, text="拖拽压缩文件到此区域\n(支持 ZIP, 7z, RAR, TAR 等36种格式)",
                                       bg='#2B2B2B', fg='#AAAAAA', font=('微软雅黑', 11), relief=tk.RIDGE, height=8)
        self.unzip_drop_area.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.unzip_drop_area.drop_target_register(tkdnd.DND_FILES)
        self.unzip_drop_area.dnd_bind('<<Drop>>', self.on_unzip_drop)
        
        self.unzip_file_label = ttk.Label(unzip_frame, text="未选择文件", anchor='center', wraplength=300)
        self.unzip_file_label.pack(fill=tk.X, pady=5)
        
        self.unzip_progress = ttk.Progressbar(unzip_frame, mode='indeterminate', length=200)
        self.unzip_progress.pack(pady=5)
        
        unzip_btn_frame = tk.Frame(unzip_frame, bg='#1E1E1E')
        unzip_btn_frame.pack(fill=tk.X, pady=(5, 0))
        self.clear_unzip_btn = ttk.Button(unzip_btn_frame, text="清除", command=self.clear_unzip)
        self.clear_unzip_btn.pack(side=tk.LEFT, padx=5)
        self.unzip_btn = ttk.Button(unzip_btn_frame, text="🚀 解压", command=self.start_unzip)
        self.unzip_btn.pack(side=tk.RIGHT, padx=5)
        
        # 压缩面板
        zip_frame = ttk.Labelframe(panes, text="🗜️ 压缩文件", padding=15)
        zip_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        
        self.zip_drop_area = tk.Label(zip_frame, text="拖拽文件夹到此区域",
                                     bg='#2B2B2B', fg='#AAAAAA', font=('微软雅黑', 11), relief=tk.RIDGE, height=8)
        self.zip_drop_area.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.zip_drop_area.drop_target_register(tkdnd.DND_FILES)
        self.zip_drop_area.dnd_bind('<<Drop>>', self.on_zip_drop)
        
        self.zip_folder_label = ttk.Label(zip_frame, text="未选择文件夹", anchor='center', wraplength=300)
        self.zip_folder_label.pack(fill=tk.X, pady=5)
        
        fmt_frame = tk.Frame(zip_frame, bg='#1E1E1E')
        fmt_frame.pack(fill=tk.X, pady=5)
        ttk.Label(fmt_frame, text="格式:").pack(side=tk.LEFT, padx=(0, 5))
        self.format_var = tk.StringVar(value='zip')
        format_combo = ttk.Combobox(fmt_frame, textvariable=self.format_var, values=['zip', '7z', 'tar', 'gztar', 'bztar', 'xztar'], state='readonly', width=8)
        format_combo.pack(side=tk.LEFT)
        
        self.zip_progress = ttk.Progressbar(zip_frame, mode='indeterminate', length=200)
        self.zip_progress.pack(pady=5)
        
        zip_btn_frame = tk.Frame(zip_frame, bg='#1E1E1E')
        zip_btn_frame.pack(fill=tk.X, pady=(5, 0))
        self.clear_zip_btn = ttk.Button(zip_btn_frame, text="清除", command=self.clear_zip)
        self.clear_zip_btn.pack(side=tk.LEFT, padx=5)
        self.zip_btn = ttk.Button(zip_btn_frame, text="📦 压缩", command=self.start_zip)
        self.zip_btn.pack(side=tk.RIGHT, padx=5)
        
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=5)
        status_bar.pack(fill=tk.X, pady=(10, 0))
    
    def on_unzip_drop(self, event):
        files = self.tk.splitlist(event.data)
        if files:
            path = files[0].strip('{}')
            if os.path.isfile(path):
                self.unzip_paths = [path]
                self.unzip_file_label.config(text=os.path.basename(path))
                self.status_var.set(f"已选择文件: {path}")
            else:
                messagebox.showwarning("提示", "请拖入一个压缩文件，而非文件夹。")
    
    def on_zip_drop(self, event):
        files = self.tk.splitlist(event.data)
        if files:
            path = files[0].strip('{}')
            if os.path.isdir(path):
                self.zip_folder_path = path
                self.zip_folder_label.config(text=os.path.basename(path))
                self.status_var.set(f"已选择文件夹: {path}")
            else:
                messagebox.showwarning("提示", "请拖入一个文件夹。")
    
    def clear_unzip(self):
        self.unzip_paths.clear()
        self.unzip_file_label.config(text="未选择文件")
        self.status_var.set("就绪")
    
    def clear_zip(self):
        self.zip_folder_path = None
        self.zip_folder_label.config(text="未选择文件夹")
        self.status_var.set("就绪")
    
    def start_unzip(self):
        if not self.unzip_paths:
            messagebox.showwarning("提示", "请先拖入压缩文件")
            return
        target_dir = filedialog.askdirectory(title="选择解压目标文件夹")
        if not target_dir:
            return
        self.unzip_btn.config(state=tk.DISABLED)
        self.clear_unzip_btn.config(state=tk.DISABLED)
        self.unzip_progress.start()
        self.status_var.set("正在解压...")
        threading.Thread(target=self.unzip_thread, args=(self.unzip_paths[0], target_dir), daemon=True).start()
    
    def unzip_thread(self, archive_path, target_dir):
        try:
            ext = os.path.splitext(archive_path)[1].lower()
            target_folder = os.path.join(target_dir, Path(archive_path).stem)
            os.makedirs(target_folder, exist_ok=True)
            
            if ext == '.7z':
                with py7zr.SevenZipFile(archive_path, mode='r') as z:
                    z.extractall(target_folder)
            elif ext == '.rar':
                with rarfile.RarFile(archive_path) as rf:
                    rf.extractall(target_folder)
            elif ext == '.zip':
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    zf.extractall(target_folder)
            elif ext in ('.tar', '.gz', '.bz2', '.xz', '.tgz', '.tbz2', '.txz'):
                shutil.unpack_archive(archive_path, target_folder)
            else:
                shutil.unpack_archive(archive_path, target_folder)
            
            self.queue.put(('unzip_done', target_folder, None))
        except Exception as e:
            self.queue.put(('unzip_error', str(e)))
    
    def start_zip(self):
        if not self.zip_folder_path:
            messagebox.showwarning("提示", "请先拖入文件夹")
            return
        fmt = self.format_var.get()
        ext_map = {'zip': '.zip', '7z': '.7z', 'tar': '.tar', 'gztar': '.tar.gz', 'bztar': '.tar.bz2', 'xztar': '.tar.xz'}
        default_ext = ext_map.get(fmt, '.zip')
        save_path = filedialog.asksaveasfilename(
            title="保存压缩包",
            defaultextension=default_ext,
            filetypes=[("压缩文件", f"*{default_ext}")],
            initialfile=os.path.basename(self.zip_folder_path) + default_ext
        )
        if not save_path:
            return
        self.zip_btn.config(state=tk.DISABLED)
        self.clear_zip_btn.config(state=tk.DISABLED)
        self.zip_progress.start()
        self.status_var.set("正在压缩...")
        threading.Thread(target=self.zip_thread, args=(self.zip_folder_path, save_path, fmt), daemon=True).start()
    
    def zip_thread(self, folder_path, save_path, fmt):
        try:
            base_name = os.path.splitext(save_path)[0]
            if fmt == '7z':
                with py7zr.SevenZipFile(save_path, 'w') as z:
                    z.writeall(folder_path, os.path.basename(folder_path))
            else:
                shutil.make_archive(base_name, fmt, root_dir=folder_path, base_dir='.')
            self.queue.put(('zip_done', save_path, None))
        except Exception as e:
            self.queue.put(('zip_error', str(e)))
    
    def process_queue(self):
        try:
            while True:
                msg = self.queue.get_nowait()
                if msg[0] == 'unzip_done':
                    self.unzip_progress.stop()
                    self.unzip_btn.config(state=tk.NORMAL)
                    self.clear_unzip_btn.config(state=tk.NORMAL)
                    target_folder = msg[1]
                    self.status_var.set(f"解压完成: {target_folder}")
                    items = os.listdir(target_folder)
                    if items:
                        first = os.path.join(target_folder, items[0])
                        if os.name == 'nt':
                            subprocess.Popen(['explorer', '/select,', os.path.normpath(first)])
                        else:
                            subprocess.Popen(['open', '-R', first] if sys.platform == 'darwin' else ['xdg-open', target_folder])
                    else:
                        os.startfile(target_folder) if os.name == 'nt' else subprocess.Popen(['xdg-open', target_folder])
                    self.unzip_paths.clear()
                    self.unzip_file_label.config(text="未选择文件")
                elif msg[0] == 'unzip_error':
                    self.unzip_progress.stop()
                    self.unzip_btn.config(state=tk.NORMAL)
                    self.clear_unzip_btn.config(state=tk.NORMAL)
                    self.status_var.set("解压失败")
                    messagebox.showerror("错误", f"解压失败:\n{msg[1]}")
                elif msg[0] == 'zip_done':
                    self.zip_progress.stop()
                    self.zip_btn.config(state=tk.NORMAL)
                    self.clear_zip_btn.config(state=tk.NORMAL)
                    save_path = msg[1]
                    self.status_var.set(f"压缩完成: {save_path}")
                    if os.name == 'nt':
                        subprocess.Popen(['explorer', '/select,', os.path.normpath(save_path)])
                    elif sys.platform == 'darwin':
                        subprocess.Popen(['open', '-R', save_path])
                    else:
                        subprocess.Popen(['xdg-open', os.path.dirname(save_path)])
                    self.zip_folder_path = None
                    self.zip_folder_label.config(text="未选择文件夹")
                elif msg[0] == 'zip_error':
                    self.zip_progress.stop()
                    self.zip_btn.config(state=tk.NORMAL)
                    self.clear_zip_btn.config(state=tk.NORMAL)
                    self.status_var.set("压缩失败")
                    messagebox.showerror("错误", f"压缩失败:\n{msg[1]}")
        except queue.Empty:
            pass
        self.after(100, self.process_queue)
    
    def on_close(self):
        self.destroy()
        sys.exit(0)

if __name__ == "__main__":
    app = NBUnzipApp()
    app.mainloop()
