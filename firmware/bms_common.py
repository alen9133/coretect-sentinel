"""
CORETECT Sentinel — BMS 公共工具库
CRC-16/Modbus + 帧构建/解析工具
适用于 HaaS506-ED1 (ESP32-S3) MicroPython
"""

import struct


# ─── CRC-16 / Modbus ──────────────────────────────────────────────────────────

def crc16(data: bytes) -> int:
    """计算 Modbus CRC-16，返回整数（低字节在低位）"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def append_crc(frame: bytearray) -> bytearray:
    """在帧末尾追加 CRC（低字节先），返回完整帧"""
    c = crc16(frame)
    frame.append(c & 0xFF)
    frame.append((c >> 8) & 0xFF)
    return frame


def verify_crc(frame: bytes) -> bool:
    """验证帧 CRC（最后两字节是 CRC-L / CRC-H）"""
    if len(frame) < 4:
        return False
    calc = crc16(frame[:-2])
    recv = frame[-2] | (frame[-1] << 8)
    return calc == recv


# ─── Modbus 请求帧构建 ─────────────────────────────────────────────────────────

def build_read_req(slave_addr: int, reg_start: int, reg_count: int) -> bytes:
    """构建 Modbus FC-03 读寄存器请求帧"""
    frame = bytearray([
        slave_addr,
        0x03,
        (reg_start >> 8) & 0xFF,
        reg_start & 0xFF,
        (reg_count >> 8) & 0xFF,
        reg_count & 0xFF,
    ])
    return bytes(append_crc(frame))


def build_write_single_req(slave_addr: int, reg_addr: int, value: int) -> bytes:
    """构建 Modbus FC-06 写单个寄存器请求帧"""
    frame = bytearray([
        slave_addr,
        0x06,
        (reg_addr >> 8) & 0xFF,
        reg_addr & 0xFF,
        (value >> 8) & 0xFF,
        value & 0xFF,
    ])
    return bytes(append_crc(frame))


def build_write_multi_req(slave_addr: int, reg_start: int, values: list) -> bytes:
    """
    构建 Modbus FC-10 (0x10) 写多个寄存器请求帧
    values: list of 16-bit integers
    """
    n = len(values)
    frame = bytearray([
        slave_addr,
        0x10,
        (reg_start >> 8) & 0xFF,
        reg_start & 0xFF,
        (n >> 8) & 0xFF,
        n & 0xFF,
        n * 2,  # byte count
    ])
    for v in values:
        frame.append((v >> 8) & 0xFF)
        frame.append(v & 0xFF)
    return bytes(append_crc(frame))


# ─── 响应帧解析 ───────────────────────────────────────────────────────────────

def parse_fc03_response(frame: bytes, slave_addr: int) -> bytes | None:
    """
    解析 FC-03 响应帧，返回数据字节（不含地址/功能码/字节数/CRC）
    失败返回 None
    """
    if not frame or len(frame) < 5:
        return None
    if not verify_crc(frame):
        return None
    if frame[0] != slave_addr:
        return None
    if frame[1] & 0x80:  # 从机返回了错误码
        return None
    if frame[1] != 0x03:
        return None
    data_len = frame[2]
    if len(frame) != data_len + 5:
        return None
    return frame[3: 3 + data_len]


# ─── 字节序解析工具 ───────────────────────────────────────────────────────────

def u16be(data: bytes, offset: int) -> int:
    """大端 unsigned 16-bit"""
    return (data[offset] << 8) | data[offset + 1]


def i16be(data: bytes, offset: int) -> int:
    """大端 signed 16-bit"""
    v = u16be(data, offset)
    return v - 0x10000 if v >= 0x8000 else v


def u32be(data: bytes, offset: int) -> int:
    """大端 unsigned 32-bit（Modbus 高字寄存器在前）"""
    return (data[offset] << 24) | (data[offset+1] << 16) | \
           (data[offset+2] << 8) | data[offset+3]


def i32be(data: bytes, offset: int) -> int:
    """大端 signed 32-bit"""
    v = u32be(data, offset)
    return v - 0x100000000 if v >= 0x80000000 else v
