"""Lamp camera tool: diagnostics, offline replay, or one live preview.

No UART/SPI/GPIO/servo imports, no image/video/log recording, no background jobs.
Haar settings and image sizes follow the retained official Picamera2 example.
"""
import argparse
from dataclasses import asdict, replace
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

from face_tracking import FaceTracker, finite_number, overlap
from roll_detection import detect_faces
from latest_worker import LatestWorker

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from bio_inspire.runtime.gaze_policy import gaze_intent


def operator_motor_start(motor, profile, factory):
    """Explicit M only: retire faulted UART owner before fresh live preflight."""
    if motor is not None:
        if not motor.fault_message() and motor.snapshot_view().get('state')!='STOPPED' and getattr(motor,'operator_stopped',False) is not True:return motor
        motor.disconnect_for_retry()
    return factory(profile,operator_start=True)


def boot_motor_start(profile,factory,park_only=False):
    """One explicit boot start; no automatic fault retry or guard bypass."""
    data=json.loads(Path(profile).read_text(encoding='utf-8-sig'))
    if (data.get('boot_auto_start_approved') is not True or data.get('automatic_fsm_enabled') is not True
            or data.get('normal_ahm_condition')!='C1' or data.get('ahm_scope')!='all_states'
            or data.get('lab07_recording_seconds') is not None or data.get('normal_measurement_source') is not None):
        raise ValueError('Boot needs dedicated approved live six-state profile')
    return factory(profile,operator_start=True,park_only=True) if park_only else factory(profile,operator_start=True)


def normalized_boxes(rectangles, width, height):
    if not all(finite_number(v) and v > 0 for v in (width, height)):
        raise ValueError('Invalid image dimensions')
    boxes = []
    for rect in rectangles:
        x, y, w, h = (float(v) for v in rect)
        if (not all(finite_number(v) for v in (x, y, w, h))
                or x < 0 or y < 0 or w <= 0 or h <= 0
                or x + w > width or y + h > height):
            raise ValueError('Detector returned an invalid rectangle')
        boxes.append((x / width, y / height, w / width, h / height))
    return boxes


class PreviewEngine:
    """State here is injected by preview/replay, not the actual emotion FSM."""
    def __init__(self, max_age_s):
        self.tracker = FaceTracker(max_age_s)
        self.previous_state = 'normal'
        self.preserving_player=False;self.recovery_until=None
        self._clear_candidate()

    def _clear_candidate(self):
        self.recovery_candidate=None;self.candidate_since=None
        self.candidate_last=None;self.candidate_count=0

    def _confirm_returned_player(self,observation,boxes,captured,processed):
        # Bounded post-glance geometric reacquisition, NOT face identity.
        # Preserve the ordinary overlap lock outside this explicit window.
        probe=FaceTracker(self.tracker.max_age_s).update(boxes,captured,processed)
        if probe.status in ('INVALID','STALE'):
            self._clear_candidate()
            return replace(observation,status=probe.status,box=None,error_xy=None)
        old=self.tracker.previous_box
        min_area=max(.015,0.45*old[2]*old[3] if old is not None else 0.)
        eligible=[tuple(b) for b in boxes if b[2]*b[3]>=min_area
                  and .05<=b[0]+b[2]/2<=.95 and .05<=b[1]+b[3]/2<=.95]
        if len(eligible)!=1:
            self._clear_candidate();return observation
        candidate,=eligible;prior=self.recovery_candidate
        stable=(prior is not None and self.candidate_last is not None
                and 0<captured-self.candidate_last<=.3
                and overlap(prior,candidate)>=.5*min(prior[2]*prior[3],candidate[2]*candidate[3])
                and .7<=candidate[2]*candidate[3]/(prior[2]*prior[3])<=1.4)
        if not stable:self.candidate_since=captured;self.candidate_count=0
        self.recovery_candidate=candidate;self.candidate_last=captured;self.candidate_count+=1
        if self.candidate_count<3 or captured-self.candidate_since<.15:return observation
        self.tracker.previous_box=candidate;self.recovery_until=None
        error=(2*(candidate[0]+candidate[2]/2)-1,2*(candidate[1]+candidate[3]/2)-1)
        return replace(observation,status='ACQUIRED',box=candidate,error_xy=error)

    def step(self, row):
        if not isinstance(row, dict):
            raise ValueError('Each replay row must be a JSON object')
        if any(type(row.get(key, False)) is not bool for key in ('reset', 'fault', 'preserve_player', 'acquisition_scan')):
            raise ValueError('reset/fault/preserve_player/acquisition_scan must be JSON booleans')
        if not all(key in row for key in ('boxes', 'captured_s', 'processed_s')):
            raise ValueError('Row requires boxes, captured_s and processed_s')
        state = row.get('state', self.previous_state)
        if state not in ('normal', 'interested', 'happy', 'afraid', 'sleepy'):
            raise ValueError('Unknown preview state')
        if row.get('reset', False) or (self.previous_state == 'sleepy' and state != 'sleepy'):
            self.tracker.reset();self.preserving_player=False;self.recovery_until=None;self._clear_candidate()
        self.previous_state = state
        preserve=row.get('preserve_player',False);now=row['processed_s']
        if preserve:
            self.preserving_player=True;self.recovery_until=None;self._clear_candidate()
        elif self.preserving_player:
            self.preserving_player=False;self.recovery_until=now+5. if finite_number(now) else None
        if row.get('acquisition_scan',False) and not preserve and finite_number(now):
            self.recovery_until=now+.5
        recovering=(self.recovery_until is not None and finite_number(now) and now<=self.recovery_until)
        # When there was no valid old player, do not instantly acquire a tiny
        # background detection on the first frame after looking away.
        suppress=preserve or recovering and self.tracker.previous_box is None
        observation=self.tracker.update([] if suppress else row['boxes'],row['captured_s'],now)
        if recovering and not row.get('fault',False):
            if observation.status in ('LOST','WAITING'):
                observation=self._confirm_returned_player(observation,row['boxes'],row['captured_s'],now)
            elif observation.status in ('TRACKING','ACQUIRED'):self.recovery_until=None;self._clear_candidate()
            else:self._clear_candidate()
        else:self._clear_candidate()
        intent = gaze_intent(observation, state, row.get('fault', False))
        return {'state': state, 'observation': asdict(observation), 'intent': asdict(intent)}


def replay_rows(rows, max_age_s):
    engine = PreviewEngine(max_age_s)
    for row in rows:
        yield engine.step(row)


def capture_configuration(fps):
    # IMX708 1536x864 high-speed mode crops the sensor; 2304x1296 uses full FOV.
    return dict(main={'size':(640,360)},
                lores={'size':(320,180),'format':'YUV420'},queue=True,
                sensor={'output_size':(2304,1296),'bit_depth':10},
                controls={'FrameRate':fps} if fps else {})


def configure_full_sensor_view(camera):
    """Explicit full sensor crop after configuration; never crop to a face box."""
    properties=getattr(camera,'camera_properties',{})
    controls=getattr(camera,'camera_controls',{})
    crop=controls.get('ScalerCrop')
    maximum=tuple(crop[1]) if crop else None
    if maximum and len(maximum)==4 and min(maximum[2:])>0:
        camera.set_controls({'ScalerCrop':maximum})
    return dict(model=properties.get('Model'),pixel_array_size=properties.get('PixelArraySize'),
                requested_scaler_crop=maximum)


def dependency_report():
    modules = {name: importlib.util.find_spec(name) is not None for name in ('cv2', 'picamera2')}
    return {'python': sys.executable, 'modules': modules,
            'display_available': bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')),
            'sensor_clock_available': hasattr(time, 'CLOCK_BOOTTIME'),
            'motor_output_enabled': False,
            'note': 'Module presence only; camera, cascade and display not opened/tested.'}


def find_cascade(cv2, explicit=None):
    if explicit is not None:
        candidates = [Path(explicit)]
    else:
        candidates = [Path('/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml')]
        data = getattr(cv2, 'data', None)
        if data is not None:
            candidates.append(Path(data.haarcascades) / 'haarcascade_frontalface_default.xml')
    for candidate in candidates:
        if candidate.is_file():
            classifier = cv2.CascadeClassifier(str(candidate))
            if not classifier.empty():
                return classifier
    raise RuntimeError('Face cascade missing/unreadable. Supply --cascade PATH; see CAMERA_NEXT_SESSION_TH.md')


def draw_result(cv2, image, boxes, result, motor=None):
    height, width = image.shape[:2]
    for x, y, w, h in boxes:
        cv2.rectangle(image, (int(x * width), int(y * height)),
                      (int((x + w) * width), int((y + h) * height)), (150, 150, 150), 1)
    selected = result['observation']['box']
    if selected is not None:
        x, y, w, h = selected
        cv2.rectangle(image, (int(x * width), int(y * height)),
                      (int((x + w) * width), int((y + h) * height)), (0, 255, 0), 2)
    cv2.drawMarker(image, (width // 2, height // 2), (255, 180, 0))
    status = result['observation']['status']
    mode = result['intent']['mode']
    output='MOTORS OFFLINE' if motor is None else (f'YAW +/-{motor.range_deg}deg' if (getattr(motor,'yaw_follow_enabled',True) or getattr(motor,'small_happy_trial',False) is True) else 'YAW HOLD')+(f' PITCH +/-{getattr(motor,"pitch_range_deg",3)}deg' if getattr(motor,'pitch_enabled',False) else '')
    controller=getattr(motor,'controller',None)
    if controller is not None and getattr(motor,'pitch_enabled',False):
        low,high=controller.active_pitch_window();center=controller.normal[5]
        output=output.split(' PITCH')[0]+f' PITCH -{round((center-low)*360/4096)}/+{round((high-center)*360/4096)}deg'
    cv2.putText(image, f'{status} | {mode} | {output}', (6, 18),
                cv2.FONT_HERSHEY_SIMPLEX, .36, (0, 255, 255), 1)
    cv2.putText(image, f"preview state: {result['state']}", (6, height - 8),
                cv2.FONT_HERSHEY_SIMPLEX, .36, (0, 255, 255), 1)
    if motor is not None:
        band=int(motor.deadband_px)
        for x in (width//2-band,width//2+band):cv2.line(image,(x,78),(x,height-40),(100,180,180),1)
        legends=(motor.label(),('G:pitch follow | U/K:probe J:centre' if getattr(motor,'tuning_id',1)==5 else f'T:+{motor.range_deg} Y:-{motor.range_deg} B:centre G:follow'),'I:Interested S:Sleepy N:Normal H:stop')
        if getattr(motor,'automatic_fsm_enabled',False):
            legends=(motor.label(),'AUTO FSM: '+str(motor.snapshot_view().get('emotion','normal')),'Real button / touch / ToF | M:start H:stop Q:exit')
        for line,text in enumerate(legends):
            cv2.putText(image,text,(6,36+line*16),cv2.FONT_HERSHEY_SIMPLEX,.34,(0,255,255),1)
        fault=motor.fault_message()
        if motor.snapshot_view().get('state')=='WAIT_TOF':
            cv2.putText(image,'ToF: holding; resumes when valid, clear >=28cm',(6,100),cv2.FONT_HERSHEY_SIMPLEX,.32,(0,200,255),1)
        if getattr(motor,'physical_button',None) is not None:
            cv2.putText(image,f"Real button: ready | presses {getattr(motor,'button_sequence',0)}",(6,136),cv2.FONT_HERSHEY_SIMPLEX,.32,(180,255,180),1)
        if not fault and motor.snapshot_view().get('state')=='NORMAL_STARTUP':
            waiting=getattr(motor,'status_wait',[])
            cv2.putText(image,'Normal: '+(waiting[0] if waiting else 'checking stationary feedback'),(6,100),cv2.FONT_HERSHEY_SIMPLEX,.34,(0,200,255),1)
            if getattr(motor,'pending_behavior',None) is not None:
                cv2.putText(image,'LOOK BUTTON queued - no need to click again',(6,116),cv2.FONT_HERSHEY_SIMPLEX,.32,(0,255,255),1)
        if fault:
            cv2.putText(image,'STOPPED - support lamp; M: reconnect + Normal',(6,100),cv2.FONT_HERSHEY_SIMPLEX,.34,(0,0,255),1)
            for n in range(2):
                cv2.putText(image,fault[n*44:(n+1)*44],(6,116+n*15),cv2.FONT_HERSHEY_SIMPLEX,.32,(0,0,255),1)
    return image


def live_preview(args):
    # Import only in explicit --live mode. No device access from --help/check/replay.
    headless=getattr(args,'headless',False)
    simple=getattr(args,'simple_ui',False)
    if not headless and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        raise RuntimeError('No desktop display; run inside the Pi VNC desktop terminal.')
    import fcntl
    import cv2
    from picamera2 import Picamera2

    detector = find_cascade(cv2, args.cascade)
    if not hasattr(time, 'CLOCK_BOOTTIME'):
        raise RuntimeError('CLOCK_BOOTTIME required to compare SensorTimestamp in the same clock domain')
    # Lock our existing source inode, creating no lock file or session directory.
    with open(__file__, 'rb') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('This camera preview is already open') from exc
        camera = None
        motor = None
        vision = None
        started = False
        window = ('Lamp Bio - Normal / face centering' if getattr(args,'normal_profile',None)
                  else 'Lamp camera - preview only (no motor connection)')
        engine = PreviewEngine(args.max_age_s)
        state, reset, frames = 'normal', False, 0
        last_wake_serial=0
        last_diagnostic_s=-1.
        motor_error=''
        panel=None;behavior_panel=None
        try:
            camera = Picamera2(camera_num=args.camera)
            camera.configure(camera.create_preview_configuration(
                **capture_configuration(getattr(args,'fps',None))))
            camera_view=configure_full_sensor_view(camera)
            print('CAMERA_FULL_SENSOR_VIEW',camera_view,flush=True)
            width, height = camera.stream_configuration('lores')['size']
            if not headless:
                cv2.namedWindow(window, cv2.WINDOW_NORMAL)
                if getattr(args,'manual_tuning',False):
                    from tuning_panel import TuningPanel
                    profile_data=json.loads(Path(args.normal_profile).read_text(encoding='utf-8-sig'))
                    panel=TuningPanel(cv2,window,profile_data.get('manual_tuning_initial'),target_id=profile_data.get('manual_tuning_id',1))
                elif getattr(args,'normal_profile',None) is not None:
                    from behavior_panel import BehaviorPanel
                    profile_data=json.loads(Path(args.normal_profile).read_text(encoding='utf-8-sig'))
                    manual_cpg=profile_data.get('cpg_normal_amplitude_mode')=='manual_1_3'
                    behavior_panel=BehaviorPanel(cv2,window,cpg_amplitude=profile_data.get('cpg_normal_amplitude_deg',2.) if manual_cpg else None,afraid_enabled=profile_data.get('afraid_pose_trial_enabled') is True and profile_data.get('physical_tof_enabled') is not True,automatic=profile_data.get('automatic_fsm_enabled') is True,simple=simple)
                if simple:cv2.resizeWindow(window,640,576)
                else:cv2.resizeWindow(window, 640, 740 if panel is not None else 480 if behavior_panel is not None and behavior_panel.cpg_amplitude is not None else 360)
            camera.start()
            started = True
            angles = (-15,15) if getattr(args,'roll_compensation',False) else ()
            def find_latest(item):
                grey,stamp,epoch=item
                began=time.perf_counter()
                rects=detect_faces(grey,detector,cv2,angles)
                return normalized_boxes(rects,width,height),stamp,epoch,(time.perf_counter()-began)*1000
            vision=LatestWorker(find_latest)
            epoch=0;last_detection=0;boxes=[];detector_ms=0.;display_start=time.perf_counter()
            previous_source=None
            result={'state':'normal','observation':{'status':'WAITING','box':None,'error_xy':None,
                    'captured_s':0.,'processed_s':0.,'source_id':0},
                    'intent':{'mode':'HOLD','error_xy':None,'counts_as_activity':False,'motor_output_enabled':False}}
            if getattr(args,'normal_profile',None) is not None and getattr(args,'auto_normal_start',False):
                from bio_inspire.runtime.camera_motor import CameraMotor
                motor=(boot_motor_start(args.normal_profile,CameraMotor,park_only=getattr(args,'boot_park',False)) if getattr(args,'boot_ready',False) else CameraMotor(args.normal_profile))
            print('HEADLESS_PLAY: stop through service; fault never auto-rearms' if headless else 'Camera preview. q/ESC: exit, M: start/retry Normal.',flush=True)
            while not args.max_frames or frames < args.max_frames:
                request = camera.capture_request()
                try:
                    # Same request supplies pixels and source metadata. Copy before release.
                    grey = request.make_array('lores')[:height, :width].copy()
                    frame_metadata=request.get_metadata()
                    stamp = frame_metadata.get('SensorTimestamp')
                finally:
                    request.release()
                captured = stamp / 1e9 if finite_number(stamp) else float('nan')
                new_frame=captured!=previous_source
                previous_source=captured
                if motor is not None:
                    motor.poll()
                    if motor.just_ready:epoch+=1;reset=True
                    if getattr(motor,'wake_serial',0)!=last_wake_serial:
                        last_wake_serial=motor.wake_serial;state='normal';epoch+=1;reset=True
                    actual_behavior=motor.snapshot_view().get('behavior')
                    if actual_behavior in ('normal','interested','sleepy','happy','afraid') and actual_behavior!=state:
                        state=actual_behavior;epoch+=1
                if new_frame:vision.submit((grey,captured,epoch))
                latest=vision.latest()
                now=time.clock_gettime(time.CLOCK_BOOTTIME)
                if latest is not None and latest[0]!=last_detection:
                    last_detection=latest[0]
                    new_boxes,source_stamp,source_epoch,detector_ms=latest[1]
                    if source_epoch==epoch:
                        boxes=new_boxes
                        selected_boxes=boxes
                        if motor is not None and not motor.vision_ready():
                            engine.tracker.reset();selected_boxes=[]
                        result=engine.step({'boxes':selected_boxes,'captured_s':source_stamp,
                                           'processed_s':now,'state':state,'reset':reset,
                                           'preserve_player':motor is not None and motor.snapshot_view().get('behavior')=='button_look' and motor.snapshot_view().get('route_phase') in ('look','return'),
                                           'acquisition_scan':motor is not None and (motor.snapshot_view().get('yaw_acquisition_scan') or {}).get('active') is True})
                        reset=False
                if now-result['observation']['captured_s']>args.max_age_s:
                    result={**result,'observation':{**result['observation'],'status':'STALE','box':None,'error_xy':None},
                            'intent':{'mode':'HOLD','error_xy':None,'counts_as_activity':False,'motor_output_enabled':False}}
                    boxes=[]
                if motor is not None:motor.apply(result)
                if headless:
                    if motor is not None and motor.fault_message():
                        raise RuntimeError('Boot controller stopped: '+motor.fault_message())
                    if getattr(args,'boot_park',False) and motor is not None and motor.ready():
                        print('BOOT_NORMAL_PARKED_WAITING_FOR_MANUAL_START',flush=True)
                        break
                    frames+=int(new_frame)
                    time.sleep(.001)
                    continue
                image = cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR)
                if simple:
                    from play_view import draw as draw_play_view
                    image=draw_play_view(cv2,image,result,motor,motor_error)
                else:
                    if motor is None and getattr(args,'normal_profile',None) is not None:
                        cv2.putText(image,'M: support lamp + start Normal',(6,40),cv2.FONT_HERSHEY_SIMPLEX,.4,(0,255,255),1)
                        if motor_error:
                            cv2.putText(image,'START BLOCKED: '+motor_error[:34],(6,58),cv2.FONT_HERSHEY_SIMPLEX,.32,(0,0,255),1)
                    fps=(frames+int(new_frame))/max(.001,time.perf_counter()-display_start)
                    distance=None if motor is None else motor.snapshot_view().get('distance')
                    if distance is not None:
                        cm=distance.get('distance_cm')
                        label=(f'ToF {cm:.1f}cm | near20 clear28' if type(cm) in (int,float) else
                               'ToF: no target detected' if distance.get('measurement_state')=='no_target' else
                               'ToF: no new distance event' if distance.get('measurement_state')=='unreliable' else
                               'ToF: waiting for sensor data')
                        cv2.putText(image,label,(6,height-42),cv2.FONT_HERSHEY_SIMPLEX,.34,(0,255,255),1)
                    cv2.putText(image,f'Preview {fps:.1f}fps Detect {detector_ms:.0f}ms',(6,height-26),
                                cv2.FONT_HERSHEY_SIMPLEX,.34,(0,255,255),1)
                    image=draw_result(cv2,image,boxes,result,motor)
                if getattr(args,'diagnostic_snapshot',False) and now-last_diagnostic_s>=1.:
                    # Two bounded overwrite files, no video/session accumulation.
                    diagnostic=Path(args.normal_profile).parent/'last_camera_frame.jpg'
                    temporary=diagnostic.with_name('last_camera_frame.tmp.jpg')
                    try:
                        if not cv2.imwrite(str(temporary),image):raise OSError('Camera snapshot failed')
                        temporary.replace(diagnostic)
                        meta=diagnostic.with_suffix('.json')
                        data=dict(frame_captured_s=captured,write_s=now,result=result,
                                  camera={**camera_view,'actual_scaler_crop':frame_metadata.get('ScalerCrop'),'frame_duration_us':frame_metadata.get('FrameDuration')},
                                  motor=None if motor is None else motor.snapshot_view())
                        tmp=meta.with_suffix('.tmp');tmp.write_text(json.dumps(data),encoding='utf-8');tmp.replace(meta)
                    except OSError as error:print('DIAGNOSTIC_SNAPSHOT_FAILED',str(error),flush=True)
                    last_diagnostic_s=now
                if not simple and motor_error and motor is not None:
                    cv2.putText(image,'Retry M: '+motor_error[:46],(6,70),cv2.FONT_HERSHEY_SIMPLEX,.32,(0,0,255),1)
                cv2.imshow(window,panel.draw(image,motor) if panel is not None else behavior_panel.draw(image,motor) if behavior_panel is not None else image)
                frames += int(new_frame)
                key = cv2.waitKey(1) & 255
                if behavior_panel is not None:key=behavior_panel.take(key)
                if getattr(args,'normal_profile',None) is not None and key==ord('m'):
                    from bio_inspire.runtime.camera_motor import CameraMotor
                    try:
                        motor=operator_motor_start(motor,args.normal_profile,CameraMotor);motor_error=''
                    except Exception as error:
                        motor_error=str(error);print('MOTOR_START_BLOCKED',motor_error,flush=True)
                        # Keep the old fault owner reference for retry/cleanup.
                if motor is not None:motor.key(key)
                if behavior_panel is not None:behavior_panel.dispatch(motor)
                if panel is not None:panel.dispatch(key,motor)
                if key in (27, ord('q')) or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                    break
                if key == ord('r'):
                    reset = True;epoch+=1
                if key == ord('s') and motor is None:
                    state = 'sleepy';epoch+=1
                if key == ord('n') and motor is None:
                    state = 'normal';epoch+=1
                if key in (ord('r'),ord('s'),ord('n')):
                    result={**result,'state':state,
                            'observation':{**result['observation'],'status':'WAITING','box':None,'error_xy':None},
                            'intent':{'mode':'HOLD','error_xy':None,'counts_as_activity':False,'motor_output_enabled':False}}
                    if motor is not None:motor.apply(result)
        finally:
            try:
                if motor is not None:motor.close()
            finally:
                try:
                    if vision is not None:vision.close()
                    if camera is not None:
                        try:
                            if started:camera.stop()
                        finally:camera.close()
                finally:
                    if not headless:cv2.destroyAllWindows()


        if started and frames:
            elapsed=time.perf_counter()-display_start
            print('PREVIEW_STATS',json.dumps({'frames':frames,'elapsed_s':round(elapsed,3),
                  'fps':round(frames/max(.001,elapsed),2),'last_detector_ms':round(detector_ms,2)}),flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='Check module presence without opening camera')
    mode.add_argument('--replay', type=Path, help='Replay JSONL boxes without camera/motors')
    mode.add_argument('--live', action='store_true', help='Open one camera preview; no actuator access')
    parser.add_argument('--max-age-s', type=float, help='Explicit preview age limit; choose during daylight trial')
    parser.add_argument('--fps',type=float,help='Explicit approved camera frame rate; exposure may darken')
    parser.add_argument('--cascade', type=Path, help='Existing OpenCV frontal face XML')
    parser.add_argument('--roll-compensation', action='store_true',
                        help='Try approved image rotations -15/+15 degrees only if upright detection finds no faces')
    parser.add_argument('--normal-profile',type=Path,
                        help='Approved Normal + yaw motor profile; press M after supporting lamp to start')
    parser.add_argument('--manual-tuning',action='store_true',
                        help='Approved ID1 P/I/D/Speed sliders; explicit Apply, volatile changes only')
    parser.add_argument('--auto-normal-start',action='store_true',
                        help='Explicit automatic Normal startup (only after startup path validation; requires profile)')
    parser.add_argument('--simple-ui',action='store_true',help='Camera-first Start/Stop screen')
    parser.add_argument('--headless',action='store_true',help='Run without desktop/window; stop through service or power switch')
    parser.add_argument('--boot-park',action='store_true',help='Boot to Normal only, close hardware owner, then await GUI Start Auto')
    parser.add_argument('--boot-ready',action='store_true',help='One authorized boot Normal start using live preflight; never retries a fault')
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--diagnostic-snapshot',action='store_true',help='Overwrite one annotated image + metadata beside the profile for diagnosis')
    parser.add_argument('--max-frames', type=int, default=0, help='0: until window closed; does not retain frames')
    args = parser.parse_args(argv)
    if args.simple_ui and (args.headless or args.manual_tuning or not args.live or not args.normal_profile):parser.error('--simple-ui needs live motor preview without tuning/headless')
    if args.boot_park and not args.boot_ready:parser.error('--boot-park requires --boot-ready')
    if args.headless and (args.manual_tuning or args.diagnostic_snapshot):parser.error('Headless mode has no tuning panel or image snapshots')
    if args.headless and not args.live:parser.error('--headless requires --live')
    if args.boot_ready and not (args.live and args.headless and args.auto_normal_start and args.normal_profile):parser.error('--boot-ready requires --live --headless --auto-normal-start and profile')
    if args.diagnostic_snapshot and args.normal_profile is None:parser.error('--diagnostic-snapshot requires --normal-profile')
    if args.manual_tuning and args.normal_profile is None:parser.error('--manual-tuning requires --normal-profile')
    if args.fps is not None and (not finite_number(args.fps) or args.fps<=0):parser.error('--fps must be positive finite')
    if args.max_frames < 0 or args.camera < 0:
        parser.error('--max-frames and --camera must be nonnegative')
    if args.normal_profile and not args.live:parser.error('--normal-profile requires --live')
    if args.auto_normal_start and not args.normal_profile:parser.error('--auto-normal-start requires --normal-profile')
    if not args.check and (not finite_number(args.max_age_s) or args.max_age_s <= 0):
        parser.error('--live/--replay require an explicit positive --max-age-s')
    try:
        if args.check:
            report = dependency_report()
            print(json.dumps(report, indent=2))
            return 0 if all(report['modules'].values()) else 2
        if args.replay:
            with args.replay.open(encoding='utf-8-sig') as source:
                rows = (json.loads(line) for line in source if line.strip())
                for row in replay_rows(rows, args.max_age_s):
                    print(json.dumps(row, allow_nan=False))
        else:
            if args.headless:
                import signal
                def terminate(signum,frame):raise KeyboardInterrupt
                previous=signal.signal(signal.SIGTERM,terminate)
                try:live_preview(args)
                finally:signal.signal(signal.SIGTERM,previous)
            else:live_preview(args)
        return 0
    except KeyboardInterrupt:
        return 130
    except (ImportError, OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        print(f'Camera tool stopped: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
