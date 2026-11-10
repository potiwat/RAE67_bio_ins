import math
import unittest
import json
from pathlib import Path
import tempfile

from bio_inspire.experiments import ahm_cpg_compare as experiment


class CourseComparisonTests(unittest.TestCase):
    def test_common_warmup_matches_retained_lab05_initial_state(self):
        a, b = experiment.warmup()
        self.assertAlmostEqual(a, -0.026965330782974153)
        self.assertAlmostEqual(b, -0.5608626776309884)

    def test_direct_and_hormone_have_identical_pre_stimulus_states(self):
        direct, hormone = experiment.simulate('C0'), experiment.simulate('C1')
        self.assertEqual(len(direct), 601)
        for a, b in zip(direct[:201], hormone[:201]):
            self.assertEqual((a['o1'], a['o2']), (b['o1'], b['o2']))

    def test_command_uses_old_hormone_and_next_state_uses_updated_hormone(self):
        c0, c1 = experiment.simulate('C0'), experiment.simulate('C1')
        self.assertEqual(c0[200]['phi_rad_per_update'], .4)
        self.assertEqual(c1[200]['phi_rad_per_update'], .2)
        self.assertAlmostEqual(c1[200]['h_next'], .04)
        self.assertAlmostEqual(c1[201]['phi_rad_per_update'], .208)
        self.assertEqual(c0[400]['phi_rad_per_update'], .2)
        self.assertGreater(c1[400]['phi_rad_per_update'], .39)

    def test_each_c1_step_matches_teacher_functions(self):
        course, contract = experiment.course_model(), experiment.contract()
        for row in experiment.simulate('C1')[:-1]:
            a, b = course['step_cpg'](row['o1'], row['o2'], 1.1, row['phi_rad_per_update'])
            h = course['hormone_step'](row['h'], row['stimulus'], .05, (.8, .6, .2))
            self.assertEqual((row['o1_next'], row['o2_next']), (a, b))
            self.assertEqual(row['h_next'], h['h'])
            self.assertEqual(row['phi_rad_per_update'], course['mapped_parameters'](row['r_used'], contract, 'phi-only')['phi_rad'])

    def test_invalid_input_resets_hormone_and_uses_bounded_baseline(self):
        values = [1.] * 600
        values[100] = math.nan
        for condition in ('C0', 'C1'):
            row = experiment.simulate(condition, values)[100]
            self.assertEqual(row['fault'], 1)
            self.assertEqual(row['phi_rad_per_update'], .2)
            self.assertEqual(row['stimulus'], None)
            if condition == 'C1':
                self.assertEqual(row['h_next'], 0.)
        with self.assertRaises(ValueError):
            experiment.simulate('C0', [0.] * 599)

    def test_deterministic_replay_and_parameter_bounds(self):
        for condition in ('C0', 'C1'):
            rows = experiment.simulate(condition)
            self.assertEqual(rows, experiment.simulate(condition))
            for row in rows[:-1]:
                self.assertTrue(.1 <= row['phi_rad_per_update'] <= .45)
                self.assertTrue(abs(row['o1_next']) <= 1)
                self.assertAlmostEqual(row['t_next_s'] - row['t_s'], .05)
        with self.assertRaises(ValueError):
            experiment.simulate('B2')

    def test_complete_period_frequency_and_delta_t_use_output_crossings(self):
        samples = [(i * .05, round(math.sin(2 * math.pi * i * .05), 12)) for i in range(81)]
        periods = experiment.output_periods(samples)
        summary = experiment.period_metrics(periods)
        self.assertAlmostEqual(summary['frequency_hz'], 1.)
        self.assertAlmostEqual(summary['delta_t_max_s'], 0., places=10)
        self.assertEqual(summary['period_count'], 4)

    def test_delta_t_is_absolute_change_between_adjacent_periods(self):
        periods = [{'start_s': 0., 'end_s': 1., 'period_s': 1.},
                   {'start_s': 1., 'end_s': 3., 'period_s': 2.},
                   {'start_s': 3., 'end_s': 4., 'period_s': 1.}]
        self.assertEqual(experiment.period_metrics(periods)['delta_t_mean_s'], 1.)

    def test_insufficient_data_is_missing_not_zero(self):
        self.assertIsNone(experiment.period_metrics([])['frequency_hz'])
        self.assertIsNone(experiment.period_metrics([{'period_s': 1.}])['delta_t_mean_s'])
        self.assertEqual(experiment.output_periods([(0., 1.), (1., 1.)]), [])

    def test_segments_exclude_boundary_spanning_periods(self):
        periods = [{'start_s': 9., 'end_s': 11., 'period_s': 2.},
                   {'start_s': 11., 'end_s': 12., 'period_s': 1.}]
        self.assertEqual(experiment.segment_periods(periods, 10., 20.), periods[1:])

    def test_teacher_reference_metrics_are_reproduced(self):
        for condition, max_step, latency, recovery in [('C0', .2, 0., 0.), ('C1', .008, .15, 2.85)]:
            summary = experiment.analyze(experiment.simulate(condition))
            self.assertAlmostEqual(summary['phi_max_step_rad'], max_step)
            self.assertAlmostEqual(summary['command_latency_10pct_s'], latency)
            self.assertAlmostEqual(summary['command_recovery_10pct_s'], recovery)
        c0 = experiment.analyze(experiment.simulate('C0'))
        self.assertAlmostEqual(c0['segments']['on']['frequency_hz'], 1.2683661431330577)


class EvidencePackageTests(unittest.TestCase):
    def test_protected_inventory_includes_pid_configurations(self):
        from bio_inspire.experiments import run_ahm_cpg_compare as runner
        protected = runner.protected_hashes()
        for path in (experiment.ROOT/'shared/hardware').glob('*pid*.json'):
            self.assertIn(path.relative_to(experiment.ROOT).as_posix(), protected)

    def test_export_paired_runs_replays_and_checks_protected_files(self):
        from bio_inspire.experiments import run_ahm_cpg_compare as runner
        with tempfile.TemporaryDirectory(dir=experiment.ROOT / 'bio_inspire/experiments') as temp:
            out = Path(temp) / 'result'
            runner.run_experiment(out, repeats=3, make_plots=False)
            verification = json.loads((out/'verification.json').read_text())
            self.assertTrue(verification['protected_files_unchanged'])
            self.assertTrue(verification['paired_stimulus_identical'])
            self.assertTrue(verification['deterministic_repeats_identical'])
            self.assertEqual(len(verification['trials']), 6)
            self.assertEqual(len(list(out.glob('C?_r??/trace.csv'))), 6)
            with self.assertRaises(FileExistsError):
                runner.run_experiment(out, repeats=3, make_plots=False)

    def test_reject_invalid_repeat_counts_before_creating_output(self):
        from bio_inspire.experiments import run_ahm_cpg_compare as runner
        with tempfile.TemporaryDirectory(dir=experiment.ROOT / 'bio_inspire/experiments') as temp:
            for value in (True, 0, -1, 100, 2.5):
                out = Path(temp) / str(value)
                with self.assertRaises(ValueError):
                    runner.run_experiment(out, repeats=value, make_plots=False)
                self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
