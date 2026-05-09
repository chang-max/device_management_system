# 测试 HTML 输出
ADMIN_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>测试</title>
</head>
<body>
    <button onclick="loadUsers()">测试</button>
    <div id="result"></div>

    <script>
        function loadUsers() {
            console.log('loadUsers called');
            document.getElementById('result').textContent = '成功!';
        }
    </script>
</body>
</html>
'''

print(ADMIN_HTML)
print("=" * 50)
print("HTML length:", len(ADMIN_HTML))
