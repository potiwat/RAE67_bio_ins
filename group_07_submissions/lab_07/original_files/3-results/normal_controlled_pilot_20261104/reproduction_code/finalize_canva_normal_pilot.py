from pathlib import Path
import csv,json,hashlib,shutil,zipfile
from PIL import Image

ROOT=Path(__file__).resolve().parent
P=ROOT/'LeLamp_Experimental_Results_Normal_Pilot_20261104_05'
def read(name):
    with (P/'CSV'/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
checked=0
for c in ('C0','C1'):
    data=json.loads((P/'raw_sources'/f'{c.lower()}_r01'/f'last_normal_measurement_{c}.json').read_text())
    rows=read(f'01_phi_{c}.csv');assert len(rows)==len(data['trace'])
    for r,s in zip(rows,data['trace']):
        a=s['rhythm']['normal_ahm']
        for k,v in [('Time (s)',s['elapsed_s']),(f'Phi {c} (rad/update)',a['phi']),('Stimulus S',a['stimulus']),('Hormone H',a['h'])]:assert float(r[k])==v
        checked+=1
    for sid in (2,3):
        motors=read(f'02_motor_ID{sid}_{c}.csv');assert len(motors)==len(rows)
        for r,s in zip(motors,data['trace']):
            fb=next(x for x in s['rows'] if x['id']==sid)
            assert float(r['Commanded Position (ticks)'])==s['command_goals'][str(sid)]
            assert float(r['Actual Encoder Position (ticks)'])==fb['position_raw']
            assert float(r['Encoder Sample Clock MONOTONIC (s)'])==fb['sampled_monotonic_s']
            checked+=1
    periods=read(f'04_cpg_periods_{c}.csv');assert len(periods)==7 and periods[0]['Delta T (s)']==''
    for i in range(1,7):assert float(periods[i]['Delta T (s)'])==abs(float(periods[i]['Period (s)'])-float(periods[i-1]['Period (s)']))
pngs=list((P/'PNG').glob('*.png'));assert len(pngs)==6
for f in pngs:
    with Image.open(f) as im:assert im.size==(3840,2160);im.verify()
(P/'SLIDE_NOTES_EN.md').write_text('''# Slide-ready notes

**Dataset:** Normal controlled hardware pilot, comparison_r01, recorded on 4 November 2026. One paired 50 s C0/C1 trial; same recorded-input replay. These are not the later six-emotion trials.

1. **Phi over time:** C0 follows the replay stimulus directly; C1 changes phi through the logged hormone model. Maximum observed adjacent-snapshot phi step: C0 0.030000; C1 0.002553 rad/update. Snapshot intervals vary.
2. **Command vs encoder:** ID2 has complete command and feedback fields in both conditions (652 C0 / 659 C1 snapshots). Positions are raw ticks. Command and feedback are not simultaneous measurements. The visible command/feedback mismatch does not identify a unique mechanical or control cause.
3. **Stimulus and hormone:** Recorded hardware input was replayed; H is the runtime model state. H persists and decays after S returns to zero. It is not a measured biological hormone.
4. **Period / Delta T:** Values use the logical CPG o1 clock, not motor-motion frequency. Mean Delta T: C0 0.428482 s; C1 0.460994 s. Maximum Delta T: C0 1.109319 s; C1 1.325658 s. Mean frequency (1/mean period): C0 0.155311 Hz; C1 0.155429 Hz. Seven periods / six differences per condition.

**Supported conclusion:** C1 reduced the size of observed phi steps in this pilot. It did not reduce mean cycle-to-cycle Delta T. Physical motor smoothness was not established.

**Limits:** One pair; different initial encoder positions; irregular recording intervals; skipped reference indices and unlogged CPG nodes; no motor jerk or physical frequency measurement. Do not label this as a 91.5% improvement in motor smoothness, a statistical result, or a test of the latest Happy/Angry motion.

**Canva:** Upload the PNGs directly to preserve the actual numeric time axes. CSVs retain each condition's own timestamps; do not pair rows by index or force a categorical equally spaced time axis.
''',encoding='utf-8')
code=P/'reproduction_code';code.mkdir(exist_ok=True)
for name in ('build_canva_normal_pilot.py','plot_canva_normal_pilot.py','finalize_canva_normal_pilot.py'):shutil.copy2(ROOT/name,code/name)
(code/'README.md').write_text('Export/finalize scripts were run from bio_inspire/results in the original project layout. The plot script reads the exported CSVs; set BASE to the extracted package folder to rerender elsewhere. Archived original metric analysis and deployed runtime/config are in raw_sources. Export uses Python standard library; plotting uses matplotlib; image checks use Pillow. No script controls hardware.\n',encoding='utf-8')
audit={'status':'PASS','exact_export_rows_checked':checked,'png_count':6,'png_dimensions':[3840,2160],'period_counts':{'C0':7,'C1':7},'first_delta_t_blank':True,'visual_review':'All 6 graphs reviewed via contact sheet; English labels, no clipping','source_metrics_recomputed_match':True}
(P/'EXPORT_VERIFICATION.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
manifest={f.relative_to(P).as_posix():sha(f) for f in sorted(P.rglob('*')) if f.is_file() and f.name!='MANIFEST_SHA256.json'}
(P/'MANIFEST_SHA256.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
archive=Path(shutil.make_archive(str(P),'zip',root_dir=P.parent,base_dir=P.name))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for name,digest in manifest.items():assert hashlib.sha256(z.read(P.name+'/'+name)).hexdigest()==digest
archive.with_suffix('.zip.sha256').write_text(sha(archive)+'  '+archive.name+'\n',encoding='utf-8')
print(json.dumps({'verification':audit,'manifest_files':len(manifest),'zip':str(archive),'zip_bytes':archive.stat().st_size,'zip_sha256':sha(archive)},indent=2))
