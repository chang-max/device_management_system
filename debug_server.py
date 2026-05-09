#!/usr/bin/env python3
"""调试服务器 - 输出 HTML 到文件检查"""
import os
import sys

# 获取脚本所在目录
script_dir = os.path.dirname(os.path.abspath(__file__))
server_file = os.path.join(script_dir, 'user_manager_server.py')
output_file = os.path.join(script_dir, 'debug_admin.html')

# 读取 user_manager_server.py 中的 ADMIN_HTML
with open(server_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 提取 ADMIN_HTML
start = content.find("ADMIN_HTML = '''") + len("ADMIN_HTML = '''")
end = content.find("'''", start)
html = content[start:end]

# 保存到文件
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(html)

print("HTML 已保存到 debug_admin.html")
print(f"HTML 长度: {len(html)} 字符")
print(f"包含 'loadUsers': {'loadUsers' in html}")
print(f"包含 '<script>': {'<script>' in html}")
print(f"包含 '</script>': {'</script>' in html}")

# 检查 script 标签位置
script_start = html.find('<script>')
script_end = html.find('</script>')
print(f"Script 位置: {script_start} - {script_end}")
