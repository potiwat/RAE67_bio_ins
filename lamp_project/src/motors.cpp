// motors.cpp - the body:
//   1) joints, targets (always clamped), servo output, health / thermal checks, stop / resume
//   2) set-up tools: teach <joint>, soft ranges, save / forget / poses
//   3) RGB ring (colour of the emotion, breathing with the CPG)
#include "lamp.h"

// ====================================================================================================
// 1) JOINTS + OUTPUT + SAFETY
// ====================================================================================================
SMS_STS st;
Servo mg;
Preferences prefs;

// Values = the taught limits of 2026-11-07 for reference. Real STS limits are re-read from the servos at boot;
// a servo whose limits can't be trusted is DISABLED (never moved) - we never guess limits, because a
// range that crosses the 4095->0 wrap makes the servo drive through the blocked side (docs/issues.md #8).
Joint J[] = {
  //  name       type id  origin   lo      hi     tgt cmd speed ok  temp enabled
  {"base",     MG,  MG_PIN, 90,  -90.0f,  90.0f, 0, 0, 45, true, 0, true},
  {"shoulder", STS, 1, STS_ORIGIN, -58.3f,  74.1f, 0, 0, 45, true, 0, true},
  {"elbow",    STS, 2, STS_ORIGIN, -46.7f,   2.3f, 0, 0, 45, true, 0, true},   // origin at its top end
  {"pitch",    STS, 3, STS_ORIGIN, -70.8f,  33.1f, 0, 0, 45, true, 0, true},   // head look up/down
  {"yaw",      STS, 4, STS_ORIGIN, -70.8f,  64.4f, 0, 0, 45, true, 0, true},   // head turn left/right
};
extern const int NJ = sizeof(J) / sizeof(J[0]);

bool estop = false;

// ---------------- helpers ----------------
int stepsFromDeg(const Joint &j, float d) { return (int)lroundf(j.originNative + d * STEPS_PER_DEG); }
float degFromSteps(const Joint &j, int s) { return (s - j.originNative) / STEPS_PER_DEG; }

bool useHardRange = false;                          // true while sleepy, or while holding a hand pose (resume)
void setTarget(int i, float deg) {                 // the ONLY way to set a target -> always clamped
  if (i < 0 || i >= NJ) return;
  float lo = useHardRange ? J[i].loDeg : J[i].softLo, hi = useHardRange ? J[i].hiDeg : J[i].softHi;
  J[i].target = constrain(deg, lo, hi);
}

// target = pose + rhythm  -> through setTarget (clamped). Counts how often the rhythm hits a limit.
uint32_t clampTicks = 0;
float ampScale = 1.0f;       // set by the hormone system
void composeTargets() {
  for (int i = 0; i < NJ; i++) {
    // hot joint: rhythm fades out between TEMP_EASE_C and TEMP_STILL_C (less work, it only holds)
    float heat = constrain((TEMP_STILL_C - J[i].temp) / (float)(TEMP_STILL_C - TEMP_EASE_C), 0.0f, 1.0f);
    float want = J[i].pose + cpg.gain * ampScale * ampGain * heat * J[i].amp * cpgOut(J[i].src);
    setTarget(i, want);
    if (J[i].target != want) clampTicks++;
  }
}


// ---------------- MG996R ----------------
void mgWriteDeg(const Joint &j, float d) {          // d = deg from origin
  float absDeg = constrain(j.originNative + d, 0.0f, 180.0f);
  mg.writeMicroseconds(MG_MIN_US + (int)lroundf(absDeg * (MG_MAX_US - MG_MIN_US) / 180.0f));
}
void mgLimp() { ledcWrite(MG_PIN, 0); }             // stop pulses, keep the channel (never detach - issues.md #14)


int findJoint(const char *s) {
  if (isDigit(s[0])) return atoi(s);
  for (int i = 0; i < NJ; i++) if (!strcmp(s, J[i].name)) return i;
  return -1;
}

void printJoints() {
  Serial.println(" #  name      type id   min      max      (normal range)    target   cmd      ok  temp");
  for (int i = 0; i < NJ; i++) {
    const Joint &j = J[i];
    Serial.printf(" %d  %-9s %-4s %-3d  %+7.1f  %+7.1f  (%+6.1f..%+6.1f)  %+7.1f  %+7.1f  %s  %d%s\n", i, j.name,
                  j.type == STS ? "STS" : "MG", j.id, j.loDeg, j.hiDeg, j.softLo, j.softHi, j.target, j.cmd,
                  j.ok ? "y" : "N", j.temp, !j.enabled ? "  DISABLED" : j.cooling ? "  COOLING (limp)" : "");
  }
}


// ---------------- boot ----------------
void loadLimits() {
  // MG: values saved by servo_test (Preferences "sts")
  prefs.begin("sts", true);
  float lo = prefs.getFloat("mlo", 0), hi = prefs.getFloat("mhi", 180), o = prefs.getFloat("mor", 90);
  prefs.end();
  J[0].originNative = o; J[0].loDeg = lo - o; J[0].hiDeg = hi - o;

  // STS: limits stored inside each servo
  for (int i = 0; i < NJ; i++) if (J[i].type == STS) readLimits(J[i], true);
}

// Read the taught limits stored inside one STS. Returns true when they are valid (joint may be used).
// No answer at all (motor power off / bus problem) -> 'unread': healthStep() tries again when it answers.
bool readLimits(Joint &j, bool atBoot) {
  // Read until two reads in a row agree (at boot one read once gave the elbow -114..+93 instead of -46.7..+2.3)
  int l = -1, h = -1;
  for (int k = 0; k < 4; k++) {
    int l2 = st.readWord(j.id, SMS_STS_MIN_ANGLE_LIMIT_L), h2 = st.readWord(j.id, SMS_STS_MAX_ANGLE_LIMIT_L);
    if (l2 >= 0 && h2 >= 0 && l2 == l && h2 == h) break;
    l = l2; h = h2;
    if (k == 3) l = h = -1;                                       // never agreed -> treat as no answer, retry later
    delay(5);
  }
  if (l < 0 || h < 0) {
    j.enabled = false; j.unread = true;
    if (atBoot) Serial.printf("WAIT %s (ID %d): no answer (motor power off?) - it is enabled by itself when it answers\n",
                              j.name, j.id);
    return false;
  }
  j.unread = false;
  // Valid only if: ordered, contains origin 2048 (+/- the 20-step inset), and is not the
  // factory 0..4095 (= never taught / uncalibrated origin).
  bool valid = l < h && l <= STS_ORIGIN + 20 && STS_ORIGIN - 20 <= h && !(l == 0 && h == 4095);
  if (!valid) {
    j.enabled = false;
    Serial.printf("DISABLED %s (ID %d): limits %d..%d not taught -> run 'teach %d'\n", j.name, j.id, l, h, j.id);
    return false;
  }
  j.loDeg = degFromSteps(j, l); j.hiDeg = degFromSteps(j, h);
  return true;
}

// A servo that was silent at boot answers now (motor power switched on later): load its limits, start it at
// its CURRENT position (no jump) and let it glide like at boot. Called by healthStep().
static void lateEnable(Joint &j) {
  if (!readLimits(j, false)) return;
  int p = st.ReadPos(j.id);
  if (p < 0) { j.unread = true; return; }                       // try again next round
  float d = degFromSteps(j, p);
  if (d < j.loDeg - 15 || d > j.hiDeg + 15) {
    j.enabled = false; j.unread = true;                          // keep checking: enabled once moved back by hand
    if (!j.farOut) Serial.printf("DISABLED %s: now at %+.1f deg, far outside %+.1f..%+.1f -> move it back by hand "
                                 "(or re-teach)\n", j.name, d, j.loDeg, j.hiDeg);
    j.farOut = true;
    return;
  }
  j.farOut = false;
  j.cmd = j.target = constrain(d, j.loDeg, j.hiDeg);
  if (!autoMode) j.pose = 0;                                     // waiting: glide to origin, as after boot
  j.enabled = true; j.lost = false;
  st.writeWord(j.id, SMS_STS_TORQUE_LIMIT_L, TORQUE_LIMIT);
  if (!estop && !sleepLimp) st.EnableTorque(j.id, 1);
  Serial.printf("OK  %s (ID %d) answered: limits %+.1f..%+.1f loaded, enabled at %+.1f deg%s\n", j.name, j.id,
                j.loDeg, j.hiDeg, j.cmd, estop ? " (STOP: torque stays off)" : "");
}

void startPose() {
  // STS: start the output at the CURRENT position so nothing jumps, then glide to origin.
  for (int i = 0; i < NJ; i++) {
    Joint &j = J[i];
    if (j.type == STS) {
      if (!j.enabled) { st.EnableTorque(j.id, 0); continue; }
      int p = st.ReadPos(j.id);
      j.ok = p >= 0;
      // A position far outside the limits means origin/limits don't match this servo -> don't touch it.
      if (j.ok && (degFromSteps(j, p) < j.loDeg - 15 || degFromSteps(j, p) > j.hiDeg + 15)) {
        j.enabled = false; st.EnableTorque(j.id, 0);
        j.unread = true; j.farOut = true;                        // healthStep() enables it once it is back in range
        Serial.printf("DISABLED %s: now at %+.1f deg, far outside %+.1f..%+.1f -> move it back by hand "
                      "(or re-teach)\n", j.name, degFromSteps(j, p), j.loDeg, j.hiDeg);
        continue;
      }
      j.cmd = j.ok ? constrain(degFromSteps(j, p), j.loDeg, j.hiDeg) : 0;
      st.writeWord(j.id, SMS_STS_TORQUE_LIMIT_L, TORQUE_LIMIT);
      st.EnableTorque(j.id, 1);
    } else {
      j.cmd = 0;                                    // MG has no feedback: it JUMPS to origin here
    }
    setTarget(i, 0);
  }
  mg.setPeriodHertz(50);
  mg.attach(MG_PIN, MG_MIN_US, MG_MAX_US);          // attach ONCE
  mg.setTimerWidth(16);                             // after attach (docs/issues.md #2)
  mgWriteDeg(J[0], 0);
}

// ---------------- 20 Hz control step ----------------
void sendOutputs() {
  if (estop || sleepLimp) return;
  u8 ids[8]; s16 pos[8]; u16 spd[8]; u8 acc[8]; int n = 0;
  for (int i = 0; i < NJ; i++) {
    Joint &j = J[i];
    float vmax = fminf(fminf(j.maxSpeed, speedCap), MAX_DEG_S);
    float step = vmax * DT; // slew limit per tick (course: <= 0.8 rad/s)
    j.cmd += constrain(j.target - j.cmd, -step, step);
    j.cmd = constrain(j.cmd, j.loDeg, j.hiDeg);     // second safety clamp right before output
    if (j.type == MG) { mgWriteDeg(j, j.cmd); continue; }
    if (!j.enabled || j.cooling || j.lost) continue;
    ids[n] = j.id;
    pos[n] = stepsFromDeg(j, j.cmd);
    spd[n] = (u16)(vmax * STEPS_PER_DEG * 1.5f);   // servo may move a bit faster than the setpoint ramp
    acc[n] = 0;                                     // 0 = no extra ramp: the 20 Hz setpoints are the ramp
    n++;
  }
  if (n) st.SyncWritePosEx(ids, n, pos, spd, acc);  // one bus packet for all STS
}

// Health: one STS per tick (round robin) so the bus time per tick stays small.
void healthStep() {
  static int k = 0;
  static uint32_t lastTorque = 0;
  int i = 1 + (k++ % (NJ - 1));                     // joints 1..4 are STS
  Joint &j = J[i];
  int t = st.ReadTemper(j.id);
  bool ok = t >= 0;
  if (ok != j.ok) Serial.printf("%s %s (ID %d)\n", ok ? "OK  " : "WARN no reply:", j.name, j.id);
  j.ok = ok;
  if (ok && j.unread) lateEnable(j);                 // silent at boot, answers now -> use it
  if (ok) {
    if (t >= TEMP_EASE_C && j.temp < TEMP_EASE_C) Serial.printf("WARN %s warm %d C: rhythm fading out\n", j.name, t);
    j.temp = t;
    if (!j.cooling && j.enabled && t >= TEMP_LIMP_C) {
      j.cooling = true;
      st.EnableTorque(j.id, 0);
      Serial.printf("HOT %s %d C: torque OFF to cool (back on at %d C)\n", j.name, t, TEMP_BACK_C);
    } else if (j.cooling && t <= TEMP_BACK_C && !estop && !sleepLimp) {
      int p = st.ReadPos(j.id);
      if (p >= 0) j.cmd = constrain(degFromSteps(j, p), j.loDeg, j.hiDeg);   // resume from where it sagged to
      st.EnableTorque(j.id, 1);
      j.cooling = false;
      Serial.printf("%s cooled to %d C: torque back on\n", j.name, t);
    }
  }
  if (millis() - lastTorque > 5000 && !estop && !sleepLimp) {   // torque limit is RAM in the servo -> refresh (docs/issues.md #17)
    lastTorque = millis();
    for (int m = 0; m < NJ; m++)
      if (J[m].type == STS && J[m].enabled && !J[m].cooling) st.writeWord(J[m].id, SMS_STS_TORQUE_LIMIT_L, TORQUE_LIMIT);
  }
}

void emergencyStop() {
  estop = true;
  cpg.on = false; cpg.gain = 0;
  for (int i = 0; i < NJ; i++) if (J[i].type == STS) st.EnableTorque(J[i].id, 0);   // all, enabled or not
  mgLimp();
  Serial.println("!!! STOP: STS torque off, MG pulses off. 'resume' to continue");
}

// Read a position reliably: the bus sometimes misses one reply (seen 2026-11-07: only ID 1 was read).
int readPosRetry(int id) {
  for (int k = 0; k < 6; k++) {
    int p = st.ReadPos(id);
    if (p >= 0) return p;
    delay(3);
  }
  return -1;
}

void resume() {
  // First read EVERY joint (torque still off), then switch torque on only where the read worked.
  for (int i = 0; i < NJ; i++) {
    Joint &j = J[i];
    if (j.type != STS || !j.enabled || j.cooling) continue;
    int p = readPosRetry(j.id);
    if (p < 0) {
      j.lost = true;                                // excluded from every position write (a goal write
      Serial.printf("  %-8s READ FAILED -> stays limp (check its cable), type resume again\n", j.name);
      continue;                                     // would switch the STS torque back on by itself)
    }
    j.lost = false;
    float d = degFromSteps(j, p);
    j.cmd = j.target = j.pose = constrain(d, j.loDeg, j.hiDeg);
    if (fabsf(d - j.cmd) > 1.0f)
      Serial.printf("  %-8s is at %+6.1f deg = OUTSIDE its taught limits %+.1f..%+.1f -> moved to %+.1f (re-teach to allow it)\n",
                    j.name, d, j.loDeg, j.hiDeg, j.cmd);
    else if (j.cmd < j.softLo - 0.5f || j.cmd > j.softHi + 0.5f)
      Serial.printf("  %-8s held at %+6.1f deg  (outside the normal range %+.1f..%+.1f: OK for 'save sleepy' only)\n",
                    j.name, j.cmd, j.softLo, j.softHi);
    else
      Serial.printf("  %-8s held at %+6.1f deg\n", j.name, j.cmd);
  }
  for (int i = 0; i < NJ; i++) {
    Joint &j = J[i];
    if (j.type == STS && j.enabled && !j.cooling && !j.lost) st.EnableTorque(j.id, 1);
  }
  J[0].target = J[0].pose = J[0].cmd;               // MG resumes at its last commanded angle
  // HOLD this pose: emotions would otherwise overwrite it every tick (bug 2026-11-07).
  autoMode = false;
  useHardRange = true;                              // allow holding a pose beyond the normal range (for save sleepy)
  cpg.on = false; cpg.gain = 0;                     // still, so the pose can be saved exactly
  sleepLimp = false;
  estop = false;
  Serial.println("resumed: HOLDING this pose (auto off). 'save <emotion>' to store it, 'auto on' to continue");
}

// ====================================================================================================
// 2) SET-UP TOOLS (used while preparing the robot, not by the emotion runtime)
//   teach <joint>              origin + limits by hand (safe method: origin -> 2048, no 4095/0 wrap)
//   soft <joint> <min> <max>   normal range for every emotion except sleepy
//   save <emotion> | poses     store / list the pose of each emotion (stop -> pose by hand -> resume -> save)
// ====================================================================================================
// Preferences keys: pose of an emotion "p<slot>", soft range of joint i "sl<i>" / "sh<i>"
static void poseKey(int e, char *k, size_t n) { snprintf(k, n, "p%d", POSE_KEY[e]); }
static void softKeys(int i, char *lo, char *hi, size_t n) { snprintf(lo, n, "sl%d", i); snprintf(hi, n, "sh%d", i); }

void savePose(int e) {
  for (int i = 0; i < NJ; i++) {
    float v = J[i].cmd;                                       // the pose the robot is in right now
    if (!restEmo(e) && (v < J[i].softLo || v > J[i].softHi)) {   // only sleepy / tired may leave the normal range
      v = constrain(v, J[i].softLo, J[i].softHi);
      Serial.printf("  note: %s clamped to its normal range -> %+.1f\n", J[i].name, v);
    }
    EMO_POSE[e][i] = v;
  }
  char k[12]; poseKey(e, k, sizeof k);
  prefs.begin("lamp", false); prefs.putBytes(k, EMO_POSE[e], sizeof(EMO_POSE[e]));
  bool tiredOwn = prefs.getBytesLength("p8") == sizeof(EMO_POSE[TIRED]);
  prefs.end();
  if (e == SLEEPY && !tiredOwn) memcpy(EMO_POSE[TIRED], EMO_POSE[SLEEPY], sizeof(EMO_POSE[TIRED]));   // tired follows sleepy
  Serial.printf("saved pose '%s': base %+.1f shoulder %+.1f elbow %+.1f pitch %+.1f yaw %+.1f\n", EMO_NAME[e],
                EMO_POSE[e][0], EMO_POSE[e][1], EMO_POSE[e][2], EMO_POSE[e][3], EMO_POSE[e][4]);
}
void loadPoses() {
  prefs.begin("lamp", true);
  for (int e = 0; e < NEMO; e++) {
    char k[12]; poseKey(e, k, sizeof k);
    if (prefs.getBytesLength(k) == sizeof(EMO_POSE[e])) prefs.getBytes(k, EMO_POSE[e], sizeof(EMO_POSE[e]));
  }
  // no own 'save tired' -> tired uses the (hand-saved) sleepy pose
  if (prefs.getBytesLength("p8") != sizeof(EMO_POSE[TIRED])) memcpy(EMO_POSE[TIRED], EMO_POSE[SLEEPY], sizeof(EMO_POSE[TIRED]));
  prefs.end();
}
// soft (normal) range per joint, saved in Preferences "lamp"; default = whole taught range
void loadSoftLimits() {
  prefs.begin("lamp", true);
  for (int i = 0; i < NJ; i++) {
    char a[12], b[12]; softKeys(i, a, b, sizeof a);
    J[i].softLo = constrain(prefs.getFloat(a, J[i].loDeg), J[i].loDeg, J[i].hiDeg);
    J[i].softHi = constrain(prefs.getFloat(b, J[i].hiDeg), J[i].loDeg, J[i].hiDeg);
    if (J[i].softLo > J[i].softHi) { J[i].softLo = J[i].loDeg; J[i].softHi = J[i].hiDeg; }
  }
  prefs.end();
}
void setSoftLimits(int i, float lo, float hi) {
  if (lo > hi) { float t = lo; lo = hi; hi = t; }
  J[i].softLo = constrain(lo, J[i].loDeg, J[i].hiDeg);
  J[i].softHi = constrain(hi, J[i].loDeg, J[i].hiDeg);
  char a[12], b[12]; softKeys(i, a, b, sizeof a);
  prefs.begin("lamp", false); prefs.putFloat(a, J[i].softLo); prefs.putFloat(b, J[i].softHi); prefs.end();
  Serial.printf("%s normal range %+.1f..%+.1f deg (taught %+.1f..%+.1f; sleepy may use all of it)\n",
                J[i].name, J[i].softLo, J[i].softHi, J[i].loDeg, J[i].hiDeg);
}

// forget <emotion>: delete the hand-saved pose -> back to the default (EMO_POSE_DEF in brain.cpp)
void forgetPose(int e) {
  char k[12]; poseKey(e, k, sizeof k);
  prefs.begin("lamp", false); prefs.remove(k); prefs.end();
  memcpy(EMO_POSE[e], (e == TIRED) ? EMO_POSE[SLEEPY] : EMO_POSE_DEF[e], sizeof(EMO_POSE[e]));
  Serial.printf("pose '%s' back to default%s\n", EMO_NAME[e], e == TIRED ? " (= the sleepy pose)" : "");
}

void printPoses() {
  Serial.println("emotion    base  shoulder elbow  pitch  yaw");
  for (int e = 0; e < NEMO; e++)
    Serial.printf("%-9s %+6.1f %+6.1f %+6.1f %+6.1f %+6.1f\n", EMO_NAME[e],
                  EMO_POSE[e][0], EMO_POSE[e][1], EMO_POSE[e][2], EMO_POSE[e][3], EMO_POSE[e][4]);
}

// ---------------- teach (the safe method of the old servo_test tool, built in) ----------------
// 1) hand the joint to its ORIGIN pose -> Enter (calibrated to 2048, so the range never crosses 4095->0)
// 2) one end -> Enter   3) other end -> Enter.  Limits saved in the servo's EEPROM, inset ~1.8 deg.
const int SHRINK = 20;
static int followUntilEnter(int id, bool &wrapped) {   // print the position until Enter, return the last one
  while (Serial.available()) Serial.read();
  int prev = readPosRetry(id);
  uint32_t tPrint = 0;
  while (!Serial.available()) {
    int p = st.ReadPos(id);
    if (p >= 0 && prev >= 0 && abs(p - prev) > 2048) wrapped = true;
    if (p >= 0) prev = p;
    if (millis() - tPrint > 300) { tPrint = millis(); Serial.printf("  pos %4d (%+6.1f deg)\n", p, (p - STS_ORIGIN) / STEPS_PER_DEG); }
    delay(20);
  }
  while (Serial.available()) Serial.read();
  return prev;
}

void teachJoint(int i) {
  Joint &j = J[i];
  if (j.type != STS) { Serial.println("teach works for STS joints only (the MG996R base has no position feedback)"); return; }
  if (readPosRetry(j.id) < 0) { Serial.printf("%s (ID %d) not answering\n", j.name, j.id); return; }
  emergencyStop();                                   // everything limp + nothing commanded while teaching
  prefs.begin("sts", false); char k[8]; snprintf(k, sizeof k, "t%d", j.id); prefs.putBool(k, false); prefs.end();
  st.unLockEprom(j.id);
  st.writeWord(j.id, SMS_STS_MIN_ANGLE_LIMIT_L, 0); st.writeWord(j.id, SMS_STS_MAX_ANGLE_LIMIT_L, 4095);
  st.LockEprom(j.id);
  st.EnableTorque(j.id, 0);
  bool wrapped = false;
  Serial.printf("TEACH %s (ID %d). Step 1/3: turn it to the ORIGIN pose, then Enter\n", j.name, j.id);
  followUntilEnter(j.id, wrapped);
  st.unLockEprom(j.id); st.CalibrationOfs(j.id); delay(100); st.LockEprom(j.id);
  st.EnableTorque(j.id, 0);
  int o = readPosRetry(j.id);
  if (o < 0 || abs(o - STS_ORIGIN) > 20) { Serial.printf("origin calibration FAILED (pos %d) - nothing saved\n", o); return; }
  wrapped = false;
  Serial.println("Step 2/3: turn to ONE end, then Enter");
  int e1 = followUntilEnter(j.id, wrapped);
  Serial.println("Step 3/3: turn to the OTHER end, then Enter");
  int e2 = followUntilEnter(j.id, wrapped);
  if (wrapped || e1 < 0 || e2 < 0) { Serial.println("NOT saved: more than 180 deg from origin or read error. teach again"); return; }
  int lo = min(min(e1, e2), STS_ORIGIN) + SHRINK, hi = max(max(e1, e2), STS_ORIGIN) - SHRINK;
  if (hi - lo < 20) { Serial.println("NOT saved: range too small. teach again"); return; }
  st.unLockEprom(j.id);
  st.writeWord(j.id, SMS_STS_MIN_ANGLE_LIMIT_L, lo); st.writeWord(j.id, SMS_STS_MAX_ANGLE_LIMIT_L, hi);
  st.LockEprom(j.id);
  prefs.begin("sts", false); prefs.putBool(k, true); prefs.end();
  j.loDeg = degFromSteps(j, lo); j.hiDeg = degFromSteps(j, hi); j.enabled = true;
  j.softLo = j.loDeg; j.softHi = j.hiDeg;           // normal range = new taught range (narrow it with 'soft')
  char a[12], b[12]; softKeys(i, a, b, sizeof a);
  prefs.begin("lamp", false); prefs.putFloat(a, j.softLo); prefs.putFloat(b, j.softHi); prefs.end();
  Serial.printf("%s saved: %+.1f .. %+.1f deg from origin (normal range = same; 'soft %s <min> <max>' to narrow)\n",
                j.name, j.loDeg, j.hiDeg, j.name);
  Serial.println("still STOPPED - type resume");
}

// ---------------- set-up commands (called first by handleLine in lamp_main.cpp) ----------------
bool handleSetupCommand(const char *c, const char *a, int n, const char *line) {
  if (!strcmp(c, "poses")) printPoses();
  else if (!strcmp(c, "forget") && n >= 2) {
    int e = findEmotion(a);
    if (e < 0) { Serial.println("forget <normal|sleepy|excited|happy|interested|bored|afraid|tired>"); return true; }
    forgetPose(e);
  }
  else if ((!strcmp(c, "teach") || !strcmp(c, "tech")) && n >= 2) {
    int i = findJoint(a);
    if (i < 0 || i >= NJ) { Serial.println("teach <joint>   (shoulder elbow pitch yaw, or 1..4)"); return true; }
    teachJoint(i);
  }
  else if (!strcmp(c, "soft")) {                    // soft <joint> <min> <max> | soft <joint> reset
    if (n < 2) { for (int i = 0; i < NJ; i++) Serial.printf("  %-8s normal %+6.1f..%+6.1f  taught %+6.1f..%+6.1f\n",
                   J[i].name, J[i].softLo, J[i].softHi, J[i].loDeg, J[i].hiDeg); return true; }
    int i = findJoint(a);
    if (i < 0 || i >= NJ) { Serial.println("unknown joint"); return true; }
    float lo = 0, hi = 0; char w[8] = {0};
    if (sscanf(line, "%*s %*s %7s", w) == 1 && !strcmp(w, "reset")) { setSoftLimits(i, J[i].loDeg, J[i].hiDeg); return true; }
    if (sscanf(line, "%*s %*s %f %f", &lo, &hi) != 2) { Serial.println("use: soft <joint> <min> <max>  |  soft <joint> reset  |  soft"); return true; }
    setSoftLimits(i, lo, hi);
  }
  else if (!strcmp(c, "save") && n >= 2) {
    int e = findEmotion(a);
    if (e < 0) { Serial.println("save <normal|sleepy|excited|happy|interested|bored|afraid|tired>"); return true; }
    if (estop) { Serial.println("'resume' first (so the pose is read from the servos)"); return true; }
    savePose(e);
  }
  else return false;
  return true;
}

// ====================================================================================================
// 3) RGB RING  -  WS2812 x32 on GPIO27. Colour = EMO_RGB[emotion]; brightness breathes with the CPG (o1),
//    sleepy / tired dim, excited blinks 2 Hz, afraid flashes 4 Hz during the jolt, STOP = dim white,
//    'light off' = dark. Written only when the colour really changes.
// ====================================================================================================
Adafruit_NeoPixel ring(RING_COUNT, RING_PIN, NEO_GRB + NEO_KHZ800);

bool ringOn = true;                            // 'light off' (GUI Light OFF) = ring dark, everything else unchanged

void lightsBegin() { ring.begin(); ring.clear(); ring.show(); }

void lightsStep() {
  float r, g, b, level;
  if (estop) { r = g = b = 255; level = 0.15f; }
  else {
    const uint8_t *c = EMO_RGB[emo];
    r = c[0]; g = c[1]; b = c[2];
    float breath = 0.5f + 0.5f * constrain(cpgOut(1), -1.0f, 1.0f);      // 0..1 with the rhythm
    level = 1.0f - RING_BREATH * cpg.gain * (1.0f - breath);
    if (restEmo(emo)) level *= 0.25f;
    if (emo == AFRAID && jolting && (millis() / 125) % 2) level *= 0.2f; // 4 Hz flash during the jolt
    if (emo == EXCITED  && (millis() / 250) % 2) level *= 0.3f;          // 2 Hz blink (slower, playful)
  }
  level *= RING_BRIGHTNESS / 255.0f;
  if (!ringOn) level = 0;
  uint32_t col = ring.Color((uint8_t)(r * level), (uint8_t)(g * level), (uint8_t)(b * level));
  static uint32_t last = 0xFFFFFFFF;
  if (col == last) return;                     // ring.show() takes ~1 ms for 32 LEDs: only when needed
  last = col;
  ring.fill(col);
  ring.show();
}
