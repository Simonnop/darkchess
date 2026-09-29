# Dark Chess Online（暗棋联机）

前端 + 后端一体化目录。服务端 FastAPI（房间制 WebSocket，内存态、无持久化），
前端为单页双模式（单机同屏 / 联机）。

## 结构

```
darkchess/
├── app.py             FastAPI 服务：房间、表决、广播（端口 30902）
├── rules.py           规则与合法性判定（与前端 JS 对拍一致）
├── test_rules.py      规则单测
├── crosscheck.py      JS/PY 规则对拍脚本
├── requirements.txt   fastapi + uvicorn[standard]
├── ctl.sh             start|stop|restart|status|log|deploy
├── web/
│   └── dark_chess.html   前端源文件（唯一事实来源）
├── tests/             浏览器集成测试页 + CDP 驱动器
├── logs/              运行日志（darkchess.log）
└── .venv/             虚拟环境
```

## 常用命令

```bash
./ctl.sh start      # 启动（127.0.0.1:30902）
./ctl.sh status     # 状态 + /health
./ctl.sh restart
./ctl.sh log
./ctl.sh deploy     # 前端发布到 /home/ubuntu/www/games/dark_chess.html 并校验（免 sudo）
```

## 部署与访问路径

- 前端由 nginx 静态托管（公开）：`/games/dark_chess.html`（邀请链接即此路径）
- 后端经 nginx 反代（公开）：`/darkchess/` → `http://127.0.0.1:30902/`
  - `POST /api/rooms` 建房、`GET /api/rooms/{code}` 探测
  - `WS /ws?room=CODE&token=T&side=bottom|top` 进房 / 重连
  - `GET /health` 健康检查（health-probe.sh 每分钟探测）
- 改完前端务必 `./ctl.sh deploy` 同步，避免源文件与线上不一致。

## 测试

```bash
.venv/bin/python test_rules.py      # 规则单测
.venv/bin/python crosscheck.py      # JS/PY 对拍
```

`tests/` 下的 HTML 需通过站点 `/games/dark_chess.html` 加载（用无头 Chromium CDP 驱动）。
