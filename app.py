"""暗棋联机服务端 —— 房间制 WebSocket（内存态，无持久化）。

路由（经 nginx 反代时前缀 /darkchess/ 会被剥离）：
  GET  /health                健康检查
  POST /api/rooms             建房 → {"code": "ABC123"}
  GET  /api/rooms/{code}      房间探测 → {"exists": bool, "counts": {...}}
  WS   /ws?room=CODE&token=T&side=bottom|top

多人同房：房间分「下方 / 上方」两个半场，每边最多 SIDE_MAX 人。
选了半场之后不分选手/观战——同一边任何人在轮到自己这边时都能「提议」，
**同一边在线成员全部同意才执行**；单人在线时一步到位（等价于原来的双人对局）。
和棋 / 再来一局属于双方事务，需要两边在线成员全部同意。
棋盘标点（可带预设短语）只在房间内转发，不落库，客户端 10 秒淡出。

规则与合法性判定全部在 rules.py；本模块只管房间、表决与广播。
"""

import asyncio
import json
import secrets
import time

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

import rules as R

PORT = 30902
ROOM_TTL = 30 * 60          # 闲置 30 分钟回收
RECLAIM_AFTER = 120         # 断线超过 2 分钟，同一标识可被新连接接管（仅用于令牌找回）
MAX_ROOMS = 200
MAX_WS_PER_IP = 12
SIDE_MAX = 2                # 固定 2v2：每边 2 人，房间共 4 座
ALPHABET = "0123456789"     # 房间码：6 位纯数字
COLORS = ["#B04A3C", "#3F6C8A", "#5F7D5B", "#B8873C",
          "#6C5B8A", "#2F7A72", "#8A5C7A", "#6E6A3E"]

app = FastAPI(title="Dark Chess Online")

rooms = {}        # code -> room
ip_conns = {}     # ip -> 当前活跃 WS 数
started_at = time.time()


# ------------------------------------------------------------------ 房间

def new_code():
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(6))
        if code not in rooms:
            return code


def new_room():
    code = new_code()
    now = time.time()
    room = {"code": code, "state": None, "members": {}, "seq": 0,
            "proposal": None, "created": now, "touched": now, "last": None}
    rooms[code] = room
    return room


def touch(room):
    room["touched"] = time.time()


def online(room, side=None):
    return [m for m in room["members"].values()
            if m["online"] and (side is None or m["side"] == side)]


def counts(room):
    out = {}
    for s in ("bottom", "top"):
        ms = [m for m in room["members"].values() if m["side"] == s]
        out[s] = {"total": len(ms), "online": sum(1 for m in ms if m["online"])}
    return out


def other_side(side):
    return "top" if side == "bottom" else "bottom"


def need_of(room, p):
    """该提案还差哪些在线成员点头"""
    pool = online(room, p["side"]) if p["kind"] in ("move", "flip") else online(room)
    return {m["id"] for m in pool} - p["agree"]


def prop_view(room):
    p = room.get("proposal")
    if not p:
        return None
    out = {"kind": p["kind"], "side": p["side"], "by": p["by"],
           "agree": sorted(p["agree"]), "need": sorted(need_of(room, p))}
    if p["kind"] == "move":
        out.update(fr=p.get("fr"), fc=p.get("fc"), tr=p.get("tr"), tc=p.get("tc"))
    return out


def roster_msg(room):
    return {"t": "roster", "counts": counts(room), "proposal": prop_view(room),
            "members": [{"id": m["id"], "side": m["side"], "online": m["online"],
                         "color": m["color"], "label": m["label"]}
                        for m in sorted(room["members"].values(), key=lambda x: x["id"])]}


def state_msg(room, m, evt=None):
    st = room["state"]
    msg = {"t": "state", "room": room["code"], "seat": m["side"],
           "opp": any(x["online"] for x in room["members"].values() if x["side"] == other_side(m["side"])),
           "counts": counts(room), "proposal": prop_view(room)}
    if st is None:
        msg["started"] = False
        msg.update(R.preset_view())
        msg["seatColor"] = None
        msg["last"] = room.get("last")          # 上一局结果（结束即回等待厅，结果留给客户端展示）
    else:
        msg["started"] = True
        msg.update(R.view(st, m["side"]))
        msg["seatColor"] = R.seat_color(st, m["side"])
    if evt:
        msg["evt"] = evt
    return msg


async def send(ws, msg):
    try:
        await ws.send_text(json.dumps(msg, ensure_ascii=False))
    except Exception:
        pass


async def broadcast(room, msg, skip=None):
    for m in room["members"].values():
        if skip is not None and m["id"] == skip:
            continue
        if m["ws"]:
            await send(m["ws"], msg)


async def send_side(room, side, msg, skip=None):
    """只发给某一边（同队）的在线成员"""
    for m in room["members"].values():
        if m["side"] != side:
            continue
        if skip is not None and m["id"] == skip:
            continue
        if m["ws"]:
            await send(m["ws"], msg)


async def broadcast_state(room, evt=None):
    for m in room["members"].values():
        if m["ws"]:
            await send(m["ws"], state_msg(room, m, evt))


async def broadcast_roster(room):
    await broadcast(room, roster_msg(room))


# ------------------------------------------------------------------ 表决

async def settle(room, evt=None):
    """一局结束 / 作废：记下上一局结果，回到「选边 → 等待开始」的等待厅"""
    st = room.get("state")
    result = (st.get("result") or "").strip() if st else ""
    room["last"] = {"text": result, "ts": time.time()} if result else None
    room["state"] = None
    await broadcast_state(room, evt)


async def exec_proposal(room):
    p = room["proposal"]
    if not p:
        return
    room["proposal"] = None
    kind = p["kind"]
    if kind == "move":
        st = room["state"]
        ok, evt, err = R.do_move(st, p["side"], p["fr"], p["fc"], p["tr"], p["tc"])
        if ok:
            await broadcast_state(room, evt)  # 含终局：保留最终棋子分布，结果展示在棋盘下方
        else:
            await broadcast(room, {"t": "err", "msg": err or "这步走不了"})
    elif kind == "flip":
        st = room["state"]
        ok, evt, err = R.flip_general(st, p["side"])
        if ok:
            await broadcast_state(room, evt)
        else:
            await broadcast(room, {"t": "err", "msg": err or "现在不能翻"})
    elif kind == "draw":
        st = room["state"]
        R.finish(st, {"type": "draw"})
        st["pending_draw"] = None
        await broadcast_state(room)              # 和棋同样保留当前棋盘
    elif kind == "start":
        room["state"] = R.new_state()
        room["last"] = None
        await broadcast_state(room)
    elif kind in ("reset", "rematch"):         # 新开一局 / 再来一局：只回等待厅，开局要重新「开始对局」
        room["state"] = None
        room["last"] = None
        await broadcast_state(room)
    await broadcast(room, {"t": "proposal", "p": None})


async def try_finish(room):
    p = room.get("proposal")
    if p and not need_of(room, p):
        await exec_proposal(room)
        return True
    return False


async def propose(room, m, kind, **kw):
    """发起提案；若该提案当前无待表决对象（如单人在线）则立即执行"""
    room["proposal"] = dict(kind=kind, side=m["side"], by=m["id"], agree={m["id"]}, **kw)
    if not await try_finish(room):
        await broadcast(room, {"t": "proposal", "p": prop_view(room)})


async def vote(room, m, yes):
    p = room.get("proposal")
    if not p or m["id"] not in room["members"]:
        return
    if p["kind"] == "move" and m["side"] != p["side"]:
        await send(m["ws"], {"t": "err", "msg": "这是对方半场的表决"})
        return
    if yes:
        if m["id"] in p["agree"]:
            return
        p["agree"].add(m["id"])
        if not await try_finish(room):
            await broadcast(room, {"t": "proposal", "p": prop_view(room)})
    else:
        room["proposal"] = None
        await broadcast(room, {"t": "proposal", "p": None, "declined": m["id"]})


# ------------------------------------------------------------------ HTTP

@app.get("/health")
async def health():
    return {"ok": True, "rooms": len(rooms), "uptime": int(time.time() - started_at)}


@app.post("/api/rooms")
async def create_room():
    if len(rooms) >= MAX_ROOMS:
        return JSONResponse({"error": "房间数已达上限，稍后再试"}, status_code=503)
    room = new_room()
    return {"code": room["code"]}


@app.get("/api/rooms/{code}")
async def room_info(code: str):
    room = rooms.get(code.upper())
    if not room:
        return {"exists": False}
    c = counts(room)
    full = c["bottom"]["total"] >= SIDE_MAX and c["top"]["total"] >= SIDE_MAX
    return {"exists": True, "full": full, "counts": c}


# ------------------------------------------------------------------ WebSocket

def join_room(room, side, token):
    """返回 (member, new_token) 或 (None, None)

    有令牌 → 找回原成员；否则按申请的半场入座（未指定则去人少的一边，持平进下方）。
    """
    if token:
        for m in room["members"].values():
            if m["token"] and secrets.compare_digest(m["token"], token):
                return m, m["token"]
    if side not in ("bottom", "top"):
        b = sum(1 for m in room["members"].values() if m["side"] == "bottom")
        t = sum(1 for m in room["members"].values() if m["side"] == "top")
        side = "bottom" if b <= t else "top"
    used = sum(1 for m in room["members"].values() if m["side"] == side)
    if used >= SIDE_MAX:
        free = [s for s in ("bottom", "top")
                if sum(1 for m in room["members"].values() if m["side"] == s) < SIDE_MAX]
        if not free:
            return None, None
        side = free[0]
        forced = True
    else:
        forced = False
    room["seq"] += 1
    mid = room["seq"]
    m = {"id": mid, "side": side, "token": secrets.token_hex(16), "ws": None,
         "online": False, "last_seen": time.time(),
         "color": COLORS[(mid - 1) % len(COLORS)], "label": str(mid), "forced": forced}
    room["members"][mid] = m
    return m, m["token"]


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    room_code = (ws.query_params.get("room") or "").upper()
    token = ws.query_params.get("token") or ""
    side = (ws.query_params.get("side") or "").lower()
    room = rooms.get(room_code)
    if not room:
        await ws.close(code=4004)
        return
    member, new_token = join_room(room, side, token)
    if not member:
        await ws.close(code=4003)          # 两个半场都满了
        return

    ip = ws.client.host if ws.client else "?"
    if ip_conns.get(ip, 0) >= MAX_WS_PER_IP:
        await ws.close(code=4008)
        return

    await ws.accept()
    ip_conns[ip] = ip_conns.get(ip, 0) + 1
    old_ws = member["ws"]
    member["token"] = new_token
    member["ws"] = ws
    member["online"] = True
    member["last_seen"] = time.time()
    touch(room)
    if old_ws is not None and old_ws is not ws:
        try:
            await old_ws.close(code=4006)      # 同一成员重复登录：踢掉旧连接
        except Exception:
            pass

    await send(ws, {"t": "hello", "room": room["code"], "id": member["id"],
                    "seat": member["side"], "token": new_token,
                    "color": member["color"], "label": member["label"],
                    "forced": member.pop("forced", False)})
    await send(ws, roster_msg(room))
    await send(ws, state_msg(room, member))
    await broadcast(room, roster_msg(room), skip=member["id"])

    try:
        while True:
            raw = await ws.receive_text()
            if len(raw) > 4096:
                continue
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            try:
                await handle(room, member, msg)
            except Exception as exc:                       # 单条消息出错不断连接
                print("handle error:", type(exc).__name__, exc, flush=True)
            touch(room)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        ip_conns[ip] = max(0, ip_conns.get(ip, 1) - 1)
        if member["ws"] is ws:
            member["ws"] = None
            member["online"] = False
            member["last_seen"] = time.time()
            p = room.get("proposal")
            if p:                                   # 掉线的人不再阻塞表决
                p["agree"].discard(member["id"])
                if p["by"] == member["id"]:         # 提案人走了 → 撤案
                    room["proposal"] = None
                    await broadcast(room, {"t": "proposal", "p": None})
                else:
                    await try_finish(room)
            await send_side(room, member["side"],
                            {"t": "sim:clear", "by": member["id"]})
            await broadcast_roster(room)


async def handle(room, m, msg):
    if m["id"] not in room["members"]:
        return
    t = msg.get("t")
    st = room["state"]

    if t == "mark":                              # 标点交流（全房可见）
        r, c = msg.get("r"), msg.get("c")
        if not isinstance(r, int) or not isinstance(c, int):
            return
        if not (0 <= r < R.ROWS and 0 <= c < R.COLS):
            return
        phrase = str(msg.get("phrase") or "")[:12]
        await broadcast(room, {"t": "mark", "r": r, "c": c, "phrase": phrase,
                               "by": m["id"], "side": m["side"],
                               "color": m["color"], "label": m["label"]})
        return
    if t == "marks:clear":
        await broadcast(room, {"t": "marks:clear", "by": m["id"]})
        return
    if t == "sim":                                 # 队内推演盘：只转发同一边的成员
        sim_board = msg.get("board")
        if not isinstance(sim_board, list) or len(sim_board) > R.ROWS:
            return
        sim_taken = msg.get("taken")
        if not isinstance(sim_taken, list) or len(sim_taken) > 32:
            return
        await send_side(room, m["side"], {
            "t": "sim", "board": sim_board, "taken": sim_taken,
            "by": m["id"], "color": m["color"], "label": m["label"]},
            skip=m["id"])
        return
    if t == "sim:clear":
        await send_side(room, m["side"],
                        {"t": "sim:clear", "by": m["id"]}, skip=m["id"])
        return
    if t == "flip":                                 # 定色阶段：原地翻开己方將位
        if not st or st.get("phase") != "opening":
            await send(m["ws"], {"t": "err", "msg": "现在不是定色阶段"})
            return
        if room.get("proposal"):
            await send(m["ws"], {"t": "err", "msg": "已有待表决的操作"})
            return
        gr, gc = R.GEN_SQ[m["side"]]
        if not R.operable(st, m["side"], gr, gc):
            await send(m["ws"], {"t": "err", "msg": "还没轮到你翻牌"})
            return
        await propose(room, m, "flip")
        return
    if t == "start":                                 # 开始对局（双方一致同意）
        if room["state"] is not None:
            await send(m["ws"], {"t": "err", "msg": "已经开局了"})
            return
        c = counts(room)
        if not c["bottom"]["total"] or not c["top"]["total"]:
            await send(m["ws"], {"t": "err", "msg": "两个半场都要有人才能开始"})
            return
        if room.get("proposal"):
            await send(m["ws"], {"t": "err", "msg": "已有待表决的操作"})
            return
        await propose(room, m, "start")
        return

    if t in ("rematch", "reset"):                   # 回到选边等待厅（不再直接开新局）
        if room["state"] is None:
            await send(m["ws"], {"t": "err", "msg": "还没开局"})
            return
        if room.get("proposal"):
            await send(m["ws"], {"t": "err", "msg": "已有待表决的操作"})
            return
        await propose(room, m, t)
        return

    if t == "side":                                  # 开局前换边
        want = (msg.get("side") or "").lower()
        if want not in ("bottom", "top"):
            return
        if room["state"] is not None:
            await send(m["ws"], {"t": "err", "msg": "已开局，换边请先退出房间"})
            return
        if want == m["side"]:
            await broadcast_roster(room)
            return
        if sum(1 for x in room["members"].values() if x["side"] == want) >= SIDE_MAX:
            await send(m["ws"], {"t": "err", "msg": "那一半场人已满"})
            return
        m["side"] = want
        await broadcast_roster(room)
        return

    if t == "agree":
        await vote(room, m, True)
        return
    if t == "decline":
        await vote(room, m, False)
        return

    if st is None:
        await send(m["ws"], {"t": "err", "msg": "等两个半场都有人后再走"})
        return
    if st.get("phase") == "opening":
        await send(m["ws"], {"t": "err", "msg": "定色阶段：请先翻开你这一边的將位"})
        return

    my_turn = R.seat_color(st, m["side"]) == st["turn"]

    if t in ("sel", "move") and not my_turn:
        await send(m["ws"], {"t": "err", "msg": "还没轮到你这一边"})
        return

    if t == "sel":
        r, c = msg.get("r"), msg.get("c")
        if not isinstance(r, int) or not isinstance(c, int):
            return
        moves = R.select_moves(st, m["side"], r, c)
        if moves is None:
            await send(m["ws"], {"t": "err", "msg": "这枚子你现在动不了"})
            return
        await send(m["ws"], {"t": "moves", "r": r, "c": c,
                             "moves": [[a, b] for a, b in moves]})

    elif t == "move":
        vals = [msg.get(k) for k in ("fr", "fc", "tr", "tc")]
        if not all(isinstance(v, int) for v in vals):
            return
        fr, fc, tr, tc = vals
        moves = R.select_moves(st, m["side"], fr, fc)
        if moves is None or (tr, tc) not in moves:
            await send(m["ws"], {"t": "err", "msg": "这步走不了"})
            return
        if room.get("proposal"):
            await send(m["ws"], {"t": "err", "msg": "已有待表决的操作"})
            return
        await propose(room, m, "move", fr=fr, fc=fc, tr=tr, tc=tc)

    elif t == "draw":
        if st.get("phase") != "play" or st["over"] or room.get("proposal"):
            return
        await propose(room, m, "draw")

    elif t == "rematch":
        if room.get("proposal"):
            return
        await propose(room, m, "rematch")

    elif t == "leave":
        member = room["members"].pop(m["id"], None)
        if member:
            p = room.get("proposal")
            if p:
                p["agree"].discard(m["id"])
                if p["by"] == m["id"]:
                    room["proposal"] = None
                    await broadcast(room, {"t": "proposal", "p": None})
                else:
                    await try_finish(room)
            ws_old = member["ws"]
            member["ws"] = None
            member["online"] = False
            await send_side(room, member["side"],
                            {"t": "sim:clear", "by": member["id"]})
            await broadcast_roster(room)
            if ws_old:
                try:
                    await ws_old.close(code=4007)
                except Exception:
                    pass


# ------------------------------------------------------------------ 回收

async def cleaner():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        for code in list(rooms):
            room = rooms.get(code)
            if not room:
                continue
            if now - room["touched"] > ROOM_TTL:
                for m in room["members"].values():
                    if m["ws"]:
                        try:
                            await m["ws"].close(code=4005)
                        except Exception:
                            pass
                del rooms[code]


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(cleaner())


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info",
                ws_ping_interval=25, ws_ping_timeout=20)
