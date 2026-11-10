from pathlib import Path
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE=Path(__file__).resolve().parent/'LeLamp_Experimental_Results_Normal_Pilot_20261104_05'
OUT=BASE/'PNG'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':13,'axes.spines.top':False,'axes.spines.right':False,'axes.titlesize':15,'axes.labelsize':13,'legend.fontsize':11,'lines.linewidth':2})
COLORS={'C0':'#2563AB','C1':'#D76819'}
def read(name):
    with (BASE/'CSV'/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def nums(rows,key):return [float(r[key]) if r[key] else float('nan') for r in rows]
def layout(title,rows=1):
    fig,axs=plt.subplots(rows,1,figsize=(12.8,7.2),squeeze=False)
    fig.subplots_adjust(left=.10,right=.96,bottom=.17,top=.84,hspace=.42)
    fig.suptitle(title,x=.10,ha='left',fontsize=21,fontweight='bold',y=.96)
    fig.text(.10,.895,'Normal hardware pilot | comparison_r01 | 4 Nov 2026 | C0 / C1: 50 s each',fontsize=11,color='#52606D')
    for ax in axs[:,0]:ax.grid(alpha=.18);ax.set_axisbelow(True)
    return fig,list(axs[:,0])
def save(fig,name,note):
    fig.text(.10,.055,note,fontsize=10,color='#52606D',va='bottom')
    fig.savefig(OUT/name,dpi=300,facecolor='white');plt.close(fig)

fig,axes=layout('C0 vs C1: Phi over Time')
ax=axes[0]
for c in ('C0','C1'):
    rs=read('01_phi_'+c+'.csv')
    key=next(k for k in rs[0] if k.startswith('Phi'))
    ax.plot(nums(rs,'Time (s)'),nums(rs,key),label=c,color=COLORS[c])
ax.set(xlabel='Elapsed time from each trial start (s)',ylabel='Phi (rad / update)',xlim=(0,50.1))
ax.legend(loc='upper right')
save(fig,'01_C0_C1_Phi.png','Recorded-input replay on hardware; logged runtime phi. Each trial uses its own elapsed timestamps.\nNo row-index pairing or resampling; smaller phi steps do not establish smoother motor motion.')

def motor(conditions,name):
    fig,axes=layout('ID2: Motor Command vs Encoder Feedback',len(conditions))
    for c,ax in zip(conditions,axes):
        rs=read('02_motor_ID2_'+c+'.csv');t=nums(rs,'Time (s)')
        ax.plot(t,nums(rs,'Commanded Position (ticks)'),label='Command (sent-goal cache)',color='#2563AB')
        ax.plot(t,nums(rs,'Actual Encoder Position (ticks)'),label='Encoder feedback',color='#BD3C3C',linewidth=1.6)
        ax.set(xlim=(0,50.1),ylim=(2819,2862),ylabel='Position (raw ticks)')
        ax.set_title(c,loc='left',fontweight='bold');ax.legend(loc='lower left',ncol=2)
    axes[-1].set_xlabel('Owner snapshot elapsed time (s)')
    save(fig,name,'STS3215 ID2 | 4096 ticks = 360 degrees. C0 and C1 are separate runs of the same pilot version.\nCommand and feedback are not simultaneous samples; raw encoder timestamps are retained in CSV.')
motor(('C0','C1'),'02_ID2_Command_Feedback.png')
motor(('C0',),'02_ID2_C0.png');motor(('C1',),'02_ID2_C1.png')

fig,axes=layout('Stimulus S vs Hormone H: C1')
ax=axes[0];rs=read('03_stimulus_hormone_C1.csv');t=nums(rs,'Time (s)')
ax.step(t,nums(rs,'S'),where='post',label='S (recorded replay input)',color='#64748B',linewidth=1.6)
ax.plot(t,nums(rs,'H'),label='H (logged hormone model)',color=COLORS['C1'])
ax.set(xlabel='Elapsed time from C1 trial start (s)',ylabel='Normalized S / H',xlim=(0,50.1),ylim=(-.04,1.10));ax.legend(loc='upper left')
save(fig,'03_Stimulus_Hormone_C1.png','Hardware pilot with recorded-input replay (R08, source 80–130 s); not a simulation-only trial.\nH is a runtime model state, not a physical hormone measurement. Lines connect logged snapshots.')

fig,axes=layout('CPG Period and Cycle-to-Cycle Delta T',2)
for c in ('C0','C1'):
    rs=read('04_cpg_periods_'+c+'.csv');t=nums(rs,'Time (s)')
    axes[0].plot(t,nums(rs,'Period (s)'),marker='o',label=c,color=COLORS[c])
    axes[1].plot(t,nums(rs,'Delta T (s)'),marker='o',label=c,color=COLORS[c])
axes[0].set_ylabel('Period T (s)');axes[1].set_ylabel('Absolute Delta T (s)')
for ax in axes:ax.legend(loc='upper right');ax.set_xlim(0,51)
axes[1].set_xlabel('Cycle end time: CPG logical output clock (s)')
save(fig,'04_CPG_Period_DeltaT.png','Logical CPG o1, NOT measured motor-motion frequency. Rising crossings use linear interpolation.\n7 complete periods / 6 Delta T pairs per condition; first Delta T is unavailable, not zero.')
print('Rendered 6 PNGs at 3840 x 2160 pixels, 300 dpi')
