#!/usr/bin/env python3
"""检查 HTML 模板中的问题"""
import os
import re

script_dir = os.path.dirname(os.path.abspath(__file__))
server_file = os.path.join(script_dir, 'user_manager_server.py')

with open(server_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 提取 ADMIN_HTML
start = content.find("ADMIN_HTML = '''") + len("ADMIN_HTML = '''")
end = content.find("'''\n\n\nif __name__", start)
html = content[start:end]

print("=" * 60)
print("检查 HTML 模板")
print("=" * 60)

# 检查关键元素
checks = [
    ('<script>', html.count('<script>')),
    ('</script>', html.count('</script>')),
    ('function loadUsers', 'loadUsers' in html),
    ('function renderUsers', 'renderUsers' in html),
    ('window.onload', 'window.onload' in html),
    ('${user.username}', '${user.username}' in html),
    ("'''", "'''" in html),
]

print("\n关键元素检查:")
for name, result in checks:
    status = "✓" if result else "✗"
    print(f"  {status} {name}: {result}")

# 检查是否有未闭合的标签
print("\n标签平衡检查:")
tags = ['div', 'table', 'thead', 'tbody', 'tr', 'td', 'th', 'button', 'script']
for tag in tags:
    open_count = len(re.findall(f'<{tag}[\s>]', html, re.IGNORECASE))
    close_count = len(re.findall(f'</{tag}>', html, re.IGNORECASE))
    status = "✓" if open_count == close_count else "✗"
    print(f"  {status} <{tag}>: 开{open_count} 闭{close_count}")

# 检查引号
print("\n引号检查:")
single_quotes = html.count("'")
double_quotes = html.count('"')
backticks = html.count('`')
print(f"  单引号: {single_quotes}")
print(f"  双引号: {double_quotes}")
print(f"  反引号: {backticks}")

# 检查是否有 Python 三引号冲突
print("\n潜在问题:")
if "'''" in html:
    print("  ✗ 发现 ''' 可能破坏 Python 字符串")
else:
    print("  ✓ 未发现 ''' 冲突")

# 输出 HTML 长度和 script 位置
print(f"\nHTML 总长度: {len(html)} 字符")
script_pos = html.find('<script>')
if script_pos > 0:
    print(f"<script> 位置: {script_pos}")
    # 显示 script 标签附近的内容
    print("\nScript 标签前 100 字符:")
    print(repr(html[script_pos-100:script_pos]))
    print("\nScript 标签后 100 字符:")
    print(repr(html[script_pos:script_pos+100]))
