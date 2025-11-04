"""
百度网盘试卷去手写自动化工具 - GUI 界面
使用 ttkbootstrap 提供现代化的深色主题界面
"""

import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import queue
import threading
import logging
from pathlib import Path
import asyncio
from PIL import Image, ImageTk
from io import BytesIO
import base64

# 导入核心模块
from baidu_automation import BaiduPicFilter


logger = logging.getLogger(__name__)


class LoginWindow(tk.Toplevel):
    """登录窗口，显示二维码并等待用户确认"""
    
    def __init__(self, parent, qrcode_path=None, qrcode_base64=None):
        super().__init__(parent)
        self.title("百度网盘 - 扫码登录")
        self.geometry("500x600")
        self.resizable(False, False)
        self.attributes('-topmost', True)
        
        self.result = None
        self.scanned = False
        
        # 中心窗口
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=BOTH, expand=True, padx=20, pady=20)
        
        # 标题
        title_label = ttk.Label(main_frame, text="📱 请扫描二维码登录", 
                               font=('Microsoft YaHei UI', 14, 'bold'))
        title_label.pack(pady=(0, 20))
        
        # 二维码区域
        qrcode_frame = ttk.Frame(main_frame)
        qrcode_frame.pack(pady=20)
        
        try:
            if qrcode_base64:
                # 从 base64 创建图片
                image_bytes = base64.b64decode(qrcode_base64)
                image = Image.open(BytesIO(image_bytes))
            elif qrcode_path and Path(qrcode_path).exists():
                # 从文件加载图片
                image = Image.open(qrcode_path)
            else:
                # 显示默认占位符
                image = Image.new('RGB', (300, 300), color='lightgray')
            
            # 调整大小
            image = image.resize((300, 300), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            
            qrcode_label = ttk.Label(qrcode_frame, image=photo)
            qrcode_label.image = photo  # 保持引用
            qrcode_label.pack()
        except Exception as e:
            error_label = ttk.Label(qrcode_frame, text=f"⚠️  无法加载二维码\n{e}", 
                                   font=('Microsoft YaHei UI', 10))
            error_label.pack()
        
        # 提示文本
        tip_label = ttk.Label(main_frame, text="使用手机百度 App 或微信扫一扫\n扫描上方二维码进行登录", 
                             font=('Microsoft YaHei UI', 10), justify='center')
        tip_label.pack(pady=20)
        
        # 倒计时标签
        self.countdown_label = ttk.Label(main_frame, text="等待中...", 
                                        font=('Microsoft YaHei UI', 10), foreground='#3498DB')
        self.countdown_label.pack(pady=10)
        
        # 按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=20, fill=X)
        
        # "我已扫描登录"按钮
        confirm_button = ttk.Button(button_frame, text="✅ 我已扫描登录", 
                                   command=self.on_scanned, bootstyle="success")
        confirm_button.pack(side=LEFT, fill=X, expand=True, padx=(0, 5))
        
        # "取消"按钮
        cancel_button = ttk.Button(button_frame, text="❌ 取消", 
                                  command=self.on_cancel, bootstyle="danger")
        cancel_button.pack(side=LEFT, fill=X, expand=True, padx=(5, 0))
        
        self.transient(parent)
        self.grab_set()
        
        # 启动倒计时
        self.start_countdown()
    
    def start_countdown(self):
        """启动倒计时"""
        self.countdown = 300  # 5分钟
        self.update_countdown()
    
    def update_countdown(self):
        """更新倒计时"""
        if self.scanned:
            return
        
        if self.countdown > 0:
            mins, secs = divmod(self.countdown, 60)
            self.countdown_label.config(text=f"请在 {mins}:{secs:02d} 内完成登录，登录后关闭本窗口")
            self.countdown -= 1
            self.after(1000, self.update_countdown)
        else:
            self.countdown_label.config(text="❌ 登录超时，请重试", foreground='#E74C3C')
            self.result = False
            self.destroy()
    
    def on_scanned(self):
        """用户点击'我已扫描登录'按钮"""
        self.scanned = True
        self.result = True
        self.countdown_label.config(text="✅ 正在验证登录状态...", foreground='#27AE60')
        self.after(1000, self.destroy)
    
    def on_cancel(self):
        """用户点击取消"""
        self.result = False
        self.destroy()


class QueueHandler(logging.Handler):
    """将日志送到队列"""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(self.format(record))


class App(ttk.Window):
    """试卷去手写自动化工具 GUI"""
    
    def __init__(self, themename='darkly'):
        super().__init__(themename=themename)
        self.title("百度网盘试卷去手写 - 自动化工具")
        self.geometry("1200x700")
        
        self.bg_color = self.style.colors.get('bg')
        self.style.configure('Transparent.TFrame', background=self.bg_color)
        self.style.configure('White.TLabel', foreground=self.style.colors.get('fg'), 
                           background=self.bg_color, font=('Microsoft YaHei UI', 10))
        self.style.configure('White.TLabelframe.Label', foreground=self.style.colors.get('fg'), 
                           background=self.bg_color, font=('Microsoft YaHei UI', 10))
        
        self.placeholder_text = "输入图片路径或文件夹..."
        self.placeholder_color = 'grey'
        self.default_fg_color = self.style.lookup('TEntry', 'foreground')
        
        self.create_widgets()
        self.setup_logging()
        self.process_thread = None
        self.process_loop = None
        self.client = None
        
    def create_widgets(self):
        """创建GUI组件"""
        bg_frame = ttk.Frame(self)
        bg_frame.pack(fill=BOTH, expand=True)
        
        main_frame = ttk.Frame(bg_frame, padding="15", style='Transparent.TFrame')
        main_frame.pack(fill=BOTH, expand=True)
        main_frame.grid_rowconfigure(2, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        # ============ 标题区域 ============
        title_frame = ttk.Frame(main_frame, style='Transparent.TFrame')
        title_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        
        title_label = ttk.Label(title_frame, text="📝 百度网盘试卷去手写自动化工具", 
                               font=('Microsoft YaHei UI', 14, 'bold'), style='White.TLabel')
        title_label.pack(anchor="w")
        
        # ============ 配置区域 ============
        controls_frame = ttk.Labelframe(main_frame, text="⚙️ 处理配置", 
                                       padding="12", style='White.TLabelframe')
        controls_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        controls_frame.grid_columnconfigure(1, weight=1)
        
        # 输入行1：图片选择
        ttk.Label(controls_frame, text="图片文件:", style='White.TLabel').grid(
            row=0, column=0, sticky="w", padx=5, pady=8)
        
        self.image_var = tk.StringVar()
        self.image_entry = ttk.Entry(controls_frame, textvariable=self.image_var, 
                                    font=('Microsoft YaHei UI', 10))
        self.image_entry.grid(row=0, column=1, sticky="ew", padx=(0, 5), pady=8)
        self.image_entry.insert(0, self.placeholder_text)
        self.image_entry.config(foreground=self.placeholder_color)
        self.image_entry.bind('<FocusIn>', self.on_input_focus_in)
        self.image_entry.bind('<FocusOut>', self.on_input_focus_out)
        
        self.browse_button = ttk.Button(controls_frame, text="📂 选择文件/文件夹", 
                                       command=self.browse_files, bootstyle="light-outline")
        self.browse_button.grid(row=0, column=2, padx=5, pady=8)
        
        self.start_button = ttk.Button(controls_frame, text="🚀 开始处理", 
                                      command=self.start_process, bootstyle="success")
        self.start_button.grid(row=0, column=3, padx=5, pady=8)
        
        self.open_folder_button = ttk.Button(controls_frame, text="📁 打开输出文件夹", 
                                            command=self.open_output_folder, bootstyle="info")
        self.open_folder_button.grid(row=0, column=4, padx=5, pady=8)
        
        # 选项行
        ttk.Label(controls_frame, text="选项:", style='White.TLabel').grid(
            row=1, column=0, sticky="w", padx=5, pady=8)
        
        options_frame = ttk.Frame(controls_frame, style='Transparent.TFrame')
        options_frame.grid(row=1, column=1, columnspan=4, sticky="ew", padx=0, pady=8)
        options_frame.grid_columnconfigure(2, weight=1)
        
        self.headless_var = tk.BooleanVar(value=False)
        self.headless_check = ttk.Checkbutton(options_frame, text="后台运行（无头模式）", 
                                             variable=self.headless_var, bootstyle="round-toggle")
        self.headless_check.grid(row=0, column=0, padx=(0, 15))
        
        ttk.Label(options_frame, text="输出文件夹:", style='White.TLabel').grid(
            row=0, column=1, sticky='w', padx=(0, 5))
        
        self.output_var = tk.StringVar(value="./output")
        self.output_entry = ttk.Entry(options_frame, textvariable=self.output_var, width=20)
        self.output_entry.grid(row=0, column=2, padx=(0, 5), sticky='ew')
        
        self.output_button = ttk.Button(options_frame, text="...", 
                                       command=self.browse_output, width=3, bootstyle="secondary")
        self.output_button.grid(row=0, column=3, padx=(0, 15))
        
        # ============ 日志区域 ============
        log_frame = ttk.Labelframe(main_frame, text="📋 处理日志", padding="10", 
                                  style='White.TLabelframe')
        log_frame.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame, state='disabled', wrap=tk.WORD, 
            font=("Courier New", 9), relief="solid", borderwidth=1, 
            bg="#1C2833", fg="white", insertbackground="white"
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        
        # 配置日志标签样式
        self.log_text.tag_config('INFO', foreground='white')
        self.log_text.tag_config('SUCCESS', foreground='#27AE60', font=("Courier New", 9, "bold"))
        self.log_text.tag_config('WARNING', foreground='#F39C12')
        self.log_text.tag_config('ERROR', foreground='#E74C3C')
        self.log_text.tag_config('PROGRESS', foreground='#3498DB', font=("Courier New", 9, "bold"))
        
        # ============ 状态栏 ============
        status_frame = ttk.Frame(main_frame, style='Transparent.TFrame')
        status_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        
        self.status_var = tk.StringVar(value="✅ 就绪")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, 
                                     style='White.TLabel', font=('Microsoft YaHei UI', 9))
        self.status_label.pack(anchor="w")
        
    def on_input_focus_in(self, event):
        """输入框获得焦点时"""
        if self.image_entry.get() == self.placeholder_text:
            self.image_entry.delete(0, "end")
            self.image_entry.config(foreground=self.default_fg_color)
    
    def on_input_focus_out(self, event):
        """输入框失去焦点时"""
        if not self.image_entry.get():
            self.image_entry.insert(0, self.placeholder_text)
            self.image_entry.config(foreground=self.placeholder_color)
    
    def browse_files(self):
        """浏览文件"""
        files = filedialog.askopenfilenames(
            title="选择图片文件（支持多选）",
            filetypes=(("Image files", "*.jpg *.jpeg *.png *.webp *.bmp"), 
                      ("All files", "*.*")),
            parent=self
        )
        if files:
            self.on_input_focus_in(None)
            self.image_var.set(";".join(files))
    
    def browse_output(self):
        """浏览输出文件夹"""
        folder = filedialog.askdirectory(title="选择输出文件夹", parent=self)
        if folder:
            self.output_var.set(folder)
    
    def open_output_folder(self):
        """打开输出文件夹"""
        import os, sys, subprocess
        output_path = Path(self.output_var.get())
        if not output_path.exists():
            output_path.mkdir(parents=True, exist_ok=True)
        
        try:
            if sys.platform == "win32":
                os.startfile(output_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(output_path)])
            else:
                subprocess.Popen(["xdg-open", str(output_path)])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件夹: {e}", parent=self)
    
    def setup_logging(self):
        """设置日志"""
        self.log_queue = queue.Queue()
        self.queue_handler = QueueHandler(self.log_queue)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        self.queue_handler.setFormatter(formatter)
        logger.addHandler(self.queue_handler)
        logger.setLevel(logging.DEBUG)
        self.after(100, self.poll_log_queue)
    
    def poll_log_queue(self):
        """轮询日志队列"""
        try:
            while True:
                record = self.log_queue.get(block=False)
                self.display_log(record)
        except queue.Empty:
            pass
        finally:
            self.after(100, self.poll_log_queue)
    
    def display_log(self, record):
        """显示日志"""
        self.log_text.configure(state='normal')
        
        # 判断日志级别
        level_tag = 'INFO'
        if '✅' in record or '成功' in record:
            level_tag = 'SUCCESS'
        elif '⚠️' in record or '警告' in record or 'WARNING' in record:
            level_tag = 'WARNING'
        elif '❌' in record or 'ERROR' in record:
            level_tag = 'ERROR'
        elif '🚀' in record or '🔄' in record:
            level_tag = 'PROGRESS'
        
        self.log_text.insert(tk.END, record + '\n', level_tag)
        self.log_text.configure(state='disabled')
        self.log_text.yview(tk.END)
    
    def get_image_files(self):
        """获取图片文件列表"""
        input_str = self.image_var.get().strip()
        
        if not input_str or input_str == self.placeholder_text:
            return None
        
        # 支持多文件选择
        if ";" in input_str:
            files = [f.strip() for f in input_str.split(";") if f.strip()]
        else:
            files = [input_str]
        
        # 过滤存在的文件
        valid_files = []
        for file_path in files:
            path = Path(file_path)
            if path.exists():
                if path.is_file():
                    valid_files.append(str(path))
                elif path.is_dir():
                    for img_file in path.glob("*"):
                        if img_file.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']:
                            valid_files.append(str(img_file))
        
        return valid_files if valid_files else None
    
    def start_process(self):
        """开始处理"""
        image_files = self.get_image_files()
        if not image_files:
            messagebox.showwarning("输入错误", "请输入有效的图片文件路径或文件夹。", parent=self)
            return
        
        self.start_button.config(text="⏹️ 取消处理", command=self.cancel_process, bootstyle="danger")
        self.browse_button.config(state="disabled")
        self.image_entry.config(state="disabled")
        
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state="disabled")
        
        self.status_var.set("⏳ 处理中...")
        
        self.process_thread = threading.Thread(
            target=self.run_async_process,
            args=(image_files,),
            daemon=True
        )
        self.process_thread.start()
    
    def cancel_process(self):
        """取消处理"""
        self.start_button.config(text="正在取消...", state="disabled")
        if self.process_loop and self.process_loop.is_running():
            self.process_loop.call_soon_threadsafe(self.shutdown_async_tasks)
    
    def shutdown_async_tasks(self):
        """关闭异步任务"""
        if not self.process_loop or not self.process_loop.is_running():
            return
        for task in asyncio.all_tasks(loop=self.process_loop):
            task.cancel()
    
    def run_async_process(self, image_files):
        """运行异步处理"""
        import warnings
        
        # 抑制 Windows asyncio 的资源警告
        warnings.filterwarnings('ignore', category=ResourceWarning)
        
        self.process_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.process_loop)
        
        try:
            self.process_loop.run_until_complete(self.async_process_logic(image_files))
        except asyncio.CancelledError:
            logger.info('⚠️  处理已被取消')
        except Exception as e:
            logger.error(f'❌ 处理出错: {e}')
        finally:
            try:
                # 取消所有待处理任务
                pending = asyncio.all_tasks(self.process_loop)
                for task in pending:
                    task.cancel()
                # 运行一次循环以处理取消
                self.process_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            finally:
                self.process_loop.close()
                self.process_loop = None
                self.on_process_complete()
    
    async def async_process_logic(self, image_files):
        """异步处理逻辑"""
        async def show_login_window(qrcode_base64=None, qrcode_path=None):
            """显示登录窗口的回调函数（异步版本）"""
            result_event = asyncio.Event()
            result_holder = {'value': None}
            
            def show_in_main_thread():
                """在主线程中显示登录窗口"""
                login_win = LoginWindow(self, qrcode_path=qrcode_path, qrcode_base64=qrcode_base64)
                self.wait_window(login_win)
                result_holder['value'] = login_win.result
                # 通知异步函数可以继续
                self.process_loop.call_soon_threadsafe(result_event.set)
            
            # 在主线程（GUI线程）中执行
            self.after(0, show_in_main_thread)
            
            # 等待结果
            await result_event.wait()
            return result_holder['value']
        
        self.client = BaiduPicFilter(
            headless=self.headless_var.get(),
            output_dir=self.output_var.get(),
            display_login_ui=show_login_window  # 传入 GUI 回调
        )
        
        try:
            logger.info('🚀 启动浏览器...')
            await self.client.start()
            
            logger.info('🔐 检查登录状态...')
            await self.client.ensure_login()
            
            logger.info(f'📊 开始处理 {len(image_files)} 张图片...')
            await self.client.process_batch(image_files)
            
            # 显示统计信息
            stats = self.client.get_stats()
            logger.info(f'{"="*50}')
            logger.info('📊 处理完成统计')
            logger.info(f'{"="*50}')
            logger.info(f'总数: {stats["total"]}')
            logger.info(f'✅ 成功: {stats["success"]}')
            logger.error(f'❌ 失败: {stats["failed"]}')
            
            if stats['failed_files']:
                logger.warning('\n失败的文件:')
                for fname in stats['failed_files']:
                    logger.warning(f'  - {fname}')
            
            logger.info(f'{"="*50}')
            logger.info(f'📁 输出文件夹: {self.client.output_dir.absolute()}')
            
        finally:
            logger.debug('关闭浏览器...')
            await self.client.close()
    
    def on_process_complete(self):
        """处理完成"""
        self.start_button.config(text="🚀 开始处理", command=self.start_process, bootstyle="success")
        self.start_button.config(state="normal")
        self.browse_button.config(state="normal")
        self.image_entry.config(state="normal")
        
        self.status_var.set("✅ 就绪")
        logger.info('\n✅ 所有任务完成！')


def main():
    """主函数"""
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
