"""One OpenCV window: stage sliders, explicit apply, and readback display.

UI callbacks never touch UART. Motor requests go to the existing owner mailbox.
"""
from manual_tuning import BOUNDS,DEFAULTS,validate_values,bounds_for,defaults_for

class TuningPanel:
    def __init__(self,cv2,window,initial=None,target_id=1,manual_joints=False):
        self.target_id=target_id;self.bounds=bounds_for(target_id);self.defaults=defaults_for(target_id)
        self.cv=cv2;self.window=window;self.actions=[];self.status='M: start Normal; V/A can pause startup to tune' if manual_joints else 'M: start Normal, then G: follow'
        initial=validate_values(initial,target_id) if initial is not None else self.defaults
        self.labels={k:f'{k.upper()} [{a}..{b}]' for k,(a,b) in self.bounds.items()}
        for k,(low,high) in self.bounds.items():
            cv2.createTrackbar(self.labels[k],window,initial[k],high,lambda value:None)
            cv2.setTrackbarMin(self.labels[k],window,low)
        cv2.setMouseCallback(window,self.click)
    def select_joint(self,sid,values):
        if bounds_for(sid)!=self.bounds:raise ValueError('Cannot change panel bounds during selection')
        v=validate_values(values,sid)
        self.target_id=sid;self.defaults=defaults_for(sid)
        for k,value in v.items():self.cv.setTrackbarPos(self.labels[k],self.window,value)
        self.actions=[]
    def values(self):
        return validate_values({k:self.cv.getTrackbarPos(n,self.window) for k,n in self.labels.items()},self.target_id)
    def click(self,event,x,y,flags,param):
        if event!=self.cv.EVENT_LBUTTONDOWN or not 430<=y<=470:return
        if 10<=x<=200:self.actions=['apply']
        elif 220<=x<=410:self.actions=['restore']
        elif 430<=x<=630:self.actions=['hold']
    def dispatch(self,key,motor):
        actions=self.actions;self.actions=[]
        if key==ord('a'):actions=['apply']
        elif key==ord('v'):actions=['restore']
        # Never dispatch a pending click on the same frame as stop/quit.
        if key in (ord('h'),32,ord('q'),27):actions=[]
        for action in actions:
            if action=='hold':
                if motor is not None:motor.key(ord('h'))
                continue
            if action=='restore':
                for k,v in self.defaults.items():self.cv.setTrackbarPos(self.labels[k],self.window,v)
            if motor is not None:
                if getattr(motor,'joint_mode',False):motor.request_joint_tuning(self.target_id,self.values())
                else:motor.request_tuning(self.values())
            else:self.status='Press M to connect before Apply'
    def draw(self,image,motor):
        cv=self.cv
        canvas=cv.copyMakeBorder(cv.resize(image,(640,360)),0,145,0,0,cv.BORDER_CONSTANT,value=(25,25,25))
        v=self.values();text=' '.join(f'{k.upper()}={v[k]}' for k in ('p','i','d','speed'))
        cv.putText(canvas,'STAGED: '+text,(10,382),cv.FONT_HERSHEY_SIMPLEX,.5,(0,220,255),1)
        view=motor.tuning_view() if motor is not None else dict(applied={},status=self.status)
        applied=view['applied']
        text=' '.join(f'{k.upper()}={applied.get(k,"?")}' for k in ('p','i','d','speed'))
        cv.putText(canvas,'READBACK: '+text,(10,404),cv.FONT_HERSHEY_SIMPLEX,.5,(110,255,150),1)
        cv.putText(canvas,view['status'][:75],(10,424),cv.FONT_HERSHEY_SIMPLEX,.45,(220,220,220),1)
        for x1,x2,label,color in [(10,200,'APPLY (A)',(50,100,50)),(220,410,'RESTORE (V)',(90,70,30)),(430,630,'HOLD (H)',(30,70,150))]:
            cv.rectangle(canvas,(x1,430),(x2,470),color,-1)
            cv.putText(canvas,label,(x1+14,455),cv.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),1)
        cv.putText(canvas,f'ID{self.target_id} | '+('Speed/acc fixed1 | U/K/J: move | Q:exit' if self.target_id!=1 else 'Speed: raw (deg/s uncalibrated) | Q:hold+exit'),
                   (10,495),cv.FONT_HERSHEY_SIMPLEX,.42,(210,210,210),1)
        return canvas
