"""Simple Thai manual PID tuner; no camera, no automatic Apply or movement."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import queue
import sys
import threading
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from manual_tuning import bounds_for,validate_values
from normal_gaze_motor import manual_trial_degrees

NAMES={1:'ฐานหมุน',2:'แขนล่าง',3:'ข้อศอก',4:'หมุนหัว',5:'ก้ม–เงย'}


def describe(snapshot,tuning,desired,sid):
    state=snapshot.get('state','IDLE');status=tuning.get('status','')
    actual=tuning.get('applied',{})
    applied=tuning.get('joint_id')==sid and all(actual.get(k)==desired[k] for k in ('p','i','d'))
    result=dict(applied=applied,settings='ตั้งค่าให้มอเตอร์แล้ว ✓' if applied else 'ค่าใหม่ยังไม่ได้ใช้ — กด «ใช้ค่านี้»',
                title='พร้อมทดลองขยับ',message='กด − / กลับกลาง / + แล้วดูความสมูท',color='#17603d')
    if state=='IDLE':result.update(title='ยังไม่ได้เริ่มใช้งาน',message='รองรับโคม แล้วกด «เริ่มใช้งาน»',color='#40536a')
    elif state=='FAULT':
        error=snapshot.get('error','')
        text='มอเตอร์ออกนอกช่วงทดลอง' if 'allowed=' in error or 'outside' in error else 'ติดต่อมอเตอร์ไม่ได้' if 'reply' in error or 'UART' in error else 'ตรวจพบปัญหามอเตอร์'
        result.update(title='หยุดแล้ว: '+text,message='รองรับโคม ตรวจสาย/ไฟ แล้วกดเชื่อมต่อใหม่ ดูสาเหตุเพิ่มในรายละเอียด',color='#a32929')
    elif state=='NORMAL_STARTUP':result.update(title='กำลังจัดท่าเริ่มต้น',message='ถ้าค้าง: กด «คืนค่าเริ่มต้น» รอตั้งค่าสำเร็จ แล้วจัดท่าใหม่',color='#9c5b13')
    elif state=='STOPPED':result.update(title='พร้อมปรับหรือคืนค่า PID',message='เมื่อพร้อมลองขยับ ให้กด «จัดท่าเริ่มต้น» ก่อน',color='#40536a')
    elif state=='READY':
        row=next((r for r in snapshot.get('rows',[]) if r['id']==sid),None)
        goal=snapshot.get('active_goal')
        if row and goal and goal['joint_id']==sid:
            if row['speed_raw'] or row['moving_raw']:result.update(title=f'มอเตอร์ {sid} กำลังขยับ',color='#9c5b13')
            elif abs(goal['raw']-row['position_raw'])>22:
                result.update(title='ยังไม่ถึงเป้า',message='ใช้ค่าแล้ว แต่มอเตอร์ยังไปไม่ถึงตำแหน่ง ลองเพิ่ม P หรือคืนค่าเริ่มต้น',color='#9c5b13')
            elif status.startswith('SENT'):
                result.update(title='ขยับถึงเป้าในเกณฑ์แล้ว',message='คำสั่งทำงานแล้ว ความสมูทให้ดูจากการขยับจริง')
    if status.startswith('WAIT'):result.update(title='กำลังรอมอเตอร์หยุดเพื่อใช้ค่า',message='ยังไม่เปลี่ยนค่า รอข้อความตั้งค่าสำเร็จ',color='#9c5b13')
    elif status.startswith('Not applied') or status.startswith('Blocked'):
        result.update(message='ยังไม่ได้เปลี่ยนค่า: กดกลับกลางหรือหยุด แล้วกดใช้ค่าอีกครั้ง',color='#9c5b13')
    elif status.startswith('Wait for move'):result.update(message='รอขยับเสร็จ หรือกดหยุด ก่อนเปลี่ยนมอเตอร์',color='#9c5b13')
    return result


def save_favorite(path,sid,values,tuning):
    v=validate_values(values,sid)
    if tuning.get('joint_id')!=sid or tuning.get('applied')!=v:raise ValueError('กดใช้ค่าและรอตั้งค่าสำเร็จก่อนบันทึก')
    path=Path(path);data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    data[str(sid)]=dict(values=v,assessment='operator_selected_smooth',time_utc=datetime.now(timezone.utc).isoformat())
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(path)
    return data


class SimpleTuner:
    def __init__(self,root,tk,ttk,profile):
        self.root=root;self.tk=tk;self.ttk=ttk;self.profile=Path(profile)
        config=json.loads(self.profile.read_text(encoding='utf-8-sig')) if self.profile.exists() else {}
        self.ranges=manual_trial_degrees(config.get('limb_range_deg',3),config.get('loaded_probe_deg'))
        self.motor=None;self.connecting=False;self.closing=False;self.loaded=None;self.pending_select=None;self.results=queue.SimpleQueue()
        self.sid=tk.IntVar(value=5);self.values={k:tk.IntVar(value=v) for k,v in dict(p=32,i=0,d=32).items()}
        self.notice=tk.StringVar();self.details_visible=tk.BooleanVar(value=False)
        root.title('Lamp — จูน PID มอเตอร์');root.geometry('900x690');root.minsize(780,650);root.configure(bg='#f3f5f7')
        root.option_add('*Font',('FreeSerif',13))
        style=ttk.Style(root);style.configure('TLabel',font=('FreeSerif',13))
        style.configure('TButton',font=('FreeSerif',14),padding=(8,4))
        style.configure('TRadiobutton',font=('FreeSerif',12))
        style.configure('TCheckbutton',font=('FreeSerif',12))
        main=ttk.Frame(root,padding=22);main.pack(fill='both',expand=True)
        ttk.Label(main,text='จูนมอเตอร์',font=('FreeSerif',23,'bold')).pack(anchor='w')
        ttk.Label(main,text='เลือกมอเตอร์ → ปรับ P / I / D → ใช้ค่า → ลองขยับ').pack(anchor='w',pady=(0,12))
        selectors=ttk.Frame(main);selectors.pack(fill='x')
        for i in range(1,6):ttk.Radiobutton(selectors,text=f'{i} {NAMES[i]}',variable=self.sid,value=i,command=self.select).pack(side='left',expand=True)
        self.status_box=tk.Frame(main,bg='#40536a',padx=15,pady=10);self.status_box.pack(fill='x',pady=12)
        self.title=tk.Label(self.status_box,text='ยังไม่ได้เริ่มใช้งาน',fg='white',bg='#40536a',font=('FreeSerif',18,'bold'),anchor='w')
        self.title.pack(fill='x')
        self.message=tk.Label(self.status_box,text='รองรับโคม แล้วกดเริ่มใช้งาน',fg='white',bg='#40536a',anchor='w',wraplength=805,justify='left');self.message.pack(fill='x')
        top=ttk.Frame(main);top.pack(fill='x')
        self.connect_btn=ttk.Button(top,text='เริ่มใช้งาน',command=self.connect);self.connect_btn.pack(side='left',fill='x',expand=True,padx=(0,6))
        self.normal_btn=ttk.Button(top,text='จัดท่าเริ่มต้น',command=self.normal,state='disabled');self.normal_btn.pack(side='left',fill='x',expand=True)
        box=ttk.Frame(main,padding=(0,12));box.pack(fill='x');self.scales={}
        for row,key in enumerate(('p','i','d')):
            ttk.Label(box,text=key.upper(),font=('FreeSerif',16,'bold'),width=3).grid(row=row,column=0)
            scale=tk.Scale(box,from_=1,to=64,orient='horizontal',variable=self.values[key],resolution=1,showvalue=True,
                           length=650,borderwidth=0,highlightthickness=0,command=lambda value:self.render_settings())
            scale.grid(row=row,column=1,sticky='ew');self.scales[key]=scale
        box.columnconfigure(1,weight=1)
        self.settings=ttk.Label(main,text='ยังไม่ได้อ่านค่าจากมอเตอร์');self.settings.pack(anchor='w')
        actions=ttk.Frame(main);actions.pack(fill='x',pady=(8,12))
        self.apply_btn=ttk.Button(actions,text='ใช้ค่านี้',command=self.apply,state='disabled');self.apply_btn.pack(side='left',expand=True,fill='x',padx=(0,6))
        self.restore_btn=ttk.Button(actions,text='คืนค่าเริ่มต้น',command=self.restore,state='disabled');self.restore_btn.pack(side='left',expand=True,fill='x',padx=(0,6))
        self.save_btn=ttk.Button(actions,text='สมูทดี บันทึกชุดนี้',command=self.save,state='disabled');self.save_btn.pack(side='left',expand=True,fill='x')
        moves=ttk.Frame(main);moves.pack(fill='x');self.moves=[]
        for label,key in [('ขยับ −','k'),('กลับกลาง','j'),('ขยับ +','u')]:
            b=ttk.Button(moves,text=label,command=lambda k=key:self.key(k),state='disabled');b.pack(side='left',fill='x',expand=True,padx=3,ipady=9);self.moves.append(b)
        self.range_label=ttk.Label(main,text='ช่วงทดลอง ±6° • ความเร็วคงที่');self.range_label.pack(anchor='w',pady=(6,0))
        ttk.Label(main,textvariable=self.notice,foreground='#934d00',wraplength=810).pack(anchor='w')
        bottom=ttk.Frame(main);bottom.pack(fill='x',pady=(9,0))
        tk.Button(bottom,text='หยุด',command=lambda:self.key('h'),bg='#af3030',fg='white',font=('FreeSerif',15,'bold'),width=15).pack(side='right')
        ttk.Checkbutton(bottom,text='รายละเอียด',variable=self.details_visible,command=self.toggle_details).pack(side='left')
        ttk.Label(main,text='รองรับโคมก่อนเริ่ม • ปุ่มหยุดค้างท่า ไม่ตัดไฟ • ไม่มีการเปิดกล้อง',foreground='#657184').pack(anchor='w')
        self.details=tk.Text(main,height=6,font=('monospace',10),state='disabled')
        self.set_sliders(5,dict(p=32,i=0,d=32))
        root.protocol('WM_DELETE_WINDOW',self.close);root.bind('<space>',lambda event:self.key('h'));root.bind('<Escape>',lambda event:self.close());root.bind('<Key-q>',lambda event:self.close())
        self.poll()
    def desired(self):return {k:v.get() for k,v in self.values.items()}
    def set_sliders(self,sid,values):
        bounds=bounds_for(sid)
        for k,scale in self.scales.items():scale.configure(from_=bounds[k][0],to=bounds[k][1]);self.values[k].set(values[k])
        self.range_label.configure(text=f'ช่วงทดลอง ±{self.ranges[sid]}° • Speed/Acceleration คงที่ 1')
    def select(self):
        self.notice.set('')
        if self.motor is None:self.set_sliders(self.sid.get(),dict(p=32,i=0,d=32));return
        self.pending_select=self.sid.get();self.notice.set('กำลังเลือกมอเตอร์และอ่านค่าที่ใช้อยู่')
        self.motor.key(ord(str(self.sid.get())))
    def connect(self):
        if self.connecting:return
        self.connecting=True;self.notice.set('กำลังเชื่อมต่อและอ่านค่า ยังไม่สั่งไปท่า Normal')
        old=self.motor;self.motor=None;self.loaded=None;selected=self.sid.get()
        def work():
            try:
                if old is not None:old.close()
                from bio_inspire.runtime.camera_motor import CameraMotor
                self.results.put(('connected',CameraMotor(self.profile,initial_joint=selected)))
            except Exception as error:self.results.put(('error',str(error)))
        threading.Thread(target=work,name='manual-connect',daemon=False).start()
    def key(self,k):
        if self.motor is not None:self.motor.key(ord(k));self.notice.set('')
    def normal(self):
        if self.motor is None:return
        state=self.motor.snapshot_view().get('state')
        self.key('h' if state=='NORMAL_STARTUP' else 'j' if state=='READY' else 'm')
    def apply(self):
        if self.motor is None:return
        if self.pending_select is not None:self.notice.set('รออ่านค่ามอเตอร์ที่เลือกก่อน');return
        self.motor.request_joint_tuning(self.sid.get(),dict(self.desired(),speed=1));self.notice.set('รอการตั้งค่าสำเร็จ ก่อนลองขยับ')
    def restore(self):self.set_sliders(self.sid.get(),dict(p=32,i=0,d=32));self.apply()
    def save(self):
        if self.motor is None:return
        try:
            save_favorite(ROOT/'shared/hardware/joint_pid_favorites.json',self.sid.get(),dict(self.desired(),speed=1),self.motor.tuning_view())
            self.notice.set(f'บันทึกชุดที่คุณเลือกว่าดีของมอเตอร์ {self.sid.get()} แล้ว')
        except (ValueError,OSError) as error:self.notice.set(str(error))
    def render_settings(self):
        if hasattr(self,'settings') and self.motor is not None:
            d=describe(self.motor.snapshot_view(),self.motor.tuning_view(),self.desired(),self.sid.get())
            self.settings.configure(text=d['settings'],foreground='#17603d' if d['applied'] else '#9c5b13')
    def toggle_details(self):
        if self.details_visible.get():self.details.pack(fill='x',pady=(8,0))
        else:self.details.pack_forget()
    def close(self):
        if self.closing:return
        self.closing=True
        if self.motor is None and not self.connecting:self.root.destroy();return
        if self.motor is not None:
            motor=self.motor;self.motor=None
            def work():
                try:motor.close();self.results.put(('closed',None))
                except Exception as error:self.results.put(('close_error',str(error)))
            threading.Thread(target=work,name='manual-close',daemon=False).start()
    def poll(self):
        while not self.results.empty():
            kind,value=self.results.get()
            if kind=='connected':
                self.connecting=False;self.motor=value;self.notice.set('')
                if self.closing:self.closing=False;self.close()
            elif kind=='closed':self.root.destroy();return
            elif kind=='close_error':self.notice.set('หยุดไม่สำเร็จ: รองรับโคมและใช้สวิตช์ตัดไฟ');self.closing=False
            elif kind=='error':
                self.connecting=False;self.notice.set('เชื่อมต่อไม่สำเร็จ ตรวจไฟเลี้ยง/สาย หรือเปิดรายละเอียด');self.details.configure(state='normal');self.details.delete('1.0','end');self.details.insert('1.0',value);self.details.configure(state='disabled')
                if self.closing:self.root.destroy();return
        state={'state':'IDLE'};tuning={'applied':{},'joint_id':self.sid.get(),'status':''}
        if self.motor is not None:
            self.motor.poll();state=self.motor.snapshot_view();tuning=self.motor.tuning_view()
            live=tuning['joint_id']
            if self.pending_select==live:self.pending_select=None;self.notice.set('')
            elif self.pending_select is not None and tuning['status'].startswith('Wait for move'):
                self.pending_select=None;self.notice.set('รอมอเตอร์หยุด หรือกดหยุดก่อนเปลี่ยนข้อ')
            if self.loaded!=live and tuning['applied']:
                self.sid.set(live);self.set_sliders(live,tuning['applied']);self.loaded=live
            elif self.sid.get()!=live and self.pending_select is None:self.sid.set(live)
            if self.details_visible.get():
                self.details.configure(state='normal');self.details.delete('1.0','end');self.details.insert('1.0',json.dumps(dict(state=state,tuning=tuning),ensure_ascii=False,indent=2));self.details.configure(state='disabled')
        d=describe(state,tuning,self.desired(),self.sid.get())
        self.title.configure(text='กำลังเชื่อมต่อ…' if self.connecting else 'กำลังเลือกมอเตอร์…' if self.pending_select is not None else d['title'],bg=d['color']);self.message.configure(text=d['message'],bg=d['color']);self.status_box.configure(bg=d['color'])
        self.settings.configure(text=d['settings'] if self.motor else 'เลื่อนค่าได้ เมื่อเชื่อมต่อจะอ่านค่าที่มอเตอร์ใช้อยู่จริง',foreground='#17603d' if d['applied'] else '#9c5b13')
        connected=self.motor is not None and state.get('state')!='FAULT' and not self.closing
        self.connect_btn.configure(text='เชื่อมต่อใหม่' if state.get('state')=='FAULT' else 'เชื่อมต่อแล้ว' if connected else 'เริ่มใช้งาน',state='disabled' if self.connecting or connected else 'normal')
        self.normal_btn.configure(state='normal' if connected else 'disabled',text='หยุดจัดท่า' if state.get('state')=='NORMAL_STARTUP' else 'กลับกลาง' if state.get('state')=='READY' else 'จัดท่าเริ่มต้น')
        for b in (self.apply_btn,self.restore_btn,self.save_btn):b.configure(state='normal' if connected and self.pending_select is None else 'disabled')
        for b in self.moves:b.configure(state='normal' if connected and self.pending_select is None and state.get('state')=='READY' else 'disabled')
        self.root.after(60,self.poll)


def run(profile):
    import tkinter as tk
    from tkinter import ttk
    import signal
    root=tk.Tk();app=SimpleTuner(root,tk,ttk,profile)
    signal.signal(signal.SIGTERM,lambda *args:root.after(0,app.close))
    root.mainloop()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,default=ROOT/'bio_inspire/hardware/manual_joint_tuning.json')
    parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    if args.live:run(args.profile)
    else:parser.print_help()
