// brain.cpp - the bio-inspired part (course Week 03 + Week 04):
//   1) SO(2) CPG            a(t+1) = W(alpha, phi) tanh(a(t)),  o = tanh(a)                    (Week 03)
//   2) hormones             P = kp S, C = kc H_old, B = kb R_old, H = clamp(H_old + dt (P - C - B)) (Week 04)
//   3) emotion tables       pose / CPG amplitude / CPG speed / colour of every emotion
//   4) senses -> stimuli S  (what each hormone "feels")
//   5) emotion choice       receptors R -> one emotion (priority list, held >= EMO_HOLD_MS)
//   6) emotion -> body      bounded mapping R -> CPG phi / amplitude, poses, tracking, sleep
// emotionStep() runs 4) -> 2) -> 5) -> 6) once per 50 ms tick (called by loop() in lamp_main.cpp).
#include "lamp.h"

// ====================================================================================================
// 1) SO(2) CPG  (Week 03)
// ====================================================================================================
CPG cpg;

void cpgStep() {
  // W(alpha, phi) = alpha [[cos phi, sin phi], [-sin phi, cos phi]]
  float w11 = cpg.alpha * cosf(cpg.phi), w12 = cpg.alpha * sinf(cpg.phi);
  float w21 = -w12, w22 = w11;
  // simultaneous update: BOTH new activations are computed from the OLD outputs
  float s1 = tanhf(cpg.a1), s2 = tanhf(cpg.a2);          // sigma(a) = tanh(a)  (Lab convention)
  float n1 = w11 * s1 + w12 * s2;
  float n2 = w21 * s1 + w22 * s2;
  float prev1 = cpg.o1;
  cpg.a1 = n1; cpg.a2 = n2;
  cpg.o1 = tanhf(cpg.a1); cpg.o2 = tanhf(cpg.a2);

  // amplitude estimate (for normalising o to -1..1): follows peaks quickly, decays slowly
  float m = fmaxf(fabsf(cpg.o1), fabsf(cpg.o2));
  cpg.peak = (m > cpg.peak) ? m : cpg.peak * 0.995f + m * 0.005f;
  if (cpg.peak < 0.05f) cpg.peak = 0.05f;
  // period: time between upward zero crossings of o1
  if (prev1 < 0 && cpg.o1 >= 0) {
    uint32_t now = millis();
    if (cpg.lastCross) cpg.period = (now - cpg.lastCross) / 1000.0f;
    cpg.lastCross = now;
  }
  // gain fades 0 <-> 1 in ~1 s, so switching the rhythm on / off never jumps
  float g = cpg.on ? 1.0f : 0.0f;
  cpg.gain += constrain(g - cpg.gain, -DT, DT);

  if (cpg.csv) Serial.printf("%lu,%.4f,%.4f,%.4f,%.4f,%.3f,%.3f\n", (unsigned long)millis(),
                             cpg.a1, cpg.a2, cpg.o1, cpg.o2, cpg.alpha, cpg.phi);
}

float cpgOut(int src) {                       // CPG output for one joint, normalised -1..1
  float o = (abs(src) == 1) ? cpg.o1 : (abs(src) == 2) ? cpg.o2 : 0;
  return (src < 0 ? -o : o) / cpg.peak;
}

void cpgDefaults() {                          // which CPG output drives which joint
  for (int i = 0; i < NJ; i++) { J[i].pose = 0; J[i].src = 0; J[i].amp = 0; }
  J[1].src = 1;  J[1].amp = 4;     // shoulder   <- o1
  J[2].src = 1;                    // elbow      <- o1 (amp set per emotion)
  J[3].src = 2;  J[3].amp = 3;     // head pitch <- o2 (lags o1 -> looks like breathing)
  J[4].src = 1;                    // head yaw   <- o1 (bored: look left / right, waving back)
}

// ====================================================================================================
// 2) HORMONES  (Week 04 Euler model - update order from the slides: use OLD H and OLD R for all rates)
// ====================================================================================================
Hormone HM[] = {
  //  name       kp       kc       kb      tuned so that:
  {"social",   0.40f,   0.12f,   0.05f,   0, 0, 0},   // rises in ~5 s with a person, fades in ~10 s
  {"novelty",  1.60f,   0.45f,   0.20f,   0, 0, 0},   // spikes on something NEW, fades in ~4 s
  {"boredom",  0.0153f, 0.0123f, 0.0030f, 0, 0, 0},   // tau ~65 s: same object ~60 s -> R 0.6 -> bored
  {"stress",   2.00f,   1.60f,   0.40f,   0, 0, 0},   // kp = kc + kb -> H follows S (steady H = S), ~0.5 s
  {"fatigue",  0.10f,   0.08f,   0.02f,   0, 0, 0},   // S = motor heat; kp = kc + kb -> H follows S in ~10 s
};

// receptor R = clamp((H - H_min) / (H_max - H_min), 0, 1) with H_min 0, H_max 1
float receptor(float h) { return constrain((h - 0.0f) / (1.0f - 0.0f), 0.0f, 1.0f); }

void hormoneStep(Hormone &h) {
  float H_old = h.H, R_old = h.R;
  float P = h.kp * h.S, C = h.kc * H_old, B = h.kb * R_old;   // production, clearance, binding
  float raw = H_old + DT * (P - C - B);                       // H_raw
  h.H = constrain(raw, 0.0f, 1.0f);                           // H = clamp(H_raw, 0, 1)
  h.R = receptor(h.H);
}

// slide check (Week 04): kp .8 kc .6 kb .2, S = 1, H0 = R0 = 0 -> H1 = 0.040, H2 = 0.0784
void hormoneSelfTest() {
  Hormone t = {"test", 0.8f, 0.6f, 0.2f, 0, 0, 1};
  hormoneStep(t); float h1 = t.H; hormoneStep(t); float h2 = t.H;
  Serial.printf("hormone self-test: H1 %.4f (0.0400)  H2 %.4f (0.0784)  %s\n", h1, h2,
                (fabsf(h1 - 0.04f) < 1e-4f && fabsf(h2 - 0.0784f) < 1e-4f) ? "PASS" : "FAIL");
}

// hottest STS that answered (the MG996R has no sensor); 0 if none -> stimulus of the fatigue hormone
float hottestStsC() {
  float t = 0;
  for (int i = 0; i < NJ; i++) if (J[i].type == STS && J[i].enabled && J[i].ok) t = fmaxf(t, J[i].temp);
  return t;
}

// ====================================================================================================
// 3) EMOTION TABLES - one row per emotion, columns {base, shoulder, elbow, pitch, yaw}
// ====================================================================================================
const char *EMO_NAME[NEMO] = {"normal", "sleepy", "excited", "happy", "interested", "bored", "afraid", "tired"};

// posture, deg from origin. Signs VERIFIED on the robot 2026-11-07: shoulder + = up / back, pitch + = look up,
// elbow - = down. Every pose can be set BY HAND: stop -> move the robot -> resume -> 'save <emotion>'
// (Preferences "lamp", loaded at boot on top of these defaults; 'forget <emotion>' = back to the default).
const float EMO_POSE_DEF[NEMO][5] = {
  {0,   0,   0,   0, 0},   // normal     (+ HEAD_UP_DEG on the pitch, see poseFor)
  {0, -12, -15, -20, 0},   // sleepy     droop (set by hand: save sleepy)
  {0,   5,  -5,   5, 0},   // excited    a little up, NODS the head (CPG on pitch)
  {0,   5,   0,   8, 0},   // happy      a little up, gentle breathing
  {0, -15, -25, -35, 0},   // interested BOW DOWN to look at the object at the base (scaled by 'lean')
  {0, -15, -25, -35, 0},   // bored      (unused - stays in the interested pose and looks left / right slowly)
  {0,  20,   0,  10, 0},   // afraid     FULL recoil = BACK (shoulder +), head up; blended from normal by closeness
  {0, -12, -15, -20, 0},   // tired      = the sleepy pose (copied from a hand-saved sleepy pose unless 'save tired')
};
float EMO_POSE[NEMO][5];   // = EMO_POSE_DEF, then the hand-saved poses on top (loadPoses in motors.cpp)

// CPG amplitude per joint [deg at full output] - WHERE the rhythm is used
const float EMO_AMP[NEMO][5] = {
  {0, 0, 0, 0,  0},   // normal     STILL
  {0, 0, 0, 0,  0},   // sleepy     goes to its pose, then torque OFF (motors rest)
  {0, 0, 0, 3,  0},   // excited    small nod (pitch) - kept small so the head camera stays steady
  {0, 2, 0, 0,  0},   // happy      gentle breathing on the SHOULDER only - head still (camera watches for a wave)
  {0, 0, 0, 0,  0},   // interested still - the head TRACKS the object instead
  {0, 0, 0, 0, 25},   // bored      SLOWLY look left / right (yaw), ~10 deg/s peak
  {0, 0, 0, 0,  0},   // afraid     still, backing off
  {0, 0, 0, 0,  0},   // tired      goes to the rest pose, then torque OFF to cool down
};

// CPG speed phi [rad] per emotion; the hormones add on top (novelty / stress -> faster), see mapToCpg().
// Period of the SO(2) CPG (alpha 1.1): phi 0.04 = 16.5 s, 0.06 = 6.7 s, 0.08 = 4.5 s, 0.12 = 2.8 s, 0.15 = 2.2 s
//                          normal  sleepy excited happy  interested bored  afraid tired
const float EMO_PHI[NEMO] = {0.08f, 0.06f, 0.15f,  0.08f, 0.12f,    0.04f, 0.12f, 0.06f};   // slow: camera on the head

// RGB ring colour (lightsStep in motors.cpp). 2026-11-12 user: every colour CLEAR, not mixed -> pure colours
// (each channel full or off; yellow = red + some green, the WS2812 green LED is much brighter).
const uint8_t EMO_RGB[NEMO][3] = {
  {  0, 255,   0},   // normal     green
  {100,   0, 255},   // sleepy     purple (dim: rest emotions are shown at 25 %)
  {255,   0, 255},   // excited    magenta, blinks 2 Hz
  {255, 130,   0},   // happy      yellow
  {255, 255, 255},   // interested white
  {  0,   0, 255},   // bored      blue
  {255,   0,   0},   // afraid     PURE red - flashes 4 Hz in the jolt
  {255,  60,   0},   // tired      orange (dim: motors hot -> nap)
};

// emotion name -> index; the old names (calm, curious, wary, startled) still work
int findEmotion(const char *s) {
  for (int e = 0; e < NEMO; e++) if (!strcmp(s, EMO_NAME[e])) return e;
  if (!strcmp(s, "calm")) return NORMAL;
  if (!strcmp(s, "curious")) return INTERESTED;
  if (!strcmp(s, "wary") || !strcmp(s, "startled")) return AFRAID;
  return -1;
}

// ====================================================================================================
// STATE
// ====================================================================================================
Emotion emo = NORMAL, emoForced = NEMO;   // NEMO = not forced (GUI emotion buttons force one)
uint32_t emoSince = 0;                    // when the current emotion started
bool autoMode = true;                     // emotions drive pose + CPG ('auto off' = manual / waiting)
bool hlog = false;                        // 'hm log': print the hormones every second
uint32_t lastActivityMs = 0;              // last time anything was seen -> SLEEP_AFTER_S
bool sleepLimp = false;                   // resting (sleepy / tired) and arrived: all motors off
bool napping = false;                     // fatigue nap (motors too warm) - FATIGUE_* in lamp_main.cpp
int napCount = 0;

// stimuli bookkeeping
static bool lastPerson = false, lastThere = false;
static uint32_t greetMs = 0;              // when a person arrived -> EXCITED_GREET_MS
static float noveltyPulse = 0;            // seconds of "something new" stimulus left
// OBJECT MEMORY (habituation): every object id keeps its own boredom level. While the object is away its boredom
// fades with the SAME hormone equation (S = 0), tau ~65 s. Back while still remembered (R > RECALL_R) -> no novelty.
// id 0 = a thing seen only by the base ToF (no camera class).
static float objMemH[10] = {0};
static int curObj = -1;                   // id of the thing in front now (-1 = none)
static bool objFamiliar = false;          // the thing in front was recognised as "seen recently"

// timers of the emotion rules
static uint32_t afraidEndMs = 0;          // when afraid ended (calm-down period, AFRAID_CALM_S)
static uint32_t restEndMs = 0;            // when a BOWED emotion ended (sleepy / tired / interested / bored): the head
                                          // ToF is still ignored for HEAD_BLIND_WAKE_MS while the head lifts
static uint32_t waveUntil = 0;            // waving back until this time
bool jolting = false;                     // AFRAID + something < 10 cm: full fast recoil, held STARTLE_HOLD_MS
static uint32_t joltStart = 0, startleBlockUntil = 0;

// body: tracking / looking
static float lean = 0;                    // interested: 0..1 how far toward the object (stops at INTERESTED_STOP_CM)
static float trackYaw = 0, trackPitch = 0, trackBase = 0;   // interested: head (and base) follow the object
static bool trackingX = false, trackingY = false;           // turning toward the object right now
static float lookYaw = 0;                 // happy / excited: head turned toward the person (camera x)
static bool lookingX = false;

// Auto switched on / emotion back to automatic while someone is already in front: greet them as if they just
// arrived (otherwise the excitement happened while Auto was still OFF and was never seen)
void regreet() { lastPerson = false; }

// sleepy / tired: the head is bowed over the table, so the head ToF sees the table (or the robot's own body) as
// "something close". Ignore the head ToF then, and for HEAD_BLIND_WAKE_MS after waking (head lifting).
// Same after interested / bored: the object was taken away but the head is still bowed near the table / the hand
// -> it read ~25 cm and jumped to AFRAID every time (log 2026-11-12 08:34, 6 of 6 times).
static bool bowedEmo(Emotion e) { return restEmo(e) || e == INTERESTED || e == BORED; }
static bool headBlind() {
  if (restEmo(emo)) return true;                                   // asleep / napping
  if ((emo == INTERESTED || emo == BORED) && !thingThere()) return true;   // object just taken away, head still bowed
  return millis() - restEndMs < HEAD_BLIND_WAKE_MS;                // just stood up again
}

void cameraWave(float x) {                // sensors.cpp: the camera saw someone wave
  if (restEmo(emo)) return;               // asleep / napping: the camera does not wake it (base ToF only)
  waveUntil = millis() + WAVE_BACK_MS;
  noveltyPulse = 1.0f;                    // a greeting is something new -> a little excitement
  noteInput("cam_wave", true, millis());
  Serial.printf("wave seen (x %.2f) -> waving back\n", x);
}

// ====================================================================================================
// 4) SENSES -> STIMULI S
// ====================================================================================================
// a thing appeared / changed / went away -> object memory, boredom continues from what is remembered
static void objectMemoryStep(bool there, int id) {
  Hormone &bh = HM[H_BOREDOM];
  // the SAME thing while it stays in front (base ToF latch): the camera often loses / finds it again, which made the
  // id jump 9 -> 0 -> 9 ... = "a new object" every time -> novelty spikes and boredom reset, it never got bored
  // (log 2026-11-12 08:34). Camera lost it -> keep the id. Base-only thing (id 0) now recognised -> just relabel.
  if (there && lastThere && id != curObj) {
    if (id == 0) id = curObj;
    else if (curObj == 0) {
      objMemH[id] = fmaxf(objMemH[id], bh.H);
      curObj = id; bh.H = objMemH[id]; bh.R = receptor(bh.H);
      if (bh.R > RECALL_R) objFamiliar = true;
    }
  }
  for (int k = 0; k < 10; k++) {                                // remembered boredom of objects NOT in front fades
    if (there && k == curObj) continue;
    float h = objMemH[k];
    objMemH[k] = constrain(h - DT * (bh.kc * h + bh.kb * receptor(h)), 0.0f, 1.0f);   // hormone eq. with S = 0
  }
  if (there && (!lastThere || id != curObj)) {                  // a thing appeared, or a DIFFERENT one
    if (lastThere && curObj >= 0) objMemH[curObj] = bh.H;     // remember how boring the previous one was
    curObj = id;
    bh.H = objMemH[id]; bh.R = receptor(bh.H);                // continue from what we remember about this one
    objFamiliar = bh.R > RECALL_R;
    if (objFamiliar) Serial.printf("object %d seen recently (boredom %.2f) -> not interested\n", id, bh.R);
    else noveltyPulse = 1.0f;                                  // really new (or forgotten) -> novelty
    noteInput(objFamiliar ? "object_familiar" : "object_new", true, millis());
  } else if (!there && lastThere) {                            // the thing went away: keep it in memory
    if (curObj >= 0) objMemH[curObj] = bh.H;
    bh.H = bh.R = 0; curObj = -1; objFamiliar = false;
  }
}

static void sensesToStimuli() {
  bool there = thingThere();
  objectMemoryStep(there, sense.object ? constrain(sense.color, 0, 9) : 0);
  if (personThere() && !lastPerson) { noveltyPulse = 1.0f; greetMs = millis(); }   // a person arriving is new too
  lastPerson = personThere(); lastThere = there;
  // anything seen keeps it awake (asleep: the camera does not count - personThere() - and the head ToF is blind)
  if (personThere() || there || (hAfraid.on && !headBlind()) || hPerson.on) lastActivityMs = millis();

  HM[H_SOCIAL].S  = personThere() ? 1.0f : 0.0f;
  HM[H_NOVELTY].S = noveltyPulse > 0 ? 1.0f : 0.0f;
  noveltyPulse = fmaxf(0, noveltyPulse - DT);
  HM[H_BOREDOM].S = there ? 1.0f : 0.0f;                        // looking at the same object -> slowly bored
  // stress = HEAD ToF only: 30 cm -> 0 ... 10 cm -> 1. While looking at an object the head goes close on purpose,
  // so then only a shove (< SHOVE_CM) counts. Asleep: head bowed over the table -> ignored.
  if (headBlind()) HM[H_STRESS].S = 0;
  else if (there)  HM[H_STRESS].S = sense.headCm < SHOVE_CM ? 1.0f : 0.0f;
  else             HM[H_STRESS].S = constrain((30.0f - sense.headCm) / (30.0f - 10.0f), 0.0f, 1.0f);
  // fatigue = the hottest servo: FATIGUE_T0_C -> 0 ... FATIGUE_T1_C -> 1
  HM[H_FATIGUE].S = constrain((hottestStsC() - FATIGUE_T0_C) / (FATIGUE_T1_C - FATIGUE_T0_C), 0.0f, 1.0f);
}

// nap with hysteresis on the fatigue receptor (enter high, leave low) so it does not flicker
static void napStep() {
  float fat = HM[H_FATIGUE].R;
  if (!napping && fat > NAP_ENTER_R) { napping = true; napCount++; Serial.printf("tired (hottest %.0f C): nap\n", hottestStsC()); }
  else if (napping && fat < NAP_EXIT_R) { napping = false; lastActivityMs = millis(); Serial.printf("rested (hottest %.0f C)\n", hottestStsC()); }
}

// ====================================================================================================
// 5) EMOTION CHOICE - priority list, the first rule that matches wins
// ====================================================================================================
Emotion chooseEmotion() {
  float soc = HM[H_SOCIAL].R, nov = HM[H_NOVELTY].R, bor = HM[H_BOREDOM].R, str = HM[H_STRESS].R;
  // a) AFRAID - HEAD ToF only: < 30 cm afraid (backs off with closeness), < 10 cm afraid + jolt.
  //    Looking at an object the head goes close on purpose -> only a shove (< SHOVE_CM) is scary.
  bool blind  = headBlind();
  bool close  = !blind && (thingThere() ? (sense.headCm < SHOVE_CM) : hStartle.on);
  bool afraid = !blind && (thingThere() ? false : hAfraid.on);
  if (close || afraid || (!blind && str > STRESS_AFRAID_R)) return AFRAID;     // stress lingers a moment
  // b) someone waved -> happy + wave back (even right after a fright)
  if (millis() < waveUntil) return HAPPY;
  // c) after a fright: calm down first (Lab06: clear -> normal)
  if (emo == AFRAID || millis() - afraidEndMs < (uint32_t)(AFRAID_CALM_S * 1000)) return NORMAL;
  // d) motors hot: nap BEFORE the thermal cut-off (only the fear reflex above may interrupt it)
  if (napping) return TIRED;
  // e) a person JUST arrived -> excited first, even with an object in front (looked at afterwards)
  if (personThere() && millis() - greetMs < EXCITED_GREET_MS) return EXCITED;
  // f) something at the base -> interested; the SAME object for ~60 s (or seen recently) -> bored
  if (thingThere()) return (bor > BOREDOM_BORED_R || objFamiliar) ? BORED : INTERESTED;
  // g) the rest follows the receptors
  if (nov > NOVELTY_EXCITED_R && personThere()) return EXCITED;
  if (bor > BOREDOM_BORED_R) return BORED;
  if (soc > SOCIAL_HAPPY_R) return HAPPY;
  if (millis() - lastActivityMs > (uint32_t)(SLEEP_AFTER_S * 1000)) return SLEEPY;   // nothing seen for long
  return NORMAL;
}

// a new emotion only after the current one was held EMO_HOLD_MS (no flicker); AFRAID may interrupt any time
static void switchEmotion() {
  Emotion e = (emoForced != NEMO) ? emoForced : chooseEmotion();
  bool urgent = (e == AFRAID);
  if (e == emo || !(urgent || millis() - emoSince > EMO_HOLD_MS)) return;
  Emotion from = emo;
  if (from == AFRAID) afraidEndMs = millis();                  // starts the calm-down period
  if (bowedEmo(from) && !bowedEmo(e)) restEndMs = millis();   // head lifting: head ToF still ignored a moment
  emo = e; emoSince = millis();
  if (emo == INTERESTED) { lean = 0; trackYaw = trackPitch = trackBase = 0; trackingX = trackingY = false; }
  Serial.printf("emotion -> %s\n", EMO_NAME[emo]);
  onEmotionChange(from, emo);                                  // event log (the ring takes the new colour this tick)
}

// ====================================================================================================
// 6) EMOTION -> BODY
// ====================================================================================================
// bounded mapping receptor -> CPG (course: phi_cmd = clamp(phi0 + k R, min, max))
static void mapToCpg() {
  float nov = HM[H_NOVELTY].R, str = HM[H_STRESS].R;
  cpg.phi  = constrain(EMO_PHI[emo] + PHI_NOV_GAIN * nov + PHI_STR_GAIN * str, PHI_MIN, PHI_MAX);
  ampScale = constrain(1.0f + AMP_NOV_GAIN * nov + AMP_STR_GAIN * str, AMP_MIN, AMP_MAX);
}

// afraid + something < 10 cm -> JOLT: full recoil at full speed, held STARTLE_HOLD_MS, then no jolt for STARTLE_BLOCK_MS
static void joltStep() {
  uint32_t now = millis();
  bool closeNow = (emo == AFRAID) && (thingThere() ? sense.headCm < SHOVE_CM : hStartle.on);
  if (emo != AFRAID) jolting = false;
  else if (!jolting && closeNow && now > startleBlockUntil) { jolting = true; joltStart = now; Serial.println("jolt!"); }
  else if (jolting && now - joltStart > STARTLE_HOLD_MS) { jolting = false; startleBlockUntil = now + STARTLE_BLOCK_MS; }
}

// object offset -> what to turn by. Starts only when the target is more than TRACK_START_PCT % of the image width off
// centre, then keeps turning until it is within TRACK_STOP_PCT %, then holds still (no endless small moves).
// TRACK_START_PCT 0 = never follow. e = camera x or y (-1..1 = edge to edge, so |e| 1 = 50 % of the width).
static float trackErr(float e, bool &moving) {
  float off = fabsf(e) * 50.0f;
  if (TRACK_START_PCT <= 0) { moving = false; return 0; }
  if (!moving && off > TRACK_START_PCT) moving = true;
  else if (moving && off <= fminf(TRACK_STOP_PCT, TRACK_START_PCT)) moving = false;
  return moving ? e : 0;
}

// interested: creep forward until the head ToF says <= INTERESTED_STOP_CM, keep the object centred in the image
static void trackObject() {
  bool far = sense.headCm > INTERESTED_STOP_CM;
  lean = constrain(lean + (far ? LEAN_RATE : 0.0f) * DT, 0.0f, 1.0f);
  // follow while it is there and not jumping (lifted); taken away -> sense.object false -> no follow
  if (sense.object && !sense.posHold && sense.posFresh) {
    float ex = trackErr(sense.objX, trackingX);                    // 0 = close enough to the centre -> still
    trackYaw   = constrain(trackYaw   + TRACK_YAW_SIGN   * TRACK_DEG_S * ex * DT, -60.0f, 60.0f);
    // (2026-11-12 user: follow LEFT / RIGHT only - no up / down; trackPitch stays 0, the head keeps the bow pitch)
    if (fabsf(trackYaw) > BASE_SHARE_DEG) {                         // head turned far: the base takes over
      float m = constrain(trackYaw - copysignf(BASE_SHARE_DEG, trackYaw), -BASE_DEG_S * DT, BASE_DEG_S * DT);
      trackBase = constrain(trackBase + TRACK_BASE_SIGN * m, -80.0f, 80.0f);
      trackYaw -= m;                                                // camera turns with the base
    }
  }
  else if (!sense.object || sense.posHold) trackingX = false;              // lifted / gone: START again
}

// happy / excited with a person on camera: slowly turn the head toward them (camera x); else drift back to 0.
// Same calm start / stop band as for objects; steer only by the NEWEST camera line (posFresh).
static void lookAtPerson() {
  bool look = (emo == HAPPY || emo == EXCITED) && cameraConnected && sense.person && !sense.object;
  if (look) {
    if (sense.posFresh) lookYaw = constrain(lookYaw + TRACK_YAW_SIGN * LOOK_DEG_S * trackErr(sense.objX, lookingX) * DT,
                                            -60.0f, 60.0f);
  } else {
    lookingX = false;
    lookYaw += constrain(-lookYaw, -LOOK_DEG_S * DT, LOOK_DEG_S * DT);
  }
}

// the pose of joint i for the current emotion. back = afraid blend 0..1 (normal -> full recoil pose)
static float poseFor(int i, float back) {
  float p = EMO_POSE[emo][i];
  if (emo == INTERESTED) p = lean * EMO_POSE[INTERESTED][i] + (i == 4 ? trackYaw : i == 3 ? trackPitch : i == 0 ? trackBase : 0);
  if (emo == BORED)      p = lean * EMO_POSE[INTERESTED][i] + (i == 3 ? trackPitch : i == 0 ? trackBase : 0);   // stays where it looked
  if (emo == AFRAID)     p = EMO_POSE[NORMAL][i] + back * (EMO_POSE[AFRAID][i] - EMO_POSE[NORMAL][i]);
  if (emo == NORMAL && someoneMaybe()) p = (i == 3) ? 10.0f : (i == 1 ? 5.0f : 0.0f);   // "who's there?": head up
  if (i == 4 && (emo == HAPPY || emo == EXCITED)) p += lookYaw;                          // face the person
  // head UP (GUI "head up", tune head.up): normal / happy / excited look up so the camera sees a STANDING person
  if (i == 3 && (emo == NORMAL || emo == HAPPY || emo == EXCITED)) p += HEAD_UP_DEG;
  return p;
}

// sleepy / tired: glide to the rest pose, then ALL motors off so they rest and cool.
// Waking (any other emotion): continue from where the arm sagged to - no jump.
void sleepControl() {
  if (restEmo(emo) && !sleepLimp && !estop) {
    bool arrived = true;
    for (int i = 0; i < NJ; i++) if (fabsf(J[i].cmd - J[i].target) > 1.0f) arrived = false;
    if (arrived && millis() - emoSince > 3000) {
      for (int i = 0; i < NJ; i++) if (J[i].type == STS) st.EnableTorque(J[i].id, 0);
      mgLimp();
      sleepLimp = true;
      Serial.println("sleeping: motors off");
    }
  } else if (!restEmo(emo) && sleepLimp) {
    for (int i = 0; i < NJ; i++) {
      Joint &j = J[i];
      if (j.type != STS || !j.enabled || j.cooling) continue;
      int p = st.ReadPos(j.id);
      if (p >= 0) j.cmd = constrain(degFromSteps(j, p), j.loDeg, j.hiDeg);
      st.EnableTorque(j.id, 1);
    }
    sleepLimp = false;
    Serial.println("waking up: motors on");
  }
}

static void emotionToBody() {
  useHardRange = restEmo(emo);                      // only the rest pose (sleepy / tired) may use the whole taught range
  mapToCpg();
  joltStep();
  float spd = jolting ? MAX_DEG_S : (emo == AFRAID) ? 15 : (restEmo(emo) || emo == BORED) ? 20 : 45;
  if (emo == INTERESTED) trackObject();
  lookAtPerson();
  // wave back whatever the emotion (also a FORCED one) - only not while afraid or resting
  bool waving = millis() < waveUntil && emo != AFRAID && !restEmo(emo);
  if (waving) cpg.phi = WAVE_PHI;
  // afraid: back off gradually - the closer (30 -> 10 cm), the further back; only the jolt goes all the way
  float back = constrain((30.0f - sense.headCm) / 20.0f, 0.0f, 1.0f);
  back = jolting ? 1.0f : fminf(fmaxf(back, HM[H_STRESS].R), AFRAID_MAX_BACK);

  for (int i = 0; i < NJ; i++) {
    J[i].pose = poseFor(i, back);
    J[i].amp = (waving && i == 4) ? WAVE_AMP_DEG : EMO_AMP[emo][i];   // wave back = CPG on the head yaw
    J[i].maxSpeed = spd;
  }
  sleepControl();
}

// ====================================================================================================
// once per tick: senses -> stimuli -> hormones -> emotion -> body
// ====================================================================================================
void emotionStep() {
  sensesToStimuli();
  for (int i = 0; i < NH; i++) hormoneStep(HM[i]);
  napStep();
  switchEmotion();
  if (autoMode) emotionToBody();                    // auto off (waiting / manual): emotions do not move the robot
}

void printHormones() {
  Serial.printf("emotion %s%s | auto %s | phi %.3f ampScale %.2f | person %d object %d (colour %d) head %.0f cm\n",
                EMO_NAME[emo], emoForced != NEMO ? " (forced)" : "", autoMode ? "on" : "OFF",
                cpg.phi, ampScale, personThere(), sense.object, sense.color, sense.headCm);
  Serial.printf("  base ToF %.0f cm (object %d, person %d%s)%s\n", sense.baseCm, baseNear(), hPerson.on,
                cameraConnected ? " - ignored, camera decides" : " - fallback, no camera",
                sleepLimp ? "  | SLEEPING (motors off)" : "");
  for (int i = 0; i < NH; i++)
    Serial.printf("  %-8s S %.2f  H %.3f  R %.3f\n", HM[i].name, HM[i].S, HM[i].H, HM[i].R);
}
