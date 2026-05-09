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
    })
    .catch(e => {
        console.error('登录失败:', e);
        document.getElementById('error').textContent = '登录失败，请检查网络连接';
    });
}
