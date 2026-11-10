# Slide-ready notes

**Dataset:** Normal controlled hardware pilot, comparison_r01, recorded on 4 November 2026. One paired 50 s C0/C1 trial; same recorded-input replay. These are not the later six-emotion trials.

1. **Phi over time:** C0 follows the replay stimulus directly; C1 changes phi through the logged hormone model. Maximum observed adjacent-snapshot phi step: C0 0.030000; C1 0.002553 rad/update. Snapshot intervals vary.
2. **Command vs encoder:** ID2 has complete command and feedback fields in both conditions (652 C0 / 659 C1 snapshots). Positions are raw ticks. Command and feedback are not simultaneous measurements. The visible command/feedback mismatch does not identify a unique mechanical or control cause.
3. **Stimulus and hormone:** Recorded hardware input was replayed; H is the runtime model state. H persists and decays after S returns to zero. It is not a measured biological hormone.
4. **Period / Delta T:** Values use the logical CPG o1 clock, not motor-motion frequency. Mean Delta T: C0 0.428482 s; C1 0.460994 s. Maximum Delta T: C0 1.109319 s; C1 1.325658 s. Mean frequency (1/mean period): C0 0.155311 Hz; C1 0.155429 Hz. Seven periods / six differences per condition.

**Supported conclusion:** C1 reduced the size of observed phi steps in this pilot. It did not reduce mean cycle-to-cycle Delta T. Physical motor smoothness was not established.

**Limits:** One pair; different initial encoder positions; irregular recording intervals; skipped reference indices and unlogged CPG nodes; no motor jerk or physical frequency measurement. Do not label this as a 91.5% improvement in motor smoothness, a statistical result, or a test of the latest Happy/Angry motion.

**Canva:** Upload the PNGs directly to preserve the actual numeric time axes. CSVs retain each condition's own timestamps; do not pair rows by index or force a categorical equally spaced time axis.
