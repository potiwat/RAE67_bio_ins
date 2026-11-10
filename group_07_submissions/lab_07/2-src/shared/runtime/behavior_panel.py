"""Buttons submit explicit behavior requests; the motor worker owns execution."""
class BehaviorPanel:
    def __init__(self,cv2,window,cpg_amplitude=None,afraid_enabled=False,automatic=False,simple=False):
        self.cv2=cv2;self.width=0;self.top=0;self.pending=None;self.normal_key=ord('m')
        self.automatic=automatic;self.simple=simple;self.button_height=60 if simple else 44
        self.cpg_amplitude=None if automatic else cpg_amplitude;self.cpg_sent=None;self.cpg_owner=None
        self.afraid_enabled=afraid_enabled
        cv2.setMouseCallback(window,self.click)
    def click(self,event,x,y,flags,param):
        if self.cpg_amplitude is not None and self.width>32 and self.top+44<=y<self.top+104:
            if event in (self.cv2.EVENT_LBUTTONUP,getattr(self.cv2,'EVENT_LBUTTONDOWN',1)) or (event==getattr(self.cv2,'EVENT_MOUSEMOVE',0) and flags&1):
                self.cpg_amplitude=(10+round(20*max(0.,min(1.,(x-16)/(self.width-32)))))/10
            return
        if event!=self.cv2.EVENT_LBUTTONUP or not 0<=x<self.width or not self.top<=y<self.top+self.button_height:return
        keys=(self.normal_key,ord('i'),ord('d'),ord('s'))+((ord('f'),) if self.afraid_enabled else ())+(ord('h'),)
        if self.automatic:keys=(ord('m'),ord('h'))
        self.pending=keys[min(len(keys)-1,x*len(keys)//self.width)]
    def take(self,key):
        if self.pending is None:return key
        result=self.pending;self.pending=None;return result
    def dispatch(self,motor):
        if motor is None or self.cpg_amplitude is None:return
        if motor is not self.cpg_owner or self.cpg_sent!=self.cpg_amplitude:
            if motor.request_rhythm_amplitude(self.cpg_amplitude):self.cpg_sent=self.cpg_amplitude;self.cpg_owner=motor
    def draw(self,image,motor):
        cv=self.cv2;self.top,self.width=image.shape[:2]
        ready=motor is not None and motor.ready()
        self.normal_key=ord('n') if ready and not self.automatic else ord('m')
        out=cv.copyMakeBorder(image,0,104 if self.cpg_amplitude is not None else self.button_height,0,0,cv.BORDER_CONSTANT,value=(35,35,35))
        labels=('NORMAL','INTERESTED','HAPPY:TOUCH','SLEEPY')+(('AFRAID',) if self.afraid_enabled else ())+('STOP',)
        if self.automatic:labels=('START','STOP') if self.simple else ('START AUTO','STOP')
        for i,label in enumerate(labels):
            left=i*self.width//len(labels);right=(i+1)*self.width//len(labels)-2
            color=(50,70,170) if label=='STOP' else (75,95,65)
            cv.rectangle(out,(left,self.top+3),(right,self.top+self.button_height-3),color,-1)
            cv.putText(out,label,(left+12,self.top+(38 if self.simple else 28)),cv.FONT_HERSHEY_SIMPLEX,.62 if self.simple else .34,(255,255,255),1)
        if self.cpg_amplitude is not None:
            view={} if motor is None else motor.rhythm_view()
            current=view.get('amplitude_deg_limit')
            text=f'Normal CPG size: {self.cpg_amplitude:.1f} deg'
            if current is not None:text+=f' | now {current:.1f}'
            ids=view.get('active_joint_ids')
            if ids and len(ids)==1:text+=f' | ID{ids[0]}'
            cv.putText(out,text,(8,self.top+60),cv.FONT_HERSHEY_SIMPLEX,.34,(255,255,255),1)
            y=self.top+78;right=self.width-16
            cv.line(out,(16,y),(right,y),(160,160,160),3)
            x=16+round((self.cpg_amplitude-1)/2*(self.width-32))
            cv.circle(out,(x,y),6,(80,220,230),-1)
            cv.putText(out,'1.0          drag to adjust          3.0',(8,self.top+99),cv.FONT_HERSHEY_SIMPLEX,.30,(210,210,210),1)
        return out
