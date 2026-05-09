let editingUser = null;
let autoRefreshInterval = null;

// 页面加载时获取用户列表
window.onload = function() {
    loadUsers();
    // 设置默认有效期为3个月后
    var date = new Date();
    date.setMonth(date.getMonth() + 3);
    document.getElementById('expiryDate').value = date.toISOString().split('T')[0];

    // 启动自动刷新（每10秒刷新一次）
    startAutoRefresh();
};

// 启动自动刷新
function startAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
    autoRefreshInterval = setInterval(function() {
        // 只有在不处于编辑模式时才自动刷新
        if (document.getElementById('userModal').style.display !== 'flex') {
            loadUsers();
        }
    }, 10000); // 10秒刷新一次
}

// 停止自动刷新
function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

// 页面关闭时清理定时器
window.onbeforeunload = function() {
    stopAutoRefresh();
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

    // 统计数据
    var now = new Date();
    var validCount = 0;
    var expiredCount = 0;
    var boundCount = 0;

    users.forEach(function(user) {
        var tr = document.createElement('tr');

        // 格式化日期为中国习惯 (YYYY-MM-DD)
        var expiryDateStr = user.expiry_date ? formatDate(user.expiry_date) : '';

        // 检查是否过期
        var expiryDate = user.expiry_date ? new Date(user.expiry_date) : null;
        var isValid = expiryDate && expiryDate > now;
        var statusClass = isValid ? 'status-valid' : 'status-expired';
        var statusText = isValid ? '有效' : '已过期';

        // 统计
        if (isValid) validCount++;
        else expiredCount++;

        // MAC绑定状态
        var isUnbound = !user.mac_bind || user.mac_bind === 'FF:FF:FF:FF:FF:FF';
        if (!isUnbound) boundCount++;

        tr.innerHTML = `
            <td>${escapeHtml(user.username)}</td>
            <td>${escapeHtml(user.password)}</td>
            <td>${expiryDateStr}</td>
            <td class="${isUnbound ? 'mac-unbound' : ''}">${user.mac_bind || 'FF:FF:FF:FF:FF:FF'}</td>
            <td class="${statusClass}">${statusText}</td>
            <td class="actions">
                <button class="btn btn-primary" onclick="editUser('${escapeHtml(user.username)}', '${expiryDateStr}', '${user.mac_bind || 'FF:FF:FF:FF:FF:FF'}')">编辑</button>
                ${!isUnbound ? '<button class="btn btn-warning" onclick="unbindMac(\'' + escapeHtml(user.username) + '\')">解绑MAC</button>' : ''}
                <button class="btn btn-danger" onclick="deleteUser('${escapeHtml(user.username)}')">删除</button>
            </td>
        `;
        tbody.appendChild(tr);
    });

    // 更新统计面板
    document.getElementById('statTotal').textContent = users.length;
    document.getElementById('statValid').textContent = validCount;
    document.getElementById('statExpired').textContent = expiredCount;
    document.getElementById('statBound').textContent = boundCount;
}

// 格式化日期为 YYYY-MM-DD
function formatDate(dateStr) {
    if (!dateStr) return '';
    var date = new Date(dateStr);
    if (isNaN(date.getTime())) return dateStr;
    var year = date.getFullYear();
    var month = String(date.getMonth() + 1).padStart(2, '0');
    var day = String(date.getDate()).padStart(2, '0');
    return year + '-' + month + '-' + day;
}

// HTML 转义函数
function escapeHtml(text) {
    if (!text) return '';
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// 显示新增模态框
function showAddModal() {
    editingUser = null;
    document.getElementById('modalTitle').textContent = '新增用户';
    document.getElementById('username').value = '';
    document.getElementById('password').value = '';
    document.getElementById('username').disabled = false;
    var date = new Date();
    date.setMonth(date.getMonth() + 3);
    document.getElementById('expiryDate').value = date.toISOString().split('T')[0];
    document.getElementById('macBind').value = 'FF:FF:FF:FF:FF:FF';
    document.getElementById('userModal').style.display = 'flex';
}

// 显示编辑模态框
function editUser(username, expiryDate, macBind) {
    editingUser = username;
    document.getElementById('modalTitle').textContent = '编辑用户';
    document.getElementById('username').value = username;
    document.getElementById('password').value = '';
    document.getElementById('username').disabled = true;
    document.getElementById('expiryDate').value = expiryDate || '';
    document.getElementById('macBind').value = macBind || 'FF:FF:FF:FF:FF:FF';
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

    var url = editingUser ? '/api/users/' + encodeURIComponent(editingUser) : '/api/users';
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
    })
    .catch(e => {
        console.error('保存失败:', e);
        alert('保存失败');
    });
}

// 删除用户
function deleteUser(username) {
    if (!confirm('确定要删除用户 "' + username + '" 吗？')) return;

    fetch('/api/users/' + encodeURIComponent(username), {method: 'DELETE'})
        .then(r => r.json())
        .then(result => {
            if (result.success) {
                loadUsers();
            } else {
                alert(result.message);
            }
        })
        .catch(e => {
            console.error('删除失败:', e);
            alert('删除失败');
        });
}

// 解绑MAC
function unbindMac(username) {
    if (!confirm('确定要解绑用户 "' + username + '" 的MAC地址吗？')) return;

    fetch('/api/users/' + encodeURIComponent(username) + '/unbind', {method: 'POST'})
        .then(r => r.json())
        .then(result => {
            if (result.success) {
                loadUsers();
            } else {
                alert(result.message);
            }
        })
        .catch(e => {
            console.error('解绑失败:', e);
            alert('解绑失败');
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
