// experiment.cpp - what the course asks for to MEASURE the robot (Lab06 / Lab07 requirements, no ROS):
//   1) logs           : D,... = one CSV row per tick   E,... = events (input / emotion / RGB / motion onset / outcome)
//   2) trial          : 'trial start' ... 'trial end' -> metrics summary (S,... row) for the C0 / C1 comparison
//   3) scenario       : 'scen <seed>' plays the SAME synthetic stimuli every time (seeded noise) = repeatable simulation
// Missing values are left BLANK (never 0), as the course requires.
#include "lamp.h"

int cond = 1;                  // 1 = C1 hysteresis + dwell (normal), 0 = C0 raw threshold (baseline)

// ====================================================================================================
// 1) LOGS
// ====================================================================================================
bool dataLog = false;          // 'log on [n]' : D rows every n ticks
int logEvery = 1;
static bool trialOn = false;
static uint32_t trialStart = 0;
static float trialS() { return trialOn ? (millis() - trialStart) / 1000.0f : -1; }

// E,t_ms,trial_s,cond,kind,what,input_id,latency_s     (input_id / latency blank when not applicable)
static void ev(const char *kind, const char *what, int id, float lat) {
  if (!dataLog && !trialOn) return;
  Serial.printf("E,%lu,%.2f,C%d,%s,%s,", (unsigned long)millis(), trialS(), cond, kind, what);
  if (id > 0) Serial.printf("in_%03d", id);
  Serial.print(',');
  if (isfinite(lat)) Serial.printf("%.3f", lat);
  Serial.println();
}
static void printHeaders() {
  Serial.println("E,t_ms,trial_s,cond,kind,what,input_id,latency_s");
  Serial.print("D,t_ms,trial_s,cond,emotion,base_raw,base_f,base_ok,head_raw,head_f,head_ok,"
               "object,person,afraid,startle");
  for (int i = 0; i < NH; i++) Serial.printf(",%s_H,%s_R", HM[i].name, HM[i].name);
  Serial.print(",phi,o1,o2");
  for (int i = 0; i < NJ; i++) Serial.printf(",%s_cmd", J[i].name);
  for (int i = 0; i < NJ; i++) Serial.printf(",%s_temp", J[i].name);
  Serial.print(",napping,auto");
  Serial.println();
}
static void printData() {
  Serial.printf("D,%lu,%.2f,%d,%s,%.1f,%.1f,%d,%.1f,%.1f,%d,%d,%d,%d,%d", (unsigned long)millis(), trialS(), cond,
                EMO_NAME[emo], tofBase.raw, tofBase.filt, tofBase.valid, tofHead.raw, tofHead.filt, tofHead.valid,
                hObject.on, personThere(), hAfraid.on, hStartle.on);
  for (int i = 0; i < NH; i++) Serial.printf(",%.3f,%.3f", HM[i].H, HM[i].R);
  Serial.printf(",%.3f,%.3f,%.3f", cpg.phi, cpg.o1, cpg.o2);
  for (int i = 0; i < NJ; i++) Serial.printf(",%.1f", J[i].cmd);
  for (int i = 0; i < NJ; i++) { Serial.print(','); if (J[i].type == STS && J[i].ok) Serial.print(J[i].temp); }   // blank = no sensor / no answer
  Serial.printf(",%d,%d", napping, autoMode ? 1 : 0);
  Serial.println();
}

// ---- input -> emotion -> motion onset bookkeeping ----
struct Pending { int id = 0; uint32_t src = 0, at = 0; bool open = false; };
static Pending inp;                      // latest input still waiting for an emotion change
static int nextId = 1;
static bool onsetWait = false;           // an emotion changed: waiting for the joints to start moving
static uint32_t onsetDecision = 0, onsetSrc = 0;
static int onsetCause = 0;
static float snap[8];                    // joint commands at the moment of the decision

// trial counters
static int nIn, nResp, nNoChange, nSuper, nTrans, nOnset, nOnsetLat, nNoMotion, nPreempt;
static float latSum, latMax;
static int tMax[8], napAtStart;
static uint32_t emoMs[NEMO], invAtStart;

static void closeInput(const char *status) {
  if (!inp.open) return;
  ev("outcome", status, inp.id, NAN);
  if (trialOn) { if (!strcmp(status, "no_state_change")) nNoChange++; else if (!strcmp(status, "superseded")) nSuper++; }
  inp.open = false;
}

// called for every recognised input: ToF hysteresis switching on/off, simulated camera (s person / s object)
void noteInput(const char *name, bool on, uint32_t srcMs) {
  closeInput("superseded");
  inp.id = nextId++; inp.src = srcMs; inp.at = millis(); inp.open = true;
  if (trialOn) nIn++;
  char what[24]; snprintf(what, sizeof what, "%s_%s", name, on ? "on" : "off");
  ev("input", what, inp.id, (millis() - srcMs) / 1000.0f);        // latency here = source -> recognised (dwell)
}

// called by emotionStep() whenever the emotion changes
void onEmotionChange(Emotion from, Emotion to) {
  int id = 0; uint32_t src = 0; float lat = NAN;
  if (inp.open) { id = inp.id; src = inp.src; lat = (millis() - src) / 1000.0f; inp.open = false; if (trialOn) nResp++; }
  char what[32]; snprintf(what, sizeof what, "%s->%s", EMO_NAME[from], EMO_NAME[to]);
  ev("emotion", what, id, lat);                                   // latency = source -> decision
  if (trialOn) nTrans++;
  if (onsetWait) { ev("outcome", "preempted", onsetCause, NAN); if (trialOn) nPreempt++; }
  onsetWait = true; onsetDecision = millis(); onsetSrc = src; onsetCause = id;
  for (int i = 0; i < NJ; i++) snap[i] = J[i].cmd;
  ev("rgb_set", EMO_NAME[to], id, src ? (millis() - src) / 1000.0f : NAN);   // ring shows it in this same tick
}

// once per tick, AFTER sendOutputs()
void experimentStep() {
  uint32_t now = millis();
  if (inp.open && now - inp.at > INPUT_WAIT_MS) closeInput("no_state_change");
  if (onsetWait) {                                  // first tick the APPLIED command really moved
    float d = 0;
    for (int i = 0; i < NJ; i++) if (J[i].enabled && !J[i].lost) d = fmaxf(d, fabsf(J[i].cmd - snap[i]));
    if (d > MOTION_ONSET_DEG) {
      float lat = onsetSrc ? (now - onsetSrc) / 1000.0f : NAN;   // source -> first motion
      ev("motion_onset", EMO_NAME[emo], onsetCause, lat);
      if (trialOn) { nOnset++; if (isfinite(lat)) { nOnsetLat++; latSum += lat; latMax = fmaxf(latMax, lat); } }
      onsetWait = false;
    } else if (now - onsetDecision > ONSET_WAIT_MS) {
      ev("outcome", "no_motion", onsetCause, NAN); if (trialOn) nNoMotion++;
      onsetWait = false;
    }
  }
  if (trialOn) {
    emoMs[emo] += PERIOD_MS;
    for (int i = 0; i < NJ; i++) if (J[i].type == STS && J[i].ok) tMax[i] = max(tMax[i], J[i].temp);
  }
  static int k = 0;
  if (dataLog && ++k >= logEvery) { k = 0; printData(); }
}

// ====================================================================================================
// 2) TRIAL  -  metrics for one run (C0 or C1)
// ====================================================================================================
static void trialBegin() {
  nIn = nResp = nNoChange = nSuper = nTrans = nOnset = nOnsetLat = nNoMotion = nPreempt = 0;
  latSum = latMax = 0;
  memset(tMax, 0, sizeof tMax); napAtStart = napCount;
  memset(emoMs, 0, sizeof emoMs);
  invAtStart = tofBase.invalidCount + tofHead.invalidCount;
  inp.open = false; onsetWait = false;
  trialOn = true; trialStart = millis();
  printHeaders();
  ev("trial", "start", 0, NAN);
  Serial.printf("TRIAL START  condition C%d (%s)\n", cond, cond ? "hysteresis + dwell" : "raw threshold");
}
static void blankOr(float x) { Serial.print(','); if (isfinite(x)) Serial.printf("%.3f", x); }
static void trialEnd() {
  if (!trialOn) { Serial.println("no trial running ('trial start')"); return; }
  closeInput("censored_end");
  if (onsetWait) { ev("outcome", "censored_end", onsetCause, NAN); onsetWait = false; }
  ev("trial", "end", 0, NAN);
  float dur = (millis() - trialStart) / 1000.0f;
  float perMin = dur > 0 ? nTrans * 60.0f / dur : NAN;
  float latMean = nOnsetLat ? latSum / nOnsetLat : NAN;
  uint32_t inv = tofBase.invalidCount + tofHead.invalidCount - invAtStart;
  trialOn = false;
  Serial.printf("TRIAL END  C%d  %.1f s\n", cond, dur);
  Serial.printf("  inputs %d: changed emotion %d | no state change %d | superseded %d\n", nIn, nResp, nNoChange, nSuper);
  Serial.printf("  emotion transitions %d = %.2f / min\n", nTrans, perMin);
  Serial.printf("  motion onsets %d (with input latency %d), no motion %d, preempted %d\n", nOnset, nOnsetLat, nNoMotion, nPreempt);
  if (nOnsetLat) Serial.printf("  input -> motion latency  mean %.3f s  max %.3f s\n", latMean, latMax);
  else Serial.println("  input -> motion latency  N/A (no measured onset)");
  Serial.printf("  max temperature:");
  for (int i = 0; i < NJ; i++) if (J[i].type == STS) Serial.printf(" %s %d C", J[i].name, tMax[i]);
  Serial.printf("  | fatigue naps %d\n", napCount - napAtStart);
  Serial.printf("  invalid ToF samples %lu\n  time in each emotion:", (unsigned long)inv);
  for (int e = 0; e < NEMO; e++) Serial.printf(" %s %.0f%%", EMO_NAME[e], dur > 0 ? emoMs[e] / 10.0f / dur : 0);
  Serial.println();
  // one CSV row per trial: paste all of them into one sheet
  Serial.print("S,cond,duration_s,inputs,changed,no_state_change,superseded,transitions,transitions_per_min,"
               "motion_onsets,no_motion,preempted,lat_mean_s,lat_max_s,invalid_samples,naps");
  for (int i = 0; i < NJ; i++) if (J[i].type == STS) Serial.printf(",%s_maxC", J[i].name);
  for (int e = 0; e < NEMO; e++) Serial.printf(",%s_pct", EMO_NAME[e]);
  Serial.printf("\nS,C%d,%.1f,%d,%d,%d,%d,%d", cond, dur, nIn, nResp, nNoChange, nSuper, nTrans);
  blankOr(perMin);
  Serial.printf(",%d,%d,%d", nOnset, nNoMotion, nPreempt);
  blankOr(latMean); blankOr(nOnsetLat ? latMax : NAN);
  Serial.printf(",%lu,%d", (unsigned long)inv, napCount - napAtStart);
  for (int i = 0; i < NJ; i++) if (J[i].type == STS) { Serial.print(','); if (tMax[i] > 0) Serial.print(tMax[i]); }
  for (int e = 0; e < NEMO; e++) Serial.printf(",%.1f", dur > 0 ? emoMs[e] / 10.0f / dur : 0);
  Serial.println();
}

// ====================================================================================================
// 3) SCRIPTED SCENARIO (repeatable synthetic stimuli -> the "simulation" run, same for C0 and C1)
//    Distances in cm replace the RAW ToF samples (they still go through contract -> low-pass -> hysteresis).
//    999 = nothing there, 2 = out of range (INVALID -> fault -> no event). Noise = uniform +/- noise cm,
//    seeded, so C0 and C1 get exactly the same inputs for the same seed (use seeds 41, 42, 43).
// ====================================================================================================
struct Seg { float t; const char *id; float base, head, noise; };
static const Seg SCEN[] = {
  //  t [s]  source id        base   head   noise
  {  0, "quiet_01",          999,   999,   0 },
  {  3, "approach_01",        60,   999,   3 },   // person walks up to the base (no camera -> base ToF = person)
  { 15, "clear_01",          999,   999,   0 },
  { 18, "object_01",        19.5,   999,   4 },   // object right at the 20 cm threshold + noise
  { 32, "clear_02",          999,   999,   0 },
  { 35, "near_01",           999,  29.5,   4 },   // hand right at the 30 cm afraid threshold + noise
  { 43, "startle_01",        999,     8, 0.5 },   // very close to the face
  { 45, "clear_03",          999,   999,   0 },
  { 48, "invalid_01",        999,     2,   0 },   // out-of-range sample -> INVALID -> must cause nothing
  { 50, "quiet_02",          999,   999,   0 },
  { 60, "end",               999,   999,   0 },
};
static const int NSEG = sizeof(SCEN) / sizeof(SCEN[0]);
static bool scenOn = false;
bool scenarioRunning() { return scenOn; }   // sensors.cpp: the camera is ignored while a scenario runs
static uint32_t scenStart = 0, rng = 1;
static int seg = -1;
static float rnd() { rng = rng * 1664525u + 1013904223u; return (rng >> 8) / 16777216.0f; }   // 0..1, repeatable

static void scenarioEnd(const char *why) {
  scenOn = false;
  tofBase.simCm = tofHead.simCm = NAN;              // back to the real sensors
  trialEnd();
  Serial.printf("scenario %s (ToF back to real sensors)\n", why);
}

void scenarioStep() {                               // once per tick, BEFORE sensorsStep()
  if (!scenOn) return;
  float t = (millis() - scenStart) / 1000.0f;
  while (seg + 1 < NSEG && t >= SCEN[seg + 1].t) { seg++; ev("source", SCEN[seg].id, 0, NAN); }
  const Seg &s = SCEN[seg];
  if (!strcmp(s.id, "end")) { scenarioEnd("done"); return; }
  float n = s.noise * (2 * rnd() - 1);
  tofBase.simCm = s.base + (s.base < 900 ? n : 0);
  tofHead.simCm = s.head + (s.head < 900 ? n : 0);
}

// ====================================================================================================
// commands: cond / log / trial / scen / rgb
// ====================================================================================================
bool handleExperimentCommand(const char *c, const char *a, int n, float v) {
  if (!strcmp(c, "cond")) {
    if (n >= 2) cond = atoi(a) ? 1 : 0;
    Serial.printf("condition C%d (%s)\n", cond, cond ? "hysteresis + dwell" : "raw threshold, baseline");
  } else if (!strcmp(c, "log")) {
    if (n >= 2 && !strcmp(a, "on")) { dataLog = true; logEvery = (n >= 3 && v >= 1) ? (int)v : 1; printHeaders(); }
    else dataLog = false;
    Serial.printf("data log %s (every %d tick)\n", dataLog ? "on" : "off", logEvery);
  } else if (!strcmp(c, "trial")) {
    if (n >= 2 && !strcmp(a, "start")) trialBegin();
    else if (n >= 2 && !strcmp(a, "end")) trialEnd();
    else Serial.println("trial start | trial end");
  } else if (!strcmp(c, "scen")) {
    if (n >= 2 && !strcmp(a, "stop")) { if (scenOn) scenarioEnd("stopped"); }
    else {
      if (trialOn) trialEnd();
      rng = (n >= 2 && atoi(a) > 0) ? (uint32_t)atoi(a) : 41;
      Serial.printf("scenario seed %lu, %.0f s, condition C%d\n", (unsigned long)rng, SCEN[NSEG - 1].t, cond);
      sense.person = sense.object = false; sense.color = 0;
      seg = -1; scenOn = true; scenStart = millis();
      trialBegin();
    }
  } else if (!strcmp(c, "rgb")) {
    const uint8_t *col = EMO_RGB[emo];
    Serial.printf("RGB ring GPIO%d x%d, brightness %d: %s = %d,%d,%d\n", RING_PIN, RING_COUNT, RING_BRIGHTNESS,
                  EMO_NAME[emo], col[0], col[1], col[2]);
  } else return false;
  return true;
}
