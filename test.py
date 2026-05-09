import socket
import threading

# ===================== 你只需要改这里 =====================
TARGET_IP = "112.64.32.181"  # 你的服务器公网IP
START_PORT = 1                # 起始端口
END_PORT = 65535              # 结束端口（全端口扫描）
# ==========================================================

open_ports = []

def scan_port(port):
    try:
        # 创建socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)  # 超时时间，越快扫描越快
        result = s.connect_ex((TARGET_IP, port))
        
        if result == 0:
            print(f"✅ 开放端口: {port}")
            open_ports.append(port)
        
        s.close()
    except Exception:
        pass

# 多线程扫描
def start_scan():
    print(f"开始扫描服务器 {TARGET_IP} 开放端口...\n")
    
    threads = []
    for port in range(START_PORT, END_PORT + 1):
        t = threading.Thread(target=scan_port, args=(port,))
        threads.append(t)
        t.start()
        
        # 限制并发数，避免卡死
        if len(threads) > 500:
            for t in threads:
                t.join()
            threads = []

    for t in threads:
        t.join()

    print("\n========== 扫描完成 ==========")
    print(f"服务器开放端口列表：{sorted(open_ports)}")

if __name__ == "__main__":
    start_scan()