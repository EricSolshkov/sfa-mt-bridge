"""sing-box BPF v1 -> QRS binary metadata -> zlib -> systematic LT frames.

Wire formats verified against SagerNet Apple BinaryMeta/EncodedBlock and
sing-box experimental/libbox/profile_import.go. No networking is involved.
Degree-one LT blocks are intentionally cycled: each missed block is recoverable
on the next cycle, and frame density stays constant.
"""
import base64
import gzip
import json
import struct
import zlib


def uvarint(value):
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def string(value):
    raw = value.encode('utf-8')
    return uvarint(len(raw)) + raw


def profile_bytes(config, name):
    # MessageTypeProfileContent=3, version=1, ProfileTypeLocal=int32(0).
    content = string(name) + struct.pack('>i', 0) + string(config)
    return b'\x03\x01' + gzip.compress(content, mtime=0)


def wrap_profile(config, name):
    data = profile_bytes(config, name)
    meta = json.dumps({'filename': 'MT.bpf', 'contentType': 'application/octet-stream'},
                      separators=(',', ':')).encode('utf-8')
    return struct.pack('>I', len(meta)) + meta + struct.pack('>I', len(data)) + data


def frames(config, name, slice_size=350):
    if not name.strip() or len(name.encode('utf-8')) > 200:
        raise ValueError('配置名称不能为空，且不能超过 200 UTF-8 字节')
    if not 100 <= slice_size <= 800:
        raise ValueError('无效二维码分片大小')
    wrapped = wrap_profile(config, name)
    compressed = zlib.compress(wrapped)
    k = (len(compressed) + slice_size - 1) // slice_size
    if k > 1500:
        raise ValueError('配置过大，不适合屏幕扫码传输')
    checksum = zlib.crc32(wrapped) ^ k
    result = []
    for index in range(k):
        block = compressed[index*slice_size:(index+1)*slice_size].ljust(slice_size, b'\x00')
        header = struct.pack('<IIIII', 1, index, k, len(compressed), checksum)
        result.append('https://qrss.netlify.app/#' + base64.b64encode(header + block).decode('ascii'))
    return result
