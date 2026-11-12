// lamp_main.cpp - Lamp_Robot main program:
//   1) TUNING   every value you may want to change (the GUI 'tune' keys change some of them live)
//   2) LIVE TUNING  'tune' command, saved in Preferences "tune"
//   3) setup() + loop()  the fixed 20 Hz tick: senses -> hormones -> emotion -> CPG -> targets -> motors
//   4) SERIAL COMMANDS   (type h for the list)
// The steps of one tick live in their own files (see lamp.h). All joint angles are DEGREES FROM ORIGIN.
#include "lamp.h"

// =====================================================================================================
//  TUNING - every value you may want to change is HERE.   Distances in cm, times in seconds.
// =====================================================================================================
// ---- ToF sensors (Week 02 pipeline: contract -> low-pass -> hysteresis + dwell; test in env tof_test) ----
extern const bool  TOF_ON_AT_BOOT = true;    // real ToF starts at boot (false = only after 'tof on')
extern const bool  AUTO_AT_BOOT   = false;   // false = after boot: glide to origin and HOLD STILL (no breathing, no
                                            // emotion poses) until 'auto on' (GUI: AUTO or Auto ON). true = old way
extern const float TOF_BETA       = 0.25f;   // low-pass weight of a new sample (Week 02: 0.25)
extern const float TOF_MIN_CM     = 3;       // sensor contract: valid range
extern const float TOF_MAX_CM     = 120;
extern const uint32_t TOF_STALE_MS = 120;    // sample older than this = INVALID
//                                     T_enter              T_exit                    t_enter                 t_exit
extern const float OBJ_ENTER_CM     = 20, OBJ_EXIT_CM     = 25, OBJ_T_IN     = 0.5f, OBJ_T_OUT     = 2.0f;  // BASE: object
extern const bool OBJ_NEED_BASE = true;   // interested only STARTS when the BASE ToF sees the object (< OBJ_ENTER_CM);
                                          // the camera alone cannot start it (false = old rule: camera alone is enough)
extern const float AFRAID_ENTER_CM    = 30, AFRAID_EXIT_CM    = 35, AFRAID_T_IN    = 0.2f, AFRAID_T_OUT    = 1.0f;  // HEAD: afraid
extern const float STARTLE_ENTER_CM = 10, STARTLE_EXIT_CM = 14, STARTLE_T_IN = 0.0f, STARTLE_T_OUT = 1.0f;  // HEAD: afraid JOLT (< 10 cm)
// PERSON from the BASE ToF wakes the robot to look; it counts as a person only while no camera is connected
extern const float PERSON_LO_CM = 25, PERSON_ENTER_CM = 80, PERSON_EXIT_CM = 95, PERSON_T_IN = 1.5f, PERSON_T_OUT = 3.0f;
// ---- behaviour timing ----
float SLEEP_AFTER_S = 90;                           // nothing seen for this long -> sleepy (motors off). live: tune sleep.after
extern const uint32_t HEAD_BLIND_WAKE_MS = 3000;   // head ToF ignored while sleepy / tired (the head is bowed over the
                                                   // table - it would read the table as "something close" -> afraid)
                                                   // and this long after waking, while the head lifts again
extern const uint32_t STARTLE_HOLD_MS   = 2500;    // jolt (full recoil) held this long, then eases to <= 70 % back
extern const uint32_t STARTLE_BLOCK_MS  = 5000;    // no new startle for this long after one
extern const uint32_t EXCITED_GREET_MS  = 3000;    // a person just arrived: excited wins over interested this long
extern const float    INTERESTED_STOP_CM   = 15;      // head ToF: stop leaning in this close to the object
extern const float    LEAN_RATE  = 0.4f;           // interested: lean 0 -> 1 (full bow) at this rate per second
extern const float    SHOVE_CM   = 8;              // looking at an object: only a head ToF reading below this is scary
extern const float    AFRAID_MAX_BACK = 0.7f;      // afraid backs off at most 70 % of the recoil pose (jolt = 100 %)
// (bored after ~60 s on the same object = the boredom hormone in brain.cpp)
// ---- emotion rules (brain.cpp chooseEmotion): receptor R thresholds ----
extern const float STRESS_AFRAID_R   = 0.10f;      // stress R above this -> afraid (lingers after the hand left)
extern const float NOVELTY_EXCITED_R = 0.40f;      // novelty R above this + a person -> excited
extern const float BOREDOM_BORED_R   = 0.60f;      // boredom R above this -> bored (~60 s on the same object)
extern const float SOCIAL_HAPPY_R    = 0.35f;      // social R above this -> happy (person there ~1 s)
extern const uint32_t EMO_HOLD_MS    = 1500;       // an emotion is held this long before another (afraid: at once)
// ---- bounded mapping receptor -> CPG (brain.cpp mapToCpg) ----
extern const float PHI_NOV_GAIN = 0.08f, PHI_STR_GAIN = 0.30f, PHI_MIN = 0.04f, PHI_MAX = 0.40f;  // phi = EMO_PHI + ...
extern const float AMP_NOV_GAIN = 0.25f, AMP_STR_GAIN = 0.30f, AMP_MIN = 0.5f,  AMP_MAX = 1.5f;   // ampScale = 1 + ...
// ---- motors / safety ----
extern const int TORQUE_LIMIT = 500;               // 0..1000 (500 = 50 %)
extern const int TEMP_EASE_C  = 55;                // above this the rhythm on that joint fades out ...
extern const int TEMP_STILL_C = 62;                // ... and is fully off here (joint just holds its pose)
extern const int TEMP_LIMP_C  = 66;                // torque OFF (limp) to cool down - STS itself cuts near 70 C
extern const int TEMP_BACK_C  = 55;                // torque back on when cooled to this
// fatigue hormone (brain.cpp): S = hottest STS temperature, FATIGUE_T0 -> 0 ... FATIGUE_T1 -> 1.
// R > NAP_ENTER_R -> the lamp takes a NAP (sleepy = motors off) BEFORE the 66 C cut-off; wakes when R < NAP_EXIT_R.
extern const float FATIGUE_T0_C = 50, FATIGUE_T1_C = 62;   // ~58 C -> nap,  ~53 C -> awake again
extern const float NAP_ENTER_R  = 0.65f, NAP_EXIT_R = 0.25f;
extern const float MAX_DEG_S  = 45;                // EVERY joint, every emotion (course: slew <= 0.8 rad/s = 45.8 deg/s)
// ---- RGB ring (WS2812 x32 on GPIO27; colour per emotion = EMO_RGB in brain.cpp) ----
extern const uint8_t RING_BRIGHTNESS = 60;          // 0..255 overall brightness (60 = ~25 %, also limits the current)
extern const float   RING_BREATH     = 0.30f;       // 0..1 how much the light "breathes" with the CPG rhythm
// ---- experiment / measurement (experiment.cpp; course Lab06/Lab07) ----
extern const float MOTION_ONSET_DEG = 0.5f;        // a joint command moved this much -> "motion onset"
extern const uint32_t INPUT_WAIT_MS = 3000;        // input with no emotion change within this -> "no_state_change"
extern const uint32_t ONSET_WAIT_MS = 5000;        // emotion change with no motion within this -> "no_motion"
// ---- camera (USB webcam on the head -> laptop camera/lamp_camera.py -> CAM / WAVE lines on this USB serial) ----
extern const uint32_t CAM_TIMEOUT_MS = 1000;       // no CAM line for this long -> camera LOST -> ToF only
extern const float CAM_T_IN  = 0.3f;               // camera person / object must be seen this long (dwell, C1) ...
extern const float CAM_T_OUT = 1.0f;               // ... and missing this long before it is gone (object)
extern const float CAM_PERSON_T_OUT = 10.0f;       // a PERSON must be missing this long before gone: once someone is
                                                  // seen, assume they are still in front until they really left
                                                  // (a short miss / turned head must not re-trigger "excited")
                                                  // live: tune cam.person_out
float AFRAID_CALM_S = 3.0f;                       // after afraid: stay NORMAL (calm down) this long before happy /
                                                  // excited (Lab06: clear -> normal). 0 = old behaviour. tune afraid.calm
extern const float CAM_ID_T  = 2.0f;               // while an object is there its id is LOCKED; a different id must persist
                                                   // this long to count as a new object (the laptop also locks each object)
extern const uint32_t WAVE_BACK_MS = 3000;         // waving back lasts this long
extern const float WAVE_AMP_DEG = 20;              // head yaw swing when waving back
extern const float WAVE_PHI     = 0.25f;           // CPG speed while waving back (~1.3 s per swing)
extern const float LOOK_DEG_S   = 20;              // happy / excited: how fast the head turns toward the person
float HEAD_UP_DEG = 15;                            // normal / happy / excited: head pitch + this (look up at a STANDING
                                                   // person). GUI Behaviour tab "head up" (tune head.up)
// object memory: a returning object whose remembered boredom R is still above this is "seen recently" -> stays bored.
// boredom fades with tau ~65 s -> an object that was boring (R 0.6) is forgotten after ~60 s away.
extern const float RECALL_R     = 0.25f;
// ---- following the object (interested): head first, the base helps when the head is turned far ----
float TRACK_DEG_S   = 25;                   // head turn speed per unit of image offset (x 1.0 = image edge)
float TRACK_START_PCT = 10;                // object must be this far from the image centre (% of the image width)
                                          // before the head starts to turn: 0 = never follow, 1 = follow every tiny move
float TRACK_STOP_PCT  = 4;                // ... then it turns until the object is this close to the centre, and holds still
extern const float TRACK_YAW_SIGN = -1, TRACK_PITCH_SIGN = 1, TRACK_BASE_SIGN = 1;   // yaw -1: measured 2026-11-11
                                                  // (with +1 the head turned AWAY from the person: 14 of 18 turns)   // flip if it turns AWAY
extern const float OBJ_JUMP      = 0.35f;          // object position jumps this much between frames -> lifted? HOLD
extern const float OBJ_SETTLE_S  = 0.4f;           // ... it stays at the new place this long -> follow it there
                                                  // (was 1.0 s)
extern const float BASE_SHARE_DEG = 30;            // head yaw beyond this -> the base turns to help ...
extern const float BASE_DEG_S    = 10;             // ... this fast (the head turns back by the same amount)
// =====================================================================================================

// =====================================================================================================
//  2) LIVE TUNING (GUI Control page) - saved in Preferences "tune", loaded at boot
//   tune                 print all values (one line: "tune <key> <value> ... saved|unsaved")
//   tune <key> <value>   change one value now     tune save   keep after reboot     tune reset   back to the TUNING above
// =====================================================================================================
float ampGain  = 1.0f;          // x every CPG amplitude (emotions still choose WHICH joints breathe and how much)
float speedCap = MAX_DEG_S;     // deg/s, cap on every joint on top of what the emotion asks (never above MAX_DEG_S)
struct TuneVar { const char *key; float *p; float lo, hi; float def; };
TuneVar TUNE[] = {
  {"alpha", &cpg.alpha, 1.01f, 1.5f}, {"amp", &ampGain, 0, 2}, {"speed", &speedCap, 5, MAX_DEG_S},
  {"object.enter", &hObject.enterCm, 3, 120}, {"object.exit", &hObject.exitCm, 3, 120},
  {"object.tin",   &hObject.tEnter,  0, 10},  {"object.tout", &hObject.tExit,  0, 10},
  {"afraid.enter", &hAfraid.enterCm, 3, 120}, {"afraid.exit", &hAfraid.exitCm, 3, 120},
  {"afraid.tin",   &hAfraid.tEnter,  0, 10},  {"afraid.tout", &hAfraid.tExit,  0, 10},
  {"jolt.enter",   &hStartle.enterCm, 3, 120}, {"jolt.exit",  &hStartle.exitCm, 3, 120},
  {"jolt.tin",     &hStartle.tEnter,  0, 10},  {"jolt.tout",  &hStartle.tExit,  0, 10},
  {"person.enter", &hPerson.enterCm, 3, 120}, {"person.exit", &hPerson.exitCm, 3, 120},
  {"person.tin",   &hPerson.tEnter,  0, 10},  {"person.tout", &hPerson.tExit,  0, 10},
  {"cam.person_out", &dCamPerson.tExit, 0, 30}, {"afraid.calm", &AFRAID_CALM_S, 0, 10},
  {"track.speed", &TRACK_DEG_S, 0, 45},   {"track.start", &TRACK_START_PCT, 0, 50},
  {"track.stop", &TRACK_STOP_PCT, 0, 50},   {"sleep.after", &SLEEP_AFTER_S, 10, 600},
  {"head.up", &HEAD_UP_DEG, -20, 30},
};
const int NTUNE = sizeof(TUNE) / sizeof(TUNE[0]);
bool tuneDirty = false;

static void tuneFix() {
  for (int i = 0; i < NTUNE; i++) *TUNE[i].p = constrain(*TUNE[i].p, TUNE[i].lo, TUNE[i].hi);
  for (Hyst *h : {&hObject, &hAfraid, &hStartle, &hPerson}) if (h->exitCm < h->enterCm) h->exitCm = h->enterCm;  // exit never inside enter
}
void tunePrint() {
  Serial.print("tune");
  for (int i = 0; i < NTUNE; i++) Serial.printf(" %s %g", TUNE[i].key, *TUNE[i].p);
  Serial.println(tuneDirty ? " unsaved" : " saved");
}
void tuneBegin() {              // call in setup(): remember the TUNING defaults, then load the saved values on top
  for (int i = 0; i < NTUNE; i++) TUNE[i].def = *TUNE[i].p;
  Preferences tp; tp.begin("tune", true);
  float v[NTUNE];
  if (tp.getBytesLength("v") == sizeof(v)) { tp.getBytes("v", v, sizeof(v)); for (int i = 0; i < NTUNE; i++) *TUNE[i].p = v[i]; }
  tp.end();
  tuneFix(); tunePrint();
}
void tuneCommand(const char *line) {
  char k[20] = {0}; float x = 0;
  int n = sscanf(line, "%*s %19s %f", k, &x);
  if (n >= 1 && !strcmp(k, "save")) {
    float v[NTUNE]; for (int i = 0; i < NTUNE; i++) v[i] = *TUNE[i].p;
    Preferences tp; tp.begin("tune", false); tp.putBytes("v", v, sizeof(v)); tp.end();
    tuneDirty = false; Serial.println("tune: saved to the ESP32 (kept after reboot)");
  } else if (n >= 1 && !strcmp(k, "reset")) {
    for (int i = 0; i < NTUNE; i++) *TUNE[i].p = TUNE[i].def;
    Preferences tp; tp.begin("tune", false); tp.remove("v"); tp.end();
    tuneDirty = false; Serial.println("tune: back to the TUNING defaults (saved values erased)");
  } else if (n == 2) {
    int i = 0; while (i < NTUNE && strcmp(k, TUNE[i].key)) i++;
    if (i == NTUNE) { Serial.printf("tune: unknown '%s'\n", k); return; }
    *TUNE[i].p = x; tuneFix(); tuneDirty = true;
  } else if (n >= 1) { Serial.println("tune | tune <key> <value> | tune save | tune reset"); return; }
  tunePrint();
}

// =====================================================================================================
//  3) SETUP + 20 Hz LOOP
// =====================================================================================================
bool showStats = false;                // 'stat': print the loop speed every second

void setup() {
  Serial.setTxBufferSize(2048);   // BEFORE begin: printing a D row (~250 B, 20/s for the GUI) must not block the
  Serial.setRxBufferSize(1024);   // 20 Hz loop (default = only the 128 B hardware FIFO -> ~10 ms wait per row)
  Serial.begin(115200);
  delay(300);
  Serial.printf("\nLamp_Robot (CPG + hormones) - reset reason %d\n", (int)esp_reset_reason());
  Serial2.begin(BUS_BAUD, SERIAL_8N1, BUS_RX, BUS_TX);
  st.pSerial = &Serial2;
  delay(500);
  loadLimits();
  cpgDefaults();
  hormoneSelfTest();
  memcpy(EMO_POSE, EMO_POSE_DEF, sizeof(EMO_POSE));   // defaults first, saved poses on top
  loadPoses();
  loadSoftLimits();
  tuneBegin();                                      // saved GUI tuning on top of TUNING
  lastActivityMs = millis();
  startPose();
  lightsBegin();                                    // RGB ring off until the first tick
  if (tofEnabled) { tofInit(tofBase); tofInit(tofHead); }
  else Serial.println("ToF: OFF - type 'tof on' to start the real sensors ('s base' / 's near' simulate them)");
  printJoints();
  autoMode = AUTO_AT_BOOT;
  Serial.println(autoMode ? "gliding to origin. type h for the command list"
                          : "gliding to origin, then WAITING (auto off) - press AUTO in the GUI or type 'auto on' to start");
}

void loop() {
  static uint32_t next = millis(), lastStat = millis();
  static uint32_t ticks = 0, overruns = 0, worstUs = 0;
  static bool autoBreath = false;
  if (!autoBreath && millis() > 3000) {             // always alive: the CPG runs by itself after boot
    autoBreath = true;
    if (!estop && autoMode) { cpg.on = true; Serial.println("cpg on"); }   // waiting (auto off): stay still
  }

  readSerial();                                     // between ticks: never blocks

  uint32_t now = millis();
  if ((int32_t)(now - next) < 0) return;
  if ((int32_t)(now - next) > (int32_t)PERIOD_MS) next = now;   // fell behind: don't burst-catch-up
  next += PERIOD_MS;

  uint32_t t0 = micros();
  // ---- one 50 ms tick: senses -> hormones -> emotion -> CPG -> setTarget -> motors ----
  scenarioStep();       // 'scen': scripted synthetic stimuli (replaces the raw ToF samples)
  sensorsStep();        // real ToF -> sense.baseCm / sense.headCm
  emotionStep();
  cpgStep();            // runs always (so it is warmed up); joints only feel it when 'cpg on'
  if (!estop) composeTargets();
  sendOutputs();
  lightsStep();         // RGB ring: emotion colour, breathing with the CPG
  healthStep();
  experimentStep();     // logs, motion-onset detection, RGB keep-alive
  // ---------------------------------------------------------------------------------------------
  uint32_t us = micros() - t0;
  ticks++;
  if (us > worstUs) worstUs = us;
  if (us > PERIOD_MS * 1000) overruns++;

  if (millis() - lastStat >= 1000 && hlog) printHormones();
  if (millis() - lastStat >= 1000) {
    if (showStats || overruns) Serial.printf("loop: %lu ticks/s, worst %lu us, overruns %lu\n",
                                             (unsigned long)ticks, (unsigned long)worstUs, (unsigned long)overruns);
    ticks = 0; worstUs = 0; overruns = 0; lastStat = millis();
  }
}

// =====================================================================================================
//  4) SERIAL COMMANDS (type h for the list)
// =====================================================================================================
void printHelp() {
  Serial.println(
    "\n===== STATUS =====\n"
    "  j                    joint table (limits, target, temperature, state)\n"
    "  hm  | hm log         emotion + 4 hormones + senses  (log = every second)\n"
    "  cpg                  CPG alpha, phi, period, amplitude\n"
    "  poses                pose of every emotion\n"
    "  soft                 normal ranges   soft <joint> <min> <max> | soft <joint> reset\n"
    "                       (all emotions use the normal range; sleepy may use the whole taught range)\n"
    "  stat                 loop speed (should be 20 ticks/s)\n"
    "  tune [<key> <v>|save|reset]  live tuning (GUI), saved in the ESP32\n"
    "  htest                hormone formula check vs slides (PASS)\n"
    "===== SAFETY =====\n"
    "  stop                 EMERGENCY STOP - all motors limp\n"
    "  teach <joint>        re-teach origin + limits by hand (e.g. teach elbow)\n"
    "  resume               continue from the current pose\n"
    "===== SIMULATED SENSES (until ToF / camera) =====\n"
    "  s person 1|0         person there / gone            (camera)\n"
    "  s object 1..9|0      object of colour n / none      (camera)\n"
    "  s pos <x> <y>        object position in image -1..1 (camera)\n"
    "  s base <cm>          BASE ToF distance (<50 = something there -> interested)\n"
    "  s near <cm> | s far  HEAD ToF distance (<30 afraid, <10 afraid + jolt) / nothing\n"
    "  s clear              clear all senses     s real   use the real ToF again\n"
    "  cam                  camera status (CAM lines from camera/lamp_camera.py on the laptop)\n"
    "===== ToF =====\n"
    "  tof on | tof off     start / stop the real ToF sensors (ON at boot: TOF_ON_AT_BOOT)\n"
    "  tof | tof live       sensors + event states / stream them (live: type again to stop)\n"
    "  tof scan             wiring check: SDA/SCL idle level + I2C scan of both ToF buses\n"
    "===== EMOTIONS & POSES =====\n"
    "  emo <name> | emo auto   force an emotion / back to automatic\n"
    "  save <name>          store CURRENT pose for it (stop -> pose by hand -> resume -> save)\n"
    "  forget <name>        delete the saved pose -> back to the default\n"
    "  auto on|off          emotions drive the robot / manual control\n"
    "  light on | light off RGB ring on / off\n"
    "  names: normal sleepy excited happy interested bored afraid tired\n"
    "         (course states: normal interested happy afraid sleepy; old names calm/curious/wary still work)\n"
    "===== EXPERIMENT (course Lab06/07) =====\n"
    "  cond 0|1             C0 = raw threshold (baseline) / C1 = hysteresis + dwell (normal)\n"
    "  trial start | end    one run -> summary + S,... CSV row (transitions/min, latency, ...)\n"
    "  scen <seed> | stop   scripted 60 s stimuli, same every time (seeds 41 42 43); runs a trial\n"
    "  log on [n] | off     D,... CSV row every n ticks + E,... events (input/emotion/motion onset)\n"
    "  rgb                  RGB ring: pin + colour now\n"
    "===== MANUAL (auto off) =====\n"
    "  t <joint> <deg>      pose of a joint, deg from origin\n"
    "  home                 all joints to origin\n"
    "  v <deg/s>            max joint speed\n"
    "  joints: base(0) shoulder(1) elbow(2) pitch(3) yaw(4)\n"
    "===== CPG =====\n"
    "  cpg on|off           rhythm on / off\n"
    "  phi <0.05..0.8>      rhythm speed       alpha <1.01..1.5>  wave shape\n"
    "  amp <joint> <deg>    rhythm size        src <joint> <0|1|2|-1|-2>  which output\n"
    "  csv on|off           stream a1,a2,o1,o2 for plots\n"
    "  (with auto on, emotions overwrite phi/amp)\n");
}

// ---- s ... : simulated senses (replace the camera / the RAW ToF samples) ----
static void simCommand(const char *a, int n, float v, const char *line) {
  if (!strcmp(a, "person")) { sense.person = v > 0; noteInput("cam_person", sense.person, millis()); }
  else if (!strcmp(a, "object")) { sense.color = (int)v; sense.object = sense.color > 0;    // s object <colour id>, 0 = none
                                   noteInput("cam_object", sense.object, millis()); }
  else if (!strcmp(a, "near")) tofHead.simCm = (n >= 3) ? v : NAN;   // replaces the RAW head sample
  else if (!strcmp(a, "far"))  tofHead.simCm = 999;                   // out of range -> nothing there
  else if (!strcmp(a, "base")) tofBase.simCm = (n >= 3) ? v : NAN;   // replaces the RAW base sample
  else if (!strcmp(a, "pos")) { float x = 0, y = 0; sscanf(line, "%*s %*s %f %f", &x, &y);
                                sense.objX = constrain(x, -1.0f, 1.0f); sense.objY = constrain(y, -1.0f, 1.0f); }
  else if (!strcmp(a, "clear")) { sense.person = sense.object = false; sense.color = 0; tofHead.simCm = tofBase.simCm = 999; }
  else if (!strcmp(a, "real"))  { tofHead.simCm = tofBase.simCm = NAN; Serial.println("ToF: real sensors again"); return; }
  else { Serial.println("s person 0|1 | s object <colour 1..9, 0=none> | s pos <x> <y> | s near <cm> | s far | s base <cm> | s clear"); return; }
  Serial.printf("senses: person %d object %d (colour %d) head %.0f cm base %.0f cm\n",
                sense.person, sense.object, sense.color, sense.headCm, sense.baseCm);
}

// ---- tof ... : status / live stream / wiring scan / on / off ----
static void tofCommand(const char *a, int n) {
  if (n >= 2 && !strcmp(a, "scan")) tofScan();
  else if (n >= 2 && !strcmp(a, "live")) { tofLive = !tofLive; Serial.printf("ToF live %s\n", tofLive ? "on" : "off"); }
  else if (n >= 2 && !strcmp(a, "on"))  { tofEnabled = true; tofInit(tofBase); tofInit(tofHead); Serial.println("ToF ON"); }
  else if (n >= 2 && !strcmp(a, "off")) { tofEnabled = false; Serial.println("ToF OFF (no ToF events; simulation still works)"); }
  else {
    for (Tof *t : {&tofBase, &tofHead})
      Serial.printf("ToF %s: %s%s raw %.1f filt %.1f cm %s (invalid samples %lu)\n", t->name,
                    t->ok ? "OK" : "NOT CONNECTED", isnan(t->simCm) ? "" : " (SIMULATED)",
                    t->raw, t->filt, t->valid ? "ok" : "INVALID", (unsigned long)t->invalidCount);
    for (Hyst *h : {&hObject, &hPerson, &hAfraid, &hStartle})
      Serial.printf("  %-8s %s  (enter %.0f, exit %.0f cm, t_enter %.1f s, t_exit %.1f s)\n", h->name,
                    h->on ? "ON " : "off", h->enterCm, h->exitCm, h->tEnter, h->tExit);
  }
}

// ---- CPG by hand: cpg on|off, alpha, phi, csv, amp, src (with auto on the emotions overwrite phi / amp) ----
static bool cpgCommand(const char *c, const char *a, int n, float v) {
  if (!strcmp(c, "cpg")) {
    if (n >= 2 && !strcmp(a, "on"))  { if (estop) { Serial.println("in STOP - 'resume' first"); return true; } cpg.on = true; Serial.println("cpg on"); }
    else if (n >= 2 && !strcmp(a, "off")) { cpg.on = false; Serial.println("cpg off"); }
    else Serial.printf("cpg %s gain %.2f | alpha %.3f phi %.3f rad | period %.2f s | amplitude %.3f | limit hits %lu\n",
                       cpg.on ? "ON" : "off", cpg.gain, cpg.alpha, cpg.phi, cpg.period, cpg.peak, (unsigned long)clampTicks);
  }
  else if (!strcmp(c, "alpha") && n >= 2) { cpg.alpha = constrain(atof(a), 1.01f, 1.5f); Serial.printf("alpha %.3f\n", cpg.alpha); }
  else if (!strcmp(c, "phi") && n >= 2)   { cpg.phi = constrain(atof(a), 0.05f, 0.8f); Serial.printf("phi %.3f rad%s\n", cpg.phi, autoMode ? " (auto on: hormones will override - 'auto off' to keep it)" : ""); }
  else if (!strcmp(c, "csv") && n >= 2) {
    cpg.csv = !strcmp(a, "on");
    if (cpg.csv) Serial.println("t_ms,a1,a2,o1,o2,alpha,phi");
  }
  else if ((!strcmp(c, "amp") || !strcmp(c, "src")) && n >= 3) {
    int i = findJoint(a);
    if (i < 0 || i >= NJ) { Serial.println("unknown joint"); return true; }
    if (!strcmp(c, "amp")) J[i].amp = constrain(v, 0.0f, 30.0f);
    else J[i].src = constrain((int)v, -2, 2);
    Serial.printf("%s: src %d amp %.1f deg\n", J[i].name, J[i].src, J[i].amp);
  }
  else return false;
  return true;
}

// ---- manual joints: home, v <deg/s>, t <joint> <deg> (switch auto off) ----
static bool manualCommand(const char *c, const char *a, int n, float v) {
  if (!strcmp(c, "home")) { autoMode = false; for (int i = 0; i < NJ; i++) J[i].pose = 0; Serial.println("home (auto off)"); }
  else if (!strcmp(c, "v") && n >= 2) {
    float s = constrain(atof(a), 5.0f, MAX_DEG_S);
    for (int i = 0; i < NJ; i++) J[i].maxSpeed = s;
    Serial.printf("max speed %.0f deg/s\n", s);
  }
  else if (!strcmp(c, "t") && n >= 3) {
    int i = findJoint(a);
    if (i < 0 || i >= NJ) { Serial.println("unknown joint"); return true; }
    if (estop) { Serial.println("in STOP - 'resume' first"); return true; }
    if (!J[i].enabled) { Serial.printf("%s is DISABLED (not taught)\n", J[i].name); return true; }
    float pv = constrain(v, J[i].loDeg, J[i].hiDeg);
    if (autoMode) { autoMode = false; Serial.println("(auto off - emotions no longer move the pose; 'auto on' to return)"); }
    J[i].pose = pv;
    Serial.printf("%s pose %+.1f deg%s\n", J[i].name, pv, pv != v ? " (clamped)" : "");
  }
  else return false;
  return true;
}

void handleLine(char *line) {
  if (!strncmp(line, "cam,", 4))  { cameraLine(line); return; }   // camera data from the laptop (not a command)
  if (!strncmp(line, "wave,", 5)) { waveLine(line); return; }
  char c[12] = {0}, a[12] = {0}; float v = 0;
  int n = sscanf(line, "%11s %11s %f", c, a, &v);
  if (n < 1) return;
  if (handleSetupCommand(c, a, n, line)) return;   // teach / soft / save / forget / poses -> motors.cpp
  if (handleExperimentCommand(c, a, n, v)) return; // cond / trial / scen / log / rgb       -> experiment.cpp
  if (cpgCommand(c, a, n, v)) return;
  if (manualCommand(c, a, n, v)) return;
  if (!strcmp(c, "stop")) emergencyStop();
  else if (!strcmp(c, "resume")) resume();
  else if (!strcmp(c, "j")) printJoints();
  else if (!strcmp(c, "s")) simCommand(a, n, v, line);
  else if (!strcmp(c, "tof")) tofCommand(a, n);
  else if (!strcmp(c, "hm")) {
    if (n >= 2 && !strcmp(a, "log")) { hlog = !hlog; Serial.printf("hormone log %s\n", hlog ? "on" : "off"); }
    else printHormones();
  }
  else if (!strcmp(c, "auto") && n >= 2) {
    bool was = autoMode;
    autoMode = !strcmp(a, "on");
    if (autoMode && !was) regreet();                 // someone already in front -> greet (excited) now
    if (autoMode && !estop) cpg.on = true;          // emotions use the CPG again
    if (autoMode) useHardRange = false;
    for (int i = 0; i < NJ; i++) J[i].maxSpeed = MAX_DEG_S;
    Serial.printf("auto %s\n", autoMode ? "on" : "off");
  }
  else if (!strcmp(c, "emo") && n >= 2) {
    int e = findEmotion(a);
    if (e < 0 && emoForced != NEMO) regreet();     // back to automatic -> greet a person already there
    emoForced = (e < 0) ? NEMO : (Emotion)e;
    Serial.printf("emotion %s\n", emoForced == NEMO ? "back to automatic" : EMO_NAME[emoForced]);
  }
  else if (!strcmp(c, "light") && n >= 2) {       // light on | light off  (RGB ring)
    ringOn = strcmp(a, "off") != 0;
    Serial.printf("light %s\n", ringOn ? "on" : "off");
  }
  else if (!strcmp(c, "cam")) {
    Serial.printf("camera %s | lines %lu, lost %lu | raw person %d object %d id %d | filtered person %d object %d "
                  "id %d | x %.2f y %.2f\n", cameraConnected ? "CONNECTED" : "not connected", (unsigned long)camLines,
                  (unsigned long)camLost, camRawPerson, camRawObject, camRawId, sense.person, sense.object,
                  sense.color, sense.objX, sense.objY);
  }
  else if (!strcmp(c, "htest")) hormoneSelfTest();
  else if (!strcmp(c, "tune")) tuneCommand(line);
  else if (!strcmp(c, "stat")) showStats = !showStats;
  else if (!strcmp(c, "h") || !strcmp(c, "help")) printHelp();
  else Serial.printf("? unknown '%s' - type h for the command list\n", line);
}

void readSerial() {
  static char buf[64]; static int len = 0; static int skip = 0;
  while (Serial.available()) {
    char ch = Serial.read();
    if (skip) { skip--; continue; }
    if (ch == 0x1B) { skip = 2; continue; }                 // arrow keys
    if (ch == 0x08 || ch == 0x7F) { if (len) len--; continue; }
    if (ch == '\n' || ch == '\r') {
      buf[len] = 0;
      if (len) handleLine(buf);
      len = 0;
    } else if (len < (int)sizeof(buf) - 1 && ch >= 32 && ch < 127) buf[len++] = tolower(ch);
  }
}
