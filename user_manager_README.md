# 用户管理服务器

用于远程管理 `sys_user` 表的用户信息，提供 Web 界面和 API。

## 功能特性

1. **用户列表展示** - 显示所有用户的用户名、密码、有效期、MAC绑定
2. **新增用户** - 添加新用户，有效期默认为当前时间后3个月
3. **编辑用户** - 修改密码、有效期、MAC绑定
4. **删除用户** - 删除指定用户
5. **MAC解绑** - 将MAC地址重置为 FF:FF:FF:FF:FF:FF

## 文件说明

| 文件 | 说明 |
|------|------|
| `user_manager_db.py` | 数据库操作层 |
| `user_manager_server.py` | Flask Web服务器（主程序） |
| `start_user_manager.bat` | Windows启动脚本 |
| `user_manager_ui.py` | 本地GUI版本（可选） |

## 快速启动

### 方式1：使用启动脚本（推荐）

```bash
start_user_manager.bat
```

### 方式2：命令行启动

```bash
# 安装依赖
pip install flask flask-cors pymysql dbutils

# 启动服务器
python user_manager_server.py
```

## 访问方式

服务器启动后，通过浏览器访问：

```
http://服务器IP:5000
```

- 管理密码：`admin123`（建议修改）
- 默认端口：`5000`

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/login` | POST | 登录 |
| `/api/logout` | POST | 登出 |
| `/api/users` | GET | 获取所有用户 |
| `/api/users` | POST | 新增用户 |
| `/api/users/<username>` | PUT | 修改用户 |
| `/api/users/<username>` | DELETE | 删除用户 |
| `/api/users/<username>/unbind` | POST | MAC解绑 |

### API 示例

```bash
# 登录
curl -X POST http://localhost:5000/api/login \
  -H "Content-Type: application/json" \
  -d '{"password": "admin123"}'

# 获取用户列表
curl http://localhost:5000/api/users

# 新增用户
curl -X POST http://localhost:5000/api/users \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "123456",
    "expiry_date": "2025-12-31",
    "mac_bind": "00:11:22:33:44:55"
  }'

# MAC解绑
curl -X POST http://localhost:5000/api/users/testuser/unbind
```

## 配置修改

### 修改管理密码

编辑 `user_manager_server.py`，修改第 38 行：

```python
ADMIN_PASSWORD = '你的新密码'
```

### 修改数据库配置

编辑 `user_manager_server.py`，修改第 26-33 行：

```python
DB_CONFIG = {
    'host': '数据库IP',
    'port': 3306,
    'user': '用户名',
    'password': '密码',
    'database': '数据库名',
    'charset': 'utf8mb4'
}
```

### 修改服务端口

编辑 `user_manager_server.py`，修改最后一行：

```python
app.run(host='0.0.0.0', port=8080, debug=False)  # 改为8080端口
```

## 部署到服务器

### 1. 复制文件到服务器

将以下文件复制到服务器：
- `user_manager_db.py`
- `user_manager_server.py`

### 2. 安装依赖

```bash
pip install flask flask-cors pymysql dbutils
```

### 3. 启动服务

```bash
# 前台运行（测试）
python user_manager_server.py

# 后台运行（Linux）
nohup python user_manager_server.py > user_manager.log 2>&1 &
```

### 4. 使用 systemd 守护进程（Linux）

创建 `/etc/systemd/system/user-manager.service`：

```ini
[Unit]
Description=User Manager Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/www/web1
ExecStart=/root/.pyenv/versions/3.12.0/bin/python3 user_manager_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
systemctl enable user-manager
systemctl start user-manager
systemctl status user-manager
```

## 注意事项

1. **安全性**：建议修改默认管理密码 `admin123`
2. **防火墙**：确保服务器防火墙开放 5000 端口
3. **HTTPS**：生产环境建议使用 HTTPS
4. **备份**：定期备份数据库

## 问题排查

### 无法连接数据库

检查数据库配置和网络连接：

```python
# 测试连接
python -c "import pymysql; conn = pymysql.connect(host='112.64.32.181', port=3311, user='root', password='Moso@2024!', database='MST_SQL'); print('连接成功'); conn.close()"
```

### 端口被占用

修改 `user_manager_server.py` 中的端口：

```python
app.run(host='0.0.0.0', port=5001, debug=False)  # 改为5001端口
```

### 依赖缺失

```bash
pip install flask flask-cors pymysql dbutils
```
