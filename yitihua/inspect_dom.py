"""
诊断脚本：获取万花筒节点的完整 innerHTML，以及 hover 后的变化。
"""
import asyncio
from playwright.async_api import async_playwright
import os
import json

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "dom_dumps")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def save(filename, content):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2))
    print(f"  -> 已保存: {path}")


async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        page.set_default_timeout(30000)

        try:
            print("Step 1: 登录...")
            await page.goto("https://ihub.testfarm.cn:8020/admin/login", wait_until="domcontentloaded")
            await asyncio.sleep(3)
            await page.fill("input[placeholder='邮箱']", "zhangning07@baicgroup.com.cn")
            await page.fill("input[placeholder='密码']", "000000")
            await page.click("button.button.large.align-center.normal")
            await asyncio.sleep(5)

            print("Step 2: 导航到项目页面...")
            project_link = page.locator(".el-menu-item:has-text('项目')")
            if await project_link.count() > 0:
                await project_link.click()
                await asyncio.sleep(3)
            else:
                await page.goto("https://ihub.testfarm.cn:8020/admin/new-work-item/project", wait_until="domcontentloaded")
                await asyncio.sleep(3)

            print("Step 3: 获取万花筒节点的完整 HTML...")
            # 用 data-key="25" 精确定位
            node_html_before_hover = await page.evaluate("""() => {
                const node = document.querySelector('.el-tree-node[data-key="25"]');
                return node ? node.outerHTML : '未找到 data-key=25 节点';
            }""")
            save("final_01_node_before_hover.html", node_html_before_hover)

            # 获取 custom-tree-node 的完整 HTML
            custom_node_html = await page.evaluate("""() => {
                const node = document.querySelector('.el-tree-node[data-key="25"] .custom-tree-node');
                return node ? node.outerHTML : '未找到 custom-tree-node';
            }""")
            save("final_02_custom_tree_node.html", custom_node_html)

            print("\nStep 4: Hover 万花筒后获取 HTML...")
            wht_node = page.locator('.el-tree-node[data-key="25"]')
            await wht_node.hover()
            await asyncio.sleep(2)

            node_html_after_hover = await page.evaluate("""() => {
                const node = document.querySelector('.el-tree-node[data-key="25"]');
                return node ? node.outerHTML : '未找到';
            }""")
            save("final_03_node_after_hover.html", node_html_after_hover)

            # 检查 hover 后 custom-tree-node 是否变化
            custom_node_after = await page.evaluate("""() => {
                const node = document.querySelector('.el-tree-node[data-key="25"] .custom-tree-node');
                return node ? node.outerHTML : '未找到';
            }""")
            save("final_04_custom_tree_node_after_hover.html", custom_node_after)

            # 尝试右键点击（context menu）
            print("\nStep 5: 尝试右键点击万花筒...")
            await wht_node.click(button="right")
            await asyncio.sleep(2)
            
            # 检查是否出现右键菜单
            context_menu = await page.evaluate("""() => {
                const menus = document.querySelectorAll('[class*="context"], [class*="popover"], [class*="dropdown"], [role="menu"], .el-dropdown-menu');
                let results = [];
                for (const m of menus) {
                    const rect = m.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        results.push({
                            tag: m.tagName,
                            cls: String(m.className).substring(0, 100),
                            text: m.textContent.trim().substring(0, 300),
                            html: m.outerHTML.substring(0, 2000)
                        });
                    }
                }
                return results;
            }""")
            save("final_05_context_menu.json", context_menu)
            print(f"  右键菜单数量: {len(context_menu)}")

            # 关闭右键菜单
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)

            # 尝试查找万花筒行中是否有 el-dropdown 组件
            print("\nStep 6: 查找 el-dropdown 组件...")
            dropdown_info = await page.evaluate("""() => {
                const node = document.querySelector('.el-tree-node[data-key="25"]');
                if (!node) return '未找到节点';
                // 查找所有子元素
                const allChildren = node.querySelectorAll('*');
                let results = [];
                for (const child of allChildren) {
                    results.push({
                        tag: child.tagName,
                        cls: String(child.className).substring(0, 100),
                        text: child.textContent.trim().substring(0, 50),
                        html: child.outerHTML.substring(0, 300)
                    });
                }
                return results;
            }""")
            save("final_06_all_node_children.json", dropdown_info)
            print(f"  万花筒节点内子元素数量: {len(dropdown_info)}")

            print("\n===== 诊断完成！ =====")

        except Exception as e:
            print(f"\n发生错误: {e}")
        finally:
            await asyncio.sleep(2)
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
