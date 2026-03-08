import urllib.request
import urllib.parse
import urllib.error
import ssl
import re
import json
import os
import sys

# 忽略SSL证书验证
context = ssl._create_unverified_context()


class PluginChecker:
    def __init__(self):
        self.local_plugins = []
        self.remote_plugins = []

    # ==================== 远程版本检查部分 ====================

    def check_available_url(self):
        """尝试访问两个链接，选择可以打开的"""
        urls = [
            "https://kmart.testfarm.cn:8020/static/upload.html",
            "https://kmart-in.testfarm.cn/static/upload.html"
        ]

        for url in urls:
            try:
                request = urllib.request.Request(url)
                with urllib.request.urlopen(request, timeout=10, context=context) as response:
                    if response.getcode() == 200:
                        print(f"成功访问远程服务器: {url}")
                        return url
            except:
                continue

        print("无法访问任何远程服务器")
        return None

    def get_remote_extensions(self, url, password="bjev666"):
        """获取远程插件列表"""
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            domain = f"{parsed_url.scheme}://{parsed_url.netloc}"

            # 尝试直接访问getAll端点
            plugins_url = domain + "/api/plugins/getAll"

            request = urllib.request.Request(plugins_url)
            request.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            request.add_header('Accept', 'application/json')
            request.add_header('X-Password', password)

            with urllib.request.urlopen(request, timeout=10, context=context) as response:
                content = response.read().decode('utf-8')

                try:
                    extensions_data = json.loads(content)
                    extensions = []
                    latest_versions = {}

                    if isinstance(extensions_data, dict) and 'data' in extensions_data:
                        items = extensions_data['data']
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict):
                                    name = item.get('name', item.get('extension_id', ''))
                                    version = item.get('version', '')
                                    download_url = item.get('download_url', '')
                                    extension_id = item.get('extension_id', '')
                                    
                                    if name and version:
                                        # 处理插件名称，去除发布者前缀
                                        # 如果是 a.b.c，我们只需要 c
                                        display_name = name.split('.')[-1] if '.' in name else name
                                        
                                        # 我们需要找到每个插件的最新版本
                                        if display_name not in latest_versions:
                                            latest_versions[display_name] = {
                                                "version": version,
                                                "download_url": download_url,
                                                "extension_id": extension_id
                                            }
                                        else:
                                            # 如果已经存在，比较版本号（简单字符串比较，或者可以引入更复杂的版本比较）
                                            # 这里简单起见，API返回的第一个通常是较新的
                                            pass

                    for name, info in latest_versions.items():
                        extensions.append({
                            "name": name, 
                            "version": info["version"],
                            "download_url": info["download_url"],
                            "extension_id": info["extension_id"]
                        })

                    if extensions:
                        print(f"成功获取 {len(extensions)} 个远程插件")
                        return extensions

                except Exception as e:
                    print(f"解析远程数据失败: {e}")
                    return []

        except Exception as e:
            print(f"获取远程插件失败: {e}")
            return []

    # ==================== 本地版本检查部分 ====================

    def get_local_extensions(self, project_path):
        """获取本地插件列表"""
        extensions_json_path = os.path.join(project_path, "data", "extensions", "extensions.json")

        # 检查文件是否存在
        if not os.path.exists(extensions_json_path):
            print(f"文件不存在: {extensions_json_path}")
            return []

        try:
            with open(extensions_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, list):
                data = [data]

            results = []
            for item in data:
                identifier_id = item.get('identifier', {}).get('id', '')
                plugin_name = identifier_id.split('.')[-1] if '.' in identifier_id else identifier_id

                # 跳过语言包
                if plugin_name == 'vscode-language-pack-zh-hans':
                    continue

                version = item.get('version', '')
                results.append({"name": plugin_name, "version": version})

            print(f"成功获取 {len(results)} 个本地插件")
            return results

        except Exception as e:
            print(f"读取本地插件失败: {e}")
            return []

    # ==================== 对比和输出部分 ====================

    def compare_plugins(self, local_plugins, remote_plugins):
        """对比本地和远程插件版本"""
        local_dict = {p['name']: p['version'] for p in local_plugins}
        remote_dict = {p['name']: p['version'] for p in remote_plugins}

        all_plugin_names = set(local_dict.keys()) | set(remote_dict.keys())

        comparison_results = []

        for name in sorted(all_plugin_names):
            local_version = local_dict.get(name, '不存在')
            remote_p = next((p for p in remote_plugins if p['name'] == name), None)
            remote_version = remote_p['version'] if remote_p else '不存在'
            download_url = remote_p['download_url'] if remote_p else ''

            status = '一致'
            if local_version != '不存在' and remote_version != '不存在':
                if local_version != remote_version:
                    status = '版本不同'
            elif local_version == '不存在':
                status = '仅远程存在'
            else:
                status = '仅本地存在'

            comparison_results.append({
                'name': name,
                'local_version': local_version,
                'remote_version': remote_version,
                'status': status,
                'download_url': download_url
            })

        return comparison_results

    def download_plugin(self, plugin_name, domain, save_path, download_url=None, password="bjev666"):
        """下载指定插件"""
        try:
            # 如果没有提供直接的download_url，则尝试根据name构建
            if not download_url:
                download_url = f"/api/plugins/download?name={plugin_name}"
            
            # 确保download_url是完整URL
            if not download_url.startswith('http'):
                full_download_url = domain + download_url
            else:
                full_download_url = download_url
            
            print(f"\n[找到'下载插件'按钮] 正在下载插件: {plugin_name}")
            # print(f"下载链接: {full_download_url}")
            
            request = urllib.request.Request(full_download_url)
            request.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            request.add_header('X-Password', password)
            
            print(f"正在下载插件: {plugin_name}")
            
            with urllib.request.urlopen(request, timeout=30, context=context) as response:
                if response.getcode() == 200:
                    # 获取文件名
                    content_disposition = response.getheader('Content-Disposition')
                    filename = plugin_name + ".zip"
                    if content_disposition:
                        import re
                        match = re.search(r'filename="?([^"]+)"?', content_disposition)
                        if match:
                            filename = match.group(1)
                    
                    # 保存文件
                    file_path = os.path.join(save_path, filename)
                    
                    # 确保保存目录存在
                    os.makedirs(save_path, exist_ok=True)
                    
                    with open(file_path, 'wb') as f:
                        f.write(response.read())
                    
                    print(f"成功下载插件: {filename}")
                    return file_path
                else:
                    print(f"下载插件失败，状态码: {response.getcode()}")
                    return None
        except Exception as e:
            print(f"下载插件时出错: {e}")
            return None

    def save_and_display_results(self, local_plugins, remote_plugins, comparison_results):
        """保存并显示结果"""

        # 计算统计信息
        local_count = len([p for p in comparison_results if p['local_version'] != '不存在'])
        remote_count = len([p for p in comparison_results if p['remote_version'] != '不存在'])

        status_counts = {}
        for item in comparison_results:
            status_counts[item['status']] = status_counts.get(item['status'], 0) + 1

        # 打印对比结果
        print("\n" + "=" * 90)
        print("插件版本对比结果".center(78))
        print("=" * 90)

        # 表头
        print(f"{'插件名称':<30} {'本地版本':<20} {'远程版本':<15} {'状态':<10}")
        print("-" * 90)

        # 数据行
        for item in comparison_results:
            print(f"{item['name']:<30} {item['local_version']:<20} {item['remote_version']:<20} {item['status']:<10}")

        # 统计信息
        print("-" * 90)
        # print(f"本地插件总数: {local_count}")
        # print(f"远程插件总数: {remote_count}")
        # print(f"版本一致: {status_counts.get('一致', 0)}")
        print(f"版本不同: {status_counts.get('版本不同', 0)}")
        # print(f"仅本地存在: {status_counts.get('仅本地存在', 0)}")
        # print(f"仅远程存在: {status_counts.get('仅远程存在', 0)}")
        print("=" * 90)

        # # 生成详细报告文件
        # filename = f"plugin_comparison_{pd.datetime.now().strftime('%Y%m%d_%H%M%S') if 'pd' in dir() else 'report'}.txt"
        #
        # with open('plugin_comparison.txt', 'w', encoding='utf-8') as f:
        #     f.write("=" * 120 + "\n")
        #     f.write("插件版本对比详细报告\n".center(118) + "\n")
        #     f.write("=" * 120 + "\n\n")
        #
        #     f.write(f"{'插件名称':<40} {'本地版本':<25} {'远程版本':<25} {'状态':<20}\n")
        #     f.write("-" * 120 + "\n")
        #
        #     for item in comparison_results:
        #         f.write(
        #             f"{item['name']:<40} {item['local_version']:<25} {item['remote_version']:<25} {item['status']:<20}\n")
        #
        #     f.write("-" * 120 + "\n")
        #     f.write(f"版本一致: {status_counts.get('一致', 0)}\n")
        #
        #     # 添加需要更新的插件列表
        #     need_update = [item for item in comparison_results
        #                    if item['status'] == '版本不同']
        #
        #     if need_update:
        #         f.write("\n" + "=" * 120 + "\n")
        #         f.write("建议更新的插件\n".center(118) + "\n")
        #         f.write("=" * 120 + "\n")
        #         for item in need_update:
        #             if item['status'] == '版本不同':
        #                 f.write(f"{item['name']:<30} 本地 {item['local_version']:<20}   远程 {item['remote_version']:<20}\n")
        #
        # print(f"\n 详细报告已保存到: plugin_comparison.txt")

        # 如果有版本差异，显示更新建议
        need_update = [item for item in comparison_results
                       if item['status'] == '版本不同']

        if need_update:
            print("\n" + "=" * 90)
            print("更新建议".center(78))
            print("*" * 90)
            for item in need_update:
                if item['status'] == '版本不同':
                    print(f"  {item['name']:<30} 本地 {item['local_version']:<20}  远程 {item['remote_version']:<20}")
            print("*" * 90)
        
        return need_update


# 导入datetime用于文件名
try:
    import pandas as pd
except:
    pass


# ==================== 主函数 ====================

def main():
    checker = PluginChecker()

    print("\n" + "=" * 90)
    print("插件版本检查工具".center(58))
    print("=" * 90)

    # 1. 获取远程插件
    print("\n[0/3] 使用方法...")
    print('1. 直接运行exe文件')
    print('2. 运行时，输入万花筒根路径作为参数，例如: D:\\kaleido')
    print('3. 运行时，输入y 确认下载插件')
    print('4. 脚本会自动下载插件，并保存到exe脚本当前目录下的文件中。')

    print("\n[1/3] 检查远程插件...")
    remote_url = checker.check_available_url()

    if remote_url:
        remote_plugins = checker.get_remote_extensions(remote_url)
    else:
        remote_plugins = []

    # 2. 获取本地插件
    print("\n[2/3] 检查本地插件...")
    # 检查是否通过命令行参数提供了路径
    project_path = ""
    if len(sys.argv) > 1:
        project_path = sys.argv[1].strip()
        print(f"从命令行获取路径: {project_path}")
    else:
        project_path = input("请输入万花筒根路径 (例如: D:\\kaleido): ").strip()

    if not project_path:
        project_path = "D:\\kaleido"
        print(f"使用默认路径: {project_path}")

    local_plugins = checker.get_local_extensions(project_path)

    # 3. 对比插件版本
    print("\n[3/3] 对比插件版本...")
    if local_plugins and remote_plugins:
        comparison_results = checker.compare_plugins(local_plugins, remote_plugins)
        need_update = checker.save_and_display_results(local_plugins, remote_plugins, comparison_results)
        
        # 下载插件的逻辑
        if need_update:
            print("\n" + "=" * 90)
            print("下载插件".center(78))
            print("=" * 90)
            download_choice = input("是否下载更新建议中的插件？(y/n): ").strip().lower()
            
            if download_choice == 'y':
                # 获取远程服务器域名
                from urllib.parse import urlparse
                parsed_url = urlparse(remote_url)
                domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
                
                # 确定下载保存路径（demo.exe所在路径）
                save_path = os.path.dirname(os.path.abspath(sys.argv[0]))
                print(f"插件将保存到: {save_path}")
                
                # 下载每个需要更新的插件
                print("\n开始下载插件...")
                for item in need_update:
                    plugin_name = item['name']
                    download_url = item.get('download_url')
                    checker.download_plugin(plugin_name, domain, save_path, download_url=download_url)
                
                print("\n所有插件下载完成！")
    else:
        print("\n 无法进行对比，缺少本地或远程插件信息")
        if local_plugins:
            print(f"本地插件数: {len(local_plugins)}")
        if remote_plugins:
            print(f"远程插件数: {len(remote_plugins)}")

    print("\n" + "=" * 90)
    input("按回车键退出...")  # 这行会让程序暂停，等待用户按回车


if __name__ == "__main__":
    main()

    # pyinstaller --onefile --console demonew.py
    # pyinstaller --onefile --console --icon=E:\MyDemo\version\app.ico demonew.py
    # pyinstaller --onefile --console --name=kaleido_version demonew.py
