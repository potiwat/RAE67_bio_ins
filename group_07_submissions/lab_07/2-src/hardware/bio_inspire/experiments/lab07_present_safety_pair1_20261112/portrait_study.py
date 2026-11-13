"""Attend a single real Present Safety research run with the live camera aimed at a fixed portrait."""
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import time
import instrument

BASE_PROTOCOL = instrument.PROTOCOL
PROTOCOL = BASE_PROTOCOL + "_portrait"

def study_gpio(live, channel, now, start):
    """Place scripted edges after the existing live GPIO counter, including the handoff back."""
    if now < start:
        return live
    end=start+instrument.DURATION
    edges=live["stable_edges"]
    if any(start <= edge["time_s"] < end for edge in edges):
        raise ValueError("Physical GPIO changed inside the scheduled window")
    if now < end and live["stable_pressed"]:
        raise ValueError("Physical GPIO held inside the scheduled window")
    before=[edge for edge in edges if edge["time_s"] < start]
    after=[edge for edge in edges if edge["time_s"] >= end]
    base=live["stable_sequence"]-len(after)
    script=instrument.digital(channel,min(now,end)-start,start)
    scripted=[dict(edge,sequence=edge["sequence"]+base) for edge in script["stable_edges"]]
    post=[dict(edge,sequence=edge["sequence"]+len(scripted)) for edge in after]
    return dict(live,stable_pressed=bool(live["stable_pressed"] or script["stable_pressed"]),
                stable_sequence=live["stable_sequence"]+len(scripted),stable_edges=before+scripted+post)


class BenchGate:
    def __init__(self, cap, clock):
        self.cap, self.clock = cap, clock
        self.opened = clock()
        self.face_times = deque()
        self.camera_times = deque(maxlen=16)
        self.first_ready = None
        self.measurement_face = None
        self.claimed = False
        self.error = ""
        self.start_sent = None
        self.motor = None
        self.last_source = None
        self.face_frames = 0
        self.start_face = None
        self.latest_observation = None
        self.last_status = 0.
        self.latest_motor_state = None

    @property
    def count(self):
        return len(self.face_times)

    def open(self):
        return self

    def close(self):
        pass

    def observe(self, result, motor, start_error):
        now = self.clock()
        if motor is not None:
            self.motor = motor
        fault = start_error or (motor.fault_message() if motor is not None else "")
        if fault and not self.cap.done and not self.cap.aborted:
            self.cap.aborted = str(fault)
        if motor is not None and self.cap.start is None and now - self.last_status >= 4.:
            self.last_status = now
            snap = motor.snapshot_view()
            self.latest_motor_state = {k: snap.get(k) for k in ("state", "ready", "error", "positions", "behavior", "route_phase")}
            print("START_POSTURE", self.latest_motor_state, flush=True)
        obs = result.get("observation") or {}
        stamp = obs.get("captured_s")
        if obs.get("status") in ("INVALID","STALE") or stamp is None or not 0 <= now - stamp <= .5:
            self.camera_times.clear()
            self.face_times.clear()
            return
        if not self.camera_times or stamp != self.camera_times[-1]:
            if self.camera_times and not 0 < stamp-self.camera_times[-1] <= .3:
                self.camera_times.clear()
            self.camera_times.append(stamp)
        if obs.get("status") not in ("ACQUIRED", "TRACKING") or not obs.get("box"):
            self.face_times.clear()
            return
        if stamp == self.last_source:
            return
        if self.last_source is not None and not 0 < stamp - self.last_source <= .3:
            self.face_times.clear()
        self.last_source = stamp
        self.face_times.append(stamp)
        while len(self.face_times) > 1 and stamp - self.face_times[0] > .5:
            self.face_times.popleft()
        self.face_frames += 1
        self.latest_observation = {"captured_s":stamp,"status":obs["status"],"box":obs["box"]}

    def allow_measurement(self, ready):
        if not ready:
            return False
        now=self.clock()
        if self.first_ready is None:
            self.first_ready=now
        stamps=[t for t in tuple(self.face_times) if t>=self.first_ready and 0<=now-t<=.5]
        if len(stamps)>=3 and stamps[-1]-stamps[0]>=.15:
            self.measurement_face=self.latest_observation
            return True
        if now-self.first_ready>=30 and not self.cap.aborted:
            self.cap.aborted="No stable real face after the native Normal pose was ready"
        return False

    def filter_key(self, motor, key, visible):
        if key in (27, ord("q"), ord("h"), ord(" ")) or not visible:
            if not self.cap.done and not self.cap.aborted:
                self.cap.aborted = "Operator stop or viewer closed"
            return key
        if self.cap.aborted or self.cap.done:
            return ord("q")
        if self.claimed:
            return 255 if key == ord("m") else key
        if self.clock() - self.opened > 30:
            self.cap.aborted = "No fresh video frames before startup"
            return ord("q")
        if len(self.camera_times) >= 3 and self.camera_times[-1] - self.camera_times[0] >= .15:
            self.claimed = True
            self.start_sent = self.clock()
            self.start_face = self.latest_observation
            print("PORTRAIT_CAMERA_AUTO_START_NORMAL", self.start_face, flush=True)
            return ord("m")
        return 255 if key == ord("m") else key


def main():
    original_hooks, original_identity = instrument.hooks, instrument.identity
    def identity():
        data = original_identity()
        data["desktop_default_start_gate"] = data["start_gate"]
        data.update(start_gate="single authorized Normal startup on live video; stable real face in Normal starts acquisition",
                    vision_target="fixed displayed portrait; production camera and detector",
                    end_gate="native Q, then verify motor cleanup", portrait_sha256=instrument.sha(__file__))
        return data

    def hooks(cap, runtime):
        @contextmanager
        def watched(*args, **kwargs):
            from shared.experiments.presentation_safety_play_20261110 import launch
            import play_view
            clock = lambda: time.clock_gettime(time.CLOCK_BOOTTIME)
            gate = BenchGate(cap, clock)
            native_enter = cap.enter
            native_observe_input=cap.observe_input
            def observe_input(source,m,now,details):
                physical={}
                def read_once(owner,when,out):
                    value=source(owner,when,physical)
                    out.update(physical)
                    return value
                result=native_observe_input(read_once,m,now,details)
                if (cap.start is not None and m is cap.owner and result is not None
                        and details is not None and len(physical.get("views",[]))==2):
                    try:
                        details["views"]=[study_gpio(view,ch,cap.last_input["time_s"],cap.start)
                                          for ch,view in zip(("button","touch"),physical["views"])]
                    except ValueError as exc:
                        cap.physical_coinput=True
                        cap.aborted=str(exc)
                        details["views"]=physical["views"]
                return result
            def enter(m, now):
                if not PROTOCOL.endswith("_prep") and cap.start is None and not cap.aborted:
                    if m.bus.central_feedback.brake_capture.core.phase!="PLAY":
                        cap.aborted="Present Safety intervention before the research clock"
                        return
                    normal=m.controller.state in ("READY","FOLLOWING") and m.behavior_trial=="normal"
                    if not gate.allow_measurement(normal):
                        if gate.first_ready is not None and clock()-gate.first_ready>=35 and not cap.aborted:
                            cap.aborted="Normal and a stable real face did not coincide"
                        return
                native_enter(m,now)
            try:
                with original_hooks(cap, runtime)(*args, **kwargs) as sessions:
                    original_draw = play_view.draw
                    def draw(cv, image, result, motor=None, start_error=""):
                        gate.observe(result, motor, start_error)
                        return original_draw(cv, image, result, motor, start_error)
                    with patch.object(launch, "InitialButtonStart", lambda: gate), patch.object(play_view, "draw", draw), patch.object(cap,"enter",enter), patch.object(cap,"observe_input",observe_input):
                        yield sessions
            finally:
                if cap.scratch:
                    instrument.save(cap.folder / "portrait_close.json", dict(
                        start_sent_s=gate.start_sent, live_face_at_start=gate.start_face,
                        live_face_at_measurement=gate.measurement_face, native_normal_ready_s=gate.first_ready,
                        live_face_frames=gate.face_frames, last_startup_view=gate.latest_motor_state,
                        native_cleanup_confirmed=bool(gate.motor and gate.motor.cleanup_confirmed),
                        native_owner_existed=gate.motor is not None, study_done=cap.done, aborted=cap.aborted))
        return watched

    with patch.object(instrument, "PROTOCOL", PROTOCOL), patch.object(instrument, "identity", identity), patch.object(instrument, "hooks", hooks):
        instrument.main()


if __name__ == "__main__":
    main()
