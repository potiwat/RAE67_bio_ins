"""Supervised Normal startup and bounded ID1 gaze; never auto release torque."""
import math
from pathlib import Path
import sys
import time
from write_ack import receive_write_ack


def manual_trial_degrees(limb_range_deg=3,loaded_probe_deg=None):
    if type(limb_range_deg)is not int or limb_range_deg not in (3,6):
        raise ValueError('Unreviewed manual limb range')
    if loaded_probe_deg is not None and (type(loaded_probe_deg)is not int or loaded_probe_deg!=3 or limb_range_deg!=6):
        raise ValueError('Unreviewed loaded joint probe range')
    return {1:3,2:loaded_probe_deg or limb_range_deg,3:loaded_probe_deg or limb_range_deg,4:limb_range_deg,5:6}


def speed_write_allowed(sid,address,value,manual_tuning=False,motion_speed=1):
    if type(value)is not int or sid not in range(1,6):return False
    if address==41:return value in ((1,3) if sid==1 else (1,))
    if address!=46:return False
    allowed=(range(1,101) if manual_tuning else (1,3,4)) if sid==1 else (1,)
    return value in allowed or (motion_speed in (100,200,400,600) and value==motion_speed)


def happy_extra_acceleration_allowed(sid,address,value,enabled):
    return (enabled is True and address==41 and type(value)is int
            and (sid,value) in ((4,6),(5,3)))


def decode_state(sid,block):
    if len(block) not in (34,38):raise ValueError('Incomplete RAM33..66/70 feedback')
    row=dict(id=sid,sampled_monotonic_s=time.monotonic(),mode=block[0],
                goal_raw=int.from_bytes(block[9:11],'little'),target_speed_raw=int.from_bytes(block[13:15],'little'),acceleration_raw=block[8],
                torque_raw=block[7],position_raw=int.from_bytes(block[23:25],'little'),
                speed_raw=int.from_bytes(block[25:27],'little'),
                load_raw=int.from_bytes(block[27:29],'little'),voltage_V=block[29]/10,
                temperature_C=block[30],status_raw=block[32],moving_raw=block[33])
    if len(block)==38:
        row.update(internal_target_raw=int.from_bytes(block[34:36],'little'),
                   current_raw=int.from_bytes(block[36:38],'little'))
    return row


def open_bus():
    root=Path(__file__).resolve().parents[2]
    parser_path=root/'calibration_readonly'
    if not parser_path.is_dir():parser_path=root.parent/'calibration_readonly'
    sys.path.insert(0,str(parser_path))
    from read_only_bus import ReadOnlyBus, READS

    class Bus(ReadOnlyBus):
        def __init__(self):
            super().__init__();self.windows={};self.armed=set();self.manual_tuning=False;self.group_pid_trial=False;self.tuning_id=1
            try:
                if any(self.read(i,8,1)!=b'\1' for i in range(1,6)):
                    raise RuntimeError('Expected response level1; inspect configuration without changing EEPROM')
            except BaseException:self.close();raise
        def read(self,sid,address,count):
            if sid not in range(1,6) or (address,count) not in READS|{(8,1),(18,1),(21,3),(55,1),(41,1),(42,2),(46,2),(64,1),(33,34),(33,38)}:
                raise ValueError('Read denied')
            body=bytes([sid,4,2,address,count])
            return self._read_response(b'\xff\xff'+body+bytes([~sum(body)&255]),sid,count)
        def snapshot(self):
            count=38 if getattr(self,'extended_feedback_diagnostic',False) else 34
            return [decode_state(sid,self.read(sid,33,count)) for sid in range(1,6)]
        def write(self,sid,address,data):
            value=int.from_bytes(data,'little')
            if sid not in range(1,6):raise ValueError('Unicast only')
            if address==42:
                if len(data)!=2 or sid not in self.windows or not self.windows[sid][0]<=value<=self.windows[sid][1]:
                    raise ValueError('Goal outside reviewed window')
            elif address in (41,46):
                sleepy_speed=(sid==5 and address==46 and value==25 and getattr(self,'sleepy_trial',False))
                sleepy_fold_speed=(sid==3 and address==46 and value==9 and getattr(self,'sleepy_native_fold_trial',False))
                interested_speed=(sid==4 and address==46 and value==75 and getattr(self,'interested_trial',False))
                button_speed=(address==46 and value in (1000,1250) and getattr(self,'button_look_speed_trial',False))
                button_return_speed=(address==46 and value in (750,1000) and getattr(self,'button_look_return_trial',False))
                yaw_speed=(sid==1 and address==46 and value in (400,600) and getattr(self,'yaw_speed400_trial',False))
                happy_speed=(address==46 and ((value==750 and getattr(self,'happy_speed750_trial',False)) or (value==1000 and getattr(self,'happy_speed1000_trial',False))))
                happy_acc=(sid in (2,3) and address==41 and value==3 and getattr(self,'happy_body_acc3_trial',False))
                happy_extra_acc=happy_extra_acceleration_allowed(sid,address,value,getattr(self,'happy_fast_acceleration_trial',False))
                dance_acc=(address==41 and getattr(self,'happy_dynamic_trial',False) is True and (sid,value) in ((2,8),(3,8),(4,12),(5,6)))
                restore=getattr(self,'acceleration_restore',None)
                restore_acc=(address==41 and restore is not None
                             and getattr(restore,'restoring',None)==(sid,value)
                             and restore.pending.get(sid)==value and restore.stable.get(sid,0)>=3
                             and sid not in restore.pinned
                             and (sid,value) in ((1,3),(2,8),(3,8),(4,12),(5,6)))
                wide_dance_acc=(address==41 and getattr(self,'happy_wide_caps_trial',False) is True
                                and (sid,value) in ((1,8),(2,16),(3,16),(4,24),(5,6)))
                button_dynamic_acc=(address==41 and getattr(self,'button_look_dynamic_acceleration_trial',False) is True
                                    and (sid,value) in ((1,3),(2,8),(3,8),(4,12),(5,6)))
                awake_acc=(address==41 and getattr(self,'awake_dynamic_acceleration_trial',False) is True
                           and (sid,value) in ((1,3),(2,8),(3,8),(4,12),(5,6)))
                interested_acc=(sid in (2,3) and address==41 and value==3 and getattr(self,'interested_body_acc3_trial',False))
                gentle_entry=(address==46 and getattr(self,'interested_gentle_entry_trial',False) is True
                              and (sid,value) in ((2,150),(3,150),(4,100)))
                interested_native=(sid in (2,3) and address==46 and ((value==17 and getattr(self,'interested_native_body_trial',False)) or (value==25 and getattr(self,'presentation_angry_speed_trial',False) is True)))
                if len(data)!=(1 if address==41 else 2) or not (restore_acc or wide_dance_acc or awake_acc or button_dynamic_acc or dance_acc or happy_extra_acc or sleepy_fold_speed or gentle_entry or interested_native or interested_acc or happy_acc or happy_speed or yaw_speed or sleepy_speed or interested_speed or button_speed or button_return_speed or speed_write_allowed(sid,address,value,self.manual_tuning,getattr(self,'motion_speed',1))):
                    raise ValueError('Speed/acceleration outside approved trial')
            elif address==21:
                group_allowed=(self.group_pid_trial and bytes(data)==bytes((8,16,1)))
                if not ((self.manual_tuning and sid==self.tuning_id) or group_allowed) or len(data)!=3:
                    raise ValueError('PID trial disabled or wrong ID/length')
                from manual_tuning import validate_values
                validate_values(dict(p=data[0],d=data[1],i=data[2],speed=1),sid=1 if group_allowed else sid)
                if self.read(sid,55,1)!=b'\1':raise RuntimeError('Volatile lock1 required')
            elif address==40:
                if data!=b'\1' or sid not in self.armed:raise ValueError('Fresh hold required; no automatic release')
                actual=int.from_bytes(self.read(sid,56,8)[:2],'little')
                if abs(actual-int.from_bytes(self.read(sid,42,2),'little'))>2:raise RuntimeError('Hold shifted before enable')
            else:raise ValueError('RAM goal/speed/acceleration/enable only')
            restore=getattr(self,'acceleration_restore',None)
            if address==41 and restore is not None and restore.defer(sid,value):return
            body=bytes([sid,len(data)+3,3,address])+bytes(data)
            packet=b'\xff\xff'+body+bytes([~sum(body)&255])
            self.port.reset_input_buffer()
            if self.port.write(packet)!=len(packet):raise IOError('Partial servo WRITE transmission')
            self.port.flush()
            receive_write_ack(self.port,sid,packet)
            if self.read(sid,address,len(data))!=data:raise RuntimeError('Write readback mismatch')
        def sync_positions(self,goals,cancelled):
            # Opt-in position-only transport. No change to startup/PID/holds.
            from sync_position_writer import PositionSyncWriter
            if not hasattr(self,'position_sync_writer'):self.position_sync_writer=PositionSyncWriter()
            return self.position_sync_writer.commit(self,goals,cancelled)
        def hold_actual(self,sid):
            actual=int.from_bytes(self.read(sid,56,8)[:2],'little')
            if not 0<=actual<=4095:raise RuntimeError('Invalid hold actual')
            old=self.windows.get(sid)
            self.windows[sid]=(actual,actual)
            try:self.write(sid,42,actual.to_bytes(2,'little'))
            finally:
                if old is not None:self.windows[sid]=old
    return Bus()


class NormalGaze:
    def __init__(self, bus, origin, normal,tracking_speed=1,tracking_acceleration=1,yaw_range_deg=3,
                 manual_tuning=False,command_margin_ticks=0,pitch_probe=False,pitch_tracking=False,pitch_range_deg=3,manual_joints=False,limb_range_deg=3,loaded_probe_deg=None,motion_speed=1,normal_tolerances=None,pitch_up_deg=None):
        if normal_tolerances not in (None,{}, {3:34},{3:34,5:34},{2:34,3:34,5:34}):raise ValueError('Unreviewed Normal readiness tolerance')
        self.normal_tolerances={i:22 for i in range(1,6)}
        if normal_tolerances:self.normal_tolerances.update(normal_tolerances)
        if type(motion_speed)is not int or motion_speed not in (1,100,200,400,600):raise ValueError('Unreviewed all-joint speed trial')
        self.motion_speed=motion_speed
        manual_profile=(manual_tuning and type(tracking_speed)is int and (1<=tracking_speed<=100 or tracking_speed==motion_speed==200)
                        and tracking_acceleration==3 and (yaw_range_deg==10 or yaw_range_deg==20 and tracking_speed==motion_speed==200))
        manual_profile=manual_profile or (manual_tuning and type(tracking_speed)is int and (tracking_speed,tracking_acceleration,yaw_range_deg) in ((400,3,30),(600,3,30)) and motion_speed in (200,400,600))
        if not manual_profile and (tracking_speed,tracking_acceleration,yaw_range_deg) not in ((1,1,3),(3,3,10),(4,3,10)):
            raise ValueError('Unreviewed tracking trial limits')
        if type(command_margin_ticks)is not int or command_margin_ticks not in (0,13):
            raise ValueError('Unreviewed command margin')
        if type(pitch_range_deg)is not int or pitch_range_deg not in (3,6):raise ValueError('Unreviewed pitch range')
        self.manual_joints=manual_joints is True
        self.active_joint_id=5;self.pending_joint=None;self.joint_stable=0
        self.pitch_ticks=round(pitch_range_deg*4096/360)
        self.pitch_probe_enabled=pitch_probe is True
        self.pitch_tracking_enabled=pitch_tracking is True
        if self.pitch_tracking_enabled and not self.pitch_probe_enabled:raise ValueError('Pitch probe approval required')
        self.last_pitch_goal=None
        self.command_margin_ticks=command_margin_ticks
        if set(origin)!=set(range(1,6)) or set(normal)!=set(origin):raise ValueError('Five joints required')
        if any(type(v)is not int or not 0<=v<=4095 for v in (*origin.values(),*normal.values())):
            raise ValueError('Invalid raw pose')
        self.bus=bus;self.origin=dict(origin);self.normal=dict(normal)
        self.state='IDLE';self.enabled=set();self.stable=0;self.direction=None
        self.tracking_speed=tracking_speed;self.tracking_acceleration=tracking_acceleration
        self.yaw_range_deg=yaw_range_deg;self.yaw_ticks=round(yaw_range_deg*4096/360)
        self.yaw_window=(normal[1]-self.yaw_ticks,normal[1]+self.yaw_ticks)
        if pitch_up_deg is not None and (type(pitch_up_deg)is not int or pitch_up_deg!=30 or pitch_range_deg!=6):raise ValueError('Unreviewed asymmetric pitch range')
        self.pitch_window=(normal[5]-round((pitch_up_deg or pitch_range_deg)*4096/360),normal[5]+self.pitch_ticks)
        self.joint_degrees=manual_trial_degrees(limb_range_deg)
        self.joint_ticks={i:round(deg*4096/360) for i,deg in self.joint_degrees.items()}
        self.joint_windows={i:(normal[i]-self.joint_ticks[i],normal[i]+self.joint_ticks[i]) for i in normal}
        self.joint_probe_ticks={i:round(deg*4096/360) for i,deg in manual_trial_degrees(limb_range_deg,loaded_probe_deg).items()}
        self.last_joint_targets=dict(normal)
        self.last_goal=None;self.last_error=''
        self.windows={i:(min(origin[i],normal[i])-22,max(origin[i],normal[i])+22) for i in normal}
        self.last_rows=[];self.started=None;self.last_tick=None
    def start(self,now,hold_only=False,pre_motion_check=None):
        if hold_only and not self.manual_joints:raise ValueError('Hold-only connect is manual mode only')
        if not isinstance(now,(int,float)) or not math.isfinite(now) or now<0:raise ValueError('Invalid start clock')
        if self.state!='IDLE':raise RuntimeError('Already started')
        rows=self.bus.snapshot()
        if [r['id'] for r in rows]!=list(range(1,6)):raise RuntimeError('Incomplete snapshot')
        for r in rows:
            i=r['id']
            if r['mode'] or r['status_raw'] or r['moving_raw'] or r['speed_raw'] or abs(r['position_raw']-self.origin[i])>2:
                raise RuntimeError('Live start differs; inspect current pose')
            if r['torque_raw'] not in (0,1):raise RuntimeError('Unknown torque')
            if self.bus.read(i,18,1)!=b'\x0c' or self.bus.read(i,64,1)!=b'\0':raise RuntimeError('Phase/pending differs')
            if r['torque_raw'] and abs(int.from_bytes(self.bus.read(i,42,2),'little')-r['position_raw'])>self.normal_tolerances[i]:
                raise RuntimeError('Active goal is not nearby hold')
        self.bus.windows=dict(self.windows)
        torques={r['torque_raw'] for r in rows}
        if len(torques)!=1:raise RuntimeError('Mixed torque state; inspect before starting')
        if torques=={1}:
            # Already holding: rebasing a loaded joint to encoder position can
            # change its equilibrium. Preserve active holds; never re-enable.
            for i in self.normal:
                limits=(int.from_bytes(self.bus.read(i,46,2),'little'),self.bus.read(i,41,1)[0])
                allowed={(1,1),(self.motion_speed,1)}|({(self.tracking_speed,self.tracking_acceleration)} if i==1 else set())
                if i==1 and getattr(self.bus,'manual_tuning',False):allowed|={(s,3) for s in range(1,101)}
                if limits not in allowed:
                    raise RuntimeError('Active hold speed/acceleration differs from approved values')
            fresh=self.bus.snapshot()
            if [r['id'] for r in fresh]!=list(range(1,6)) or any(
                    abs(r['position_raw']-self.origin[r['id']])>2 or r['status_raw']
                    or r['mode'] or r['torque_raw']!=1 or r['moving_raw'] or r['speed_raw'] for r in fresh):
                raise RuntimeError('Active hold not stationary; inspect before resume')
            self.enabled=set(self.normal)
            try:
                for i in self.normal:
                    if int.from_bytes(self.bus.read(i,46,2),'little')!=self.motion_speed or self.bus.read(i,41,1)!=b'\1':
                        self.bus.write(i,46,self.motion_speed.to_bytes(2,'little'));self.bus.write(i,41,b'\1')
                if not hold_only:
                    for i in self.normal:
                        if pre_motion_check is not None:pre_motion_check()
                        self.bus.write(i,42,self.normal[i].to_bytes(2,'little'))
                self.state='STOPPED' if hold_only else 'NORMAL_STARTUP';self.started=now;self.last_tick=now
                self.last_goal=int.from_bytes(self.bus.read(1,42,2),'little') if hold_only else self.normal[1]
                return
            except BaseException:
                self.hold('resume failed',all_axes=True);self.state='FAULT';raise
        try:
            # Mark possibly active BEFORE any write; firmware may enable on goal.
            for i in self.normal:
                if pre_motion_check is not None:pre_motion_check()
                self.enabled.add(i)
                self.bus.write(i,42,self.origin[i].to_bytes(2,'little'))
                self.bus.write(i,46,self.motion_speed.to_bytes(2,'little'));self.bus.write(i,41,b'\1')
            fresh=self.bus.snapshot()
            if any(abs(r['position_raw']-self.origin[r['id']])>2 or r['status_raw'] for r in fresh):
                raise RuntimeError('Pose moved during arming')
            for i in self.normal:
                if pre_motion_check is not None:pre_motion_check()
                if hasattr(self.bus,'armed'):self.bus.armed.add(i)
                self.bus.write(i,40,b'\1')
            target=self.origin if hold_only else self.normal
            for i in self.normal:
                if pre_motion_check is not None:pre_motion_check()
                self.bus.write(i,42,target[i].to_bytes(2,'little'))
            self.state='STOPPED' if hold_only else 'NORMAL_STARTUP';self.started=now;self.last_tick=now;self.last_goal=target[1]
        except BaseException:
            self.hold('startup failed',all_axes=True);self.state='FAULT';raise
    def feedback_window(self,i):
        low,high=(self.yaw_window if i==1 and self.state!='NORMAL_STARTUP' else self.windows[i])
        if i!=1:
            # Readiness and the subsequent Normal feedback check must agree.
            # This changes measurement tolerance only, not command windows.
            low=min(low,self.normal[i]-self.normal_tolerances[i])
            high=max(high,self.normal[i]+self.normal_tolerances[i])
        allowance=6 if i==1 and self.state!='NORMAL_STARTUP' else 0
        if i in getattr(self,'behavior_joint_windows',{}) and self.state!='NORMAL_STARTUP':
            low,high=self.behavior_joint_windows[i];allowance=getattr(self,'behavior_joint_allowances',{}).get(i,6)
        if i==5 and self.pitch_probe_enabled and self.state!='NORMAL_STARTUP':
            low,high=getattr(self,'behavior_pitch_window',None) or self.active_pitch_window();allowance=6
        if self.manual_joints and i in self.joint_windows and self.state!='NORMAL_STARTUP':
            low,high=self.joint_windows[i];allowance=6
        if self.manual_joints and self.state=='STOPPED':low,high=self.windows[i];allowance=0
        if getattr(self,'pose_route_windows',None) is not None and self.state!='NORMAL_STARTUP':
            low,high=self.pose_route_windows[i];allowance=0
        return low-allowance,high+allowance

    def tick(self,now):
        if self.state in ('IDLE','FAULT') or (self.state=='STOPPED' and not self.manual_joints):return
        try:
            if not isinstance(now,(int,float)) or not math.isfinite(now) or now<self.last_tick:
                raise RuntimeError('Invalid/nonmonotonic control clock')
            self.last_tick=now
            self.last_rows=self.bus.snapshot()
            if [r['id'] for r in self.last_rows]!=list(range(1,6)):raise RuntimeError('Incomplete feedback')
            for r in self.last_rows:
                i=r['id'];low,high=self.feedback_window(i)
                if r['status_raw'] or r['mode'] or r['torque_raw']!=1 or not low<=r['position_raw']<=high:
                    raise RuntimeError(f"ID{i}: pos={r['position_raw']} allowed={low}..{high} status={r['status_raw']} mode={r['mode']} torque={r['torque_raw']}")
            restore=getattr(self.bus,'acceleration_restore',None)
            if restore is not None:restore.service(self.last_rows,self.bus.write)
            if getattr(self,'pose_route',None) is not None:self.pose_route.step(self.last_rows)
            for sid in list(getattr(self,'behavior_joint_returns',set())):
                row=next(r for r in self.last_rows if r['id']==sid)
                if abs(row['position_raw']-self.normal[sid])<=self.normal_tolerances[sid] and not row['speed_raw'] and not row['moving_raw']:
                    self.behavior_joint_windows.pop(sid,None);self.behavior_joint_returns.remove(sid)
                    getattr(self,'behavior_joint_allowances',{}).pop(sid,None)
                    self.bus.windows[sid]=self.windows[sid]
            if getattr(self,'sleepy_return_pending',False) and getattr(self,'pose_route_windows',None) is None:
                head=next(r for r in self.last_rows if r['id']==5)
                if self.pitch_window[0]<=head['position_raw']<=self.pitch_window[1] and not head['speed_raw'] and not head['moving_raw']:
                    self.behavior_pitch_window=None;self.sleepy_return_pending=False
                    self.bus.windows[5]=self.pitch_window
            if self.state=='NORMAL_STARTUP':
                if now-self.started>120:raise RuntimeError('Normal startup exceeded prior 120s limit')
                ready=all(abs(r['position_raw']-self.normal[r['id']])<=self.normal_tolerances[r['id']] and not r['moving_raw'] and not r['speed_raw'] for r in self.last_rows)
                self.stable=self.stable+1 if ready else 0
                if self.stable>=3:
                    self.state='READY';self.bus.windows[1]=self.yaw_window
                    if self.manual_joints:self.bus.windows.update(self.joint_windows)
                    print('NORMAL_READY residual_raw', {r['id']:r['position_raw']-self.normal[r['id']] for r in self.last_rows},flush=True)
            if self.manual_joints and self.pending_joint is not None and self.state=='READY':
                r=next(r for r in self.last_rows if r['id']==self.pending_joint)
                stopped=not r['speed_raw'] and not r['moving_raw'] and abs(r['position_raw']-self.last_joint_targets[self.pending_joint])<=22
                self.joint_stable=self.joint_stable+1 if stopped else 0
                if self.joint_stable>=3:self.pending_joint=None
            sweep=getattr(self,'behavior_sweep',None)
            if sweep is not None and self.state=='READY':
                row=next(r for r in self.last_rows if r['id']==sweep['sid'])
                target=sweep['center']+sweep['direction']*sweep['offset']
                stopped=not row['speed_raw'] and not row['moving_raw'] and abs(row['position_raw']-target)<=self.normal_tolerances[sweep['sid']]
                sweep['stable']=sweep['stable']+1 if stopped else 0
                if sweep['stable']>=3:
                    sweep['direction']*=-1;sweep['stable']=0
                    self.bus.write(sweep['sid'],42,(sweep['center']+sweep['direction']*sweep['offset']).to_bytes(2,'little'))
        except Exception as e:
            self.hold(str(e),all_axes=True);self.state='FAULT'
    def resume_normal(self,now):
        if not self.manual_joints or self.state!='STOPPED':raise RuntimeError('Pause manual startup before retry')
        rows=self.bus.snapshot()
        if [r['id'] for r in rows]!=list(range(1,6)) or any(
                r['mode'] or r['status_raw'] or r['torque_raw']!=1 or r['speed_raw'] or r['moving_raw'] for r in rows):
            raise RuntimeError('Retry Normal requires healthy stationary supported joints')
        self.origin={r['id']:r['position_raw'] for r in rows}
        self.windows={i:(min(self.origin[i],self.normal[i])-22,max(self.origin[i],self.normal[i])+22) for i in self.normal}
        self.stable=0;self.state='IDLE';self.start(now)

    def set_direction(self,sign):
        if type(sign)is not int or sign not in (-1,1):raise ValueError('Direction must be -1 or +1')
        self.direction=sign
    def active_pitch_window(self):
        return getattr(self,'interest_pitch_window',None) or self.pitch_window
    def configure_tracking(self,yaw=True,pitch=True):
        if self.state not in ('READY','FOLLOWING'):raise RuntimeError('Normal must be ready first')
        try:
            if yaw:
                self.bus.write(1,46,self.tracking_speed.to_bytes(2,'little'))
                self.bus.write(1,41,bytes([self.tracking_acceleration]))
            if self.pitch_tracking_enabled and pitch:
                self.bus.windows[5]=self.active_pitch_window()
                self.bus.write(5,46,self.motion_speed.to_bytes(2,'little'));self.bus.write(5,41,b'\1')
        except BaseException:
            self.hold('tracking configuration failed',all_axes=True);self.state='FAULT';raise
    def goal_yaw(self,goal):
        if self.state not in ('READY','FOLLOWING'):return False
        if not self.yaw_window[0]<=goal<=self.yaw_window[1]:raise ValueError('Yaw outside trial')
        try:
            if goal!=self.last_goal:
                self.bus.write(1,42,goal.to_bytes(2,'little'));self.last_goal=goal
            return True
        except Exception as e:
            self.hold(str(e),all_axes=True);self.state='FAULT';return False
    def goal_pitch(self,goal):
        if not self.pitch_tracking_enabled or self.state not in ('READY','FOLLOWING'):return False
        if type(goal)is not int or not self.active_pitch_window()[0]<=goal<=self.active_pitch_window()[1]:
            raise ValueError('Pitch outside reviewed trial')
        try:
            self.bus.windows[5]=self.active_pitch_window()
            if goal!=self.last_pitch_goal:
                self.bus.write(5,42,goal.to_bytes(2,'little'));self.last_pitch_goal=goal
            return True
        except Exception as e:
            self.hold(str(e),all_axes=True);self.state='FAULT';return False

    def follow(self,error,now):
        if self.state not in ('READY','FOLLOWING') or self.direction is None:return False
        if not isinstance(error,(int,float)) or not math.isfinite(error) or not -1<=error<=1:
            self.hold('bad image error');return False
        if not isinstance(now,(int,float)) or not math.isfinite(now) or now<self.last_tick:
            self.hold('invalid follow clock',all_axes=True);self.state='FAULT';return False
        if not self.goal_yaw(self.normal[1]+round(34*self.direction*error)):return False
        self.state='FOLLOWING';return True
    def probe(self,positive=True):
        if self.state not in ('READY','FOLLOWING'):return
        try:
            if int.from_bytes(self.bus.read(1,46,2),'little')!=self.motion_speed:self.bus.write(1,46,self.motion_speed.to_bytes(2,'little'))
            if self.bus.read(1,41,1)!=b'\1':self.bus.write(1,41,b'\1')
            ticks=self.yaw_ticks-self.command_margin_ticks
            offset=ticks if positive is True else -ticks if positive=='negative' else 0
            if self.goal_yaw(self.normal[1]+offset):self.state='READY'
        except Exception as error:
            self.hold(str(error),all_axes=True);self.state='FAULT'
    def probe_joint(self,sid,direction):
        if type(sid)is not int or sid not in (1,2,3,4,5) or type(direction)is not int or direction not in (-1,0,1):
            raise ValueError('Manual joint1..5 and direction -1/0/1 only')
        if not self.manual_joints or self.state not in ('READY','FOLLOWING'):return False
        try:
            ticks=self.joint_probe_ticks[sid]
            self.bus.windows[sid]=self.joint_windows[sid]
            self.bus.write(sid,46,self.motion_speed.to_bytes(2,'little'));self.bus.write(sid,41,b'\1')
            goal=self.normal[sid]+direction*ticks
            self.bus.write(sid,42,goal.to_bytes(2,'little'));self.last_joint_targets[sid]=goal
            self.pending_joint=sid;self.joint_stable=0
            self.state='READY';return True
        except Exception as error:
            self.hold(str(error),all_axes=True);self.state='FAULT';return False

    def probe_pitch(self,positive=True):
        if not self.pitch_probe_enabled or self.state not in ('READY','FOLLOWING'):return False
        try:
            self.bus.windows[5]=self.pitch_window
            self.bus.write(5,46,self.motion_speed.to_bytes(2,'little'));self.bus.write(5,41,b'\1')
            goal=self.pitch_window[1] if positive is True else self.pitch_window[0] if positive=='negative' else self.normal[5]
            self.bus.write(5,42,goal.to_bytes(2,'little'))
            self.state='READY'
            return True
        except Exception as error:
            self.hold(str(error),all_axes=True);self.state='FAULT';return False

    def hold(self,reason,all_axes=False):
        self.behavior_sweep=None
        if getattr(self,'pose_route',None) is not None:self.pose_route.cancel()
        self.last_error=reason
        if self.manual_joints:self.pending_joint=None;self.joint_stable=0
        failed=False
        stationary_rows=None
        for i in sorted(self.enabled if all_axes or self.state=='NORMAL_STARTUP' else self.enabled&({1,self.active_joint_id} if self.manual_joints else {1,5} if self.pitch_tracking_enabled else {1})):
            try:
                if i!=1 and not (i==5 and self.pitch_tracking_enabled and not self.manual_joints) and self.state!='NORMAL_STARTUP':
                    if stationary_rows is None:
                        try:stationary_rows={r['id']:r for r in self.bus.snapshot()}
                        except Exception:stationary_rows={}
                    r=stationary_rows.get(i)
                    goal=int.from_bytes(self.bus.read(i,42,2),'little') if r is not None else None
                    low,high=self.feedback_window(i)
                    # A loaded joint can rest offset from its goal. Replacing
                    # that goal with encoder position repeatedly ratchets pose.
                    if (r is not None and not r['mode'] and not r['status_raw'] and r['torque_raw']==1
                            and not r['moving_raw'] and not r['speed_raw']
                            and low<=r['position_raw']<=high and low<=goal<=high
                            and abs(goal-r['position_raw'])<=self.normal_tolerances[i]):
                        continue
                if hasattr(self.bus,'hold_actual'):self.bus.hold_actual(i)
                else:
                    rows=self.bus.snapshot();p=next(r['position_raw'] for r in rows if r['id']==i)
                    self.bus.write(i,42,p.to_bytes(2,'little'))
                if i==1:self.last_goal=None
            except Exception as e:
                failed=True;self.last_error+=f'; ID{i} hold unconfirmed: {e}'
        if self.pitch_tracking_enabled:self.last_pitch_goal=None
        if failed:self.state='FAULT'
        elif self.state not in ('IDLE','NORMAL_STARTUP','FAULT','STOPPED'):self.state='READY'
        return not failed
