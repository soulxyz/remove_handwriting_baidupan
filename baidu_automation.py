"""
百度网盘试卷去手写自动化核心模块
负责浏览器操作、图片上传下载等核心功能
"""
import asyncio
from pathlib import Path
from typing import Optional
import sys


# 优先使用Patchright，如果未安装则使用Playwright
try:
    from patchright.async_api import async_playwright, Browser, Page, BrowserContext
    USING_PATCHRIGHT = True
except ImportError:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext
    USING_PATCHRIGHT = False

from cookie_manager import CookieManager

# Windows: 使用Proactor事件循环以支持子进程（patchright/playwright需要）
if sys.platform.startswith('win'):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass


class BaiduPicFilter:
    """百度网盘试卷去手写自动化客户端"""
    
    def __init__(self, headless: bool = False, output_dir: str = "./output", display_login_ui=None):
        """
        初始化客户端
        
        Args:
            headless: 是否无头模式（默认False，显示浏览器）
            output_dir: 输出文件夹路径
            display_login_ui: 显示登录UI的回调函数（用于GUI集成）
        """
        self.headless = headless
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.base_url = "https://pan.baidu.com/aipan/uploadimg?key=ai_tools_to_write"
        
        # Display login UI 回调（用于 GUI 集成）
        self.display_login_ui = display_login_ui
        
        # Cookie管理
        self.cookie_manager = CookieManager("baidu_cookies.json")
        self._logged_in = False
        
        # 页面加载配置（快速加载模式）
        self.page_load_strategy = 'domcontentloaded'  # 'load' 或 'domcontentloaded'，而不是 'networkidle'
        self.page_load_timeout = 30000  # 页面加载超时30秒
        self.nav_timeout = 30000  # 导航超时30秒
        
        # 统计信息
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'failed_files': []
        }
    
    async def start(self):
        """启动浏览器（完整反检测）"""
        global USING_PATCHRIGHT
        print(f"✅ 使用 {'Patchright（增强反检测）' if USING_PATCHRIGHT else 'Playwright（建议安装Patchright）'}")

        # 兼容性：Patchright在部分Windows环境下会触发NotImplementedError
        # 这里做一次运行时降级到Playwright
        playwright = None
        try:
            playwright = await async_playwright().start()
        except Exception as e:
            if isinstance(e, NotImplementedError) or 'NotImplementedError' in str(e):
                print("⚠️  Patchright 启动失败（NotImplementedError），自动切换到 Playwright ...")
                try:
                    from playwright.async_api import async_playwright as pw_async_playwright
                    USING_PATCHRIGHT = False
                    playwright = await pw_async_playwright().start()
                except Exception as e2:
                    # 无法降级则抛出原始异常
                    raise e2
            else:
                raise
        
        # 启动浏览器
        if USING_PATCHRIGHT:
            self.browser = await playwright.chromium.launch(headless=self.headless)
        else:
            self.browser = await playwright.chromium.launch(
                headless=self.headless,
                channel='chrome' if not self.headless else None,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-infobars',
                    '--window-position=0,0',
                    '--ignore-certifcate-errors',
                    '--disable-gpu',
                    '--no-first-run',
                    '--no-default-browser-check',
                    '--disable-extensions',
                ]
            )
        
        # 创建上下文
        context_options = {
            'viewport': {'width': 1920, 'height': 1080},
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'locale': 'zh-CN',
            'timezone_id': 'Asia/Shanghai',
            'accept_downloads': True,
        }
        
        if not USING_PATCHRIGHT:
            context_options.update({
                'extra_http_headers': {
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"',
                }
            })
        
        self.context = await self.browser.new_context(**context_options)
        
        # 注入反检测脚本
        await self._inject_stealth_scripts()
        
        self.page = await self.context.new_page()
        print("✅ 浏览器已启动")
    
    async def _inject_stealth_scripts(self):
        """注入JavaScript反检测代码"""
        if not USING_PATCHRIGHT:
            # Playwright需要完整的反检测注入
            await self.context.add_init_script("""
            // 覆盖webdriver标记
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false
            });
            
            // 添加chrome对象
            window.navigator.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // 覆盖permissions API
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // 覆盖plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    {
                        description: "Portable Document Format",
                        filename: "internal-pdf-viewer",
                        name: "Chrome PDF Plugin"
                    }
                ]
            });
            
            // 覆盖languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en-US', 'en']
            });
            
            // 删除自动化痕迹
            delete window.__playwright;
            delete window.__pw_manual;
            
            console.log('✅ Playwright反检测已加载');
            """)
        else:
            # Patchright只需少量补充
            await self.context.add_init_script("""
            if (!window.chrome) {
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {}
                };
            }
            
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en-US', 'en']
            });
            
            console.log('✅ Patchright反检测已加载');
            """)
    
    async def ensure_login(self):
        """确保已登录（使用Cookie或手动登录）"""
        # 尝试加载保存的Cookie
        saved_cookies = self.cookie_manager.load_cookies("baidu")
        
        if saved_cookies:
            print("📦 检测到保存的Cookie，尝试自动登录...")
            await self._load_cookies(saved_cookies)
            
            # 访问页面验证
            await self.page.goto(self.base_url, wait_until='domcontentloaded', timeout=self.nav_timeout)
            await asyncio.sleep(2)
            
            if await self._check_login_status():
                print("✅ Cookie登录成功！")
                self._logged_in = True
                return
            else:
                print("⚠️  Cookie已失效，需要重新登录")
                self.cookie_manager.clear_cookies("baidu")
        
        # 手动登录
        await self._manual_login()
    
    async def _load_cookies(self, saved_cookies: dict):
        """加载Cookie到浏览器"""
        cookie_list = []
        for name, value in saved_cookies.items():
            cookie_list.append({
                'name': name,
                'value': value,
                'domain': '.baidu.com',
                'path': '/'
            })
        await self.context.add_cookies(cookie_list)
    
    async def _manual_login(self):
        """手动登录流程 - 通过点击上传按钮弹出登录框"""
        print("\n" + "="*60)
        print("🔐 首次使用或Cookie已过期，请扫码登录")
        print("="*60)
        print("步骤：")
        print("  1. 脚本将点击'选择本地图片'按钮")
        print("  2. 弹出百度登录框后，请选择'扫码登录'")
        print("  3. 使用手机百度或相机扫描下方二维码")
        print("  4. 登录成功后，脚本会自动保存Cookie")
        print("="*60 + "\n")
        
        await self.page.goto(self.base_url, wait_until='domcontentloaded', timeout=self.nav_timeout)
        await asyncio.sleep(2)
        
        # 尝试点击"选择本地图片"按钮以弹出登录框
        print("📷 点击以弹出登录框...")
        try:
            # 方法1: 优先点击登录检查遮罩层（如果存在）来弹出登录框
            login_mask = await self.page.query_selector('.aiTools-upload-file__login-check')
            
            if login_mask:
                print("   ✓ 检测到登录检查遮罩层，点击遮罩层弹出登录框...")
                await login_mask.click()
                await asyncio.sleep(2)
                print("   ✓ 登录框应该已弹出")
            else:
                # 方法2: 如果没有遮罩层，则点击上传按钮
                print("   ✓ 未检测到遮罩层，点击上传按钮...")
                upload_button = await self.page.query_selector('button.aiTools-upload-local__button')
                
                if upload_button:
                    await upload_button.click()
                    await asyncio.sleep(2)
                    print("   ✓ 按钮已点击，登录框应该已弹出")
                else:
                    print("   ⚠️  未找到上传按钮，尝试导航到登录页面")
                    # 备选方案：直接导航到登录页面
                    await self.page.goto("https://passport.baidu.com/v3/login", wait_until='domcontentloaded', timeout=self.nav_timeout)
                    await asyncio.sleep(2)
        except Exception as e:
            print(f"   ⚠️  点击出错: {e}")
        
        # 等待登录框出现并显示二维码
        print("\n⏳ 等待登录框和二维码加载...")
        qrcode_displayed = False
        
        for attempt in range(15):  # 尝试15次，每次2秒，共30秒
            try:
                # 检查当前URL，看是否已经跳回目标页面
                current_url = self.page.url
                print(f"   当前URL: {current_url[:60]}...")
                
                # 检查是否已跳回目标页面（登录成功的最终标志）
                if await self._check_login_status():
                    print("✅ 登录成功！")
                    self._logged_in = True
                    await self._save_cookies()
                    return
                
                # 检测二维码元素并显示
                qrcode_elem = await self.page.query_selector('#TANGRAM__PSP_11__footerQrcodeBtn, [id*="Qrcode"], .qrcode-img, img[src*="qrcode"]')
                
                if qrcode_elem:
                    is_visible = await qrcode_elem.is_visible()
                    if is_visible:
                        print("   ✓ 检测到二维码！")
                        
                        if not qrcode_displayed:
                            # 截图二维码区域
                            await self._capture_and_display_qrcode()
                            qrcode_displayed = True
                        
                        print("\n✅ 请使用手机扫描上方二维码进行登录...")
                        print("   (或在浏览器中输入账号密码登录)\n")
            except Exception as e:
                pass
            
            # 尝试自动跳转回目标页面
            if await self._auto_return_to_target():
                # 重新检查登录状态
                await asyncio.sleep(2)
                if await self._check_login_status():
                    print("✅ 登录成功！")
                    self._logged_in = True
                    await self._save_cookies()
                    return
            
            await asyncio.sleep(3)  # 增加等待时间到3秒
        
        # 如果未检测到二维码，提示用户在浏览器中手动登录
        if not qrcode_displayed:
            print("⚠️  未能检测到二维码，请在浏览器中手动登录")
            print("   选择'扫码登录'或输入账号密码")
        
        # 等待用户完成登录（最多5分钟）
        print("\n⏳ 等待登录完成（扫码后请稍候）...")
        login_success = False
        
        for i in range(60):  # 最多5分钟
            await asyncio.sleep(5)
            
            # 尝试自动跳转
            await self._auto_return_to_target()
            
            # 检查登录状态
            if await self._check_login_status():
                login_success = True
                print("✅ 检测到登录成功！")
                break
            
            # 检查是否在个人中心页面（登录成功的标志之一）
            current_url = self.page.url
            if 'ucenter' in current_url or 'disk' in current_url:
                print("✅ 检测到已跳转到个人中心，正在返回目标页面...")
                await self.page.goto(self.base_url, wait_until='domcontentloaded', timeout=self.nav_timeout)
                await asyncio.sleep(2)
                if await self._check_login_status():
                    login_success = True
                    break
            
            if i % 6 == 0 and i > 0:
                print(f"   仍在等待登录... ({i*5}秒)")
        
        if not login_success:
            raise Exception("登录超时（5分钟），请重新运行脚本")
        
        print("✅ 登录成功！")
        self._logged_in = True
        
        # 保存Cookie
        await self._save_cookies()
    
    async def _save_cookies(self):
        """保存当前Cookie"""
        cookies = await self.context.cookies()
        cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}
        self.cookie_manager.save_cookies(cookie_dict, "baidu")
        print("💾 Cookie已保存，下次将自动登录")
    
    async def _check_login_status(self) -> bool:
        """检查是否已登录"""
        try:
            current_url = self.page.url
            
            # 检查是否在登录页面
            if 'passport.baidu.com' in current_url or 'login' in current_url.lower():
                return False
            
            # 检查是否有登录按钮
            login_button = await self.page.query_selector('text=/登录|登入/i')
            if login_button and await login_button.is_visible():
                return False
            
            # 检查是否有上传按钮（已登录的标志）
            upload_button = await self.page.query_selector('text=/上传图片|选择本地图片/i')
            if upload_button and await upload_button.is_visible():
                return True
            
            # 如果在目标页面且没有明显登录提示，认为已登录
            if self.base_url in current_url:
                return True
            
            return False
            
        except Exception as e:
            print(f"⚠️  检查登录状态时出错: {e}")
            return False
    
    async def _auto_return_to_target(self):
        """登录成功后自动跳回目标界面"""
        try:
            current_url = self.page.url
            
            # 检查是否在百度 ucenter 页面（登录成功的中间跳转）
            if 'passport.baidu.com' in current_url and 'ucenter' in current_url:
                print("   📍 检测到在 ucenter 页面，自动跳回目标界面...")
                await asyncio.sleep(2)  # 等待页面稳定
                await self.page.goto(self.base_url, wait_until='domcontentloaded', timeout=self.nav_timeout)
                await asyncio.sleep(2)
                print("   ✓ 已跳回目标界面")
                return True
            
            return False
        except Exception as e:
            print(f"   ⚠️  自动跳转出错: {e}")
            return False
    
    async def process_batch(self, image_paths: list):
        """批量处理图片"""
        total = len(image_paths)
        self.stats['total'] = total  # 设置总数
        self.stats['success'] = 0  # 重置成功数
        self.stats['failed'] = 0  # 重置失败数
        self.stats['failed_files'] = []  # 重置失败文件列表
        
        print(f"\n{'='*60}")
        print(f"📊 开始批量处理 {total} 张图片")
        print(f"{'='*60}\n")
        
        for index, image_path in enumerate(image_paths, 1):
            success = await self.process_image(image_path, index, total)
            
            if success:
                self.stats['success'] += 1
            else:
                self.stats['failed'] += 1
                self.stats['failed_files'].append(Path(image_path).name)
            
            # 每张图片之间暂停一下
            if index < total:
                await asyncio.sleep(2)
        
        print(f"\n{'='*60}")
        print(f"✅ 批量处理完成")
        print(f"{'='*60}\n")
    
    async def process_image(self, image_path: str, index: int, total: int) -> bool:
        """
        处理单张图片
        
        Args:
            image_path: 图片文件路径
            index: 当前索引
            total: 总数量
            
        Returns:
            bool: 是否成功
        """
        file_name = Path(image_path).name
        print(f"\n{'='*60}")
        print(f"处理第 {index}/{total} 张图片: {file_name}")
        print(f"{'='*60}")
        
        try:
            # 确保在正确的页面
            if self.base_url not in self.page.url:
                print("📄 导航到试卷去手写页面...")
                await self.page.goto(self.base_url, wait_until='domcontentloaded', timeout=self.nav_timeout)
                await asyncio.sleep(1)
            
            # 上传图片（带重试机制）
            print("⬆️  [1/3] 上传图片...")
            upload_success = await self._upload_image_with_retry(image_path)
            if not upload_success:
                raise Exception("上传失败（已重试）")
            
            # 等待处理完成
            print("⏳ [2/3] 等待AI处理...")
            if not await self._wait_for_processing():
                raise Exception("处理超时或失败")
            
            # 下载结果（传递原始文件路径）
            print("⬇️  [3/3] 下载处理后的图片...")
            if not await self._download_result(image_path):
                raise Exception("下载失败")
            
            print(f"✅ 成功处理: {file_name}")
            self.stats['success'] += 1
            return True
            
        except Exception as e:
            print(f"❌ 处理失败: {file_name} - {e}")
            self.stats['failed'] += 1
            self.stats['failed_files'].append(file_name)
            return False
    
    async def _upload_image_with_retry(self, image_path: str) -> bool:
        """
        带重试机制的上传图片
        
        重试策略：
        1. 第一次失败：重新导航到页面后重试（共2次尝试）
        2. 第二次失败：重启浏览器后重试（共2次尝试）
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            bool: 是否成功
        """
        file_name = Path(image_path).name
        
        # 第一阶段：页面重试（2次尝试）
        print(f"\n   📤 第一阶段：页面重试...")
        for attempt in range(1, 3):
            print(f"   [{attempt}/2] 尝试上传...")
            
            if attempt > 1:
                # 第二次尝试前重新导航到页面
                print(f"   [重试] 重新导航到页面...")
                try:
                    await self.page.goto(self.base_url, wait_until='domcontentloaded', timeout=self.nav_timeout)
                    await asyncio.sleep(2)
                except Exception as e:
                    print(f"   ⚠️  导航失败: {e}")
            
            # 尝试上传
            if await self._upload_image(image_path):
                print(f"   ✅ 上传成功（第 {attempt} 次尝试）")
                return True
            
            if attempt < 2:
                await asyncio.sleep(2)  # 等待后重试
        
        # 第二阶段：浏览器重启重试（2次尝试）
        print(f"\n   🔄 第二阶段：浏览器重启重试...")
        for attempt in range(1, 3):
            print(f"   [{attempt}/2] 重启浏览器后尝试...")
            
            try:
                # 关闭当前浏览器
                print(f"   [重启] 关闭浏览器...")
                if self.page:
                    try:
                        await self.page.close()
                    except Exception:
                        pass
                
                if self.context:
                    try:
                        await self.context.close()
                    except Exception:
                        pass
                
                if self.browser:
                    try:
                        await self.browser.close()
                    except Exception:
                        pass
                
                await asyncio.sleep(2)
                
                # 重启浏览器
                print(f"   [重启] 启动新浏览器...")
                await self.start()
                
                # 重新登录（使用已保存的Cookie）
                print(f"   [重启] 检查登录状态...")
                await self.ensure_login()
                
                await asyncio.sleep(2)
                
                # 导航到上传页面
                print(f"   [重启] 导航到试卷去手写页面...")
                await self.page.goto(self.base_url, wait_until='domcontentloaded', timeout=self.nav_timeout)
                await asyncio.sleep(2)
                
                # 尝试上传
                if await self._upload_image(image_path):
                    print(f"   ✅ 上传成功（浏览器重启后第 {attempt} 次尝试）")
                    return True
                
            except Exception as e:
                print(f"   ⚠️  浏览器重启失败: {e}")
                
                # 尝试恢复
                try:
                    await self.start()
                except Exception:
                    pass
            
            if attempt < 2:
                await asyncio.sleep(2)
        
        print(f"   ❌ 已尝试所有重试方案，图片 '{file_name}' 上传失败")
        return False
    
    async def _upload_image(self, image_path: str) -> bool:
        """上传图片"""
        try:
            # 方法1: 直接找到input[type="file"]，用set_input_files（最直接）
            file_input = await self.page.query_selector('input[type="file"][accept*="image"]')
            
            if file_input:
                await file_input.set_input_files(image_path)
                await asyncio.sleep(2)
                print("   ✓ 图片已上传")
                return True
            
            # 方法2: 如果有登录检查遮罩层，点击遮罩层会弹出文件选择器
            login_mask = await self.page.query_selector('.aiTools-upload-file__login-check')
            
            if login_mask:
                print("   ℹ️  检测到登录检查遮罩层，点击遮罩层...")
                try:
                    async with self.page.expect_file_chooser(timeout=10000) as fc_info:
                        await login_mask.click()
                    
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(image_path)
                    await asyncio.sleep(2)
                    print("   ✓ 图片已上传")
                    return True
                except Exception as e:
                    print(f"   ⚠️  通过遮罩层上传失败: {e}")
            
            # 方法3: 点击上传按钮
            upload_button = await self.page.query_selector('button.aiTools-upload-local__button')
            
            if not upload_button:
                upload_button = await self.page.query_selector('text=/选择本地图片|选择|上传/i')
            
            if upload_button:
                try:
                    async with self.page.expect_file_chooser(timeout=10000) as fc_info:
                        await upload_button.click()
                    
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(image_path)
                    await asyncio.sleep(2)
                    print("   ✓ 图片已上传")
                    return True
                except Exception as e:
                    print(f"   ⚠️  通过按钮上传失败: {e}")
            
            print("   ⚠️  未找到上传方式")
            return False
            
        except Exception as e:
            print(f"   ❌ 上传出错: {e}")
            return False
    
    async def _wait_for_processing(self, timeout: int = 120) -> bool:
        """等待图片处理完成"""
        try:
            start_time = asyncio.get_event_loop().time()
            
            while True:
                if asyncio.get_event_loop().time() - start_time > timeout:
                    print("   ⚠️  处理超时")
                    return False
                
                # 查找下载按钮
                download_button = await self.page.query_selector('text=/下载|download/i')
                if download_button and await download_button.is_visible():
                    print("   ✓ 处理完成！")
                    return True
                
                # 检查页面文本
                page_text = await self.page.inner_text('body')
                if '处理完成' in page_text or '下载' in page_text:
                    print("   ✓ 处理完成！")
                    return True
                
                if '失败' in page_text or '错误' in page_text:
                    print("   ❌ 处理失败")
                    return False
                
                await asyncio.sleep(1)
                
                # 显示进度
                elapsed = int(asyncio.get_event_loop().time() - start_time)
                if elapsed % 10 == 0 and elapsed > 0:
                    print(f"   ⏱️  已等待 {elapsed} 秒...")
            
        except Exception as e:
            print(f"   ❌ 等待处理时出错: {e}")
            return False
    
    async def _download_result(self, original_image_path: str) -> bool:
        """从 base64 获取处理后的图片并保存"""
        try:
            import base64
            from datetime import datetime
            
            # 获取原始文件信息
            source_path = Path(original_image_path)
            file_stem = source_path.stem
            file_suffix = source_path.suffix
            
            # 使用用户指定的输出文件夹
            output_dir = self.output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成时间戳
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 避免重复添加 "_去手写" 后缀
            if "_去手写_" in file_stem:
                # 如果文件名已包含 "_去手写_"，则移除旧的时间戳部分
                # 例如：filename_去手写_20251104_205943 -> filename
                parts = file_stem.split("_去手写_")
                clean_stem = parts[0]
                output_filename = f"{clean_stem}_去手写_{timestamp}{file_suffix}"
            else:
                output_filename = f"{file_stem}_去手写_{timestamp}{file_suffix}"
            
            output_path = output_dir / output_filename
            
            print(f"   🔍 从 base64 获取处理结果...")
            
            # 从 img#resultImg 的 src 获取 base64
            try:
                # 使用 evaluate 直接执行 JavaScript 获取 img src
                img_src = await self.page.evaluate('''() => {
                    const img = document.querySelector("img#resultImg");
                    return img ? img.src : null;
                }''')
                
                if img_src and img_src.startswith('data:'):
                    print(f"   ✓ 检测到 base64 数据")
                    
                    # 解析 base64
                    # 格式: data:image/jpeg;base64,/9j/4AAQSkZJRgAB...
                    if ',' in img_src:
                        base64_data = img_src.split(',', 1)[1]
                        
                        # 解码并保存
                        try:
                            image_bytes = base64.b64decode(base64_data)
                            with open(output_path, 'wb') as f:
                                f.write(image_bytes)
                            
                            print(f"   ✓ 已保存到: {output_path}")
                            return True
                        except Exception as e:
                            print(f"   ⚠️  base64 解码保存失败: {e}")
                            return False
                else:
                    print(f"   ⚠️  未找到 base64 数据或格式错误")
                    return False
                    
            except Exception as e:
                print(f"   ❌ 获取 base64 失败: {e}")
                return False
            
        except Exception as e:
            print(f"   ❌ 下载出错: {e}")
            return False
    
    async def close(self):
        """关闭浏览器并清理资源"""
        try:
            if self.page:
                try:
                    await self.page.close()
                except Exception as e:
                    print(f"⚠️  关闭页面时出错: {e}")
            
            if self.context:
                try:
                    await self.context.close()
                except Exception as e:
                    print(f"⚠️  关闭上下文时出错: {e}")
            
            if self.browser:
                try:
                    await self.browser.close()
                except Exception as e:
                    print(f"⚠️  关闭浏览器时出错: {e}")
            
            print("✅ 浏览器已关闭")
        except Exception as e:
            print(f"⚠️  关闭浏览器时出错: {e}")
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return self.stats.copy()

    async def _capture_and_display_qrcode(self):
        """获取二维码并在控制台/GUI 显示"""
        try:
            import base64
            from io import BytesIO
            
            print("\n   🔍 正在获取二维码...")
            qrcode_data = None
            
            # 方法1: 从 URL 获取二维码（百度登录页面的情况）
            try:
                img_url = await self.page.evaluate('''() => {
                    const img = document.querySelector('img.tang-pass-qrcode-img') || 
                                document.querySelector('img[src*="qrcode"]');
                    return img ? img.src : null;
                }''')
                
                if img_url and img_url.startswith('http'):
                    print(f"   ✓ 检测到 URL 二维码")
                    
                    # 下载二维码图片
                    try:
                        import urllib.request
                        qrcode_path = "qrcode_screenshot.png"
                        urllib.request.urlretrieve(img_url, qrcode_path)
                        print(f"   ✓ 二维码已下载到: {qrcode_path}")
                        
                        # 读取文件作为 base64
                        with open(qrcode_path, 'rb') as f:
                            qrcode_data = base64.b64encode(f.read()).decode('utf-8')
                        
                        # 显示 GUI 登录窗口或 ASCII 版本
                        if self.display_login_ui:
                            # 支持同步和异步回调
                            import inspect
                            if inspect.iscoroutinefunction(self.display_login_ui):
                                await self.display_login_ui(qrcode_base64=qrcode_data)
                            else:
                                self.display_login_ui(qrcode_base64=qrcode_data)
                        else:
                            from PIL import Image
                            img = Image.open(qrcode_path)
                            await self._print_ascii_qrcode_from_image(img)
                        return
                    except Exception as e:
                        print(f"   ⚠️  处理二维码失败: {e}")
            except Exception as e:
                print(f"   ⚠️  无法从 URL 获取: {e}")
            
            # 方法2: 从 base64 获取二维码
            try:
                img_src = await self.page.evaluate('''() => {
                    const img = document.querySelector('img#resultImg') || 
                                document.querySelector('img[src*="base64"]');
                    return img ? img.src : null;
                }''')
                
                if img_src and img_src.startswith('data:'):
                    print("   ✓ 检测到 base64 二维码数据")
                    
                    if ',' in img_src:
                        base64_data = img_src.split(',', 1)[1]
                        image_bytes = base64.b64decode(base64_data)
                        
                        qrcode_path = "qrcode_screenshot.png"
                        with open(qrcode_path, 'wb') as f:
                            f.write(image_bytes)
                        print(f"   ✓ 二维码已保存到: {qrcode_path}")
                        
                        # 显示 GUI 登录窗口或 ASCII 版本
                        if self.display_login_ui:
                            # 支持同步和异步回调
                            import inspect
                            if inspect.iscoroutinefunction(self.display_login_ui):
                                await self.display_login_ui(qrcode_base64=base64_data)
                            else:
                                self.display_login_ui(qrcode_base64=base64_data)
                        else:
                            await self._print_ascii_qrcode_from_base64(base64_data)
                        return
            except Exception as e:
                print(f"   ⚠️  无法从 base64 获取: {e}")
            
            # 方法3: 从页面截图获取二维码区域
            try:
                qrcode_elem = await self.page.query_selector(
                    '.Qrcode-status-con, #TANGRAM__PSP_3__QrcodeMain, '
                    '#TANGRAM__PSP_11__footerQrcodeBtn, .qrcode-container, [id*="qrcode"]'
                )
                
                if qrcode_elem:
                    is_visible = await qrcode_elem.is_visible()
                    if is_visible:
                        box = await qrcode_elem.bounding_box()
                        if box:
                            print("   📸 正在截图二维码区域...")
                            qrcode_path = "qrcode_screenshot.png"
                            await self.page.screenshot(path=qrcode_path, clip={
                                'x': max(0, box['x'] - 10),
                                'y': max(0, box['y'] - 10),
                                'width': box['width'] + 20,
                                'height': box['height'] + 20
                            })
                            print(f"   ✓ 二维码已截图到: {qrcode_path}")
                            
                            try:
                                with open(qrcode_path, 'rb') as f:
                                    qrcode_data = base64.b64encode(f.read()).decode('utf-8')
                                
                                if self.display_login_ui:
                                    # 支持同步和异步回调
                                    import inspect
                                    if inspect.iscoroutinefunction(self.display_login_ui):
                                        await self.display_login_ui(qrcode_base64=qrcode_data)
                                    else:
                                        self.display_login_ui(qrcode_base64=qrcode_data)
                                else:
                                    from PIL import Image
                                    img = Image.open(qrcode_path)
                                    await self._print_ascii_qrcode_from_image(img)
                            except Exception:
                                pass
                            return
            except Exception as e:
                print(f"   ⚠️  截图失败: {e}")
            
            # 方法4: 截图整个登录区域
            print("   📸 正在截图登录框...")
            qrcode_path = "login_screenshot.png"
            await self.page.screenshot(path=qrcode_path)
            print(f"   ✓ 登录框已截图到: {qrcode_path}")
            
            if self.display_login_ui:
                try:
                    with open(qrcode_path, 'rb') as f:
                        qrcode_data = base64.b64encode(f.read()).decode('utf-8')
                    # 支持同步和异步回调
                    import inspect
                    if inspect.iscoroutinefunction(self.display_login_ui):
                        await self.display_login_ui(qrcode_base64=qrcode_data)
                    else:
                        self.display_login_ui(qrcode_base64=qrcode_data)
                except Exception:
                    pass
            
        except Exception as e:
            print(f"   ⚠️  获取二维码出错: {e}")
    
    async def _print_ascii_qrcode_from_base64(self, base64_data: str):
        """从 base64 数据生成并打印 ASCII 二维码"""
        try:
            import base64
            from PIL import Image
            from io import BytesIO
            
            # 解码 base64 为图片
            image_bytes = base64.b64decode(base64_data)
            image = Image.open(BytesIO(image_bytes))
            
            await self._print_ascii_qrcode_from_image(image)
        except Exception as e:
            print(f"   ⚠️  无法显示 ASCII 二维码: {e}")
    
    async def _print_ascii_qrcode_from_image(self, image):
        """从 PIL Image 生成并打印 ASCII 二维码"""
        try:
            from PIL import Image
            
            # 调整图片大小以适应控制台显示
            ascii_width = 50  # ASCII 字符宽度
            image = image.convert('L')  # 转灰度
            
            # 计算高度保持宽高比
            aspect_ratio = image.height / image.width
            ascii_height = int(ascii_width * aspect_ratio * 0.55)  # 调整高度比例
            
            # 缩放图片
            image = image.resize((ascii_width, ascii_height))
            
            # ASCII 字符集（从深到浅）
            ascii_chars = "@%#*+=-:. "
            
            # 转换为 ASCII
            pixels = image.getdata()
            ascii_str = ""
            for pixel in pixels:
                # 根据像素亮度选择字符
                ascii_str += ascii_chars[pixel // 25]
            
            # 按行分割
            ascii_lines = []
            for i in range(0, len(ascii_str), ascii_width):
                ascii_lines.append(ascii_str[i:i + ascii_width])
            
            # 打印
            print("\n" + "="*60)
            print("📱 二维码（请用手机扫描）：")
            print("="*60)
            for line in ascii_lines:
                print(line)
            print("="*60 + "\n")
            
        except Exception as e:
            print(f"   ℹ️  无法在控制台显示 ASCII 二维码（需要 PIL）: {e}")

