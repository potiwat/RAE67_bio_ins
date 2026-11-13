"""Present Safety arrival policy; protected presentation implementation stays intact.

The copied function globals preserve the original 0.5s face freshness.
Guarded source anchors fail closed if the retained implementation changes.
One factory lifetime is one viewer: its cooldown survives motor-owner recovery.
"""
import inspect
import textwrap


def policy_class(module):
    original = module.AutomaticFSM
    namespace = dict(vars(module))

    def clone(function, before=None, after=None):
        source = textwrap.dedent(inspect.getsource(function))
        if before is not None:
            if source.count(before) != 1:
                raise RuntimeError('Retained Approach implementation changed: ' + before)
            source = source.replace(before, after, 1)
        exec(compile(source, __file__, 'exec'), namespace)
        return namespace[function.__name__]

    service = clone(original.service,
                    'now-self.last_auto_approach_s<30.',
                    'now-self.last_auto_approach_s<60.')
    scan = clone(original.scan_approach)
    viewer_last_approach = [None]

    class PresentSafetyApproach(original):
        scan_approach = scan

        def service(self, m, now):
            saved = viewer_last_approach[0]
            if saved is not None and (self.last_auto_approach_s is None
                                      or saved > self.last_auto_approach_s):
                self.last_auto_approach_s = saved
            result = service(self, m, now)
            if self.last_auto_approach_s is not None:
                viewer_last_approach[0] = self.last_auto_approach_s
            return result

        def snapshot(self):
            return {**super().snapshot(), 'approach_face_max_age_s': 0.5,
                    'approach_scan_missing_s': 2.0,
                    'approach_cooldown_s': 60.0,
                    'approach_cooldown_scope': 'viewer_including_safety_recovery'}

    return PresentSafetyApproach


def scan_service(module):
    """Only extend confirmed missing-face time; retain scan bounds and stopping."""
    source = textwrap.dedent(inspect.getsource(module.service))
    before = 'if elapsed<1.:'
    if source.count(before) != 1:
        raise RuntimeError('Retained yaw scan implementation changed')
    namespace = dict(vars(module))
    exec(compile(source.replace(before, 'if elapsed<2.:', 1), __file__, 'exec'), namespace)
    return namespace['service']
