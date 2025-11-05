# 百度网盘试卷去手写工具

基于 Playwright/Patchright 的自动化工具，用于批量处理百度网盘 AI 工具箱的"试卷去手写"功能。

![Version](https://img.shields.io/badge/version-0.6.0-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

## 功能特性

- 批量处理 - 支持多文件选择或整个文件夹批量上传
- 自动登录 - Cookie持久化存储，登录一次后续自动恢复会话
- 实时监控 - GUI界面显示处理进度和详细日志
- 智能重试 - 上传失败自动重试，支持浏览器重启恢复
- 反检测 - 集成Patchright反自动化检测技术
- 异步扫描 - 大文件夹扫描不阻塞UI，大幅提升响应速度

核心流程：选择图片 → 自动上传 → AI 处理 → 自动下载

## 界面预览

基于 ttkbootstrap 的现代化深色主题 GUI 界面，包含文件选择、实时日志、进度统计等功能模块。支持后台模式运行。

## 快速开始

### 安装依赖

```bash
# 检查 Python 版本（需要 3.8+）
python --version

# 安装 Python 依赖
pip install -r requirements.txt

# 安装浏览器驱动（推荐 Patchright）
patchright install chromium
```

如果 Patchright 安装失败，可以使用 Playwright 作为备选：
```bash
pip install playwright
playwright install chromium
```

### 运行程序

```bash
python gui.py
```

也可以直接双击 `gui.py` 文件运行（需要配置 Python 文件关联）。

### 使用流程

1. **首次登录** - 程序会弹出登录窗口，扫描二维码完成百度账号登录
2. **选择文件** - 通过 GUI 界面选择图片文件或文件夹（支持 Ctrl/Cmd 多选）
3. **开始处理** - 点击"开始处理"按钮，程序自动完成上传、处理、下载流程
4. **查看结果** - 处理完成的图片保存在指定的输出目录

后续使用时会自动加载保存的 Cookie，无需重复登录。

## 使用说明

### 文件选择方式

**单文件/多文件选择**
- 通过文件选择对话框，支持 Ctrl/Cmd 键多选
- 适合处理分散的图片文件

**文件夹批量处理**
- 在输入框中指定文件夹路径
- 程序会自动扫描该文件夹下的所有图片文件（jpg, png, webp 等）
- 适合批量处理整理好的图片集

### 输出文件命名规则

处理后的文件会添加 `_去手写_时间戳` 后缀：

```
原文件：试卷_第1页.jpg
输出：  试卷_第1页_去手写_20251104_213507.jpg
```

程序会智能识别已处理过的文件，避免重复添加后缀。

### 性能建议

- 建议单次处理图片数量控制在 20-30 张以内
- 大尺寸图片（>10MB）建议预先压缩
- **重试机制** - 上传失败时会自动重试，最多重试 3 次
- 网络不稳定时可能出现超时，可适当调整超时参数

## 配置选项

### GUI 界面配置

- **后台模式** - 勾选后浏览器在后台运行，不显示窗口
- **输出文件夹** - 自定义处理后文件的保存位置

### 代码级配置

修改 `baidu_automation.py` 可调整高级参数：

```python
# 调整 AI 处理超时时间（默认 120 秒）
async def _wait_for_processing(self, timeout: int = 180):
    # ...

# 调整页面加载超时（默认 30 秒）
self.nav_timeout = 60000  # 单位：毫秒
```

## 常见问题

### 浏览器无法启动

可能是浏览器驱动损坏或版本不匹配，尝试重新安装：
```bash
patchright install chromium --force
```

### 图片上传失败的自动重试机制

本工具内置了智能重试机制来处理上传失败：

重试策略：
1. 第一阶段（页面导航重试）
   - 自动重新导航到试卷去手写页面
   - 等待页面完全加载后再重试
   - 解决临时的页面加载或网络问题

2. 第二阶段（浏览器重启重试）
   - 关闭当前浏览器实例
   - 启动全新的浏览器进程
   - 使用保存的Cookie自动重新登录
   - 适合处理浏览器异常或数据积累导致的问题

如果所有重试都失败，则跳过该文件并继续处理下一张图片。处理完成后会显示失败文件列表。

### 异步文件扫描

处理大量文件时，系统会自动使用异步扫描：

优点：
- GUI界面不会卡死
- 实时显示扫描进度
- 自动递归扫描子文件夹
- 自动限制单次处理数量

### Cookie 频繁失效

可能的原因和解决方案：
- 检查系统时间是否正确
- 删除 `baidu_cookies.json` 文件后重新登录
- 部分安全软件可能会干扰 Cookie 存储，尝试添加白名单

### 图片上传/处理失败

检查以下几点：
- 图片格式是否为常见格式（JPG、PNG、WebP）
- 图片文件大小是否超过限制（建议 <10MB）
- 网络连接是否稳定
- 百度服务是否正常

### Windows 文件路径过长

Windows 系统对文件路径有 260 字符的限制：
- 缩短输出文件夹路径
- 重命名源文件，使用较短的文件名
- 或在注册表中启用长路径支持

## 安全说明

**重要提示：**

`baidu_cookies.json` 文件包含您的百度账号登录凭证，请妥善保管：
- 不要分享给他人
- 不要上传到公开仓库
- 不要在不安全的环境中使用

本项目已在 `.gitignore` 中排除该文件，但仍需注意手动操作时的安全性。

## 项目结构

```
pdwp_rm_writing/
├── gui.py                    # GUI 主程序
├── baidu_automation.py       # 自动化引擎核心
├── requirements.txt          # 依赖包列表
├── CHANGELOG.md              # 版本更新日志
├── .gitignore                # Git 忽略规则
└── cookie_manager.py         # Cookie 管理模块
```

## 技术栈

- **Patchright/Playwright** - 浏览器自动化框架，支持反检测
- **ttkbootstrap** - 现代化 Tkinter 主题库
- **Pillow** - Python 图像处理库
- **asyncio** - 异步 I/O 编程

## 开发

欢迎提交 Issue 和 Pull Request。

对于较大的改动，建议先开 Issue 讨论。

## 协议

MIT License

## 免责声明

- 本工具仅供个人学习和研究使用
- 使用者应遵守百度网盘服务条款
- 禁止将本工具用于商业用途或大规模自动化操作
- 使用本工具产生的任何后果由使用者自行承担

## 致谢

- [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) - 反检测浏览器自动化
- [Playwright](https://playwright.dev/) - 跨浏览器自动化库
