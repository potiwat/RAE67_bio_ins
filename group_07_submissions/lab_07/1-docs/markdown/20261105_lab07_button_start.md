# Lab07 manual start at the lamp

User requests M/Start to set Normal, then five physical base-button press/release cycles to define measurement start. Only explicitly flagged Lab07 profiles change; ordinary play unchanged.

Waiting retains feedback, camera heartbeat, Stop and ToF fault checks. No FSM interactions/search/idle or CPG/AHM advance while preparing. Use stable debounced edges, count completed releases, discard preparation input queues. Fifth release starts a fresh Normal FSM and never-advanced rhythm bank with the existing 2s envelope. Record source timestamp, initial oscillator/H and input-counter baseline. Do not reset moving oscillators or alter motor settings.

Display count and recording time on existing viewer. Preserve raw evidence, Q partial semantics and 13 topics. Test held/bounced/startup presses, Stop/fault, fifth-release boundary, next button, frozen history and unequal preparation durations. Regress unflagged gameplay, deploy with backup/hash, reopen waiting Start.
