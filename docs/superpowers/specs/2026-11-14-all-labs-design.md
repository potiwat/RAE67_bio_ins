# RAE67 Bio-Inspired Robotics Labs 02-07 Design

## Intent

Complete Labs 02-07 from the instructor starter state in the student's fork, with code, experiment evidence, and explanations that the student can reproduce and defend. Work must start before the previously merged student solutions and must not reuse that student's identity, generated results, or report text.

## Goals

- Keep the GitHub fork relationship required by the instructor.
- Work on `student-work`, created from instructor starter commit `fa528b1`.
- Complete and verify each lab in order, with a separate commit per lab.
- Keep implementations small, direct, and consistent with the supplied equations and starter interfaces.
- Run the supplied checker/tests before and after each implementation and preserve truthful evidence from this checkout.
- Produce report/worksheet support from newly generated data, while leaving student identity and personal reflection fields for the student to supply or approve.

## Lab Scope

### Lab 02

Implement the four controller operations in `student_controller.py`: low-pass filtering, single threshold, hysteresis, and bounded proportional command. Run unit tests, the submission checker, and the student controller comparison.

### Lab 03

Implement the SO(2) update, alternating-tripod decoder, and bounded modulation in `student_cpg.py`. Pass all submission checks and run the requested gait and bridge experiments.

### Lab 04

Implement receptor normalization and the hormone state update in `student_hormone.py`. Pass the checker and run comparison plus zero, one, spike, fault, and Lab 03 contract cases where applicable.

### Lab 05

Do not invent a new controller: this lab is an experimental-analysis scaffold. Run comparison, contact, one-factor, and fault experiments; extract the requested metrics; and prepare worksheet/report material from the new run outputs.

### Lab 06

Complete the explicit emotion-state transition policy, pass the transition checker, run paired C0/C1 trials and replay, and prepare the transition table plus evidence-based discussion.

### Lab 07

Complete the Lab 07 policy and a fresh proposal, pass both checkers, run paired offline trials, and verify replay. Full ROS 2 Jazzy and physical-robot execution is conditional on access to Ubuntu 24.04, ROS 2 Jazzy, and the required hardware; Windows-only work must be labeled offline rather than represented as ROS/hardware evidence.

The proposed default research direction is the robustness of a hormone-modulated nod CPG under modeled message jitter/drop, using fixed policy and paired inputs while measuring software-output latency, missing-response status, and nod frequency. The student must approve or replace this direction before the proposal is finalized.

## Non-goals and Anti-goals

- Do not disguise AI assistance or attempt to evade authorship/AI detection.
- Do not copy the merged `ping-somruethai/student-work` implementation, worksheet wording, identity, figures, or output files.
- Do not fabricate experimental results, ROS 2 runs, physical latency, participant data, or hardware safety validation.
- Do not change instructor safety bounds, checker contracts, or public APIs merely to make tests pass.
- Do not push, open a pull request, or submit coursework without the student's review.

## Constraints

- Local environment is Windows/PowerShell; use the repository's Windows-compatible commands.
- Use Python 3.10 or newer and only dependencies declared by each lab.
- Lab 04-07 offline components use the standard library unless the repository says otherwise.
- Generated results may be ignored by Git; verification summaries must record exact commands and outcomes.
- Student identity is ภาณุพร มาศรี, student ID 6752500118; the group field will be left blank. Predictions and personal reflections still require student confirmation.
- Git author name is `double`; the repository uses the student-supplied email in local Git configuration.
- GitHub write access is not yet authenticated in this environment, so local commits can proceed but pushing may require the student to connect GitHub or complete an interactive credential flow.

## Approaches Considered

### A. Fork plus clean starter branch (selected)

Keep the fork's `main` unchanged and create `student-work` from `fa528b1`, the last instructor starter commit before the merged student completions. This preserves fork ancestry while keeping new work independent and reviewable.

### B. Revert completed-student commits from current `main`

This also preserves the fork, but it adds noisy revert history and risks retaining student-specific files or conflict resolutions. Rejected because the clean starter commit already exists.

### C. Create a new repository from copied starter files

This would isolate the work but would lose the instructor-requested fork relationship. Rejected.

## Implementation and Verification Strategy

For each lab:

1. Read its README, worksheet, starter file, checker, and relevant tests.
2. Run the starter checker/test and record the expected failure or baseline behavior.
3. Add focused tests only when the supplied checker does not cover an important contract.
4. Implement the minimum clear solution from the documented equations and transition rules.
5. Run the checker/tests, then the requested experiments into a new output directory.
6. Inspect raw outputs before writing any claim or metric table.
7. Commit that lab separately with a descriptive commit message.

Pre-run predictions will be drafted from the documented equations, clearly labeled as proposed wording, and shown to the student for confirmation before data-generating experiment runs. Lab 06 will use the README's fixed baseline transition contract, and the same completed policy will carry into Lab 07 unless the student requests a group-specific mapping before implementation.

## Deliverables

- Completed student source files for Labs 02, 03, 04, 06, and 07.
- Lab 05 experiment evidence and analysis rather than invented student code.
- Fresh checker/test results and reproducible commands for every lab.
- Fresh experiment outputs required by each README, subject to `.gitignore` and submission-channel limits.
- Worksheet/report drafts based only on new outputs, with identity and personal-reflection fields explicitly marked for student completion or confirmation.
- Markdown worksheets/report notes will be maintained in the repository. Ignored raw outputs will remain local and be packaged separately if the submission instructions require them; the repository will retain exact verification commands and summaries.
- A final summary of commits, commands, passing checks, limitations, and anything requiring Ubuntu/ROS/hardware.

## Decisions Left to the Builder

- Choose unique result-directory names that do not overwrite earlier evidence.
- Choose focused extra tests when the supplied checks leave a meaningful edge case uncovered.
- Keep comments concise and aligned with the terminology already used by each lab.
- Stop and report any mismatch between README instructions, checker behavior, and equations rather than silently choosing one.
