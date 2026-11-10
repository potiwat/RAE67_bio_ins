"""Operator-started ID1 baseline GUI. All trial values are explicit CLI arguments."""
import argparse,json,time,signal,hashlib
from pathlib import Path
from datetime import datetime,timezone
import tkinter as tk
from tkinter import messagebox
from motor_baseline import BaselineBus,BaselineSession,TrialConfig

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--delta-deg',type=float,required=True);p.add_argument('--speed-raw',type=int,required=True);p.add_argument('--acceleration-raw',type=int,required=True);p.add_argument('--execute',action='store_true')
 args=p.parse_args();cfg=TrialConfig(args.delta_deg,args.speed_raw,args.acceleration_raw)
 if not args.execute:
  print(json.dumps({'mode':'dry_run_no_hardware','id':1,'excursion_ticks':cfg.ticks,'actual_excursion_deg':cfg.ticks*360/4096,'speed_raw':cfg.speed_raw,'acceleration_raw':cfg.acceleration_raw,'writes_after_operator_start':['ID1 speed','ID1 acceleration','ID1 fresh hold goal','ID1 torque ON','ID1 outward goal once','ID1 return goal once'],'other_servo_writes':False,'SPI_LED_access':False},indent=2));return
 root=tk.Tk();root.title('Lamp Bio — ทดสอบฐานหมุน ID1');root.geometry('980x640')
 title=f'เฉพาะ ID1: +{cfg.ticks*360/4096:.2f}° แล้วกลับ • speed=1 ≈4.4°/s • acceleration=1 ≈8.7°/s²'
 tk.Label(root,text=title,font=('sans',14,'bold'),wraplength=950).pack(pady=10)
 tk.Label(root,text='พยุงแขนและหัวไม่ให้ลากโต๊ะ เตรียมสวิตช์ตัดไฟ • ID2–5 ยังปล่อยตัว • โปรแกรมนี้ไม่แตะ LED',font=('sans',11),wraplength=950).pack()
 status=tk.StringVar(value='กำลังเปิดพอร์ตอ่านข้อมูล — ยังไม่เปิด torque');tk.Label(root,textvariable=status,font=('sans',13),wraplength=950).pack(pady=10)
 values=tk.StringVar(value='');tk.Label(root,textvariable=values,font=('monospace',12)).pack(pady=4)
 frame=tk.Frame(root);frame.pack(pady=6)
 canvas=tk.Canvas(root,width=930,height=340,bg='white');canvas.pack(padx=15,pady=8)
 hint=tk.StringVar(value='เส้นน้ำเงิน = มุมจริงจาก encoder; เส้นเทา = goal ที่ส่ง (step เพราะใช้ ramp ในมอเตอร์)')
 tk.Label(root,textvariable=hint,wraplength=950).pack()
 folder=Path(__file__).resolve().parent/'sessions'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');folder.mkdir(parents=True,exist_ok=False)
 handle=(folder/'events.jsonl').open('x',encoding='utf8');bus=None;session=None;started=None;cycle_returned=False;closing=False;last_fb=None;ready=False;cycle_plot=None
 def summary():
  (folder/'result.json').write_text(json.dumps({'config':cfg.__dict__,'state':None if session is None else session.state,'cycle_returned':cycle_returned,'ID1_may_be_enabled':False if session is None else session.may_be_enabled,'base_raw':None if session is None else session.base,'target_raw':None if session is None else session.target,'last_feedback':last_fb,'other_IDs_written':False,'SPI_LED_access':False,'physical_smoothness':'operator_review_pending'},indent=2))
 def event(kind,**data):
  nonlocal cycle_returned,cycle_plot
  row={'kind':kind,'utc':datetime.now(timezone.utc).isoformat(),'monotonic_s':time.monotonic(),**data};handle.write(json.dumps(row)+'\n');handle.flush()
  if kind=='CYCLE_RETURNED':
   cycle_returned=True;cycle_plot=list(session.samples)
  if kind!='feedback':print(json.dumps(row),flush=True);summary()
 def start():
  nonlocal started
  if session.state!='IDLE' or not ready:return
  start_button.configure(state='disabled');status.set('กำลังตั้ง fresh hold และค่าทดสอบ — พยุงโครงไว้');root.update_idletasks()
  try:
   session.arm();started=time.monotonic();session.begin(started)
  except Exception as e:session.stop(str(e));status.set('หยุดก่อน/ระหว่างเริ่ม: '+str(e));summary()
 def stop():
  if session is None:return
  if session.state=='IDLE':status.set('ยังไม่เริ่ม ไม่มีคำสั่งเคลื่อน');return
  session.stop('Operator STOP');summary()
 def release():
  nonlocal last_fb
  if session is None or not session.may_be_enabled:return
  if not messagebox.askyesno('รับน้ำหนักก่อนปล่อย ID1','พยุงโครงครบแล้วหรือไม่?\nYes = ปล่อย torque เฉพาะ ID1\nID2–5 ไม่เปลี่ยน',parent=root):return
  try:
   if session.state in ('OUTWARD','RETURN'):session.stop('Operator release requested')
   session.release();last_fb=bus.feedback();summary();status.set('ยืนยัน torque OFF ของ ID1 แล้ว — จบรอบ')
  except Exception as e:status.set('ปล่อยยังไม่ยืนยัน: '+str(e)+' — พยุงและตรวจสวิตช์ตัดไฟ');event('RELEASE_UNCONFIRMED',error=str(e))
 def close():
  nonlocal closing
  if session is not None and session.may_be_enabled:
   session.stop('Window close requested');summary()
   if not messagebox.askyesno('มอเตอร์อาจยังมี torque','โปรแกรมหยุดเป้าแล้ว แต่ยังไม่ปล่อย torque\n\nหากรับน้ำหนัก/ตัดไฟแล้ว และต้องการปิดหน้าจอโดยไม่สั่งปล่อยอัตโนมัติ กด Yes\nหากยังไม่พร้อม กด No แล้วใช้ปุ่มปล่อย ID1 เมื่อพยุงพร้อม',parent=root):return
  closing=True;summary()
  if bus:bus.close()
  handle.close();root.destroy()
 start_button=tk.Button(frame,text='พยุงพร้อมแล้ว — เริ่มรอบนี้',font=('sans',12),command=start,state='disabled');start_button.pack(side='left',padx=8)
 tk.Button(frame,text='หยุด / ค้างท่าปัจจุบัน',bg='#ffb050',font=('sans',12),command=stop).pack(side='left',padx=8)
 release_button=tk.Button(frame,text='รับน้ำหนักแล้ว — ปล่อย ID1',font=('sans',12),command=release,state='disabled');release_button.pack(side='left',padx=8)
 root.protocol('WM_DELETE_WINDOW',close);signal.signal(signal.SIGTERM,lambda *_:stop())
 def draw():
  canvas.delete('all');left=65;top=25;right=900;bottom=300
  canvas.create_line(left,top,left,bottom,right,bottom,fill='#888')
  canvas.create_text(20,160,text='deg');canvas.create_text(880,325,text='time s')
  points=[] if session is None else cycle_plot if cycle_plot is not None else session.samples
  if not points or started is None:return
  span=max(3.,points[-1]['time_s']-started);lo=-1.;hi=cfg.delta_deg+1.
  def xy(t,p):return left+(right-left)*(t-started)/span,bottom-(bottom-top)*((p-session.base)*360/4096-lo)/(hi-lo)
  for deg in range(-1,5):
   y=bottom-(bottom-top)*(deg-lo)/(hi-lo)
   if top<=y<=bottom:canvas.create_line(left,y,right,y,fill='#eeeeee');canvas.create_text(45,y,text=str(deg))
  for key,color in [('goal_raw','#999999'),('position_raw','#1565c0')]:
   coords=[]
   for row in points:coords.extend(xy(row['time_s'],row[key]))
   if len(coords)>=4:canvas.create_line(*coords,fill=color,width=2)
 def tick():
  nonlocal last_fb,ready
  if closing:return
  try:
   if session.state=='IDLE':
    last_fb=bus.feedback();ready=last_fb['status_raw']==0 and (last_fb['torque_raw']==0 or (last_fb['torque_raw']==1 and abs(int.from_bytes(bus.read(1,42,2),'little')-last_fb['position_raw'])<=6))
    start_button.configure(state='normal' if ready else 'disabled')
    status.set('อ่านพร้อมแล้ว — กดเริ่มเมื่อพยุงพร้อม' if ready else 'ตรวจ torque/status ก่อนเริ่ม')
   elif session.state in ('OUTWARD','RETURN','HOLDING'):
    current=session.tick(time.monotonic())
    if current is not None:last_fb=current
    labels={'OUTWARD':'กำลังไป +3° — พยุงไว้','RETURN':'กำลังกลับจุดเริ่ม','HOLDING':'จบรอบแล้ว ID1 ยังประคองอยู่ — ดูกราฟและการเคลื่อนจริง'}
    status.set(labels.get(session.state,'หยุดแล้ว — '+str(session.last_error)))
   elif session.state.startswith('STOPPED'):
    status.set(('หยุดและส่งเป้าประคองแล้ว' if session.state=='STOPPED_HOLDING' else 'หยุด — ยังยืนยันการประคองไม่ได้' if session.state=='STOPPED_UNCONFIRMED' else 'หยุด — torque OFF')+' | '+str(session.last_error))
   if last_fb:values.set(f"ID1 raw={last_fb['position_raw']}  torque={last_fb['torque_raw']}  status={last_fb['status_raw']}  V={last_fb['voltage_V']:.1f}  C={last_fb['temperature_C']}")
   release_button.configure(state='normal' if session.may_be_enabled else 'disabled');draw()
  except Exception as e:
   ready=False;start_button.configure(state='disabled');status.set('อ่านไม่ได้: '+str(e))
   if session and session.may_be_enabled:session.stop(str(e))
  root.after(100,tick)
 try:
  bus=BaselineBus();session=BaselineSession(bus,cfg,event)
  event('PROGRAM_OPENED_NO_MOTION',source_sha256={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ['motor_baseline.py','motor_baseline_gui.py']},config=cfg.__dict__)
  tk.Label(root,text='บันทึก: '+str(folder),wraplength=950).pack(pady=3)
  root.after(100,tick);root.mainloop()
 except Exception as e:
  event('STARTUP_ERROR',error=str(e));messagebox.showerror('ยังไม่เริ่มทดลอง',str(e),parent=root)
  if bus:bus.close()
  if not handle.closed:handle.close()
  try:root.destroy()
  except tk.TclError:pass

if __name__=='__main__':main()
