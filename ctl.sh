#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

APP="app.py"
PID_FILE="$DIR/.darkchess.pid"
LOG_FILE="$DIR/logs/darkchess.log"
PORT="${PORT:-30902}"
PYTHON="$DIR/.venv/bin/python"

usage() {
    cat <<EOF
用法: $0 {start|stop|restart|status|log|deploy}

  start    启动 Dark Chess Online
  stop     停止服务
  restart  重启服务
  status   查看运行状态
  log      查看日志（tail -f）
  deploy   发布前端 web/dark_chess.html → /home/ubuntu/www/games/ 并校验
EOF
}

ensure_env() {
    if [[ ! -x "$PYTHON" ]]; then
        echo "错误: 虚拟环境不存在，请先运行: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
        exit 1
    fi
    mkdir -p "$DIR/logs"
}

current_pid() {
    [[ -f "$PID_FILE" ]] || return 1
    local pid
    pid="$(cat "$PID_FILE")"
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && echo "$pid"
}

is_running() { current_pid >/dev/null; }

start() {
    ensure_env
    if is_running; then
        echo "服务已在运行 (PID: $(current_pid), 端口: $PORT)"
        return 0
    fi
    nohup "$PYTHON" "$APP" >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    sleep 1
    if is_running; then
        echo "已启动 (PID: $(current_pid), 监听 127.0.0.1:$PORT)"
    else
        echo "启动失败，请查看日志: $LOG_FILE"
        return 1
    fi
}

stop() {
    if ! is_running; then
        echo "服务未运行"
        rm -f "$PID_FILE"
        return 0
    fi
    local pid
    pid="$(current_pid)"
    kill "$pid"
    for _ in $(seq 1 20); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.2
    done
    if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" || true
    fi
    rm -f "$PID_FILE"
    echo "已停止"
}

status() {
    if is_running; then
        echo "运行中 (PID: $(current_pid), 端口: $PORT)"
        curl -s -m 3 "http://127.0.0.1:$PORT/health" && echo
    else
        echo "未运行"
        return 1
    fi
}

deploy() {
    local src="$DIR/web/dark_chess.html"
    local dst="/home/ubuntu/www/games/dark_chess.html"
    [[ -f "$src" ]] || { echo "错误: 找不到前端源文件 $src"; exit 1; }
    install -m 644 "$src" "$dst"
    if diff -q "$src" "$dst" >/dev/null; then
        echo "已部署: $dst"
    else
        echo "部署校验失败: $src 与 $dst 不一致"
        return 1
    fi
    local code
    code="$(curl -s -o /dev/null -w '%{http_code}' -A "Mozilla/5.0" http://127.0.0.1/games/dark_chess.html || true)"
    echo "  公网路径 /games/dark_chess.html → HTTP $code"
}

case "${1:-}" in
    start)   start ;;
    stop)    stop ;;
    restart) stop; start ;;
    status)  status ;;
    log)     tail -f "$LOG_FILE" ;;
    deploy)  deploy ;;
    *)       usage; exit 1 ;;
esac
