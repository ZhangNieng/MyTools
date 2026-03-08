"""
日报填报自动化脚本
功能：登录 iHub 平台，导航至指定工作项，提取周一至周日日报内容。
"""
import asyncio
from playwright.async_api import async_playwright, expect
import os
import json
import sys

# ===== 配置 =====
LOGIN_URL = "https://ihub.testfarm.cn:8020/admin/login"
EMAIL = "zhangning07@baicgroup.com.cn"
PASSWORD = "000000"
PROJECT_NAME = "万花筒工具平台"
TARGET_PERSON = "张宁(20260303-7670)"  # 后续可根据时间调整

DAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "daily_reports.json")


async def safe_goto(page, url, retries=3):
    """带重试的页面导航"""
    for attempt in range(retries):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return True
        except Exception as e:
            print(f"  导航超时 (尝试 {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                await asyncio.sleep(3)
    return False


async def wait_for_text(page, text, timeout=15000):
    """等待页面中出现指定文本"""
    try:
        locator = page.locator(f"text={text}").first
        await locator.wait_for(state="visible", timeout=timeout)
        return True
    except:
        return False


async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        page.set_default_timeout(30000)

        try:
            # ==================== Step 1: 登录 ====================
            print("=" * 50)
            print("Step 1: 正在登录...")
            print("=" * 50)
            if not await safe_goto(page, LOGIN_URL):
                print("❌ 无法访问登录页面，请检查网络连接。")
                return

            await asyncio.sleep(2)

            # 填写登录信息
            email_input = page.locator("input[placeholder='邮箱']")
            pwd_input = page.locator("input[placeholder='密码']")

            await email_input.fill(EMAIL)
            await pwd_input.fill(PASSWORD)

            # 点击登录按钮
            login_btn = page.locator("button.button.large.align-center.normal")
            await login_btn.click()
            await asyncio.sleep(5)
            print(f"  ✅ 登录成功，当前URL: {page.url}")

            # ==================== Step 2: 导航到新版项目页面 ====================
            print("\n" + "=" * 50)
            print("Step 2: 导航到项目页面...")
            print("=" * 50)

            # 新版界面：点击侧边栏 "项目" 图标
            # 侧边栏使用 el-menu-item 结构
            project_link = page.locator(".el-menu-item:has-text('项目')")
            if await project_link.count() > 0:
                await project_link.click()
                await asyncio.sleep(3)
                print(f"  ✅ 通过侧边栏点击项目, URL: {page.url}")
            else:
                # 回退方案：直接导航
                if not await safe_goto(page, "https://ihub.testfarm.cn:8020/admin/new-work-item/project"):
                    print("❌ 无法导航到项目页面")
                    return
                await asyncio.sleep(3)
                print(f"  ✅ 通过直接URL导航到项目页面, URL: {page.url}")

            # ==================== Step 3: 查找万花筒工具平台 ====================
            print("\n" + "=" * 50)
            print(f"Step 3: 查找 '{PROJECT_NAME}'...")
            print("=" * 50)

            # 等待项目列表加载
            found_project = await wait_for_text(page, PROJECT_NAME, timeout=15000)
            if not found_project:
                print(f"  ❌ 未找到 '{PROJECT_NAME}'，尝试滚动查找...")
                for _ in range(5):
                    await page.evaluate("window.scrollBy(0, 300)")
                    await asyncio.sleep(1)
                    found_project = await wait_for_text(page, PROJECT_NAME, timeout=3000)
                    if found_project:
                        break

            if not found_project:
                print(f"  ❌ 仍未找到 '{PROJECT_NAME}'")
                await page.screenshot(path="debug_step3.png")
                print("  调试截图已保存为 debug_step3.png")
                return

            print(f"  ✅ 找到 '{PROJECT_NAME}'")

            # ==================== Step 4: 点击 '...' -> '查看工作项' ====================
            print("\n" + "=" * 50)
            print("Step 4: 点击项目的 '...' 按钮...")
            print("=" * 50)

            project_node = page.locator(".el-tree-node").filter(has_text=PROJECT_NAME).first
            
            # Hover 项目行以显示 '...' 按钮
            await project_node.hover()
            await asyncio.sleep(2)  

            more_button = None
            dropdown = project_node.locator(".el-dropdown, .el-dropdown-link").first
            if await dropdown.count() > 0 and await dropdown.is_visible():
                more_button = dropdown
                print("  策略1: 找到 el-dropdown")
            
            if more_button is None:
                candidates = project_node.locator("i, span, [class*='more'], [class*='btn'], [class*='action'], [data-icon]")
                for i in range(await candidates.count()):
                    el = candidates.nth(i)
                    if await el.is_visible():
                        text = await el.inner_text()
                        if text.strip() not in ["", PROJECT_NAME]:
                            more_button = el
                            break
                        elif text.strip() == "" and "icon" in (await el.get_attribute("class") or ""):
                            more_button = el
                            break

            if more_button is None:
                print("  ❌ 未找到 '...' 按钮")
                await page.screenshot(path="debug_step4_nobtn.png")
                return
            else:
                print("  正在悬停 '...' 按钮以展开菜单...")
                await more_button.hover()
                await asyncio.sleep(2)
                print("  ✅ 已悬停项目的 '...' 按钮")

            # 🔥 终极必杀：既然肉眼能看见，但 Playwright 认为不可见，直接用原生的 JavaScript 点击！
            print("  尝试通过底层 JavaScript 查找并点击 '查看工作项'...")
            
            js_clicked = await page.evaluate("""() => {
                // 1. 查找所有可能包含该文本的元素
                const allElements = document.querySelectorAll('li, span, a, div, .el-dropdown-menu__item');
                let target = null;
                
                for (const el of allElements) {
                    const text = el.textContent.trim();
                    // 排除掉含有该文本的长容器，只找最具体的元素（字数匹配或子元素少）
                    if (text === '查看工作项' || (text.includes('查看工作项') && el.children.length === 0)) {
                        // 2. 检查元素在屏幕上的物理尺寸
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        
                        // 哪怕 Playwright 认为有遮挡，只要 DOM 渲染有宽高，就不算 display: none
                        if (rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden') {
                            // 为了稳妥，找到真实的可点击层（通常是包含事件的 li 或 a）
                            const clickable = el.closest('li, a, [role="menuitem"]') || el;
                            console.log("找到目标，准备点击:", clickable);
                            clickable.click();
                            return true;
                        }
                    }
                }
                return false;
            }""")

            if js_clicked:
                await asyncio.sleep(4)
                print("  ✅ 已成功通过 JS 点击 '查看工作项'！")
            else:
                print("  ❌ JS 也未能找到出现在屏幕上的 '查看工作项'")
                await page.screenshot(path="debug_step4_nomenu.png")
                return

            print(f"  当前URL: {page.url}")

            # ==================== Step 5: 导航到指定日报 ====================
            print("\n" + "=" * 50)
            print(f"Step 5: 查找 '{TARGET_PERSON}'...")
            print("=" * 50)

            # 等待工作项页面框架加载
            await asyncio.sleep(4)

            # 树节点关键字，按层级顺序
            # 只要包含这些关键且独特的字符串，我们就能定位到那一行
            tree_node_keywords = [
                "工具小组的日报", 
                "2026年3月", 
                "第一周(3.2-3.8)"
            ]
            
            for keyword in tree_node_keywords:
                # 在 el-tree-node 的内容区域中找包含 keyword 的元素
                node_locator = page.locator(".el-tree-node__content").filter(has_text=keyword).last
                
                try:
                    await node_locator.wait_for(state="visible", timeout=10000)
                    await node_locator.scroll_into_view_if_needed()
                    await asyncio.sleep(1)
                    
                    # 检查该节点是否已展开（如果有展开图标），未展开则点击展开图标，或者直接点击内容
                    # Element UI 树节点的展开图标是 .el-tree-node__expand-icon
                    expand_icon = node_locator.locator(".el-tree-node__expand-icon").first
                    if await expand_icon.count() > 0:
                        classes = await expand_icon.get_attribute("class") or ""
                        if "expanded" not in classes and "is-leaf" not in classes:
                            await expand_icon.click()
                        else:
                            # 已经展开或是叶子节点，点击内容
                            await node_locator.click()
                    else:
                        await node_locator.click()
                        
                    await asyncio.sleep(2)  # 等待子节点加载
                    print(f"  ✅ 展开节点: 包含 '{keyword}'")
                except Exception as e:
                    print(f"  ⚠ 查找或点击节点 '{keyword}' 失败: {e}")
                    
            # 查找目标人员
            target_found = False
            # 尝试通过截断特定格式，兼容可能的空格
            target_locator = page.locator(".el-tree-node__content").filter(has_text="张宁").filter(has_text="202603").last
            
            try:
                await target_locator.wait_for(state="visible", timeout=10000)
                await target_locator.scroll_into_view_if_needed()
                await target_locator.click()
                target_found = True
                print(f"  ✅ 已点击目标节点: '{TARGET_PERSON}'")
            except:
                # 尝试滚动查找外层树容器
                tree_container = page.locator(".el-tree").first
                if await tree_container.count() > 0:
                    for _ in range(5):
                        await tree_container.evaluate("(el) => { el.parentElement.scrollBy(0, 300); }")
                        await asyncio.sleep(1)
                        if await target_locator.is_visible():
                            await target_locator.click()
                            print(f"  ✅ 已点击目标节点 (滚动后找到)")
                            target_found = True
                            break

            if not target_found:
                print(f"  ❌ 未找到 '{TARGET_PERSON}'，可能暂未建单或展开失败")
                await page.screenshot(path="debug_step5.png")
                return

            await asyncio.sleep(3)
            print(f"  当前URL: {page.url}")

            # ==================== Step 6: 提取日报内容 ====================
            print("\n" + "=" * 50)
            print("Step 6: 提取日报内容...")
            print("=" * 50)

            report_contents = {}

            for day in DAYS:
                day_label = f"{day}日报"
                print(f"\n  --- {day_label} ---")

                day_found = await wait_for_text(page, day_label, timeout=5000)
                if not day_found:
                    # 可能需要滚动
                    await page.evaluate("window.scrollBy(0, 300)")
                    await asyncio.sleep(1)
                    day_found = await wait_for_text(page, day_label, timeout=3000)

                if not day_found:
                    print(f"    ⚠ 未找到 '{day_label}'")
                    report_contents[day] = ""
                    continue

                # 采用终极稳定方案：根据界面的视觉层级直接提取纯文本
                # 思路：找到周X日报的标题，往上找它的卡片容器，取得 innerText 剥离干扰按钮。
                try:
                    # 1. 精准找到当前星期的标题 (排除左侧导航树里的，依靠可见性和文本)
                    # Playwright 会找到所有包含该文字的元素，我们选最后一个通常是主内容区的
                    day_heading = page.locator(f"text={day_label}").last
                    
                    if await day_heading.count() == 0:
                         print(f"    ⚠ 未找到对应的标题组件，提取为空")
                         report_contents[day] = ""
                         continue
                         
                    await day_heading.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)

                    content = await day_heading.evaluate(f'''(el, currentDay) => {{
                        let container = el;
                        // 往上最多找 7 层，寻找包含这个标题以及整个编辑框的大卡片
                        // 大卡片的一个明显特征是它不仅包含标题，还包含了底下的工具栏（打印、编辑等）
                        for(let i=0; i<7; i++) {{
                            if (!container.parentElement) break;
                            container = container.parentElement;
                            if (container.innerText && container.innerText.includes('打印') && container.innerText.includes('预览')) {{
                                 break; // 找到了卡片容器
                            }}
                        }}
                        
                        if (container && container.innerText) {{
                            let fullText = container.innerText;
                            // 把大段文本按照视觉换行拆解
                            let lines = fullText.split('\\n').map(l => l.trim()).filter(l => l);
                            
                            let contentLines = [];
                            let capturing = false;
                            
                            for (let i = 0; i < lines.length; i++) {{
                                let line = lines[i];
                                
                                // 忽略标题本身
                                if (line === currentDay || line.includes(currentDay)) continue;
                                
                                // 当经过工具栏时，准备开始记录正文
                                if (line === '打印' || line === '编辑' || line === '预览' || line === '全屏' || line === '退出全屏') {{
                                    capturing = true; 
                                    continue;
                                }}
                                
                                // 如果发现越界到了下一天的标题，立刻停止
                                if (/周[一二三四五六日]日报/.test(line)) {{
                                    break;
                                }}
                                
                                // 开始记录正文内容
                                if (capturing) {{
                                    contentLines.push(line);
                                }}
                            }}
                            
                            if (contentLines.length > 0) {{
                                return contentLines.join('\\n');
                            }}
                        }}
                        return null;
                    }}''', day_label)

                    if content:
                        report_contents[day] = content
                        print(f"    ✅ 从预览卡片提取成功 ({len(content)} 字符)")
                    else:
                        print(f"    ⚠ 未找到该星期的卡片文本，提取为空")
                        report_contents[day] = ""

                except Exception as e:
                    print(f"    ❌ 提取 {day_label} 时出错: {e}")
                    report_contents[day] = ""

            # ==================== Step 8: 写入周五日报 ====================
            print("\n" + "=" * 50)
            print("Step 8: 测试写入功能 (周五日报写 '### 调试')")
            print("=" * 50)

            try:
                # 滚动寻找周五日报
                target_day = "周五日报"
                friday_heading = page.locator(f"text={target_day}").last
                await friday_heading.scroll_into_view_if_needed()
                await asyncio.sleep(1)

                print(f"  正在点击 '{target_day}' 的编辑按钮...")
                clicked_edit = await page.evaluate(f'''(day) => {{
                    const h = Array.from(document.querySelectorAll('*')).reverse().find(el => (el.textContent.trim() === day || el.textContent.trim() === day + '日报') && el.children.length === 0);
                    if (!h) return false;
                    
                    let container = h;
                    for(let i=0; i<7; i++) {{
                        if (!container.parentElement) break;
                        container = container.parentElement;
                        if (container.innerText && container.innerText.includes('编辑') && container.innerText.includes('预览')) {{
                             // 寻找具体的编辑按钮 (button 里的文字或者 span 里的文字)
                             const editBtn = Array.from(container.querySelectorAll('button, span, a, div')).find(el => el.textContent.trim() === '编辑' && el.children.length === 0);
                             if (editBtn) {{
                                 // 为了防止点击到内联元素没有事件，触发它本身的点击，或者往上找 role=button
                                 const clickable = editBtn.closest('button, [role="button"]') || editBtn;
                                 clickable.click();
                                 return true;
                             }}
                        }}
                    }}
                    return false;
                }}''', target_day)

                if clicked_edit:
                    print("  ✅ 已点击编辑，等待编辑器加载...")
                    await asyncio.sleep(2)
                    
                    # 寻找当前的编辑器并聚焦
                    # 因为编辑器可能是动态加载的 textarea 或 contenteditable
                    editor_locator = page.locator("textarea:visible, .cm-content:visible, [contenteditable='true']:visible").first
                    
                    if await editor_locator.count() > 0:
                        print("  正在输入内容 '### 调试'...")
                        await editor_locator.click()
                        await asyncio.sleep(0.5)
                        
                        # 为了安全覆盖以前的内容，全选删除
                        await page.keyboard.press("Control+a")
                        await asyncio.sleep(0.1)
                        await page.keyboard.press("Backspace")
                        await asyncio.sleep(0.1)
                        
                        # 键盘输入可以完美兼容不同底层的代码编辑器 (比如 CodeMirror6)
                        await page.keyboard.type("### 调试", delay=50)
                        await asyncio.sleep(1)
                        print("  ✅ 成功输入文本")

                        # 点击预览
                        print(f"  正在点击 '{target_day}' 的预览按钮...")
                        clicked_preview = await page.evaluate(f'''(day) => {{
                            const h = Array.from(document.querySelectorAll('*')).reverse().find(el => (el.textContent.trim() === day || el.textContent.trim() === day + '日报') && el.children.length === 0);
                            let container = h;
                            for(let i=0; i<7; i++) {{
                                if (!container) break;
                                if (container.innerText && container.innerText.includes('预览')) {{
                                     const pBtn = Array.from(container.querySelectorAll('button, span, a, div')).find(el => el.textContent.trim() === '预览' && el.children.length === 0);
                                     if (pBtn) {{
                                         const clickable = pBtn.closest('button, [role="button"]') || pBtn;
                                         clickable.click();
                                         return true;
                                     }}
                                }}
                                container = container.parentElement;
                            }}
                            return false;
                        }}''', target_day)
                        
                        if clicked_preview:
                            print("  ✅ 已点击预览，准备保存...")
                            await asyncio.sleep(2)
                            
                            # 点击右上角的保存
                            # 根据截图，全局只有一个主要的“保存”按钮，可能是一个大按钮
                            save_btn = page.locator("button").filter(has_text="保存").first
                            if await save_btn.count() > 0:
                                await save_btn.click()
                                print("  ✅ 已点击全局保存按钮！")
                                
                                # 处理由于保存触发的确定弹窗
                                try:
                                    print("  等待保存确认弹窗...")
                                    confirm_btn = page.locator("button").filter(has_text="确认").first
                                    await confirm_btn.wait_for(state="visible", timeout=3000)
                                    await confirm_btn.click()
                                    print("  ✅ 已点击确认，完成写入提交！")
                                except:
                                    try:
                                        # 备选：可能是 span 里包着字
                                        confirm_span = page.locator("span").filter(has_text="确认").first
                                        await confirm_span.click(timeout=1000)
                                        print("  ✅ 已点击确认，完成写入提交！")
                                    except:
                                        print("  ⚠ 未出现确认按钮，或者可能已自动保存。")
                                        
                                await asyncio.sleep(3) # 等待整体保存和关闭的请求完成
                            else:
                                print("  ⚠ 未在页面上找到 '保存' 按钮。")
                        else:
                            print("  ❌ 点击预览失败！")
                    else:
                        print("  ❌ 未找到可见的编辑器输入框！")
                else:
                    print(f"  ❌ 未能通过JS找到 {target_day} 的编辑按钮！")
            except Exception as e:
                print(f"  ❌ 写入 {target_day} 时出现异常: {e}")

            # ==================== Step 9: 输出结果 ====================
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(report_contents, f, ensure_ascii=False, indent=2)
            print(f"\n✅ 日报内容已保存至: {OUTPUT_FILE}")

        except Exception as e:
            print(f"\n❌ 发生错误: {e}")
            try:
                await page.screenshot(path="error_screenshot.png")
                print("错误截图已保存为 error_screenshot.png")
            except:
                pass
        finally:
            await asyncio.sleep(3)
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
