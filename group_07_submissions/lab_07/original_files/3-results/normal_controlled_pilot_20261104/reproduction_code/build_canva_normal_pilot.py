"""Export only the archived Normal comparison_r01 hardware pair for slides."""
from pathlib import Path
import csv,hashlib,json,math,statistics,shutil,tarfile,sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bio_inspire.experiments.normal_controlled_analysis import verify_pair,summarize,cpg_samples
SRC=ROOT/'bio_inspire/results/normal_controlled_20261104'
OUT=ROOT/'bio_inspire/results/LeLamp_Experimental_Results_Normal_Pilot_20261104_05'
for folder in ('CSV','PNG','raw_sources','raw_sources/comparison_r01','raw_sources/deployment'):(OUT/folder).mkdir(parents=True,exist_ok=True)

def write(name,rows):
    keys=list(rows[0])
    with (OUT/'CSV'/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

data={};stats={};files={};coverage=[];phi_series={};motor_series={};period_series={};node_series={}
archived=json.loads((SRC/'comparison_r01/metrics.json').read_text())
for condition in ('C0','C1'):
    case=condition.lower()+'_r01';source=SRC/case/f'last_normal_measurement_{condition}.json'
    manifest=json.loads((SRC/case/'manifest.json').read_text())
    assert sha(source)==manifest[source.name]
    d=json.loads(source.read_text());data[condition]=d
    stats[condition]=summarize(d)
    for key in ('frequency_hz','delta_t_mean_s','delta_t_max_s'):
        assert math.isclose(stats[condition]['cpg_o1_metrics'][key],archived['conditions'][condition]['cpg_o1_metrics'][key],abs_tol=1e-12)
    raw=OUT/'raw_sources'/case;raw.mkdir(exist_ok=True)
    for name in (source.name,'manifest.json','verification.json'):shutil.copy2(SRC/case/name,raw/name)
    files[source.relative_to(ROOT).as_posix()]=sha(source)
    phi=[];motors=[]
    for i,row in enumerate(d['trace']):
        assert math.isclose(row['elapsed_s'],row['time_s']-d['started_s'],abs_tol=1e-9)
        ahm=row['rhythm']['normal_ahm']
        phi.append({'Time (s)':row['elapsed_s'],f'Phi {condition} (rad/update)':ahm['phi'],
                    'Stimulus S':ahm['stimulus'],'Hormone H':ahm['h'],'Condition':condition,
                    'Schedule Index':ahm['schedule_index'],'AHM Selection Elapsed (s)':ahm['elapsed_s'],
                    'Owner Clock BOOTTIME (s)':row['time_s'],'Source Row':i,
                    'Source File':f'raw_sources/{case}/{source.name}',
                    'Data Origin':'Hardware pilot with recorded-input replay; runtime model states'})
        for sid in (2,3):
            found=[x for x in row['rows'] if x['id']==sid]
            valid=len(found)==1 and str(sid) in row['command_goals'] and found[0].get('position_raw') is not None
            coverage.append(dict(condition=condition,servo_id=sid,row=i,complete=valid))
            assert valid
            joint=found[0]
            motors.append({'Time (s)':row['elapsed_s'],'Servo ID':sid,
                'Commanded Position (ticks)':row['command_goals'][str(sid)],
                'Actual Encoder Position (ticks)':joint['position_raw'],'Condition':condition,
                'Goal Register Readback (ticks)':joint['goal_raw'],
                'Owner Clock BOOTTIME (s)':row['time_s'],
                'Encoder Sample Clock MONOTONIC (s)':joint['sampled_monotonic_s'],
                'Source Row':i,'Source File':f'raw_sources/{case}/{source.name}',
                'Data Origin':'Hardware STS3215; command cache and encoder snapshot, not simultaneous physical onset'})
    phi_series[condition]=phi;motor_series[condition]=motors
    write(f'01_phi_{condition}.csv',phi)
    for sid in (2,3):write(f'02_motor_ID{sid}_{condition}.csv',[r for r in motors if r['Servo ID']==sid])
    nodes,missing=cpg_samples(d['trace'])
    node_series[condition]=[{'CPG Logical Output Time (s)':t,'o1':value,'Condition':condition,
        'Clock Definition':'updates * dt_s / time_scale; not encoder-motion time'} for t,value in nodes]
    write(f'04_observed_CPG_nodes_{condition}.csv',node_series[condition])
    periods=[];previous=None
    for i,p in enumerate(stats[condition]['cpg_periods'],1):
        periods.append({'Time (s)':p['end_s'],'Period (s)':p['period_s'],
            'Delta T (s)':'' if previous is None else abs(p['period_s']-previous),
            'Condition':condition,'Period Index':i,'Cycle Start (s)':p['start_s'],
            'Cycle End (s)':p['end_s'],'Cycle Midpoint (s)':p['midpoint_s'],
            'Cycle Frequency (Hz)':p['frequency_hz'],
            'Clock':'CPG logical output time = updates * dt_s / time_scale',
            'Method':'Linear rising zero crossings of observed unique logged o1 nodes; no reconstructed waveform'})
        previous=p['period_s']
    period_series[condition]=periods;write(f'04_cpg_periods_{condition}.csv',periods)

verify_pair(data['C0'],data['C1'])
assert len(phi_series['C0'])==652 and len(phi_series['C1'])==659
assert data['C0']['nominal_input']==data['C1']['nominal_input']
write('01_phi_long_timeseries.csv',[{'Time (s)':r['Time (s)'],'Phi (rad/update)':r[f'Phi {c} (rad/update)'],
     'Stimulus S':r['Stimulus S'],'Hormone H':r['Hormone H'],'Condition':c,
     'Source Row':r['Source Row'],'Source File':r['Source File']} for c in ('C0','C1') for r in phi_series[c]])
write('03_stimulus_hormone_C1.csv',[{'Time (s)':r['Time (s)'],'S':r['Stimulus S'],'H':r['Hormone H'],
    'Phi (rad/update)':r['Phi C1 (rad/update)'],'Condition':'C1','Schedule Index':r['Schedule Index'],
    'Source Row':r['Source Row'],'Source File':r['Source File'],
    'Data Origin':'Hardware pilot: recorded input replay; H is logged model/reference, not a hormone sensor'} for r in phi_series['C1']])
metrics=[]
def metric(name,unit,fn,method,scope='Normal comparison_r01; one pair'):
    metrics.append({'Metric':name,'Unit':unit,'C0':fn('C0'),'C1':fn('C1'),'Method':method,'Scope':scope})
metric('Recorded snapshots','count',lambda c:len(data[c]['trace']),'All stored owner snapshots')
metric('Last recorded elapsed time','s',lambda c:stats[c]['last_elapsed_s'],'Own measurement start aligned to t=0; nominal trial duration 50 s')
metric('Minimum phi','rad/update',lambda c:stats[c]['phi_range'][0],'Minimum logged next-interval phi parameter')
metric('Maximum phi','rad/update',lambda c:stats[c]['phi_range'][1],'Maximum logged next-interval phi parameter')
metric('Max absolute delta phi','rad/update',lambda c:stats[c]['max_phi_step'],'max(abs(phi[i]-phi[i-1])) over adjacent recorded snapshots; irregular callback intervals')
metric('Mean period','s (CPG logical output clock)',lambda c:statistics.mean(r['Period (s)'] for r in period_series[c]),'Arithmetic mean of 7 complete rising-crossing periods')
metric('Mean frequency (1 / mean period)','Hz (CPG logical output clock)',lambda c:stats[c]['cpg_o1_metrics']['frequency_hz'],'1 / arithmetic mean(T); NOT measured motor frequency')
metric('Arithmetic mean of per-cycle frequencies','Hz (CPG logical output clock)',lambda c:statistics.mean(r['Cycle Frequency (Hz)'] for r in period_series[c]),'mean(1/T); distinct from 1/mean(T)')
metric('Mean delta T','s (CPG logical output clock)',lambda c:stats[c]['cpg_o1_metrics']['delta_t_mean_s'],'mean(abs(T[n]-T[n-1])); 6 adjacent period pairs')
metric('Max delta T','s (CPG logical output clock)',lambda c:stats[c]['cpg_o1_metrics']['delta_t_max_s'],'max(abs(T[n]-T[n-1])); 6 adjacent period pairs')
metric('Complete period count','count',lambda c:stats[c]['cpg_o1_metrics']['period_count'],'7 complete periods per condition')
metric('Adjacent period-pair count','count',lambda c:stats[c]['cpg_o1_metrics']['delta_t_count'],'6 differences; first period has no predecessor')
metric('Unique logged CPG nodes','count',lambda c:stats[c]['logged_unique_cpg_nodes'],'Deduplicate repeated update indices')
metric('Unlogged CPG nodes','count',lambda c:stats[c]['unlogged_cpg_nodes'],'Sum of gaps in observed update indices; no nodes fabricated')
metric('Skipped nominal parameter indices','count',lambda c:stats[c]['skipped_nominal_parameter_indices'],'Recorded owner selection skipped indices; fixture still has 1000 reference samples')
metric('Median snapshot interval','s',lambda c:stats[c]['median_record_interval_s'],'Median difference of owner CLOCK_BOOTTIME timestamps')
for sid in (2,3):
    for field,label,unit in [('command_peak_to_peak_deg','Command peak-to-peak','degree'),('actual_peak_to_peak_deg','Encoder peak-to-peak','degree')]:
        metric(f'ID{sid} {label} after 5 s',unit,lambda c,sid=sid,field=field:stats[c]['joints'][str(sid)][field],
               '(max-min) * 360 / 4096; exclude elapsed <5 s for source metric parity')
    for field,label in [('command_range_ticks','Command'),('actual_range_ticks','Encoder')]:
        for k,word in ((0,'min'),(1,'max')):
            metric(f'ID{sid} {label} {word} after 5 s','ticks',lambda c,sid=sid,field=field,k=k:stats[c]['joints'][str(sid)][field][k],
                   'Range over stored snapshots elapsed >=5 s')
    metric(f'ID{sid} Initial encoder','ticks',lambda c,sid=sid:stats[c]['initial_feedback_raw'][str(sid)],'First stored feedback position; not identical across conditions')
write('05_metrics.csv',metrics)
write('05_motor_data_coverage.csv',[{'Condition':c,'Servo ID':sid,'Rows with Command and Encoder':sum(x['complete'] for x in coverage if x['condition']==c and x['servo_id']==sid),
    'Total Rows':len(data[c]['trace']),'Selected for Main Graph':sid==2,
    'Selection Rule':'Both joints 100 percent complete; ID2 chosen by lower-ID tie break, not by apparent result'} for c in ('C0','C1') for sid in (2,3)])
for name in ('metrics.json','REPORT_TH.md','normal_controlled_analysis.py','cpg_periods.csv','trace.csv','manifest.json'):
    shutil.copy2(SRC/'comparison_r01'/name,OUT/'raw_sources/comparison_r01'/name)
deployment=json.loads((SRC/'deployment_manifest.json').read_text())
shutil.copy2(SRC/'deployment_manifest.json',OUT/'raw_sources/deployment/deployment_manifest.json')
for name,expected in deployment['files'].items():
    p=ROOT/name
    if name.endswith('camera_motor.py'):
        with tarfile.open(SRC/'payload.tar') as tar:raw=tar.extractfile(name).read()
    else:raw=p.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==expected,name
    target=OUT/'raw_sources/deployment'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
fixture=data['C0']['nominal_input'];raw_origin=ROOT/fixture['raw_source']
assert sha(raw_origin)==fixture['raw_sha256']
shutil.copy2(raw_origin,OUT/'raw_sources/input_R08_original.jsonl')
export=dict(source_pair='normal_controlled_20261104/comparison_r01',platform='Hardware with recorded-input replay',
    measurement_date='2026-11-04',prepared_for_project_status='2026-11-04 to 2026-11-05',conditions=['C0','C1'],
    source_files=files,nominal_input_identical=True,common_model_initials=True,actual_initial_encoder_identical=False,
    actual_sampling_times_identical=False,time_alignment='each condition subtracts its own measurement started_s; no row-index join, resampling or waveform reconstruction',
    motor_id_selected=2,motor_data_complete=True,raw_source_sha256=fixture['raw_sha256'],
    original_input_window_s=[80.,130.],source_fixture_samples=1000,rows={c:len(d['trace']) for c,d in data.items()},
    recomputed_metrics_match_archived=True,physical_smoothness_measured=False,physical_frequency_measured=False,
    newest_600s_trials_included=False,missing_delta_t_first_period='blank in CSV, not zero')
(OUT/'SOURCE_AUDIT.json').write_text(json.dumps(export,indent=2),encoding='utf-8')
readme='''# LeLamp Experimental Results for Canva

## ขอบเขตที่ใช้

ใช้ Normal controlled hardware pilot `normal_controlled_20261104/comparison_r01` เพียงคู่เดียว: `c0_r01` และ `c1_r01` รอบละ50วินาที เก็บวันที่4พฤศจิกายน2026 ชุดนี้เตรียมตามสถานะโครงการ4–5พฤศจิกายน ไม่รวม Happy/Angry หรือชุด600วินาทีรุ่นใหม่

เป็น **Hardware pilot with recorded-input replay**: มอเตอร์/encoderเป็นของโคมจริง ส่วน S มาจาก inputจริงR08ช่วง80–130sที่นำมาreplay; H/φ/o1เป็นสถานะโมเดลที่runtimeบันทึก ไม่ใช่เซนเซอร์ฮอร์โมน และไม่เรียกชุดนี้ว่าSimulation

## ไฟล์พร้อมใช้ใน Canva

| กราฟ | PNG หลัก | CSV |
|---|---|---|
| 1 φ ตามเวลา | PNG/01_C0_C1_Phi.png | CSV/01_phi_C0.csv และ01_phi_C1.csv |
| 2 Command/Encoder ID2 | PNG/02_ID2_Command_Feedback.png | CSV/02_motor_ID2_C0.csv และ02_motor_ID2_C1.csv |
| 3 S/H | PNG/03_Stimulus_Hormone_C1.png | CSV/03_stimulus_hormone_C1.csv |
| 4 Period/ΔT | PNG/04_CPG_Period_DeltaT.png | CSV/04_cpg_periods_C0.csv และ04_cpg_periods_C1.csv |

PNG ทุกกราฟใช้ชื่อแกน/legendภาษาอังกฤษ ความละเอียด3840×2160px (300dpi). กราฟมอเตอร์มีC0/C1คนละpanelและPNGแยกให้เลือกใช้เพิ่ม CSVเป็นUTF-8 BOM ค่าทศนิยมเต็ม ไม่มีการเติมtimeseriesใหม่

นำCSVเข้าCanvaแยกแต่ละcondition ใช้Timeเป็นแกนXตามตัวเลขจริง ไม่วางC0/C1ทับกันด้วยหมายเลขแถว `01_phi_long_timeseries.csv` เป็นไฟล์รวมแบบlongที่คงTimeของแต่ละcondition ไม่ใช่ข้อมูลจับคู่แถว

## เวลาและหน่วย

- กราฟ1–3: Time = owner CLOCK_BOOTTIME − measurement.started_s ของconditionนั้น เริ่มต้นแต่ละรอบที่t=0 (652/659แถว) เวลาบันทึกจริงไม่ตรงกัน ห้ามอ้างว่าคำสั่งใช้พร้อมกันทุกsample
- S/H/φเป็นค่าที่บันทึกในsnapshot AHM selection time/schedule indexแยกไว้ในCSV; snapshotถูกบันทึกหลังการอ่าน/เขียน ไม่เท่ากับเวลาป้อนinputหรือphysical onset
- มอเตอร์ใช้raw encoder ticks; 4096ticksต่อ360° Commanded Positionมาจากcommand_goalsซึ่งเป็นcacheเป้าที่ส่ง ส่วนActual Encoderมาจากposition_raw เพิ่มgoal registerreadbackและเวลาfeedback CLOCK_MONOTONICไว้ต่างหาก ไม่แปลงclockนี้เป็นBOOTTIMEโดยเดา ไม่อ้างว่าcommandกับencoderอ่านพร้อมกัน
- กราฟ4: CPG logical output time = updates × dt / time_scale; dt=.05s,time_scale=.5 ไม่ใช่เวลาที่วัดการเคลื่อนมอเตอร์

## วิธีคำนวณ metric

`CSV/05_metrics.csv` คือค่าที่คำนวณได้พร้อมสูตร/หน่วย ทั้งคู่มี7คาบสมบูรณ์และ6คู่คาบ

1. Max Δφ = max |φ[i]−φ[i−1]| ระหว่างsnapshotติดกัน อัตราcallbackไม่คงที่ จึงไม่ใช่การเปลี่ยนต่อ50msตายตัว
2. Deduplicate o1 ที่updatesซ้ำ แล้วหาจุดข้ามศูนย์ขึ้นด้วยlinear interpolationระหว่างจุดที่บันทึกจริง
3. T = t_cross[n+1]−t_cross[n]; timestampของคาบในCSVคือจุดจบคาบ
4. ΔT = |T[n]−T[n−1]|; คาบแรกไม่มีค่าก่อนหน้า จึงเว้นช่องว่าง ไม่แทน0
5. Mean Frequencyหลัก = 1/mean(T) และส่งmean(1/T)อีกแถวโดยติดชื่อแยก ไม่ใช้แทนกัน

การinterpolateใช้เฉพาะประมาณเวลาข้ามศูนย์สำหรับmetric ไม่สร้างหรือเติมCPG waveform nodes ขาดไป15nodesในC0/10ในC1 บอกจำนวนไว้ครบ ช่วงencoderpeak-to-peakในmetricsตัดelapsed<5sตามรายงานต้นทาง แต่CSVและกราฟส่งครบทุกแถว

## ข้อสรุปสำหรับสไลด์

- C1 has smaller observed phi steps than C0.
- CPG mean Delta T is 0.428482 s (C0) versus 0.460994 s (C1); it does not decrease in this pilot.
- Physical motor smoothness was not established.

ห้ามเขียนว่าC1ทำให้มอเตอร์สมูทขึ้น91.5% ตัวเลขที่เคยรายงานเป็นการลดmax parameter-stepเท่านั้น ไม่ใช่ความสมูททางกล

## ข้อจำกัด

มีเพียงหนึ่งคู่50s; ไม่ใช่3repeatsหรือการเล่นกับคน10นาที ค่าเริ่มCPGเหมือนกันแต่encoderเริ่มจริงต่างกัน ทั้งสองข้าม359parameter indicesอ้างอิงระหว่างowner callbacks แม้fixtureมีครบ1000samples จังหวะใช้พารามิเตอร์จริงจึงไม่ตรงกันทุกครั้ง

มีencoderquantizationและcommand/feedbackเวลาต่างกัน ยังไม่ได้วัดmotorfrequency/jerk/physical onset การเห็นoffsetหรือencoderขยับน้อยกว่าเป้าแยกสาเหตุfriction/backlash/load/PIDไม่ได้ ไม่สรุปนัยสำคัญทางสถิติหรือการทำงานทั้ง6อารมณ์จากคู่นี้

## หลักฐานตรวจย้อนกลับ

`raw_sources/c0_r01` และ`c1_r01` เก็บJSONต้นฉบับพร้อมmanifest/verification; `raw_sources/comparison_r01` เก็บรายงาน/metricsเดิม; `raw_sources/deployment` เก็บprofile/sourceตามSHAของpilot (camera_motor.pyดึงจากpayloadเก่า ไม่ใช้ไฟล์ปัจจุบันที่เปลี่ยนรุ่นแล้ว). ทั้งสองprofileต่างกันเฉพาะnormal_ahm_condition

`SOURCE_AUDIT.json` ระบุไฟล์และSHA; `MANIFEST_SHA256.json` ตรวจทุกไฟล์ในชุด ค่าmetricคำนวณซ้ำจากrawและตรงกับmetricsเดิม ไม่มีการแก้ต้นฉบับ
'''
(OUT/'README_TH.md').write_text(readme,encoding='utf-8')
print(json.dumps(export,indent=2))
