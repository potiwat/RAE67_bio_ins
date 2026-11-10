import copy, math, unittest
from bio_inspire.experiments.ros13 import Encoder, TOPICS


def fixture():
    normal={str(i):2000+i for i in range(1,6)}
    meta=dict(run_id='unit',pair_id='P1',condition='C1',origin='synthetic_test',
              profile=dict(normal_raw=normal),clock='source_monotonic')
    row=dict(time_s=12.,state='READY',behavior='normal',
             digital_inputs={c:dict(stable_pressed=False,last_sample_s=12.,stable_edges=[]) for c in ('button','touch')},
             distance=dict(distance_cm=42.,received_s=12.,measurement_state='range'),
             rows=[dict(id=i,position_raw=2000+i+10,goal_raw=2000+i+20,sampled_monotonic_s=12.,
                        status_raw=0,voltage_V=7.2,temperature_C=30) for i in range(1,6)],
             fsm=dict(state='normal'),oscillator=dict(o1=.1,o2=.2,phi=.1),
             image_observation=dict(status='TRACKING',captured_s=12.,box=[.2,.2,.3,.4]),
             ros=dict(schema_version=1,led_behavior='normal',led_rgb_255=[255,255,255],brightness=.03,
                      events=[dict(event_id='fsm_000001',kind='button',source_s=11.9,recognized_s=12.,status='transition')],event_history_lost=False))
    return row,meta


class Tests(unittest.TestCase):
    def test_sampler_error_and_new_overflow_cannot_be_called_complete(self):
        row,meta=fixture();e=Encoder(meta)
        for channel in row['digital_inputs'].values():
            channel.update(overflow_presses=4,stable_sequence=0,sampler_error=None)
        e.encode(row,0)  # Counter predates this capture, retain as baseline.
        row['time_s']+=.05;row['digital_inputs']['touch']['overflow_presses']=5
        with self.assertRaises(ValueError):e.encode(row,1)
        row,meta=fixture();row['digital_inputs']['button']['sampler_error']='closed'
        with self.assertRaises(ValueError):Encoder(meta).encode(row,0)

    def test_all_13_types_units_and_approved_semantic_mapping(self):
        row,meta=fixture();messages=Encoder(meta).encode(row,0)
        self.assertEqual(set(TOPICS),{m['topic'] for m in messages})
        by={m['topic']:m['data'] for m in messages}
        self.assertAlmostEqual(by['/lamp/input/distance'],.42)
        self.assertEqual(by['/lamp/rgb_command'],[1.,1.,1.,1.])
        self.assertEqual(by['/lamp/servo_command'],[20*2*math.pi/4096]*3)
        joint=by['/lamp/joint_states'];self.assertEqual(len(joint['position']),5)
        self.assertEqual(joint['velocity'],[]);self.assertEqual(joint['effort'],[])

    def test_no_target_does_not_invent_distance_and_event_is_not_repeated(self):
        row,meta=fixture();e=Encoder(meta);e.encode(row,0)
        row['time_s']+=.05;row['distance'].update(measurement_state='no_target',distance_cm=None)
        messages=e.encode(row,1);topics=[m['topic'] for m in messages]
        self.assertNotIn('/lamp/input/distance',topics)
        self.assertNotIn('/lamp/interaction',topics)
        status=next(m['data'] for m in messages if m['topic']=='/lamp/input/status')
        self.assertEqual(status['distance']['measurement_state'],'no_target')

    def test_missing_feedback_or_lost_events_or_wrong_sequence_fail(self):
        row,meta=fixture()
        for change in ('feedback','history','sequence'):
            bad=copy.deepcopy(row)
            if change=='feedback':bad['rows'].pop()
            if change=='history':bad['ros']['event_history_lost']=True
            with self.assertRaises(ValueError):Encoder(meta).encode(bad,1 if change=='sequence' else 0)

    def test_clock_regression_fails(self):
        row,meta=fixture();e=Encoder(meta);e.encode(row,0);row['time_s']=11.
        with self.assertRaises(ValueError):e.encode(row,1)


if __name__=='__main__':unittest.main()
