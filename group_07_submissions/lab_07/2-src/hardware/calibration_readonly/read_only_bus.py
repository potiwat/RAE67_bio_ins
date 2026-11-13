"""STS3215 read-only transport. No write/action/reset/broadcast interface."""
import time

IDS = (1, 2, 3, 4, 5)
READS = {(33, 1), (40, 1), (56, 8), (65, 2)}


def read_packet(sid, address, count):
    if sid not in IDS or (address, count) not in READS:
        raise ValueError('Only approved single-ID READ requests are allowed')
    body = bytes((sid, 4, 2, address, count))
    return b'\xff\xff' + body + bytes(((~sum(body)) & 255,))


class ReadOnlyBus:
    def __init__(self, device='/dev/ttyAMA0'):
        import serial
        self.port = serial.Serial(port=None, baudrate=1000000, timeout=.03,
                                  write_timeout=.3, exclusive=True)
        self.port.dtr = False
        self.port.rts = False
        self.port.port = device
        self.port.open()

    def close(self):
        self.port.close()

    def read(self, sid, address, count):
        packet = read_packet(sid, address, count)
        return self._read_response(packet, sid, count)

    def _read_response(self, packet, sid, count):
        if packet[4] != 2:
            raise ValueError('Read transport only accepts READ packets')
        self.port.reset_input_buffer()
        self.port.write(packet)
        self.port.flush()
        end, data = time.monotonic() + .3, bytearray()
        while time.monotonic() < end:
            data.extend(self.port.read(self.port.in_waiting or 1))
            while len(data) >= 4:
                start = data.find(b'\xff\xff')
                if start < 0:
                    data[:] = data[-1:]
                    break
                if start:
                    del data[:start]
                if len(data) < 4:
                    break
                length = data[3]
                if not 2 <= length <= 80:
                    del data[0]
                    continue
                if len(data) < length + 4:
                    break
                frame = bytes(data[:length + 4])
                del data[:length + 4]
                if frame == packet:
                    continue
                if frame[2] != sid or length != count + 2 or sum(frame[2:]) & 255 != 255:
                    continue
                if frame[4]:
                    raise RuntimeError(f'ID{sid} response error={frame[4]}')
                return frame[5:-1]
        raise TimeoutError(f'ID{sid} read address {packet[5]}: no valid reply')

    def snapshot(self):
        rows = []
        for sid in IDS:
            mode = self.read(sid, 33, 1)[0]
            torque = self.read(sid, 40, 1)[0]
            data = self.read(sid, 56, 8)
            state = self.read(sid, 65, 2)
            rows.append(dict(id=sid, sampled_monotonic_s=time.monotonic(),
                             position_raw=int.from_bytes(data[:2], 'little'),
                             speed_raw=int.from_bytes(data[2:4], 'little'),
                             load_raw=int.from_bytes(data[4:6], 'little'),
                             voltage_V=data[6]/10, temperature_C=data[7],
                             mode=mode, torque_raw=torque, status_raw=state[0], moving_raw=state[1]))
        return rows


def record_blockers(rows, previous=None):
    reasons = []
    if [r['id'] for r in rows] != list(IDS):
        return ['Incomplete five-servo snapshot']
    for row in rows:
        sid = row['id']
        if row['torque_raw'] != 0:
            reasons.append(f'ID{sid}: torque is not OFF; tool will not change it')
        if row['mode'] != 0:
            reasons.append(f'ID{sid}: mode is not position mode')
        if row['status_raw'] != 0:
            reasons.append(f'ID{sid}: status error {row["status_raw"]}')
        if not 0 <= row['position_raw'] <= 4095:
            reasons.append(f'ID{sid}: outside single-turn encoder range')
        if previous and abs(row['position_raw'] - previous[sid]) > 2048:
            reasons.append(f'ID{sid}: encoder wrap/large discontinuity; restart recording session')
    return reasons
