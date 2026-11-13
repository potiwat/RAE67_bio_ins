# Supervised six-state experimental play

User-authorized experimental integration on 2026-11-10. Original brake criteria remain recorded as not qualified; user permits this supervised trial without requiring those criteria to pass. This is not a human-contact safety qualification. No PID, original presentation, play motion profile, EEPROM, torque limit or Desktop icon changes.

Approved flow: Start/M -> ordinary six-state play -> detected resistance -> one stop transaction -> confirmed stationary -> reset H/CPG -> wait for operator to remove foam and press R -> original coordinated Normal route -> park. Start/M must work again for another round. H/Stop, Q, native fault and uncertain recovery cannot be overridden by R.

Architecture: reuse the real central feedback owner, detector, scheduler, Supervisor and Normal route. A narrowly gated experimental Adapter enables all five IDs without pretending this is simulation or physical qualification. Clearance is an event-specific operator acknowledgment, not inferred from low current or head ToF. A short broadcast trajectory-cancel/active-hold transaction applies only to moving axes; resting equilibrium commands are retained. Stop-only ACC settings are temporary and verified/restored after stillness. Failed recovery remains latched and reports the affected ID.

LED: local wrapper uses actual CPG decoder phase in every state, same RGB and max8%, min3%, steady3% on missing phase. Original presentation remains5-8%.

Implementation checks:
- [ ] LED range and phase regressions.
- [ ] Native group cancellation/hold and RAM restoration, including partial writes, lost reads, cancellation and loaded resting axes.
- [ ] Explicit physical-trial gate, R only after stillness, reset once, H/Q/fault override, repeated Start/stop/recover.
- [ ] Real runtime memory-UART coverage for five IDs and six states, no-contact start, stuck obstacle, interrupted return and data faults.
- [ ] Independent code review and protected-source/hash checks.
- [ ] Stage only isolated files and open a clearly labelled viewer waiting for Start. No new Desktop icon.
- [ ] First physical sequence is open-path planned stop/recovery before any foam; actual contact remains a supervised experiment.
# R-return failure follow-up (2026-11-11)

Physical source: `run_1794332307841194947/CENTRAL_SAFETY.json`.
After accepted R, return began at 23432.974083652 s. A fresh ToF frame
reported unreliable status 7 (not a disconnection), causing the required
second hold at 23434.276393656 s. The old group-damping capture exceeded
its unchanged 10 ms deadline after cumulative reads (10.147 ms at ID5).
Independent recovery verified active support and close restored source ACC;
recorded PID before/after remained equal for all five axes.

Experimental fix: perform the existing reset-and-position-hold sequence per
axis, restoring active support immediately before processing the next axis.
Keep the 10 ms per-transition deadline, reviewed travel bound, original
speed/PID/caps and ACC restoration. No torque-off or new register values.
Later axes remain on their prior supported trajectories until serviced;
therefore physical total stopping travel/latency must be measured again.
Software tests do not qualify this method as human collision protection.

ToF unknown/near still pauses return. Once stationary and clear again, a new
displayed stop token and a new R are required. R never clears a native fault.
Regression covers unknown during return, two separate holds/R confirmations,
one model reset, completion at initial Normal and unchanged source profiles.

## Post-Normal button restart (2026-11-11)

User request: keep manual R for obstacle clearance; after verified initial
Normal, count five new complete base-button press/release cycles to resume.
Implementation is isolated in `restart.py`, owner-side `integration.py` and
the in-memory experimental camera launcher; no original source edits.
Only NORMAL_PARKED arms the gate. Ignore pre-park edges and a pre-held button;
the fifth release publishes a once-only owner token after healthy/still proof.
The GUI consumes it only on an idle key with no close/Stop/fault, then uses
the original operator_motor_start to retire the old owner before a fresh one.
Tests cover actual debounced input events, held/old edges, claim-once, Q
priority, original owner cleanup/factory ordering and launcher injection.

Latest physical evidence `run_1794332892365201035`: both stop transactions
verified active support and restored source ACC, H reset to 0 and all CPG
update counters reset to 0, PID unchanged and no fault. However, ToF became
unreliable during return and the run ended WAIT_CLEARANCE after its second
hold, with no NORMAL_PARKED event. This is NOT a completed physical return
or authorization to advance to foam under the user's conditional request.
Next physical check: open path Happy -> V -> R, repeat R only when needed
after clear/still, wait NORMAL RESET COMPLETE, button five releases, observe
fresh normal play, Q. Foam remains deferred until this sequence is verified.

## ToF investigation and bounded return policy (2026-11-11)

User reports approximately 80 cm sensor cable and no optical cover/obstruction.
Stationary input-only capture: `TOF_STATIONARY_20261111.json`, 82 completed
frames in 8 s: 58 range, 22 unreliable raw-status7, 2 no_target. No I2C exception;
maximum inter-frame interval 0.114269 s, mean 0.096746 s. Longest consecutive
unreliable run: 12 frames spanning 1.066966 s. This does not prove cable health
under movement or identify the optical/electrical cause. I2C1 clock readback:
100000 Hz, unchanged. Raw7 is PHASECONSISTENCY/WrapTargetFail in the Pololu
VL53L1X driver's getRangingData mapping, not a transport-error code.

Input-only mode2 then mode1 comparison (`TOF_MODES_20261111.json`) returned
all no_target in both windows; environmental/target conditions were not fixed,
so no superiority conclusion or permanent sensor-mode change. Restored mode1
and timing budget100ms. No motor commands during either diagnostic.

User requests tolerance to transient quality drops. `tof.py` allows continuing
an already R-authorized return on fresh optical-unreliable frames only within
0.5s of the latest genuinely clear frame. Bad frames never renew clear memory;
Near invalidates it. Existing 0.12s freshness stays unchanged. Stale/absent data
or I2C/hardware errors do not receive grace; R cannot begin a return on grace.
No fabricated distance; degraded quality is explicitly recorded and displayed.
Original play ToF behavior and original presentation remain unchanged.
This tolerance introduces a bounded observation gap, not collision qualification.
Tests cover short optical dips, sustained ambiguity, stale input, Near and I2C
failure, plus the independent five-button restart/confirmed-owner-retirement gate.

References:
- https://github.com/pololu/vl53l1x-arduino/blob/master/VL53L1X.cpp
- https://www.nxp.com/docs/en/user-guide/UM10204.pdf

## Verified recovery after a timing miss (2026-11-11)

Physical run `run_1794333846209198361` stopped on its first V: ID4's second
damping read returned at 24951.809246 s, 12.434ms after damping began. Its
native reference had reset to encoder1690, but the 10ms deadline faulted.
Independent recovery verified all five supports, source ACC was restored on
close, PID stayed unchanged. R was correctly refused because the old policy
classified the timing miss as a latched fault, regardless of recovery proof.

The unqualified supervised trial now distinguishes a typed reset/dispatch
deadline miss from hardware/transport errors. Keep the 10ms criterion and
primary error in the audit with timing_criterion_met=false. Only after
independent recovery, five known original states, fresh verified active
support, unchanged resting equilibria, original travel bound <=16ticks and no
cancel/unsafe ID may it return a verified hold report. STOPPING must still
prove strict standstill, restore source ACC, reset models and await a fresh
operator R. No automatic motion or fault retry. All other errors still latch.
Regression: injected ID4 12ms delay -> verified recovery -> explicit R ->
Normal; uncertain recovery, excessive travel and cancellation still rejected.
No PID, hardware register value, original source or physical qualification
threshold changed. Actual next return sequence still requires validation.

## Startup transient input readiness (2026-11-11)

Physical run `run_1794334244905193006` did not reach Normal: constructor
logged `MOTOR_START_BLOCKED ToF: disconnected or measurement stream stale`.
No central Safety state was started. PID stayed unchanged. Initial source
readiness had succeeded, but a later immediate pre-motion freshness check
failed after live-pose preparation. This message alone does not distinguish
wire failure from a transient stale/invalid measurement frame.

Isolated `startup.py` wraps the existing source's require_fresh only in the
experimental hooks. FIRST pre-motion callback can wait <=0.5s for an actually
fresh frame, preserving the original .12s validator and hardware error checks.
It never retries the motor constructor, PID setup or command sequence.
Subsequent callbacks can be between Normal goal writes: they retain the
original immediate abort/cleanup behavior, never wait while earlier axes move
before the runtime worker exists. Cancellation and I2C errors interrupt.
Console records STARTUP_TOF_WAIT/READY or an explicit bounded start-block reason.
Tests reproduce the real constructor failure with an injected first-check
stale frame, then a new valid frame after80ms; same constructor completes.
Further tests cover permanent stale, immediate hardware fault, cancellation,
and a later stale frame after a Normal goal: no wait and original cleanup.

## Native command acceptance vs trajectory completion (2026-11-11)

Finalized run `run_1794334780973194368`: initial Normal succeeded, but the
stop failed with `Active hold unconfirmed ID3`. Native readback confirmed the
exact active block (torque1, ACC50, goal3123, speed1000); the instantaneous
internal reference was3126, then3125, finally3123. The previous code required
reference convergence <=2ticks at immediate command verification and latched
despite successful command readback and independently verified recovery.

Command acceptance now requires exact active-control bytes and native healthy
state, with both encoder and reference inside existing reviewed windows and
the16tick transition envelope. A reference gap3..16ticks is explicitly pending,
not complete or a timing qualification. No target rewrite. Source ACC cannot
restore, models cannot reset, and R cannot return until the existing strict
standstill proof and reference<=2ticks both hold; recheck after ACC restoration.
Existing8s diagnostic deadline still latches a reference that never converges.

Pending envelope is checked on every available owner feedback sample while
STOPPING/WAIT_CLEARANCE and during pending close. Violations invalidate proof,
mark that axis unsafe, latch, and block ordinary cleanup writes to it. The
guard uses decoded fields without extra UART; full native verification also
checks aux/cap bytes. Intentional Normal dispatch has a narrow guard exception
because its targets differ from old stop targets. It invalidates the old proof:
if return dispatch fails after an accepted write, one NEW fresh bounded
recovery runs before latching. Never reuse a prior restored writer as proof.

Tests: pending reference converges -> R -> initial Normal; never converges ->
latch/no return; later moving reference+30 or encoder+17 -> immediate unsafe
latch; command mismatch still rejected; post-ACC pending blocks completion;
accepted Normal write followed by failure uses a new recovery transaction.
UI now displays literal WAIT_CLEARANCE and the correct R instruction, instead
of the ordinary misleading press-Start headline during a Safety pause.

## First completed physical return/restart and LED lifecycle (2026-11-11)

Run `run_1794335866669194165` physically completed HOLD_SENT, MODELS_RESET,
operatorR, initialNormal return, NORMAL_PARKED, five completed button releases
and BUTTON_RESTART_READY. A fresh owner `run_1794335940589208598` started; both
closed without Fault and with PID unchanged. This verifies that functional
sequence, not collision-force sensitivity or the original brake criteria.

Remaining evidence: owner1 startup NORMAL_STARTUP -> WAIT_TOF -> READY left
behavior=distance_wait for approximately15s until Button. The original FSM's
applied=normal cache prevented re-dispatch after poll_distance(dispatch=False)
restored native READY. Owner2 also encountered this recovery boundary. No LED
backend exception was logged. Original Adapter.park explicitly forced Normal
LED on, while the parked loop skipped ordinary LED-off output service.

Experiment-only recovery poll invalidates only the FSM dispatch cache after
healthy corePLAY / READY-FOLLOWING / actualfresh input recovery, with no Stop,
closing or urgent flag. The same original FSM tick chooses and dispatches its
state, including Near/Afraid. No direct state transition or threshold bypass.
Use importlib.import_module to patch the registered canonical distance module
across repeated isolated tests/owners, avoiding stale namespace attributes.

Park now keeps the same motor flags but closes/detaches the LED owner and
clears LED frame/color caches, rather than forcing a Normal light on. Blackout
errors remain decorative and are recorded, never hidden as motor success.
The fifth release uses the existing checked owner handoff; a fresh owner uses
normal LED service. Commands/phase/brightness are exposed in trial_safety.led.
Tests reproduce no-input startup ToF recovery + Normal LED, parked darkness,
Near priority and operatorStop preservation. No PID, presentation-original,
motor profile, CPG mapping, active RGB or3-8% brightness range changes.

## Static terminal arrival after late ToF pause (2026-11-11)

Run `run_1794336642561193683`: authorized R return started, then fresh optical
ambiguity outlasted the0.5s grace at27762.177s. The required pause cancelled the
route just before completion and generated a second verified hold. Final goals
were2012,2837,2746,1997,2696; final encoders2013,2841,2770,2001,2697, references
equal goals and all speeds/moving zero. Every actual and held goal satisfied
the existing Normal tolerances (ID2/3/5=34ticks, other IDs22). It nevertheless
remained WAIT_CLEARANCE because route.phase was cancelled, with no normal park
or five-button gate. The lit Happy frame was stale output, not a failed off
command: the old park callback had never been reached.

TrialSupervisor now offers a no-motion terminal path only for a prior R return
paused by unknown ToF. Require reset already done, allow-return, healthy fresh
continuous stationary proof, verified native support/source-ACC restoration,
all5 actual AND goal positions within unchanged Normal tolerances, converged
native references, no pending/error/H/close, and a current non-near input frame
(fresh optical ambiguity may remain). If proven, record actual per-ID arrival
evidence and park with LED off/five-release gate. Do not fabricate a completed
route, infer clearance, change targets or move automatically. Initial V stops
without R and genuinely incomplete poses cannot use this path. Near/stale or
hardware fault still disallow this terminal recognition.

HOLD now also blackouts decorative output after the stop transaction, so a
sensor pause cannot leave a stale Happy light. Tests cover delayed completion
marker with proven Normal vs actual partial pose (yaw+50ticks): only the former
parks without a second R; no extra motion. All existing stop/fault guards remain.

## User-authorized autonomous open-path sequence check (2026-11-11)

User explicitly authorizes driving motors and test inputs to check recovery
without repeated manual M/Touch/V/R/button actions. Keep path clear/operator
near physical Emergency; no obstacle/contact test. `auto_recovery.py --execute`
uses real CameraMotor/UART/encoder/ToF/LED and the same isolated profile/hooks.
Touch/Button are explicitly scripted debounced sources; centered camera input
is synthetic heartbeat, not a face-tracking result or human-scenario evidence.

Bounded75s per round: Normal+LED -> continuous Happy1.5s -> V -> verified
hold/reset/LEDoff -> R only on real fresh clear input accepted by owner ->
Normalpark/LEDoff -> five completed button releases -> existing checked owner
handoff -> fresh Normal+LED. H/CPG reset and PID/source hashes are checked.
Every failed stage records state/reason, stops and closes; no blind fault reset.
SIGINT/SIGTERM/round ABORT are checked before both constructors, after each
driver tick and via every original constructor pre-motion check. No extra
UART owner, PID tuning, new motion settings or Desktop icons. Up to two
successful runs establish repeatability of this sequence only, not collision
qualification or physical optical LED brightness measurement.

Automatic round `auto_sequence_1794337955717591432` safely failed at RETURN:
fresh optical ambiguity persisted, no valid R-clearance returned, and the
paused pose was genuinely short of Normal (e.g. ID3goal2883 vs Normal2746).
No static terminal recognition was allowed. Cleanup, PID and original hashes
were verified unchanged. This is an observed ToF-limited failure, not a pass.

User explicitly requests continued testing with LED OFF. --dark retains LED
software calls/state but replaces output only; evidence states no real LED
output/photometric verification. A separate --tof-mode2-trial uses Long mode2
only in the automatic process, unchanged100ms budget/validity/Near/stale rules,
and restores mode1 on every source close. Instance flags must confirm restore
commands completed or the test fails. Ordinary trial/presentation defaults are
not changed by this comparison. Fake-sensor unit proves sequencing only;
physical reliability and Near response are not inferred from that unit test.



## Explicit ToF isolation trial (2026-11-11)

User requests sensor failures not interrupt unrelated play, reset, return or
buttons. Opt-in --isolate-tof changes only this experimental process. Raw ToF
samples, timestamps/status/errors and worker remain physical and unmodified.
Missing/ambiguous/stale/I2C-error data reports unavailable, never clear. They
cannot trigger whole-motor WAIT_TOF or withdraw an operator-R return approval.
There is NO proximity protection from unavailable data. Genuine Near evidence
remains latched until genuine clear/no-target, and still vetoes return. Native
motor faults, stale motor feedback, clamps, operator Stop/H/Q and active-support
verification remain mandatory; this is not collision-safety qualification.

IsolatedSupervisor retains the stop/verify/H+CPG reset/operator R/Normal park/
five-release sequence. Startup ToF availability checks are nonblocking in this
opt-in process, with cancellation still enforced. Normal motor preflight and
PID settings are unchanged. UI/log report ToF unavailable separately. Default
hooks and the original presentation keep their existing policies.

Manual log VIEWER_1794339295931321838 showed gpiozero Button HoldMixin racing
close on restart (_hold_thread None in callback). Experimental SampledButton
uses DigitalInputDevice GPIO27 pull-up/active-low, the original BufferedInput
sampler and 60ms debounce, without an unused HoldMixin thread. GPIO22 Touch
already uses DigitalInputDevice. No shared source or Desktop icon changes.

Whole-runtime memory-UART tests cover unavailable data during startup/play,
all six stop/return states, operator R once, H/CPG reset, five fresh releases,
real Near and native-fault/Stop/Q preemption. These are software tests, not
physical foam/proximity qualification. Pi deploy checks hashes of all132
protected sources before and after tests; viewer waits for manual M.


## ID1 moving-resistance detection trial (2026-11-11)

Physical run1794340225601196827 did not stop:1066active ID1samples,
85samples exceeded current/PWM/internal-error thresholds but no sufficiently
stationary .30s window. Both old central/legacy stall guards missed this run.
Original integration retained torque limit1000; earlier foam sweep used160.
Neither a stopping sequence unit pass nor capped foam results qualify current
uncapped contact sensitivity. User confirms base physically obstructed.

Opt-in --id1-effort-trial uses independent sustained excess-current+PWM+
internal-error evidence with the SAME configured thresholds/.30s/min4 samples,
without requiring <=2tick progress. Native validation precedes evidence; only
ID1 evidence may enter the existing resistance stop/reset/manualR pipeline.
No PID, caps, motion speed/acceleration/targets or original presentation edits.

Counterfactual replay found66candidate frames in this contact-containing log,
zero in four documented unobstructed session files(210active samples) and the
fit baseline(1268samples, explicitly not independent validation). No exact
contact timestamps: cannot report physical detection latency/force. Not
physically qualified. Whole-runtime SlidingPlant regression verifies moving
contact -> existing stop/reset/R/park, plus no-contact control.

Authorized automatic open-path run uses actual UART/encoders, synthetic face
error bounded+/-0.20 sine4s during8sNormal,6sHappy, then existing V/reset/R/
five-release/fresh-owner check. Existing motor profile/clamps only; no contact,
LED off, ToF isolation/mode2 explicit, cancellation+close and75sbound retained.
Stop if unexpected safety trigger; do not automatically clear a false trip.


## Verified parked-owner retirement (2026-11-11)

Run1794340996633197592: real ID1 excess-effort stop requested32100.323s;
reset32101.232s; R accepted32104.123s; Normal parked32104.928s; all5 releases
recorded32108.976s. Restart failed in new preflight, not GPIO: original final
cleanup rebased head5 goal2696 to actual2711. New owner saw internal2701 and
moving1 although prior parked hold was stable. Keep startup preflight strict.

For a claimed automatic five-button handoff ONLY, capture all5 parked goals.
At exact final 'motor worker stopped' hold call, freshly read all5 native rows,
verify mode0/torque1/status0/speed0/moving0/ref-goal<=2 and unchanged goals,
actual+goal within original Normal tolerance. Preserve these active holds,
record PARKED_OWNER_RETIRED_WITHOUT_REBASE and close owner without reissuing
positions. No wait/timeout extension, no skipped native proof. If proof fails,
record core error, use original fallback hold, block automatic new owner.
Regular Q/H/manualM cleanup unchanged. Tests cover loaded-head sag15ticks with
unchanged target plus moving/status/torque/changed-goal/reference rejection.


## Healthy ID1 post-hold deflection vs command fault (2026-11-11)

Happy run1794341580161184681: ID1 held goal/ref1879 with accepted active
position control; subsequent q1862 was17ticks from reset vs16tick qualification
bound. No command change. Existing guard conflated stop-quality miss with
unknown hardware state, permanently latched and blockedreset/R/ACCcleanup.
Readonly later:all5 stationary/mode0/torque1/status0/ref=goal; PIDunchanged.
Known originalACC8/16/16/24/6 independently restored after continuous fresh
stationary proof; goals/speed/caps/PID verified unchanged. Receipt saved.

For explicit ID1 effort trial ONLY, keep strict16ticks throughout Damping/
reset/initial active-hold verification. After verified hold, healthy ID1 q
inside original mechanical window but >16ticks becomes recorded contact
 deflection/stop-quality failure, not uncertain commands. Preserve frozen goal,
continuous native validation and hard faults for mode/torque/status/command/
reference/window/data faults. Do not relabel physical stop as qualifying.

R remains independent operator path confirmation. After deflection it also
requires stationary ID1, goal-error<=12ticks, PWM<32/current<3; these are NOT
proof of obstacle removal and cannot grant automatic clearance. UI exposes
CONTACT HELD; release telemetry alone never sends a motion command. Tests cover
17tickpush after verifiedstop in each of six logicalstates, R rejected while
held, reset/R/Normal after release, and command-fault still latched. Actual
arbitrary contact force is unmeasured; original cap1000 can push strongly.

Automatic no-R clearance/probe remains a separate supervised development step,
not installed or enabled by this classification fix. Do not use low effort,
standstill, or this quality downgrade as permission to auto-return Normal.


## Explicit ID1 automatic return experiment (2026-11-11)

User verified latest real Happy obstruction -> R -> Normal -> five releases ->
newPLAY, nofault/PIDchange, then explicitly requested no-R and reuse previously
accepted probe parameters. Evidence source:FOAM_1794244375258067729 summary,
cap160 Speed600 ACC3 rest0.5, pinned16tick smooth ramp<=1tick/hoststep.
ACC4 handoff belongs to old long sweep and is not copied into Normal reset.

New --auto-id1-return is opt-in, requires ToFisolation+ID1efforttrial, affects
ID1 contact/test_stop(axis1) only. Existing native GroupStop verifies all5 stop,
resets H/CPG, retains other axes' frozen support. Probe lowers ID1cap160 before
profile/goal changes; uses same reviewed old range1691..2347 intersected with
existing mechanical window. Sourcegoal/profile/cap captured. No PID/EEPROM/
mode/torqueoff/body probe writes. Per-command ACK/readback, native reference
bounds remain hard proof, and separate native feedback scheduling stays active.

Do not infer clearance from low current. Need actualencoder10..20tickprogress,
>=4distinct fresh readings spanning>=0.1s and>=2ticks forward progression,
lowPWM<32/current<3/refgoal<=1/error<=8. No proof may span feedback gap>0.2s.
Renewed resistance pauses; retries keep same target/anchor, no cumulative walk.
Known partial progress may retry. Exhausted boundedspace becomes explicit
manual-required state; no silent active deadlock. GenuineNear pauses probe
immediately and remains latched through missingToF. H/Q alwaysoverride.

After probe success, freeze/confirm loweffortstationary>=0.15s, restore original
Speed/ACC/cap(caplast), freshly verify all5 support, then permit existingNormal
return withoutR and awaitfive freshbuttonreleases. This is experimental movement
permission, NOT wholepath-clearance or person-contact safety qualification.
ID1 resistance detection remains active on return; other-axis events remainR.

Failure handling is once-only and never reuses pre-probe GroupStop evidence.
Fresh boundedhold/restoration whereproven, otherwise markID1unsafe and prevent
legacy unknown writes. A native-reference fault never gets speculative recovery
writes. Probe restoration failure is sticky through workerfinalcleanup and
blocks restart even if a positionalhold later succeeds. Resources stillclose.

New tests cover all6logicalstates/noR, persistent/repeatedcontact, acceptedwrite
thenreadloss,partialsetup,midprobeNear,H/Q,restorationfailure,unknownreference,
proofgaps andsourceprofile/bodywritewhitelist. Physicalnofoamvalidator explicitly
usesaxis1test_stop and must verify probe+cap events andzeroR, not genericV/R PASS.
