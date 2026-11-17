/*
 LUMI FINAL DEMO V2.0 — 11 November 2026
 ESP32 + 4x STS3215 + PIR + HC-SR04 + LDR + XY-MOS LED.
 Built from the team's original FSM/CPG motion and integration V1.5.2.

 ONLY THREE NORMAL COMMANDS (Serial Monitor 115200, Newline):
    HOME  -> read all servo positions and return them home, S4 -> S3 -> S2 -> S1
    START -> start automatic FSM + CPG + sensor-driven LED, only near HOME
    STOP  -> stop NEW servo instructions; CUT SERVO POWER for emergency

 OPTIONAL: STATUS, CHECK, HELP, SHOW ON, SHOW OFF, DARK ON, DARK OFF.
 The LED reacts briefly to sensor events even in idle SAFE mode.
 No automatic servo movement at boot. Servos are still physically powered
 whenever the separate supply is on; unplug servo power for emergency stop.

 PIN MAP: PIR 32, US TRIG 25, US ECHO 33 (MUST have 5V->3.3V divider),
          LDR 34, XY-MOS PWM 26, STS UART RX16 TX17 @ 1 Mbps.

 IMPORTANT: Mechanical tick limits cannot ensure collision-free travel.
 HOME intentionally bypasses near-home tolerance for convenience, but
 rejects failed feedback/out-of-calibration readings. Observe the arm.
 XY-MOS is an electronic switch, not a constant-current LED driver.
 LED PWM capped at 64/255, only supervised LOW-POWER tests with the
 previously tested bench supply 5.00V / 0.050A limit; NOT a guarantee
 against peak LED current or heat. Do not leave unattended in PLA shade.
*/

#include <Arduino.h>
#include <SCServo.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>

#define PIR_PIN   32
#define TRIG_PIN  25
#define ECHO_PIN  33
#define LDR_PIN   34
#define LED_PIN   26

SMS_STS sts;

// Calibration ranges supplied for physical LUMI (ticks, NOT collision proof).
struct Joint { uint8_t id; int low; int home; int high; const char* name; };
const Joint JOINTS[4] = {
  {1, 1500, 2260, 3000, "S1 base"},
  {3, 1000, 1300, 1700, "S2 shoulder"},
  {2, 2600, 3000, 3500, "S3 elbow"},
  {4, 2500, 3100, 3800, "S4 head"}
};
const int HOME_TOLERANCE_TICKS = 100; // START requires near HOME; HOME itself may recover from wider calibrated range.
// HOMING DOES NOT validate physical collision clearance: operator must check path.
const int HOME_REACHED_TICKS = 20;
const uint16_t HOME_SPEED = 450;
const uint8_t HOME_ACCEL = 35;
const unsigned long HOME_TIMEOUT_MS = 5000UL;
const unsigned long HOME_READ_MS = 150UL;
const unsigned long HOME_MIN_SETTLE_MS = 300UL;
// Head -> elbow -> shoulder -> base; short correction only (<= 100 ticks each).
const uint8_t HOME_ORDER[4] = {3, 2, 1, 0};

const unsigned long PING_MS = 70;
const unsigned long ECHO_TIMEOUT_US = 12000UL;
const unsigned long FSM_MS = 50;
const unsigned long CPG_MS = 20; // 50 Hz target updates (was 20 Hz)
const unsigned long CPG_TRANSITION_MS = 800; // quintic easing of behavior poses
const uint16_t CPG_SERVO_SPEED = 1650; // only gentle CPG motion; SHOW speed unchanged
const uint8_t CPG_SERVO_ACCEL = 18;   // servo internal acceleration, tune after real test
const float CPG_MAX_STEP_TICKS = 14.0f; // limit target movement per 20 ms
const uint8_t CPG_MIN_SEND_DELTA_TICKS = 2; // legacy V1.5.1 behavior
// New approach: a short position lookahead prevents very short travel-to-stop motions;
// speed follows the requested trajectory, and a single SyncWritePosEx sends axes together.
const float CPG_LOOKAHEAD_SEC = 0.075f; // 75 ms projected motion
const float CPG_MAX_LEAD_TICKS = 22.0f;
const int CPG_MAX_SYNC_STEP_TICKS = 18;  // bound target changes per update
const uint16_t CPG_STREAM_MIN_SPEED = 80;
const uint16_t CPG_STREAM_MAX_SPEED = 1050;
const uint8_t CPG_STREAM_ACCEL = 0; // don't re-apply an accel ramp each update
bool streamMode = true; // default: synchronized, lookahead, adaptive speed
uint32_t worstCpgGapMs = 0; // compare with nominal 20ms; resetting on ARM
uint32_t streamSyncBatches = 0;
uint32_t legacyAxisPackets = 0;
const unsigned long LED_MS = 20;
const unsigned long PRINT_MS = 2000; // SAFE status; slower while ARMED to reduce serial stalls
const unsigned long PRINT_ARMED_MS = 3000;
const unsigned long IDLE_MS = 10000;
const float NEAR_ENTER_CM = 40.0f;
const float NEAR_EXIT_CM = 48.0f; // more separation helps prevent flicker
const uint8_t NEAR_CONFIRM_SAMPLES = 2; // ~140 ms with valid near readings
const uint8_t FAR_CONFIRM_SAMPLES = 3;  // ~210 ms with valid far readings
const uint8_t LOST_ECHO_CLEAR_MISSES = 7; // ~0.5 sec, not 2 missed reads
const float DISTANCE_BETA = 0.55f;   // Faster response than the original 0.25.

// LDR polarity/threshold are unverified on the physical circuit.
// DARK ON is disabled at boot; inspect bright/dark raw values before enabling.
const int LDR_DARK_THRESHOLD = 2750;
const bool LDR_DARK_WHEN_HIGH = true; // Team's original assumption; verify first.
bool darknessEnabled = false;

const uint8_t LED_MAX_PWM = 64;   // ~25% duty; not a 25% current guarantee.
const unsigned long SAFE_LED_PULSE_MS = 400;
const unsigned long SAFE_LED_COOLDOWN_MS = 400;

const float AROUSAL_TRIGGER = 0.8f;
const float AROUSAL_GAIN = 0.01f;
const float AROUSAL_DECAY = 0.005f;
// Behavior refinement: one HAPPY burst per approach, not permanent HAPPY.
// The person must leave the near region for a moment to re-arm happiness.
const unsigned long HAPPY_BURST_MS = 2000UL;
const unsigned long HAPPY_COOLDOWN_MS = 7000UL;
const unsigned long HAPPY_REARM_AWAY_MS = 1500UL;
const unsigned long PIR_HOLD_MS = 1200UL;

enum Emotion { NORMAL, CURIOUS, INTERESTED, HAPPY, AFRAID, SLEEPY, FAULT_LATCH };
enum MotionPhase { PHASE_NONE, PHASE_STARTLE, PHASE_NOD_A, PHASE_NOD_B };

Emotion state = NORMAL;
bool behaviorLocked = false;
Emotion lockedBehavior = SLEEPY; // only NORMAL or SLEEPY for isolated motion tests
int lastAppliedState = -1;
MotionPhase phase = PHASE_NONE;
bool motionArmed = false;
bool homing = false;
bool forceHoming = false; // FORCEHOME bypasses +/-100 near-home check, not calibrated ranges.
uint8_t homeStep = 0;
unsigned long homeStepAt = 0;
unsigned long homeReadAt = 0;
bool dramaticMotionEnabled = false; // Only enable SHOW after physical sweep checks.
bool faultLatched = false;

unsigned long lastPingAt = 0, lastFsmAt = 0;
unsigned long lastLedAt = 0, lastPrintAt = 0, lastActivityAt = 0;
unsigned long stateStartedAt = 0, phaseStartedAt = 0;
unsigned long safePulseStartedAt = 0, safePulseOffAt = 0;
bool safePulseEverStarted = false;
uint8_t currentLedDuty = 0;

bool pirActive = false, pirPrevious = false;
bool nearObject = false, distanceValid = false, isDark = false;
uint8_t darkSamples = 0, echoMisses = 0;
uint8_t nearConfirm = 0, farConfirm = 0;

// Define this type BEFORE the first function in the .ino file.
// Arduino sketches auto-generate function prototypes before that function.
// Those prototypes need CpgProfile to be defined already.
struct CpgProfile {
  float base[4]; // S1,S2,S3,S4 physical order
  float amp[4];
  float offset[4];
  float hz;
};

// Explicit prototypes also prevent Arduino from inventing signatures for
// functions using this custom type before it is visible.
CpgProfile effectiveCpgProfile(uint32_t now);
void configureCpg(const CpgProfile& newGoal);

// HC-SR04 ECHO capture uses a tiny ISR instead of pulseIn(12000us).
// Protected by noInterrupts()/interrupts() during transfer to main loop.
volatile uint32_t echoRiseUs = 0, echoWidthUs = 0;
volatile bool echoHighSeen = false, echoReady = false;
bool pingInFlight = false;
uint32_t pingStartedUs = 0;

void IRAM_ATTR echoChangeISR() {
  const uint32_t at = micros();
  if (digitalRead(ECHO_PIN) == HIGH) {
    echoRiseUs = at;
    echoHighSeen = true;
  } else if (echoHighSeen) {
    echoWidthUs = at - echoRiseUs;
    echoReady = true;
    echoHighSeen = false;
  }
}
float distanceCm = -1.0f, filteredCm = -1.0f;
float arousal = 0.0f;
int ldrRaw = 0;
// Timestamp comparisons use signed subtraction for millis() wrap-around.
bool happyUsedForVisit = false;
unsigned long happyEndsAt = 0;
unsigned long happyCooldownUntil = 0;
unsigned long awaySinceAt = 0;
unsigned long pirVisibleUntil = 0;

// CPG is driven by a continuous phase accumulator (not absolute millis * frequency).
// Each behavior is a target profile. Interpolate to avoid base/phase jumps.
bool cpgEnabled = false;
CpgProfile cpgFrom = {}, cpgTo = {};
float cpgTheta = 0.0f;
float filteredTarget[4] = {2260,1300,3000,3100};
int lastSentTick[4] = {2260,1300,3000,3100};
float previousPlan[4] = {2260,1300,3000,3100};
uint32_t cpgTransitionAt = 0;
uint32_t lastCpgAt = 0;

const char* stateName(Emotion s) {
  switch (s) {
    case NORMAL: return "NORMAL";
    case CURIOUS: return "CURIOUS";
    case INTERESTED: return "INTERESTED";
    case HAPPY: return "HAPPY";
    case AFRAID: return "AFRAID";
    case SLEEPY: return "SLEEPY";
    case FAULT_LATCH: return "FAULT";
  }
  return "?";
}

void ledWrite(uint8_t duty) {
  if (duty > LED_MAX_PWM) duty = LED_MAX_PWM;
  if (duty == currentLedDuty) return;
  currentLedDuty = duty;
  analogWrite(LED_PIN, duty);
}

void enterFault(const char* reason) {
  faultLatched = true;
  motionArmed = false;
  homing = false;
  forceHoming = false;
  cpgEnabled = false;
  phase = PHASE_NONE;
  state = FAULT_LATCH;
  ledWrite(0);
  Serial.print("FAULT LATCH: ");
  Serial.println(reason);
  Serial.println("Cut servo power if there is any physical danger. Recheck and reboot.");
}

bool validTarget(uint8_t id, int pos) {
  for (int i = 0; i < 4; ++i) {
    if (JOINTS[i].id == id) {
      if (pos >= JOINTS[i].low && pos <= JOINTS[i].high) return true;
      Serial.print("LIMIT BLOCK: ");
      Serial.print(JOINTS[i].name);
      Serial.print(" requested ");
      Serial.println(pos);
      return false;
    }
  }
  Serial.print("UNKNOWN SERVO ID: ");
  Serial.println(id);
  return false;
}

bool send4(int p1, int p3, int p2, int p4, uint16_t speed, uint8_t accel) {
  if (!motionArmed || faultLatched) return false;
  // Validate ALL four targets before writing to any motor.
  if (!validTarget(1, p1) || !validTarget(3, p3) ||
      !validTarget(2, p2) || !validTarget(4, p4)) {
    enterFault("servo target outside calibrated tick range");
    return false;
  }
  sts.WritePosEx(1, p1, speed, accel);
  sts.WritePosEx(3, p3, speed, accel);
  sts.WritePosEx(2, p2, speed, accel);
  sts.WritePosEx(4, p4, speed, accel);
  const int cmd[4] = {p1,p3,p2,p4};
  for (int i=0;i<4;++i) {lastSentTick[i]=cmd[i]; filteredTarget[i]=cmd[i]; previousPlan[i]=cmd[i];}
  return true;
}

bool send1(uint8_t id, int pos, uint16_t speed, uint8_t accel) {
  if (!motionArmed || faultLatched) return false;
  if (!validTarget(id, pos)) {
    enterFault("servo target outside calibrated tick range");
    return false;
  }
  sts.WritePosEx(id, pos, speed, accel);
  for (int i=0;i<4;++i) if (JOINTS[i].id == id) {
    lastSentTick[i]=pos; filteredTarget[i]=pos; previousPlan[i]=pos; break;
  }
  return true;
}

void startSafeLedPulse(const char* why) {
  if (motionArmed || homing || faultLatched) return;
  const unsigned long now = millis();
  if (safePulseEverStarted && now - safePulseStartedAt < SAFE_LED_COOLDOWN_MS) return;
  safePulseStartedAt = now;
  safePulseOffAt = now + SAFE_LED_PULSE_MS;
  safePulseEverStarted = true;
  ledWrite(LED_MAX_PWM);
  Serial.print("EVENT "); Serial.print(why); Serial.println(" -> LED pulse");
}

void noteEchoMiss() {
  distanceValid = false;
  if (echoMisses < 250) ++echoMisses;
  // A single weak reflection should NOT terminate INTERESTED or HAPPY.
  if (echoMisses >= LOST_ECHO_CLEAR_MISSES) {
    nearObject = false;
    filteredCm = -1.0f;
    distanceCm = -1.0f;
    nearConfirm = farConfirm = 0;
  }
}

void acceptEcho(uint32_t us) {
  if (us < 120 || us > ECHO_TIMEOUT_US) { noteEchoMiss(); return; }
  distanceValid = true;
  echoMisses = 0;
  const float rawCm = us * 0.0343f * 0.5f;
  if (filteredCm < 0.0f) filteredCm = rawCm;
  else filteredCm = DISTANCE_BETA * rawCm + (1.0f - DISTANCE_BETA) * filteredCm;
  distanceCm = filteredCm;

  if (!nearObject) {
    if (distanceCm <= NEAR_ENTER_CM) {
      if (++nearConfirm >= NEAR_CONFIRM_SAMPLES) {
        nearObject = true;
        nearConfirm = 0;
        startSafeLedPulse("HC-SR04 NEAR");
      }
    } else nearConfirm = 0;
  } else {
    if (distanceCm >= NEAR_EXIT_CM) {
      if (++farConfirm >= FAR_CONFIRM_SAMPLES) {
        nearObject = false;
        farConfirm = 0;
      }
    } else farConfirm = 0;
  }
}

void pollEcho() {
  if (!pingInFlight) return;
  uint32_t width=0;
  bool ready=false;
  noInterrupts();
  if (echoReady) {
    width=echoWidthUs;
    echoReady=false;
    ready=true;
  }
  interrupts();
  if (ready) {
    pingInFlight=false;
    acceptEcho(width);
  } else if ((uint32_t)(micros() - pingStartedUs) >= 15000UL) {
    pingInFlight=false;
    noteEchoMiss();
  }
}

void updateInputs() {
  pirActive = digitalRead(PIR_PIN) == HIGH;
  if (pirActive && !pirPrevious) startSafeLedPulse("PIR");
  pirPrevious = pirActive;

  // Echo is interrupt captured, never a blocking pulseIn() wait.
  pollEcho();
  const uint32_t now = millis();
  if (!pingInFlight && now - lastPingAt >= PING_MS) {
    lastPingAt = now;
    noInterrupts();
    echoReady = false;
    echoHighSeen = false;
    interrupts();
    pingInFlight = true;
    pingStartedUs = micros();
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);
  }
}

Emotion chooseEmotion(unsigned long now) {
  if (faultLatched) return FAULT_LATCH;
  if (darknessEnabled && isDark) return AFRAID;
  // HAPPY can play only during a 2s response window on this approach.
  if (nearObject && (int32_t)(happyEndsAt - now) > 0) return HAPPY;
  if (nearObject) return INTERESTED;
  // PIR modules may pulse: hold CURIOUS briefly after signal disappears.
  if (pirActive || (int32_t)(pirVisibleUntil - now) > 0) return CURIOUS;
  if (now - lastActivityAt >= IDLE_MS) return SLEEPY;
  return NORMAL;
}

void updateFSM(unsigned long now) {
  ldrRaw = analogRead(LDR_PIN);
  const bool darkSample = LDR_DARK_WHEN_HIGH
                            ? (ldrRaw > LDR_DARK_THRESHOLD)
                            : (ldrRaw < LDR_DARK_THRESHOLD);
  if (darkSample) {
    if (darkSamples < 3) ++darkSamples;
  } else {
    darkSamples = 0;
  }
  isDark = (darkSamples >= 3);

  if (nearObject) arousal += AROUSAL_GAIN;
  else arousal -= AROUSAL_DECAY;
  if (arousal > 1.0f) arousal = 1.0f;
  if (arousal < 0.0f) arousal = 0.0f;

  if (pirActive) pirVisibleUntil = now + PIR_HOLD_MS;

  if (nearObject) {
    awaySinceAt = 0;
    if (!faultLatched && !(darknessEnabled && isDark) &&
        !happyUsedForVisit && arousal >= AROUSAL_TRIGGER &&
        (int32_t)(now - happyCooldownUntil) >= 0) {
      happyUsedForVisit = true;
      happyEndsAt = now + HAPPY_BURST_MS;
      happyCooldownUntil = now + HAPPY_COOLDOWN_MS;
      Serial.println("AHM -> HAPPY BURST (2s); then return to INTERESTED");
    }
  } else {
    if (awaySinceAt == 0) awaySinceAt = now;
    if (happyUsedForVisit && now - awaySinceAt >= HAPPY_REARM_AWAY_MS) {
      happyUsedForVisit = false;
      Serial.println("AHM -> HAPPY REARMED (object moved away)");
    }
  }

  if ((darknessEnabled && isDark) || nearObject || pirActive)
    lastActivityAt = now;

  const Emotion next = faultLatched ? FAULT_LATCH : (behaviorLocked ? lockedBehavior : chooseEmotion(now));
  if (next != state) {
    state = next;
    stateStartedAt = now;
    Serial.print("STATE -> "); Serial.println(stateName(state));
  }
}

// Smoothstep with zero velocity and acceleration at both ends.
float quinticEase(float t) {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  return t*t*t*(t*(t*6.0f-15.0f)+10.0f);
}

CpgProfile effectiveCpgProfile(uint32_t now) {
  const float mix = quinticEase(float(now-cpgTransitionAt)/float(CPG_TRANSITION_MS));
  CpgProfile p = {};
  for (int i=0;i<4;++i) {
    p.base[i] = cpgFrom.base[i] + mix*(cpgTo.base[i]-cpgFrom.base[i]);
    p.amp[i] = cpgFrom.amp[i] + mix*(cpgTo.amp[i]-cpgFrom.amp[i]);
    p.offset[i] = cpgFrom.offset[i] + mix*(cpgTo.offset[i]-cpgFrom.offset[i]);
  }
  p.hz = cpgFrom.hz + mix*(cpgTo.hz-cpgFrom.hz);
  return p;
}

void configureCpg(const CpgProfile& newGoal) {
  const uint32_t now=millis();
  if (cpgEnabled) {
    cpgFrom = effectiveCpgProfile(now); // preserve progress of interrupted transitions
  } else {
    // After a show animation, read actual feedback where possible so that
    // smooth blending begins where the mechanism really is.
    cpgFrom = newGoal;
    for (int i=0;i<4;++i) {
      int pos = sts.ReadPos(JOINTS[i].id);
      if (pos < JOINTS[i].low || pos > JOINTS[i].high) pos = lastSentTick[i];
      cpgFrom.base[i] = pos;
      cpgFrom.amp[i] = 0;
      filteredTarget[i] = pos;
      previousPlan[i] = pos;
      lastSentTick[i] = pos;
    }
    cpgTheta = 0;
    lastCpgAt = now;
  }
  cpgTo = newGoal;
  cpgTransitionAt = now;
  cpgEnabled = true;
}

void configureNormal() {
  // Awake, alert, small breathing motion, unlike SLEEPY's lowered head.
  const CpgProfile p = {{2260,1300,3000,3100},{0,12,12,8},
                        {0,0,-PI/4,-PI/2},0.36f};
  configureCpg(p);
}
void configureRest() {
  // Team's SLEEPY pose preserved, eased into over 800ms.
  const CpgProfile p = {{2260,1200,3150,3400},{0,40,40,20},
                        {0,0,-PI/4,-PI/2},0.30f};
  configureCpg(p);
}
void configureLook() {
  // Subtle active lean (within calibrated ticks; real collision check still needed).
  const CpgProfile p = {{2260,1320,2970,3130},{0,20,20,10},
                        {0,0,0,0},0.80f};
  configureCpg(p);
}
void configureCurious() {
  // Team's unmistakable right turn, now blended instead of instant.
  const CpgProfile p = {{2400,1300,3000,3100},{0,25,25,15},
                        {0,0,0,0},0.50f};
  configureCpg(p);
}
void configureHappyCPG() {
  // Keep TEAM's strong S1 sway amplitude and lively frequency.
  const CpgProfile p = {{2260,1300,3000,3100},{80,20,20,20},
                        {0,0,0,0},1.20f};
  configureCpg(p);
}

void applyBehavior(Emotion s) {
  if (!motionArmed || faultLatched) return;
  lastAppliedState = (int)s;
  if (s == NORMAL) {
    Serial.println("MOTION -> NORMAL CPG (awake)");
    configureNormal();
  } else if (s == SLEEPY) {
    Serial.println("MOTION -> REST CPG (sleepy)");
    configureRest();
  } else if (s == CURIOUS) {
    Serial.println("MOTION -> LOOK_SMALL CPG");
    configureCurious();
  } else if (s == INTERESTED) {
    Serial.println("MOTION -> HOLD_LOOK CPG");
    configureLook();
  } else if (s == HAPPY) {
    if (!dramaticMotionEnabled) {
      Serial.println("MOTION -> HAPPY CPG (NOD locked until SHOW)");
      configureHappyCPG();
    } else {
      Serial.println("MOTION -> NOD_ONCE");
      cpgEnabled = false;
      phase = PHASE_NOD_A;
      phaseStartedAt = millis();
      // Team's original nod positions/speeds/accelerations.
      send4(2260, 1300, 2850, 2800, 2000, 100);
    }
  } else if (s == AFRAID) {
    if (!dramaticMotionEnabled) {
      Serial.println("MOTION -> ALERT CPG (STARTLE locked until SHOW)");
      configureLook();
    } else {
      Serial.println("MOTION -> STARTLE");
      cpgEnabled = false;
      phase = PHASE_STARTLE;
      phaseStartedAt = millis();
      // Team's original fast impact pose.
      send4(2260, 1600, 3400, 3600, 4000, 200);
    }
  } else {
    cpgEnabled = false;
  }
}

void updateAnimation(unsigned long now) {
  if (!motionArmed || faultLatched) return;
  if (phase == PHASE_STARTLE && now - phaseStartedAt >= 400) {
    send1(4, 2700, 1500, 100); // original STARTLE head recovery
    phase = PHASE_NONE;
  } else if (phase == PHASE_NOD_A && now - phaseStartedAt >= 300) {
    // Original nod second stage. Keep enough time to observe it before CPG.
    send1(2, 3150, 2000, 100);
    send1(4, 3400, 2000, 100);
    phase = PHASE_NOD_B;
    phaseStartedAt = now;
  } else if (phase == PHASE_NOD_B && now - phaseStartedAt >= 400) {
    phase = PHASE_NONE;
    if (state == HAPPY) configureHappyCPG();
  }
  if (phase == PHASE_NONE && lastAppliedState != (int)state)
    applyBehavior(state);
}

void updateCPG(unsigned long now) {
  if (!motionArmed || faultLatched || !cpgEnabled || phase != PHASE_NONE) return;
  const uint32_t intervalMs = now - lastCpgAt;
  if (intervalMs < CPG_MS) return;
  if (intervalMs > worstCpgGapMs) worstCpgGapMs = intervalMs;

  // Integrated oscillator keeps its phase when changing Behavior frequency.
  // dt comes from actual elapsed time, not a fixed 20ms assumption.
  float dt = intervalMs * 0.001f;
  if (dt > 0.10f) dt = 0.10f; // fail-soft for a stalled loop
  lastCpgAt = now;

  const CpgProfile p = effectiveCpgProfile(now);
  cpgTheta += 2.0f * PI * p.hz * dt;
  while (cpgTheta >= 2.0f * PI) cpgTheta -= 2.0f * PI;

  // A/B test: V1.5.1 legacy per-joint WritePosEx, accel=18, speed=1650.
  // This is retained for diagnosis, NOT as an independent safety mode.
  if (!streamMode) {
    for (int i = 0; i < 4; ++i) {
      const float target = p.base[i] + p.amp[i] * sinf(cpgTheta + p.offset[i]);
      const float error = target - filteredTarget[i];
      float step = 0.72f * error;
      if (step > CPG_MAX_STEP_TICKS) step = CPG_MAX_STEP_TICKS;
      if (step < -CPG_MAX_STEP_TICKS) step = -CPG_MAX_STEP_TICKS;
      filteredTarget[i] += step;
      previousPlan[i] = filteredTarget[i];
      const int tick = (int)lroundf(filteredTarget[i]);
      if (abs(tick - lastSentTick[i]) < CPG_MIN_SEND_DELTA_TICKS) continue;
      if (!validTarget(JOINTS[i].id, tick)) {
        enterFault("CPG legacy output outside calibrated range");
        return;
      }
      sts.WritePosEx(JOINTS[i].id, tick, CPG_SERVO_SPEED, CPG_SERVO_ACCEL);
      ++legacyAxisPackets;
      lastSentTick[i] = tick;
    }
    return;
  }

  uint8_t ids[4];
  int16_t positions[4];
  uint16_t speeds[4];
  uint8_t accels[4];
  uint8_t count = 0;

  for (int i = 0; i < 4; ++i) {
    // First build a continuous, slew-limited joint trajectory.
    const float target = p.base[i] + p.amp[i] * sinf(cpgTheta + p.offset[i]);
    const float error = target - filteredTarget[i];
    float step = 0.72f * error;
    if (step > CPG_MAX_STEP_TICKS) step = CPG_MAX_STEP_TICKS;
    if (step < -CPG_MAX_STEP_TICKS) step = -CPG_MAX_STEP_TICKS;
    filteredTarget[i] += step;

    const float velocity = (filteredTarget[i] - previousPlan[i]) / dt;
    previousPlan[i] = filteredTarget[i];

    // Aim ahead by ~75ms, rather than ordering a 1-tick move at high speed.
    // At a turn-around, lookahead naturally tends toward zero.
    float lead = velocity * CPG_LOOKAHEAD_SEC;
    if (lead > CPG_MAX_LEAD_TICKS) lead = CPG_MAX_LEAD_TICKS;
    if (lead < -CPG_MAX_LEAD_TICKS) lead = -CPG_MAX_LEAD_TICKS;
    int goal = (int)lroundf(filteredTarget[i] + lead);

    // Calibration limits bound positions, not swept-volume clearance.
    if (goal < JOINTS[i].low) goal = JOINTS[i].low;
    if (goal > JOINTS[i].high) goal = JOINTS[i].high;

    // The *commanded target* cannot jump more than 18 ticks per 20ms.
    // This is a software per-update bound, NOT a guaranteed motor speed.
    if (goal > lastSentTick[i] + CPG_MAX_SYNC_STEP_TICKS)
      goal = lastSentTick[i] + CPG_MAX_SYNC_STEP_TICKS;
    if (goal < lastSentTick[i] - CPG_MAX_SYNC_STEP_TICKS)
      goal = lastSentTick[i] - CPG_MAX_SYNC_STEP_TICKS;

    // Avoid re-planning an unchanged target; allow single-tick corrections.
    if (goal == lastSentTick[i]) continue;
    if (!validTarget(JOINTS[i].id, goal)) {
      enterFault("CPG stream output outside calibrated range");
      return;
    }
    // FEETECH STS speed units are position ticks/sec. Here, choose a speed
    // near trajectory speed rather than fixed 1650 for tiny increments.
    const float desiredSpeed = fabsf(velocity) * 1.20f + 45.0f;
    uint16_t speed = (uint16_t)lroundf(desiredSpeed);
    if (speed < CPG_STREAM_MIN_SPEED) speed = CPG_STREAM_MIN_SPEED;
    if (speed > CPG_STREAM_MAX_SPEED) speed = CPG_STREAM_MAX_SPEED;

    ids[count] = JOINTS[i].id;
    positions[count] = (int16_t)goal;
    speeds[count] = speed;
    accels[count] = CPG_STREAM_ACCEL;
    ++count;
  }

  if (count > 0) {
    // One bus packet starts all changed joints in the same frame.
    // Library signature: SyncWritePosEx(u8[],u8,s16[],u16[],u8[]).
    sts.SyncWritePosEx(ids, count, positions, speeds, accels);
    ++streamSyncBatches;
    for (uint8_t j = 0; j < count; ++j) {
      for (int i = 0; i < 4; ++i) {
        if (JOINTS[i].id == ids[j]) {
          lastSentTick[i] = positions[j];
          break;
        }
      }
    }
  }
}

void updateLED(unsigned long now) {
  if (faultLatched || homing) { ledWrite(0); return; }
  if (!motionArmed) {
    if (!safePulseEverStarted || (int32_t)(now - safePulseOffAt) >= 0)
      ledWrite(0);
    return;
  }

  uint8_t duty = 0;
  switch (state) {
    case NORMAL: duty = 0; break;
    case SLEEPY: duty = 6; break;
    case CURIOUS: duty = 32; break;
    case INTERESTED: duty = LED_MAX_PWM; break;
    case HAPPY: {
      // Non-blocking 2-second breathing light, 0..64 PWM.
      const float theta = (2.0f * PI / 2000.0f) * float(now % 2000UL);
      duty = (uint8_t)(0.5f * (1.0f - cosf(theta)) * LED_MAX_PWM);
      break;
    }
    case AFRAID:
      // A short flash, not a continuously driven 3W LED.
      duty = (now - stateStartedAt < 750UL && phase != PHASE_STARTLE)
               ? LED_MAX_PWM : 0;
      break;
    default: duty = 0;
  }
  ledWrite(duty);
}

void printStatus() {
  Serial.print("MODE:");
  Serial.print(faultLatched ? "FAULT" : (homing ? "HOMING" : (motionArmed ? "RUNNING" : "SAFE")));
  Serial.print(" | EMOTION:"); Serial.print(stateName(state));
  Serial.print(" | PIR:"); Serial.print(pirActive ? "MOVE" : "-");
  Serial.print(" | DIST:");
  if (distanceValid) { Serial.print(distanceCm, 1); Serial.print("cm"); }
  else Serial.print("NO ECHO");
  Serial.print(" | LDR:"); Serial.print(ldrRaw);
  Serial.print(" | H:"); Serial.print(arousal, 2);
  Serial.print(" | LED:"); Serial.print(currentLedDuty);
  Serial.print("/255 | SHOW:"); Serial.print(dramaticMotionEnabled ? "ON" : "OFF");
  Serial.print(" | DARK:"); Serial.println(darknessEnabled ? "ON" : "OFF");
}

bool validateHomePose() {
  // Reading all feedback requires servo 7.4V and a working bus.
  // Check before commanding ANY movement. Does not prove no collision.
  bool allGood = true;
  for (int i = 0; i < 4; ++i) {
    const int actual = sts.ReadPos(JOINTS[i].id);
    Serial.print(JOINTS[i].name);
    Serial.print(" ID="); Serial.print(JOINTS[i].id);
    Serial.print(" actual="); Serial.print(actual);
    Serial.print(" home="); Serial.print(JOINTS[i].home);
    if (actual < 0 || actual > 4095 ||
        abs(actual - JOINTS[i].home) > HOME_TOLERANCE_TICKS) {
      Serial.println(actual < 0 || actual > 4095 ? " -> NO FEEDBACK" : " -> TOO FAR FROM HOME");
      allGood = false;
    } else {
      Serial.println(" -> OK");
    }
  }
  return allGood;
}


// Two modes: HOME (within +/-100 ticks of home) and FORCEHOME (any tick
// inside calibrated limits). No collision-free path planner is available.
// Both modes move one joint at a time: head, elbow, shoulder, base.
void beginHomeStep() {
  if (!homing || homeStep >= 4) return;
  const Joint &j = JOINTS[HOME_ORDER[homeStep]];
  const int actual = sts.ReadPos(j.id);
  if (actual < 0 || actual > 4095 ||
      actual < j.low || actual > j.high ||
      (!forceHoming && abs(actual - j.home) > HOME_TOLERANCE_TICKS)) {
    enterFault("HOME aborted: missing feedback or position outside allowed corridor");
    return;
  }
  Serial.print("HOME STEP "); Serial.print(homeStep + 1);
  Serial.print("/4 | "); Serial.print(j.name);
  Serial.print(" actual="); Serial.print(actual);
  Serial.print(" -> "); Serial.println(j.home);
  // HOME is explicitly authorized by user command; bypass motionArmed
  // but still enforce local position range.
  if (!validTarget(j.id, j.home)) {
    enterFault("HOME target outside calibrated range");
    return;
  }
  sts.WritePosEx(j.id, j.home, HOME_SPEED, HOME_ACCEL);
  homeStepAt = millis();
  homeReadAt = homeStepAt;
}

bool validateCalibratedPose() {
  // FORCEHOME may begin outside +/-100 of home, but never without real,
  // in-range position feedback from all four servos.
  bool allGood = true;
  for (int i = 0; i < 4; ++i) {
    const Joint &j = JOINTS[i];
    const int actual = sts.ReadPos(j.id);
    Serial.print(j.name); Serial.print(" actual="); Serial.print(actual);
    Serial.print(" allowed="); Serial.print(j.low);
    Serial.print(".."); Serial.print(j.high);
    Serial.print(" home="); Serial.print(j.home);
    if (actual < j.low || actual > j.high || actual < 0 || actual > 4095) {
      Serial.println(" -> BLOCKED (no feedback / outside calibrated range)");
      allGood = false;
    } else {
      Serial.println(" -> OK");
    }
  }
  return allGood;
}

void startHome(bool force) {
  const char* command = force ? "HOME" : "HOME NEAR";
  if (faultLatched) {
    Serial.print(command); Serial.println(" BLOCKED: FAULT latched; inspect and reboot.");
    return;
  }
  if (motionArmed) {
    Serial.print(command); Serial.println(" BLOCKED: type STOP first; let old movement settle.");
    return;
  }
  if (homing) {
    Serial.println("HOME already running.");
    return;
  }
  Serial.print(command); Serial.println(" PRECHECK: reading all joints (no motion yet)...");
  const bool ready = force ? validateCalibratedPose() : validateHomePose();
  if (!ready) {
    Serial.print(command);
    Serial.println(force
      ? " BLOCKED: missing feedback or joint outside calibrated range."
      : " BLOCKED: joint exceeds +/-100 ticks. Use HOME after checking the physical path.");
    return;
  }
  // Operator must ensure the actual swept path is clear and servo power
  // cutoff can be reached. Tick ranges do not guarantee physical clearance.
  ledWrite(0);
  homing = true;
  forceHoming = force;
  cpgEnabled = false;
  phase = PHASE_NONE;
  homeStep = 0;
  Serial.print(command);
  Serial.println(": S4 -> S3 -> S2 -> S1, speed 450. Cut servo power for physical emergency.");
  beginHomeStep();
}

void updateHoming(unsigned long now) {
  if (!homing || faultLatched) return;
  if (now - homeStepAt > HOME_TIMEOUT_MS) {
    enterFault("HOME timeout: target not reached; cut servo power if unsafe");
    return;
  }
  if (now - homeReadAt < HOME_READ_MS) return;
  homeReadAt = now;

  const Joint &j = JOINTS[HOME_ORDER[homeStep]];
  const int actual = sts.ReadPos(j.id);
  if (actual < 0 || actual > 4095 || actual < j.low || actual > j.high) {
    enterFault("HOME invalid joint feedback");
    return;
  }
  if (abs(actual - j.home) <= HOME_REACHED_TICKS &&
      now - homeStepAt >= HOME_MIN_SETTLE_MS) {
    Serial.print("HOME REACHED: "); Serial.print(j.name);
    Serial.print(" actual="); Serial.println(actual);
    ++homeStep;
    if (homeStep < 4) {
      beginHomeStep();
      return;
    }
    const bool wasForced = forceHoming;
    homing = false;
    forceHoming = false;
    Serial.print(wasForced ? "HOME COMPLETE: " : "HOME NEAR COMPLETE: ");
    Serial.println("all 4 joints reached targets within +/-20 ticks.");
    Serial.println("MODE SAFE. Type START to run the robot.");
  }
}

void printHelp() {
  Serial.println("=== LUMI EASY CONTROL ===");
  Serial.println("HOME  : return all 4 servos HOME one by one (check clearance first)");
  Serial.println("START : run automatic motion + sensors + LED (requires near HOME)");
  Serial.println("STOP  : stop sending NEW servo commands (not a physical emergency stop)");
  Serial.println("Optional: STATUS | CHECK | SHOW ON | SHOW OFF | DARK ON | DARK OFF");
  Serial.println("Emergency: switch OFF the 7.4V servo power physically.");
}

void serialCommand(const char* cmd) {
  if (strcmp(cmd, "HELP") == 0 || strcmp(cmd, "?") == 0) {
    printHelp();
  } else if (strcmp(cmd, "STATUS") == 0) {
    printStatus();
  } else if (strcmp(cmd, "STOP") == 0 || strcmp(cmd, "SAFE") == 0 || strcmp(cmd, "DISARM") == 0) {
    motionArmed = false;
    homing = false;
    forceHoming = false;
    cpgEnabled = false;
    phase = PHASE_NONE;
    ledWrite(0);
    Serial.println("STOP: new motion commands disabled. Old servo targets may still finish.");
    Serial.println("Emergency? Cut 7.4V servo power, not just STOP.");
  } else if (strcmp(cmd, "CHECK") == 0) {
    if (homing || motionArmed) {
      Serial.println("CHECK blocked while moving; type STOP first.");
      return;
    }
    Serial.println("CHECK: reading feedback (NO MOTION)...");
    const bool ready = validateHomePose();
    Serial.println(ready ? "CHECK OK: near HOME" : "CHECK: not near HOME / missing servo. Inspect and type HOME if safe.");
  } else if (strcmp(cmd, "HOME") == 0 || strcmp(cmd, "FORCEHOME") == 0) {
    // HOME is the convenient full-calibrated-range recovery.
    // Never issue commands if any joint feedback is missing/out of range.
    startHome(true);
  } else if (strcmp(cmd, "HOME NEAR") == 0) {
    startHome(false);
  } else if (strcmp(cmd, "START") == 0 || strcmp(cmd, "ARM") == 0) {
    if (homing) { Serial.println("START BLOCKED: HOME in progress."); return; }
    if (faultLatched) { Serial.println("START BLOCKED: FAULT latched; inspect and reboot."); return; }
    if (motionArmed) { Serial.println("Already RUNNING."); return; }
    Serial.println("START: checking servo positions...");
    if (!validateHomePose()) {
      Serial.println("START BLOCKED: not near HOME. Inspect path; type HOME first.");
      return;
    }
    // Seed smoothing from real feedback; no position jump at first CPG update.
    for (int i = 0; i < 4; ++i) {
      const int actual = sts.ReadPos(JOINTS[i].id);
      if (actual >= JOINTS[i].low && actual <= JOINTS[i].high) {
        lastSentTick[i] = actual;
        filteredTarget[i] = actual;
        previousPlan[i] = actual;
      }
    }
    motionArmed = true;
    worstCpgGapMs = 0;
    streamSyncBatches = 0;
    legacyAxisPackets = 0;
    cpgEnabled = false;
    phase = PHASE_NONE;
    lastAppliedState = -1;
    ledWrite(0);
    Serial.println("RUNNING: automatic FSM, smooth CPG, sensors + XY-MOS LED.");
    Serial.println("SHOW OFF by default. Watch moving arm and wiring.");
  } else if (strcmp(cmd, "SHOW ON") == 0 || strcmp(cmd, "SHOW") == 0) {
    if (!motionArmed) { Serial.println("SHOW ON blocked: START first."); return; }
    dramaticMotionEnabled = true;
    Serial.println("SHOW ON: fast STARTLE/NOD enabled on next triggering state change.");
    Serial.println("Only after physical swept-path clearance check.");
  } else if (strcmp(cmd, "SHOW OFF") == 0 || strcmp(cmd, "GENTLE") == 0) {
    dramaticMotionEnabled = false;
    Serial.println("SHOW OFF: gentle CPG instead of future STARTLE/NOD.");
  } else if (strcmp(cmd, "DARK ON") == 0) {
    darknessEnabled = true;
    Serial.println("DARK ON: LDR >2750 is assumed dark (UNVERIFIED polarity).");
    Serial.println("Check LDR values in bright/dark conditions; use DARK OFF if reversed.");
  } else if (strcmp(cmd, "DARK OFF") == 0) {
    darknessEnabled = false;
    Serial.println("DARK OFF: LDR values still shown in STATUS.");
  } else if (cmd[0] != '\0') {
    Serial.println("Unknown command. Type HELP (or HOME, START, STOP).");
  }
}

void readSerialCommands() {
  static char buffer[24];
  static uint8_t length = 0;
  while (Serial.available() > 0) {
    const char c = (char)Serial.read();
    if (c == '\r' || c == '\n') {
      if (length > 0) {
        buffer[length] = '\0';
        // Accept mixed case without using dynamic Strings.
        for (uint8_t i = 0; i < length; ++i) {
          if (buffer[i] >= 'a' && buffer[i] <= 'z') buffer[i] -= 'a' - 'A';
        }
        serialCommand(buffer);
        length = 0;
      }
    } else if (length < sizeof(buffer) - 1) {
      buffer[length++] = c;
    } else {
      length = 0; // Reject overlong command.
    }
  }
}

void setup() {
  digitalWrite(LED_PIN, LOW);
  pinMode(LED_PIN, OUTPUT);
  analogWrite(LED_PIN, 0);
  currentLedDuty = 0;

  pinMode(PIR_PIN, INPUT_PULLDOWN);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(ECHO_PIN), echoChangeISR, CHANGE);
  pinMode(LDR_PIN, INPUT);
  digitalWrite(TRIG_PIN, LOW);
  analogReadResolution(12);

  Serial.begin(115200);
  Serial1.begin(1000000, SERIAL_8N1, 16, 17);
  sts.pSerial = &Serial1;

  lastActivityAt = millis();
  Serial.println();
  Serial.println("=== LUMI FINAL DEMO V2.0 ===");
  Serial.println("READY: SAFE mode, sensors & short LED pulses. SERVO MOTION OFF.");
  Serial.println("1. Inspect clearances / wires.  2. HOME.  3. START.");
  Serial.println("Type STOP to stop NEW motion commands; CUT servo power in emergency.");
  Serial.println("Type HELP for optional settings. SHOW/DARK are OFF by default.");
}

void loop() {
  readSerialCommands();
  updateInputs();

  const unsigned long now = millis();
  if (now - lastFsmAt >= FSM_MS) {
    lastFsmAt = now;
    updateFSM(now);
  }

  updateHoming(now);
  updateAnimation(now);
  updateCPG(now);

  if (now - lastLedAt >= LED_MS) {
    lastLedAt = now;
    updateLED(now);
  }

  if (now - lastPrintAt >= (motionArmed ? PRINT_ARMED_MS : PRINT_MS)) {
    lastPrintAt = now;
    printStatus();
  }
}
