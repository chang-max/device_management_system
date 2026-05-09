"""
用户管理模块 - Flask Web 服务器
用于远程管理 sys_user 表的用户信息
"""
from datetime import datetime, timedelta
from functools import wraps
import json
import os
import sys

from flask import Flask, request, jsonify, render_template_string, session, send_from_directory
from flask_cors import CORS

# 导入数据库操作层
from user_manager_db import UserManagerDB

# 尝试导入 dbutils，如果不存在则给出提示
try:
    import pymysql
    from pymysql.cursors import DictCursor
    from dbutils.pooled_db import PooledDB
except ImportError as e:
    print(f"缺少依赖: {e}")
    print("请安装: pip install PyMySQL DBUtils flask flask-cors")
    sys.exit(1)

# 获取当前文件所在目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')

app = Flask(__name__, static_folder=STATIC_DIR)
app.secret_key = 'user_manager_secret_key_2024'  # 用于session加密
CORS(app)  # 允许跨域

# 数据库配置
DB_CONFIG = {
    'host': '112.64.32.181',
    'port': 3311,
    'user': 'root',
    'password': 'Moso@2024!',
    'database': 'MST_SQL',
    'charset': 'utf8mb4'
}

# 管理后台登录密码（简单认证）
ADMIN_PASSWORD = 'admin123'  # 建议修改

# 全局数据库连接池
db_pool = None
user_db = None


def init_db_pool():
    """初始化数据库连接池"""
    global db_pool, user_db
    try:
        db_pool = PooledDB(
            creator=pymysql,
            maxconnections=10,
            mincached=2,
            maxcached=5,
            blocking=True,
            maxusage=None,
            setsession=[],
            ping=1,  # 自动检查连接
            host=DB_CONFIG['host'],
            port=DB_CONFIG['port'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password'],
            database=DB_CONFIG['database'],
            charset=DB_CONFIG['charset'],
            cursorclass=DictCursor
        )
        user_db = UserManagerDB(db_pool)
        print("数据库连接池初始化成功")
        return True
    except Exception as e:
        print(f"数据库连接池初始化失败: {e}")
        return False


def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'success': False, 'message': '请先登录'}), 401
        return f(*args, **kwargs)
    return decorated_function


# ==================== API 路由 ====================

@app.route('/')
def index():
    """首页 - 登录页面"""
    return send_from_directory(STATIC_DIR, 'index.html')


@app.route('/admin')
def admin():
    """管理页面"""
    if not session.get('logged_in'):
        return send_from_directory(STATIC_DIR, 'index.html')
    return send_from_directory(STATIC_DIR, 'admin.html')


@app.route('/<path:filename>')
def static_files(filename):
    """提供静态文件"""
    return send_from_directory(STATIC_DIR, filename)


@app.route('/api/login', methods=['POST'])
def api_login():
    """登录 API"""
    data = request.get_json()
    password = data.get('password', '')

    if password == ADMIN_PASSWORD:
        session['logged_in'] = True
        return jsonify({'success': True, 'message': '登录成功'})
    else:
        return jsonify({'success': False, 'message': '密码错误'})


@app.route('/api/logout', methods=['POST'])
def api_logout():
    """登出 API"""
    session.pop('logged_in', None)
    return jsonify({'success': True, 'message': '已登出'})


@app.route('/api/users', methods=['GET'])
@login_required
def api_get_users():
    """获取所有用户"""
    try:
        users = user_db.get_all_users()
        return jsonify({'success': True, 'data': users})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/users', methods=['POST'])
@login_required
def api_add_user():
    """新增用户"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        expiry_date = data.get('expiry_date')
        mac_bind = data.get('mac_bind', 'FF:FF:FF:FF:FF:FF').strip()
        area_info = data.get('area_info', '{}')  # 区域信息，默认为空JSON对象

        if not username or not password:
            return jsonify({'success': False, 'message': '用户名和密码不能为空'})

        # 转换日期
        if expiry_date:
            expiry_date = datetime.strptime(expiry_date, '%Y-%m-%d')
        else:
            expiry_date = datetime.now() + timedelta(days=90)

        success, message = user_db.add_user(username, password, expiry_date, mac_bind, area_info)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/users/<username>', methods=['PUT'])
@login_required
def api_update_user(username):
    """修改用户"""
    try:
        data = request.get_json()
        password = data.get('password', '').strip()
        expiry_date = data.get('expiry_date')
        mac_bind = data.get('mac_bind', '').strip()

        # 转换日期
        expiry = None
        if expiry_date:
            expiry = datetime.strptime(expiry_date, '%Y-%m-%d')

        # 如果密码为空，则不修改密码
        pwd = password if password else None

        success, message = user_db.update_user(username, pwd, expiry, mac_bind or None)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/users/<username>', methods=['DELETE'])
@login_required
def api_delete_user(username):
    """删除用户"""
    try:
        success, message = user_db.delete_user(username)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/users/<username>/unbind', methods=['POST'])
@login_required
def api_unbind_mac(username):
    """MAC 解绑"""
    try:
        success, message = user_db.unbind_mac(username)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== HTML 模板 ====================

LOGIN_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>用户管理系统 - 登录</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .login-box {
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            width: 350px;
        }
        h2 {
            text-align: center;
            color: #333;
            margin-bottom: 30px;
        }
        .input-group {
            margin-bottom: 20px;
        }
        input {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 14px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
        }
        button:hover { background: #5568d3; }
        .error {
            color: red;
            text-align: center;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="login-box">
        <h2>用户管理系统</h2>
        <div class="input-group">
            <input type="password" id="password" placeholder="请输入管理密码" onkeypress="if(event.keyCode==13)login()">
        </div>
        <button onclick="login()">登录</button>
        <div id="error" class="error"></div>
    </div>
    <script>
        function login() {
            var pwd = document.getElementById('password').value;
            fetch('/api/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({password: pwd})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    window.location.href = '/admin';
                } else {
                    document.getElementById('error').textContent = data.message;
                }
            });
        }
    </script>
</body>
</html>
'''

ADMIN_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>用户管理系统</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background: #f5f5f5;
        }
        .header {
            background: #333;
            color: white;
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header h1 { font-size: 20px; }
        .header button {
            background: #e74c3c;
            color: white;
            border: none;
            padding: 8px 20px;
            border-radius: 4px;
            cursor: pointer;
        }
        .container {
            max-width: 1200px;
            margin: 20px auto;
            padding: 0 20px;
        }
        .toolbar {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-right: 10px;
        }
        .btn-primary { background: #3498db; color: white; }
        .btn-success { background: #2ecc71; color: white; }
        .btn-danger { background: #e74c3c; color: white; }
        .btn-warning { background: #f39c12; color: white; }
        .table-container {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }
        th {
            background: #f8f9fa;
            font-weight: bold;
            color: #555;
        }
        tr:hover { background: #f8f9fa; }
        .actions button {
            padding: 5px 10px;
            margin-right: 5px;
            font-size: 12px;
        }
        .mac-unbound { color: #e74c3c; font-style: italic; }
        .modal {
            display: none;
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background: rgba(0,0,0,0.5);
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        .modal-content {
            background: white;
            padding: 30px;
            border-radius: 8px;
            width: 400px;
        }
        .modal h3 {
            margin-bottom: 20px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        .form-group input {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .modal-buttons {
            text-align: right;
            margin-top: 20px;
        }
        .modal-buttons button {
            margin-left: 10px;
        }
        .status-bar {
            background: #f8f9fa;
            padding: 10px 20px;
            border-top: 1px solid #eee;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>用户管理系统</h1>
        <button onclick="logout()">退出登录</button>
    </div>

    <div class="container">
        <div class="toolbar">
            <button class="btn btn-primary" onclick="showAddModal()">+ 新增用户</button>
            <button class="btn btn-success" onclick="loadUsers()">刷新列表</button>
        </div>

        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>用户名</th>
                        <th>密码</th>
                        <th>有效期</th>
                        <th>MAC绑定</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody id="userTable">
                    <!-- 动态加载 -->
                </tbody>
            </table>
            <div class="status-bar" id="statusBar">加载中...</div>
        </div>
    </div>

    <!-- 新增/编辑用户模态框 -->
    <div class="modal" id="userModal">
        <div class="modal-content">
            <h3 id="modalTitle">新增用户</h3>
            <div class="form-group">
                <label>用户名</label>
                <input type="text" id="username" placeholder="请输入用户名">
            </div>
            <div class="form-group">
                <label>密码</label>
                <input type="text" id="password" placeholder="请输入密码">
            </div>
            <div class="form-group">
                <label>有效期</label>
                <input type="date" id="expiryDate">
            </div>
            <div class="form-group">
                <label>MAC绑定</label>
                <input type="text" id="macBind" placeholder="FF:FF:FF:FF:FF:FF">
            </div>
            <div class="modal-buttons">
                <button class="btn" onclick="closeModal()">取消</button>
                <button class="btn btn-primary" onclick="saveUser()">保存</button>
            </div>
        </div>
    </div>

    <script>
        let editingUser = null;

        // 页面加载时获取用户列表
        window.onload = function() {
            loadUsers();
            // 设置默认有效期为3个月后
            var date = new Date();
            date.setMonth(date.getMonth() + 3);
            document.getElementById('expiryDate').value = date.toISOString().split('T')[0];
        };

        // 加载用户列表
        function loadUsers() {
            console.log('开始加载用户列表...');
            fetch('/api/users')
                .then(r => {
                    console.log('API 响应状态:', r.status);
                    if (!r.ok) {
                        throw new Error('HTTP error! status: ' + r.status);
                    }
                    return r.json();
                })
                .then(data => {
                    console.log('API 返回数据:', data);
                    if (data.success) {
                        renderUsers(data.data);
                        document.getElementById('statusBar').textContent = '共 ' + data.data.length + ' 个用户';
                    } else {
                        alert(data.message);
                    }
                })
                .catch(e => {
                    console.error('加载用户列表失败:', e);
                    document.getElementById('statusBar').textContent = '加载失败: ' + e.message;
                    alert('加载失败，请检查网络连接');
                });
        }

        // 渲染用户列表
        function renderUsers(users) {
            var tbody = document.getElementById('userTable');
            tbody.innerHTML = '';

            users.forEach(function(user) {
                var tr = document.createElement('tr');
                var expiryDate = user.expiry_date ? user.expiry_date.split('T')[0] : '';
                var isUnbound = user.mac_bind === 'FF:FF:FF:FF:FF:FF';

                tr.innerHTML = `
                    <td>${user.username}</td>
                    <td>********</td>
                    <td>${expiryDate}</td>
                    <td class="${isUnbound ? 'mac-unbound' : ''}">${user.mac_bind || 'FF:FF:FF:FF:FF:FF'}</td>
                    <td class="actions">
                        <button class="btn btn-primary" onclick='editUser(${JSON.stringify(user)})'>编辑</button>
                        ${!isUnbound ? '<button class="btn btn-warning" onclick="unbindMac(\'' + user.username + '\')">解绑MAC</button>' : ''}
                        <button class="btn btn-danger" onclick="deleteUser('${user.username}')">删除</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }

        // 显示新增模态框
        function showAddModal() {
            editingUser = null;
            document.getElementById('modalTitle').textContent = '新增用户';
            document.getElementById('username').value = '';
            document.getElementById('password').value = '';
            document.getElementById('username').disabled = false;

            // 默认3个月后
            var date = new Date();
            date.setMonth(date.getMonth() + 3);
            document.getElementById('expiryDate').value = date.toISOString().split('T')[0];

            document.getElementById('macBind').value = 'FF:FF:FF:FF:FF:FF';
            document.getElementById('userModal').style.display = 'flex';
        }

        // 编辑用户
        function editUser(user) {
            editingUser = user.username;
            document.getElementById('modalTitle').textContent = '编辑用户';
            document.getElementById('username').value = user.username;
            document.getElementById('username').disabled = true;
            document.getElementById('password').value = '';
            document.getElementById('expiryDate').value = user.expiry_date ? user.expiry_date.split('T')[0] : '';
            document.getElementById('macBind').value = user.mac_bind || 'FF:FF:FF:FF:FF:FF';
            document.getElementById('userModal').style.display = 'flex';
        }

        // 关闭模态框
        function closeModal() {
            document.getElementById('userModal').style.display = 'none';
        }

        // 保存用户
        function saveUser() {
            var username = document.getElementById('username').value.trim();
            var password = document.getElementById('password').value.trim();
            var expiryDate = document.getElementById('expiryDate').value;
            var macBind = document.getElementById('macBind').value.trim() || 'FF:FF:FF:FF:FF:FF';

            if (!username) {
                alert('用户名不能为空');
                return;
            }

            var url = editingUser ? '/api/users/' + editingUser : '/api/users';
            var method = editingUser ? 'PUT' : 'POST';

            var data = {
                username: username,
                password: password,
                expiry_date: expiryDate,
                mac_bind: macBind
            };

            fetch(url, {
                method: method,
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(result => {
                if (result.success) {
                    closeModal();
                    loadUsers();
                } else {
                    alert(result.message);
                }
            });
        }

        // 删除用户
        function deleteUser(username) {
            if (!confirm('确定要删除用户 "' + username + '" 吗？')) return;

            fetch('/api/users/' + username, {method: 'DELETE'})
                .then(r => r.json())
                .then(result => {
                    if (result.success) {
                        loadUsers();
                    } else {
                        alert(result.message);
                    }
                });
        }

        // MAC解绑
        function unbindMac(username) {
            if (!confirm('确定要解绑用户 "' + username + '" 的MAC地址吗？')) return;

            fetch('/api/users/' + username + '/unbind', {method: 'POST'})
                .then(r => r.json())
                .then(result => {
                    if (result.success) {
                        loadUsers();
                    } else {
                        alert(result.message);
                    }
                });
        }

        // 退出登录
        function logout() {
            fetch('/api/logout', {method: 'POST'})
                .then(() => window.location.href = '/');
        }

        // 点击模态框外部关闭
        window.onclick = function(e) {
            if (e.target.className === 'modal') {
                closeModal();
            }
        };
    </script>
</body>
</html>
'''


if __name__ == '__main__':
    # 初始化数据库
    if not init_db_pool():
        print("服务器启动失败：数据库连接失败")
        sys.exit(1)

    # 启动 Flask 服务器
    # host='0.0.0.0' 允许外部访问
    # port=5001 默认端口
    print("=" * 50)
    print("用户管理服务器启动成功！")
    print("访问地址: http://服务器IP:5001")
    print("管理密码: admin123 （建议修改）")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5001, debug=False)
