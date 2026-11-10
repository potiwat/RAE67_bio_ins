from pathlib import Path
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

p=Path(__file__).resolve().parent
with (p/'HAPPY_PAIR_METRICS.csv').open(encoding='utf-8-sig',newline='') as f:data=list(csv.DictReader(f))
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(1,2,figsize=(9,3.7))
for ax,key,label in zip(axes,['frequency_hz','delta_t_mean_s'],['CPG frequency (Hz)','Mean cycle-to-cycle Delta T (s)']):
 for offset,c,color in [(-.18,'C0','#2563AB'),(.18,'C1','#D76819')]:
  values=[float(next(r for r in data if r['pair']==pair and r['condition']==c)[key]) for pair in ('P1','P2','P3')]
  bars=ax.bar([i+offset for i in range(3)],values,width=.34,label=c,color=color)
  for bar,v in zip(bars,values):ax.text(bar.get_x()+bar.get_width()/2,v+.003,f'{v:.3f}',ha='center',va='bottom',fontsize=10)
 ax.set_xticks(range(3),['P1','P2','P3']);ax.set_xlabel('Hardware trial pair');ax.set_ylabel(label)
 ax.set_ylim(0,.40);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
fig.suptitle('Happy: recorded CPG logical output metrics on real hardware',fontsize=12,y=.99)
fig.legend(*axes[0].get_legend_handles_labels(),frameon=False,ncol=2,loc='upper center',bbox_to_anchor=(.5,.92))
fig.tight_layout(rect=(0,0,1,.84))
fig.savefig(p/'HAPPY_PAIR_COMPARISON.png',dpi=300,facecolor='white')
print(p/'HAPPY_PAIR_COMPARISON.png')
