@echo off
chcp 65001 >nul
echo ==========================================
echo 用户管理服务器启动脚本
echo ==========================================
echo.

REM 检查Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

REM 检查虚拟环境
if exist ".venv\Scripts\activate.bat" (
    echo [信息] 使用虚拟环境
    call .venv\Scripts\activate.bat
) else (
    echo [信息] 使用系统Python环境
)

REM 检查依赖
echo [信息] 检查依赖...
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo [信息] 安装依赖...
    pip install flask flask-cors pymysql dbutils
)

echo.
echo ==========================================
echo 启动用户管理服务器...
echo 访问地址: http://服务器IP:5000
echo 管理密码: admin123
echo ==========================================
echo.

python user_manager_server.py

pause
