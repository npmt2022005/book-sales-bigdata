"""Quản lý server PostgreSQL riêng của đề tài (cổng 55432, dữ liệu trong data/pg).

Tách biệt với mọi server PostgreSQL khác trên máy và chỉ nhận kết nối từ máy này.
Cách chạy: .venv\\Scripts\\python src\\pg_local.py init|start|stop|status
Dùng cấu hình mặc định của PostgreSQL để làm mốc so sánh chưa tối ưu.
"""
import subprocess
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = Path(os.environ.get('BOOK_SALES_PG_BIN',r"C:\Program Files\PostgreSQL\18\bin"))
DATA = ROOT / "data" / "pg"
LOG = ROOT / "results" / "postgres.log"
PORT = 55432
DB = "book_sales"


def run(*command):
    return subprocess.run(
        [str(c) for c in command],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )


def require(result):
    print(result.stdout.strip())
    if result.returncode != 0:
        sys.exit(result.returncode)


def init():
    if DATA.exists():
        sys.exit(f"Đã có {DATA}, không khởi tạo lại.")
    require(run(BIN / "initdb", "-D", DATA, "-U", "postgres", "-A", "trust", "-E", "UTF8", "--locale=C"))
    start()
    require(run(BIN / "createdb", "-h", "127.0.0.1", "-p", PORT, "-U", "postgres", DB))


def start():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    options = f"-p {PORT} -c listen_addresses=127.0.0.1"
    # pg_ctl tự ghi log vào file -l. DEVNULL để tiến trình server không giữ stdout của lệnh này.
    result = subprocess.run(
        [str(BIN / "pg_ctl"), "-D", str(DATA), "-o", options, "-l", str(LOG), "-w", "start"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    if result.returncode != 0:
        sys.exit(f"Không khởi động được, xem {LOG}")
    print(f"Server đang chạy ở cổng {PORT}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "init":
        init()
    elif action == "start":
        start()
    elif action == "stop":
        require(run(BIN / "pg_ctl", "-D", DATA, "-m", "fast", "-w", "stop"))
    elif action == "status":
        print(run(BIN / "pg_ctl", "-D", DATA, "status").stdout.strip())
    else:
        sys.exit("Dùng: init | start | stop | status")


if __name__ == "__main__":
    main()
