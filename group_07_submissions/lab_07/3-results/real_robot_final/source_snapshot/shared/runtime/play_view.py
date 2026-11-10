"""Readable camera-first play screen; no device or motion operations."""
def status_text(motor,start_error=''):
    if start_error:return 'Start blocked - check lamp'
    if motor is None:return 'Ready - press Start'
    trial=motor.snapshot_view().get('automatic_trial')
    if trial is not None and trial.get('state')=='aborted':return 'Trial aborted - Q to save; reopen for new trial'
    if getattr(motor,'operator_stopped',False):return 'Stopped - press Start to resume'
    if motor.fault_message():return 'Stopped - check lamp, then Start'
    view=motor.snapshot_view()
    if view.get('state')=='NORMAL_STARTUP':return 'Starting - moving to Normal'
    if view.get('state')=='WAIT_TOF':return 'Paused - check distance sensor'
    gate=view.get('lab07_start_gate')
    if gate is not None:
        if trial is not None and trial.get('state')=='complete':return 'Automatic trial complete - Q to save/close'
        if not gate['started']:return f"Lab07 ready - Button {gate['presses']}/5 to record"
        if gate.get('capture_finished'):return 'Lab07 capture complete - Q to save/close'
        label='Auto '+trial.get('condition','') if trial is not None else 'Recording'
        return f"{label} {gate['elapsed_s']:.0f}/{gate['ceiling_s']:.0f}s - Q to finish"
    name=view.get('emotion') or view.get('behavior') or 'normal'
    return str(name).replace('_transition','').replace('_',' ').title()

def draw(cv,image,result,motor=None,start_error=''):
    h,w=image.shape[:2];obs=result.get('observation') or {}
    box=obs.get('box')
    if box is not None:
        x,y,bw,bh=box
        cv.rectangle(image,(round(x*w),round(y*h)),(round((x+bw)*w),round((y+bh)*h)),(80,220,110),2)
    out=cv.copyMakeBorder(image,48,0,0,0,cv.BORDER_CONSTANT,value=(28,32,38))
    cv.putText(out,status_text(motor,start_error),(10,20),cv.FONT_HERSHEY_SIMPLEX,.46,(240,240,240),1)
    found=obs.get('status') in ('ACQUIRED','TRACKING') and box is not None
    cv.putText(out,'Face found' if found else 'No face detected',(10,39),cv.FONT_HERSHEY_SIMPLEX,.36,(120,220,145) if found else (185,185,185),1)
    return out
