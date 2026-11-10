"""Opt-in STS position-only Sync Write for the small Happy trial.

Protocol: https://ftservo.github.io/ftservo-wiki/reference/protocol/ft-scs/
Broadcast0xFE, instruction0x83. Fixed address42/width2/IDs1,2,3;
separate taught-Happy opt-in permits ID4 in the same frame.
No broadcast ACK exists: every goal is read back via existing guarded READ.
Not evidence of measured physical synchronization. No PID/EEPROM interface.
"""
import time

class SyncPositionError(RuntimeError):
    def __init__(self,report):
        self.report=report;super().__init__(report['error'])

def position_packet(goals,allow_roll=False):
    if (type(allow_roll)is not bool or type(goals)is not dict
            or set(goals) not in (({1,2,3},{1,2,3,4}) if allow_roll else ({1,2,3},))
            or any(type(i)is not int or type(q)is not int or not 0<=q<=4095 for i,q in goals.items())):
        raise ValueError('Only explicit integer position goals for IDs1/2/3 allowed')
    params=bytes([42,2])+b''.join(bytes([i])+goals[i].to_bytes(2,'little') for i in sorted(goals))
    body=bytes([254,len(params)+2,131])+params
    return b'\xff\xff'+body+bytes([~sum(body)&255])

class PositionSyncWriter:
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.blocked=False;self.last_report=None
    def commit(self,bus,goals,cancelled):
        if self.blocked:raise SyncPositionError(dict(error='Sync position blocked; explicit M/new owner recovery required',requires_hold=True))
        goals=dict(goals);packet=position_packet(goals,allow_roll=getattr(bus,'sync_roll_position_trial',False) is True)
        if getattr(bus,'sync_position_trial',False) is not True:
            raise ValueError('Sync position trial not explicitly enabled')
        for i,q in goals.items():
            low,high=bus.windows[i]
            if not 0<=low<=q<=high<=4095:raise ValueError('Sync goal outside existing command window')
        report=dict(status='pending',requested_goals=goals,verified_ids=[],broadcast_sent=False,
                    sent_monotonic_s=None,readback_monotonic_s={},requires_hold=False)
        try:
            if cancelled():raise RuntimeError('Cancelled before Sync Write')
            bus.port.reset_input_buffer()
            report['sent_monotonic_s']=self.clock()
            if cancelled():raise RuntimeError('Cancelled during Sync Write preparation')
            count=bus.port.write(packet)
            report['broadcast_sent']=count>0
            if count!=len(packet):raise IOError('Partial Sync Write transmission; goals uncertain')
            bus.port.flush()
            for i in sorted(goals):
                if cancelled():raise RuntimeError('Cancelled after Sync Write; confirmation incomplete')
                value=bus.read(i,42,2)
                if value!=goals[i].to_bytes(2,'little'):raise RuntimeError(f'ID{i} Sync position readback mismatch')
                report['verified_ids'].append(i);report['readback_monotonic_s'][i]=self.clock()
            report['status']='goal_readback_verified';self.last_report=report
            return report
        except Exception as error:
            self.blocked=True
            report.update(status='failed',requires_hold=True,error=str(error))
            self.last_report=report
            raise SyncPositionError(report) from error
