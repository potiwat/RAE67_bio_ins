"""Plots for the 180-second paired real-lamp study. No substitute or simulated waveform."""
from pathlib import Path
from statistics import mean
import csv
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MultipleLocator, FormatStrFormatter

from .hormone_response import write_csv, STATES

COLOR={"C0":"#1862AF","C1":"#C95315"}
GREY="#E9EBED"
DARK="#192735"
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.spines.top":False,
                     "axes.spines.right":False,"axes.labelcolor":DARK,"xtick.color":DARK,
                     "ytick.color":DARK,"axes.edgecolor":"#94A0A8","savefig.facecolor":"white",
                     "svg.fonttype":"none","axes.labelsize":10,"legend.frameon":False})
def legend(band_label="Touch held (42–59 s)"):
    return [Line2D([0],[0],color=COLOR[c],lw=2.6,label=s) for c,s in
            (("C0","C0  Direct input"),("C1","C1  Hormone"))]+[Patch(facecolor=GREY,label=band_label)]

def style(ax):
    ax.set_axisbelow(True)
    ax.grid(axis="y",color="#D9DEE2",lw=.6)
    ax.tick_params(length=3)
    ax.spines["bottom"].set_linewidth(.7)
    ax.spines["left"].set_linewidth(.7)

def header(fig,title,subtitle):
    fig.text(.12,.973,title,fontweight="bold",fontsize=17,color=DARK,va="top")
    fig.text(.12,.927,subtitle,fontsize=9.6,color="#475762",va="top")

def numeric(rows,x):return np.array([float(row[x]) for row in rows])

def recorded_window(rows, clock, start, end):
    """Include the nearest real sample outside each edge so the axes can clip the traces."""
    times=numeric(rows,clock)
    if not np.isfinite(times).all() or np.any(np.diff(times)<0):
        raise ValueError(f"Invalid time order on {clock}")
    left=max(0,int(np.searchsorted(times,start,side="left"))-1)
    right=int(np.searchsorted(times,end,side="right"))+1
    return rows[left:right]

def valid_parameter(rows, field):
    return np.array([float(row[field]) if row["valid"]=="1" else np.nan for row in rows])

def happy_interval(r):
    return [row for row in r["ctrl"] if 39<=float(row["t"])<=r["leave"] and row["valid"]=="1"
            and row["fsm"]==row["behavior"]=="happy" and row["selected"]=="happy"]

def breaks_plot(ax,t,y,**kwargs):
    t,y=np.asarray(t,dtype=float),np.asarray(y,dtype=float)
    if len(t)<1:return
    splits=np.where((np.diff(t)>.3)|(np.diff(t)<0))[0]+1
    for group in np.split(np.arange(len(t)),splits):
        if len(group):ax.plot(t[group],y[group],**kwargs)

def time_figure(path,runs):
    fig,axs=plt.subplots(4,1,figsize=(8.15,7.45),sharex=True)
    fig.subplots_adjust(left=.14,right=.975,top=.818,bottom=.10,hspace=.17)
    onset,release=runs[0]["id"]["script"]["touch"][0]
    start,end=onset-3,release+8
    header(fig,"From touch to the lamp’s dance","Pair 1  ·  Touch starts at 42 s and ends at 59 s on the trial clock")
    fig.legend(handles=legend(),loc="upper left",bbox_to_anchor=(.113,.90),ncol=3,fontsize=9)
    for ax in axs:
        style(ax);ax.axvspan(onset,release,color=GREY,zorder=-2);ax.set_xlim(start,end)
    for r in runs:
        c=r["condition"];col=COLOR[c]
        ctrl=recorded_window(r["ctrl"],"t",start,end)
        bank=recorded_window(r["ctrl"],"happy_t",start,end)
        width=2.4 if c=="C0" else 1.6
        for ax,field in ((axs[0],"R"),(axs[1],"happy_phi")):
            breaks_plot(ax,numeric(ctrl,"t"),valid_parameter(ctrl,field),color=col,lw=width,drawstyle="steps-post")
        breaks_plot(axs[2],numeric(bank,"happy_t"),numeric(bank,"happy_o1"),color=col,lw=1.6)
        motors=r["feedback"]
        q=recorded_window([v for v in motors if v["joint"]=="1"],"t",start,end)
        center=np.median([float(v["encoder_deg"]) for v in q if 45<=float(v["t"])<release
                          and v["status"]=="0" and v["torque"]=="1" and v["behavior"]==v["fsm"]=="happy"])
        yaw=np.array([float(v["encoder_deg"])-center if v["status"]=="0" and v["torque"]=="1" else np.nan for v in q])
        breaks_plot(axs[3],numeric(q,"t"),yaw,color=col,lw=1.6)
        if c=="C1":
            for lev,xtext,ytext in ((.5,release+2.2,.1280),(.1,release+4,.1235)):
                ref=next(v for v in r["levels"] if v["level_ref"]==lev)
                x=ref["t_s"]
                for ax,y in ((axs[0],ref["H"]),(axs[1],ref["phi"])):
                    ax.plot(x,y,"o",ms=4,mec=col,mfc="white",mew=1.2,zorder=5)
                axs[1].annotate(f"H ≈ {lev:.2f}",(x,ref["phi"]),xytext=(xtext,ytext),
                                fontsize=8,color=col,arrowprops={"arrowstyle":"-","color":col,"lw":.8})
    for ax,label in zip(axs,["Drive R\n(unitless)","Happy-bank φ\n(rad/update)","Happy-bank o₁\n(unitless)","Base yaw ID1\n(degrees)"]):
        ax.set_ylabel(label)
    axs[0].set_ylim(-.08,1.12);axs[1].yaxis.set_major_formatter(FormatStrFormatter("%.3f"))
    axs[-1].set_xticks([39,42,46,50,54,59,63,67]);axs[-1].set_xlabel("Time from measurement start (s)")
    fig.savefig(path,dpi=200);plt.close(fig)

def pairs_figure(path,runs):
    fig,axes=plt.subplots(3,3,figsize=(8.65,6.4),sharex=True,sharey="row")
    fig.subplots_adjust(left=.122,right=.98,top=.76,bottom=.13,hspace=.23,wspace=.10)
    onset,release=runs[0]["id"]["script"]["touch"][0]
    start,end=release-5,release+7
    header(fig,"How the rhythm slows after touch ends","Touch ends at 59 s in every pair  ·  Longer period = slower rhythm")
    fig.legend(handles=legend(),loc="upper left",bbox_to_anchor=(.11,.895),ncol=3,fontsize=9)
    for col in range(3):
        for ax in axes[:,col]:
            style(ax);ax.axvspan(max(start,onset),release,color=GREY,zorder=-2);ax.set_xlim(start,end)
        axes[0,col].set_title("Pair "+str(col+1),fontsize=11,weight="bold",loc="left",pad=5)
    for r in runs:
        col=r["pair"]-1;c=r["condition"];clr=COLOR[c];marker="o" if c=="C0" else "^"
        q=happy_interval(r)
        breaks_plot(axes[0,col],numeric(q,"t"),numeric(q,"happy_phi"),color=clr,lw=2,drawstyle="steps-post" if c=="C0" else "default")
        for i,rows,key in ((1,[v for v in r["cycles"] if v["state"]=="happy"],"T_cpg_s"),
                           (2,r["swings"],"T_dance_s")):
            z=[v for v in rows if start-3<=v["end_s"]<=end]
            axes[i,col].plot([v["end_s"] for v in z],[v[key] for v in z],color=clr,
                             lw=1.4,marker=marker,mfc="white" if c=="C0" else clr,ms=4.3)
    for ax,lab in zip(axes[:,0],["Happy φ\n(rad/update)","CPG period\n(s/cycle)","ID1 yaw period\n(s/cycle)"]):ax.set_ylabel(lab)
    axes[0,0].set_ylim(.116,.132);axes[0,0].set_yticks([.118,.124,.130]);axes[0,0].yaxis.set_major_formatter(FormatStrFormatter("%.3f"))
    axes[1,0].set_ylim(2.78,3.19);axes[2,0].set_ylim(2.42,2.88)
    for ax in axes[-1]:ax.set_xticks([55,59,62,65])
    fig.text(.55,.052,"Time from measurement start (s)",ha="center",fontsize=11)
    fig.savefig(path,dpi=200);plt.close(fig)

def state_figure(path,runs):
    fig,axes=plt.subplots(3,1,figsize=(8.45,6.35),sharex=True,gridspec_kw={"height_ratios":[.95,1,1.48]})
    fig.subplots_adjust(left=.14,right=.975,top=.755,bottom=.125,hspace=.22)
    header(fig,"Which input changed the lamp’s behavior?","Pair 1  ·  Read down each band from the input to the CPG setting and the observed state")
    items=legend()[:2]+[Patch(facecolor=GREY,label="Scripted input on")]
    fig.legend(handles=items,loc="upper left",bbox_to_anchor=(.115,.89),ncol=3,fontsize=9)
    schedule=runs[0]["id"]["script"]
    groups=[("Base button",schedule["button"]),("Touch held",schedule["touch"][:1]),
            ("3 touch taps",schedule["touch"][1:]),("Near signal",schedule["near"])]
    for title,intervals in groups:
        a,b=intervals[0][0],intervals[-1][1]
        axes[0].text((a+b)/2,1.08,f"{title}\n{a:g}–{b:g} s",transform=axes[0].get_xaxis_transform(),
                     ha="center",va="bottom",fontsize=8.8,color=DARK,linespacing=1.12)
    yy={s:i for i,s in enumerate(STATES)}
    for ax in axes:
        style(ax);ax.set_xlim(0,180)
        for _,intervals in groups:
            for a,b in intervals:ax.axvspan(a,b,color=GREY,zorder=-2)
    for r in runs:
        c=r["condition"];color=COLOR[c];rows=r["ctrl"];t=numeric(rows,"t")
        # phi_selected is already the value of the current bank at each timestamp.
        # Keeping acquisition order preserves real jumps when that bank changes.
        for ax,field in ((axes[0],"R"),(axes[1],"phi_selected")):
            breaks_plot(ax,t,valid_parameter(rows,field),color=color,lw=2.35 if c=="C0" else 1.40,drawstyle="steps-post")
        offset=.075 if c=="C1" else -.075
        breaks_plot(axes[2],t,np.asarray([yy[v['fsm']]+offset for v in rows]),color=color,lw=1.28,drawstyle="steps-post")
    axes[0].set_ylabel("Drive R\n(unitless)");axes[1].set_ylabel("Selected φ\n(rad/update)")
    axes[2].set_yticks(range(6),[s.title() for s in STATES],fontsize=9);axes[2].set_ylim(-.36,5.45)
    axes[-1].set_xticks(np.arange(0,181,20));axes[-1].set_xlabel("Time from measurement start (s)")
    fig.savefig(path,dpi=200);plt.close(fig)

def make_figures(dest,all_runs):
    figs=dest/"Figures";figs.mkdir(parents=True,exist_ok=True)
    one=[r for r in all_runs if r["pair"]==all_runs[0]["pair"]]
    if one[0]["pair"]==1:
        time_figure(figs/"01_Happy_input_CPG_and_encoder.png",one)
        state_figure(figs/"03_Six_state_timeline.png",one)
    if {r["pair"] for r in all_runs}=={1,2,3}:pairs_figure(figs/"02_Touch_release_all_pairs.png",all_runs)
    records=[]
    for r in all_runs:
        for stage in ("ON","OFF"):
            cs=[v["T_cpg_s"] for v in r["cycles"] if v["state"]=="happy" and
                (v["start_s"]>=42 and v["end_s"]<=59 if stage=="ON" else v["start_s"]>=59 and v["end_s"]<=r["leave"])]
            swing=[v["T_dance_s"] for v in r["swings"] if v["stage"]==stage]
            records.append(dict(pair=r["pair"],condition=r["condition"],stage=stage,CPG_cycles=len(cs),
                                mean_CPG_period_s=mean(cs) if cs else None,encoder_cycles=len(swing),
                                mean_ID1_period_s=mean(swing) if swing else None))
    write_csv(dest/"real_robot"/"summary"/"Happy_ON_OFF_periods.csv",records)
