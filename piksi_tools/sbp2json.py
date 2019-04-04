#!/usr/bin/env python2

import os

import sys

import io

import numpy as np
import json

from sbp.jit import msg
from sbp.jit.table import dispatch

from sbp import msg as msg_nojit
from sbp.table import dispatch as dispatch_nojit

NORM = os.environ.get('NOJIT') is not None


class SbpJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.float32) or isinstance(obj, np.float64):
            ret = float(repr(obj))
            if ret.is_integer():
                ret = int(ret)
            return ret
        elif isinstance(obj, bytes):
            return obj.decode('ascii')
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


def main():
    header_len = 6
    reader = io.open(sys.stdin.fileno(), 'rb')
    buf = np.zeros(4096, dtype=np.uint8)
    unconsumed_offset = 0
    read_offset = 0
    buffer_remaining = len(buf)
    while True:
        if buffer_remaining == 0:
            memoryview(buf)[0:(read_offset - unconsumed_offset)] = \
                memoryview(buf)[unconsumed_offset:read_offset]
            read_offset = read_offset - unconsumed_offset
            unconsumed_offset = 0
            buffer_remaining = len(buf) - read_offset
        mv = memoryview(buf)[read_offset:]
        read_length = reader.readinto(mv)
        if read_length == 0:
            unconsumed = read_offset - unconsumed_offset
            if unconsumed != 0:
                sys.stderr.write("unconsumed: {}\n".format(unconsumed))
                sys.stderr.flush()
            break
        read_offset += read_length
        buffer_remaining -= read_length
        while True:
            if NORM:
                from construct.core import StreamError
                bytes_available = read_offset - unconsumed_offset
                b = buf[unconsumed_offset:(unconsumed_offset + bytes_available)]
                try:
                    m = msg_nojit.SBP.unpack(b)
                except StreamError:
                    break
                m = dispatch_nojit(m)
                sys.stdout.write(json.dumps(m.to_json_dict(),
                                            allow_nan=False,
                                            sort_keys=True,
                                            separators=(',', ':')))
                consumed = header_len + m.length + 2
            else:
                consumed, payload_len, msg_type, sender, crc, crc_fail = \
                    msg.SBP.unpack_payload(buf, unconsumed_offset, (read_offset - unconsumed_offset))

                if not crc_fail and msg_type != 0:
                    payload = buf[unconsumed_offset + header_len:unconsumed_offset + header_len + payload_len]
                    m = dispatch(msg_type)(msg_type, sender, payload_len, payload, crc)
                    res, offset, length = m.unpack(buf, unconsumed_offset + header_len, payload_len)
                    sys.stdout.write(json.dumps(res,
                                                allow_nan=False,
                                                sort_keys=True,
                                                separators=(',', ':'),
                                                cls=SbpJSONEncoder))
                    sys.stdout.write("\n")

                if consumed == 0:
                    break
            unconsumed_offset += consumed


if __name__ == '__main__':
    main()
