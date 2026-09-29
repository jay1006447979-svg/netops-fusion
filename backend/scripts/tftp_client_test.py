"""TFTP 客户端测试脚本 — 验证内置 TFTP 服务器的读写与安全

按 RFC 1350: ACK/DATA 必须发回收到数据包的源地址(传输端口), 而非 69 端口。
"""

import socket
import struct

SERVER = ("127.0.0.1", 6969)


def tftp_read(filename):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3)
    req = struct.pack("!H", 1) + filename.encode() + b"\x00octet\x00"
    s.sendto(req, SERVER)
    data = b""
    block = 0
    peer = SERVER
    while True:
        pkt, peer = s.recvfrom(4096)
        op, b = struct.unpack("!HH", pkt[:4])
        if op == 5:
            return False, "ERROR: " + pkt[4:-1].decode(errors="replace")
        if op == 3 and b == block + 1:
            data += pkt[4:]
            block = b
            s.sendto(struct.pack("!HH", 4, block), peer)  # 回传输端口
            if len(pkt[4:]) < 512:
                return True, data.decode()
        elif op == 3:
            s.sendto(struct.pack("!HH", 4, b), peer)


def tftp_write(filename, content):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3)
    req = struct.pack("!H", 2) + filename.encode() + b"\x00octet\x00"
    s.sendto(req, SERVER)
    pkt, peer = s.recvfrom(1024)
    op, b = struct.unpack("!HH", pkt[:4])
    if op == 5:
        return False, "ERROR: " + pkt[4:-1].decode(errors="replace")
    if op != 4 or b != 0:
        return False, "no ack0"
    payload = content.encode()
    pos = 0
    block = 0
    while True:
        block += 1
        chunk = payload[pos:pos + 512]
        pos += 512
        s.sendto(struct.pack("!HH", 3, block) + chunk, peer)  # 回传输端口
        pkt, _ = s.recvfrom(1024)
        op, b = struct.unpack("!HH", pkt[:4])
        if op == 5:
            return False, "ERROR: " + pkt[4:-1].decode(errors="replace")
        if op != 4 or b != block:
            return False, "bad ack"
        if len(chunk) < 512:
            return True, "uploaded %d bytes" % len(payload)


if __name__ == "__main__":
    ok, msg = tftp_read("TEST-SW1/TEST-SW1_20260914_210000.cfg")
    print("TFTP 读备份文件:", "OK" if ok else "FAIL", "|", msg[:60].replace("\n", " "))

    ok, msg = tftp_write("device_upload_test.cfg", "upload from device test")
    print("TFTP 写入 uploads:", "OK" if ok else "FAIL", "|", msg)

    ok, msg = tftp_read("../app/main.py")
    print("TFTP 越界读取被拒:", "OK(已拒绝)" if not ok else "FAIL(越界!)", "|", msg[:40])

    ok, msg = tftp_read("不存在.cfg")
    print("TFTP 读不存在文件:", "OK(返回错误)" if not ok else "FAIL", "|", msg[:40])

    ok, msg = tftp_read("../secrets.txt")
    print("TFTP 上传目录限制:", "OK(仅限uploads)" if not ok else "FAIL", "|", msg[:40])
