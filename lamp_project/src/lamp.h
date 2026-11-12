// lamp.h - everything the modules share: types, hardware constants, globals (extern) and functions.
//   lamp_main.cpp  TUNING values (top), setup(), the 20 Hz loop, serial commands
//   brain.cpp      SO(2) CPG (Week 03) + hormones / emotions / postures (Week 04)
//   motors.cpp     joints, servo output, safety, stop/resume + set-up tools (teach / soft / save poses) + RGB ring
//   sensors.cpp    ToF pipeline (Week 02)
//   experiment.cpp what the course asks to MEASURE: CSV logs, C0/C1, trials, scripted scenario
#pragma once
#include <Arduino.h>
#include <SCServo.h>
#include <ESP32Servo.h>
#include <Preferences.h>
#include <Wire.h>
#include <VL53L0X.h>
#include <Adafruit_NeoPixel.h>

// ---------------- hardware ----------------
const int BUS_RX = 16, BUS_TX = 17;
const uint32_t BUS_BAUD = 1000000;
const int MG_PIN = 14, MG_MIN_US = 600, MG_MAX_US = 2400;   // same pulse range as servo_test
const int RING_PIN = 27, RING_COUNT = 32;                      // WS2812 RGB ring (32 LEDs), data pin
const int STS_ORIGIN = 2048;
const float STEPS_PER_DEG = 4096.0f / 360.0f;

// ---------------- tuning values (defined at the TOP of lamp_main.cpp) ----------------
// ToF pipeline + events (sensors.cpp)
extern const bool TOF_ON_AT_BOOT, AUTO_AT_BOOT;
extern const float TOF_BETA, TOF_MIN_CM, TOF_MAX_CM;
extern const uint32_t TOF_STALE_MS;
extern const float OBJ_ENTER_CM, OBJ_EXIT_CM, OBJ_T_IN, OBJ_T_OUT;
extern const bool OBJ_NEED_BASE;
extern const float AFRAID_ENTER_CM, AFRAID_EXIT_CM, AFRAID_T_IN, AFRAID_T_OUT;
extern const float STARTLE_ENTER_CM, STARTLE_EXIT_CM, STARTLE_T_IN, STARTLE_T_OUT;
extern const float PERSON_LO_CM, PERSON_ENTER_CM, PERSON_EXIT_CM, PERSON_T_IN, PERSON_T_OUT;
// behaviour (brain.cpp)
extern float SLEEP_AFTER_S, AFRAID_CALM_S, HEAD_UP_DEG;          // live-tunable: tune sleep.after / afraid.calm / head.up
extern const uint32_t HEAD_BLIND_WAKE_MS, STARTLE_HOLD_MS, STARTLE_BLOCK_MS, EXCITED_GREET_MS, EMO_HOLD_MS;
extern const float INTERESTED_STOP_CM, LEAN_RATE, SHOVE_CM, AFRAID_MAX_BACK;
extern const float STRESS_AFRAID_R, NOVELTY_EXCITED_R, BOREDOM_BORED_R, SOCIAL_HAPPY_R, RECALL_R;
extern const float PHI_NOV_GAIN, PHI_STR_GAIN, PHI_MIN, PHI_MAX, AMP_NOV_GAIN, AMP_STR_GAIN, AMP_MIN, AMP_MAX;
extern const float FATIGUE_T0_C, FATIGUE_T1_C, NAP_ENTER_R, NAP_EXIT_R;
extern const uint32_t WAVE_BACK_MS;
extern const float WAVE_AMP_DEG, WAVE_PHI, LOOK_DEG_S;
extern float TRACK_DEG_S, TRACK_START_PCT, TRACK_STOP_PCT;      // live-tunable: tune track.speed / track.start / track.stop
extern const float TRACK_YAW_SIGN, TRACK_PITCH_SIGN, TRACK_BASE_SIGN;
extern const float OBJ_JUMP, OBJ_SETTLE_S, BASE_SHARE_DEG, BASE_DEG_S;
// motors / safety (motors.cpp)
extern const int TORQUE_LIMIT, TEMP_EASE_C, TEMP_STILL_C, TEMP_LIMP_C, TEMP_BACK_C;
extern const float MAX_DEG_S;
extern const uint8_t RING_BRIGHTNESS;
extern const float RING_BREATH;
// experiment (experiment.cpp)
extern const float MOTION_ONSET_DEG;
extern const uint32_t INPUT_WAIT_MS, ONSET_WAIT_MS;
// camera (sensors.cpp)
extern const uint32_t CAM_TIMEOUT_MS;
extern const float CAM_T_IN, CAM_T_OUT, CAM_ID_T, CAM_PERSON_T_OUT;

// ---------------- timing ----------------
const uint32_t PERIOD_MS = 50;           // 20 Hz
const float DT = PERIOD_MS / 1000.0f;

// ---------------- joint table ----------------
enum JointType { STS, MG };

struct Joint {
  const char *name;
  JointType type;
  int id;            // STS id, or GPIO pin for MG
  float originNative;// STS: steps (2048)   MG: absolute degrees
  float loDeg, hiDeg;// limits in degrees FROM ORIGIN
  float target;      // deg from origin (already clamped)
  float cmd;         // deg from origin actually sent (slew limited)
  float maxSpeed;    // deg/s
  bool ok;           // last health check answered
  int temp;          // last temperature (STS)
  bool enabled;      // false = never commanded (limits not trustworthy) - stays limp
  // --- zero-initialised, set in cpgDefaults ---
  float pose;        // deg from origin: the posture the rhythm rides on
  int src;           // CPG output: 1 = o1, 2 = o2, negative = inverted, 0 = none
  float amp;         // deg of rhythm at full CPG amplitude
  bool cooling;      // true = limp because too hot (see TEMP_LIMP_C)
  bool lost;         // true = position could not be read at resume -> kept limp, never commanded
  // SOFT range (deg from origin) used by every emotion EXCEPT sleepy. loDeg/hiDeg = HARD range
  // (taught, enforced by the servo itself). Sleepy may use the whole hard range (e.g. elbow folded deep).
  float softLo, softHi;
  bool unread;       // true = did not answer at boot (motor power off?) -> limits not loaded yet; healthStep()
                     //        loads them and enables the joint as soon as it answers (no reboot needed)
  bool farOut;       // true = was found far outside its range (e.g. sagged while limp) -> kept off; healthStep()
                     //        enables it by itself once it is moved back near the range by hand
};

// ---------------- emotions ----------------
enum Emotion { NORMAL, SLEEPY, EXCITED, HAPPY, INTERESTED, BORED, AFRAID, TIRED, NEMO };
// (2026-11-10: 'startled' merged into AFRAID - the < 10 cm reflex is now AFRAID's fast full recoil, see 'jolting')
// Preferences key of each emotion's hand-saved pose: kept at the OLD slot numbers so saved poses survive.
// AFRAID uses p7 = the old startled pose (= the full recoil), TIRED p8. (p6, the old unused wary pose, is ignored.)
const int POSE_KEY[] = {0, 1, 2, 3, 4, 5, 7, 8};
// rest states: go to the rest pose, then ALL motors off. SLEEPY = nothing seen for long, TIRED = motors hot (fatigue)
inline bool restEmo(int e) { return e == SLEEPY || e == TIRED; }

// ---------------- CPG (brain.cpp) ----------------
struct CPG {
  float a1 = 0.1f, a2 = 0.0f;      // a(0) = [0.1, 0] as in the slides
  float o1 = 0, o2 = 0;
  float alpha = 1.1f;              // course baseline
  float phi = 0.12f;               // normal breathing ~2.7 s per breath (slides baseline 0.2 = 1.6 s)
  float peak = 0.1f;               // running |o| amplitude estimate (for normalisation)
  float period = 0;                // measured from o1 upward zero crossings [s]
  uint32_t lastCross = 0;
  bool on = false;
  float gain = 0;                  // 0..1 fade so start/stop never jumps
  bool csv = false;
};

// ---------------- hormones (brain.cpp) ----------------
struct Hormone {
  const char *name;
  float kp, kc, kb;        // production / clearance / binding [1/s]
  float H, R, S;
};
enum { H_SOCIAL, H_NOVELTY, H_BOREDOM, H_STRESS, H_FATIGUE, NH };

// ---------------- senses (sensors.cpp) ----------------
struct Senses {
  bool person = false;       // someone is there (camera)
  bool object = false;       // an object is shown (camera)
  int color = 0;             // which object, identified by its colour (camera); 0 = none
  float objX = 0, objY = 0;  // object position in the camera image, -1..1 (0 = centre) - for tracking
  bool posHold = false;      // the object JUMPED (being lifted / carried?) -> do not follow until it settles
  bool posFresh = false;     // objX / objY come from the NEWEST camera line (false = old position, do not steer by it)
  float headCm = 999;        // HEAD ToF, filtered [cm], 999 = nothing usable
  float baseCm = 999;        // BASE ToF, filtered [cm], 999 = nothing usable
};
struct Tof {
  const char *name;
  VL53L0X dev;
  TwoWire *bus;
  int sda, scl;
  bool ok = false;           // sensor initialised and answering
  bool warned = false;       // "not connected" printed once, retries stay quiet
  float simCm = NAN;         // 's near' / 's base': replaces the RAW sample (still goes through the pipeline)
  float raw = NAN;           // last raw sample [cm]
  bool valid = false;        // passed the sensor contract this tick
  float filt = NAN;          // low-pass filtered distance [cm]
  uint32_t lastSample = 0, lastTry = 0, invalidCount = 0;
};

// experiment condition (experiment.cpp): 1 = C1 hysteresis + dwell (normal), 0 = C0 raw threshold (baseline)
extern int cond;

// dwell filter for an on/off signal (camera person / object): ON after tEnter s of raw ON, OFF after tExit s of
// raw OFF. C0 (cond 0) = no dwell, follows the raw value at once (same C0/C1 rule as the ToF events).
struct Dwell {
  const char *name;
  float tEnter, tExit;
  bool on = false;
  float timer = 0;
  uint32_t srcMs = 0;
  bool changed = false;
  void update(bool raw) {
    if (raw == on) { timer = 0; return; }
    if (timer == 0) srcMs = millis();
    timer += DT;
    if (cond == 0 || timer >= (raw ? tEnter : tExit)) { on = raw; timer = 0; changed = true; }
  }
};

// hysteresis on distance + dwell time: state turns ON when d is inside [lo, enterCm] for tEnter seconds,
// OFF when d leaves [lo, exitCm] (or the sample is invalid) for tExit seconds.
struct Hyst {
  const char *name;
  float lo, enterCm, exitCm;   // inside = lo <= d <= enter (to switch on) / lo <= d <= exit (to stay on)
  float tEnter, tExit;         // dwell times [s]
  bool on = false;
  float timer = 0;             // how long the candidate state has been different
  uint32_t srcMs = 0;          // when the candidate first differed = SOURCE time of the event (before dwell)
  bool changed = false;        // set when 'on' flips; sensorsStep() logs it as an input and clears it
  // C1 (cond 1): exit threshold wider than enter (hysteresis) + dwell times.
  // C0 (cond 0): ONE threshold (enterCm) both ways, switch at once - the Lab06 baseline.
  void update(bool valid, float d) {
    bool cand = valid && d >= lo && d <= ((on && cond == 1) ? exitCm : enterCm);
    if (cand == on) { timer = 0; return; }
    if (timer == 0) srcMs = millis();
    timer += DT;
    if (cond == 0 || timer >= (cand ? tEnter : tExit)) { on = cand; timer = 0; changed = true; }
  }
};

// ---------------- globals ----------------
// motors.cpp
extern SMS_STS st;
extern Servo mg;
extern Preferences prefs;
extern Joint J[];
extern const int NJ;
extern bool estop, useHardRange, ringOn;
extern uint32_t clampTicks;
extern float ampScale;
// lamp_main.cpp
extern bool showStats;
extern float ampGain, speedCap;   // live tuning ('tune amp' / 'tune speed')
// brain.cpp
extern CPG cpg;
extern Hormone HM[];
extern const char *EMO_NAME[NEMO];
extern float EMO_POSE[NEMO][5];
extern const float EMO_POSE_DEF[NEMO][5];
extern const uint8_t EMO_RGB[NEMO][3];
extern Emotion emo, emoForced;
extern uint32_t emoSince, lastActivityMs;
extern bool autoMode, hlog, sleepLimp, napping, jolting;
extern int napCount;
// sensors.cpp
extern Senses sense;
extern bool cameraConnected, tofLive, tofEnabled;
extern Tof tofBase, tofHead;
extern Hyst hObject, hPerson, hAfraid, hStartle;
extern Dwell dCamPerson, dCamObject;
extern int camRawPerson, camRawObject, camRawId, camSeq;
extern uint32_t camLines, camLost;

// ---------------- functions ----------------
// brain.cpp: CPG + hormones + emotions
void cpgStep();
float cpgOut(int src);
void cpgDefaults();
float receptor(float h);
void hormoneStep(Hormone &h);
void hormoneSelfTest();
float hottestStsC();
int findEmotion(const char *s);
Emotion chooseEmotion();
void sleepControl();
void emotionStep();
void regreet();
void cameraWave(float x);
void printHormones();
// motors.cpp: joints, output, safety, set-up tools, RGB ring
int stepsFromDeg(const Joint &j, float d);
float degFromSteps(const Joint &j, int s);
void setTarget(int i, float deg);
void composeTargets();
void mgWriteDeg(const Joint &j, float d);
void mgLimp();
int findJoint(const char *s);
void printJoints();
void loadLimits();
bool readLimits(Joint &j, bool atBoot);
void startPose();
void sendOutputs();
void healthStep();
void emergencyStop();
int readPosRetry(int id);
void resume();
void savePose(int e);
void loadPoses();
void loadSoftLimits();
void setSoftLimits(int i, float lo, float hi);
void forgetPose(int e);
void printPoses();
void teachJoint(int i);
bool handleSetupCommand(const char *c, const char *a, int n, const char *line);
void lightsBegin();
void lightsStep();
// sensors.cpp: ToF pipeline + camera lines
bool tofInit(Tof &t);
void tofScan();                  // 'tof scan': SDA/SCL idle level + I2C address scan of both ToF buses
void tofStep(Tof &t);
float tofCm(const Tof &t);
bool baseNear();
bool thingThere();
bool personThere();
bool someoneMaybe();
void sensorsStep();
void cameraLine(const char *line);
void waveLine(const char *line);
// lamp_main.cpp
void printHelp();
void handleLine(char *line);
void readSerial();
// experiment.cpp: logs, trials, scenario
void noteInput(const char *name, bool on, uint32_t srcMs);
void onEmotionChange(Emotion from, Emotion to);
void experimentStep();
void scenarioStep();
bool scenarioRunning();          // 'scen' running -> camera ignored (pure ToF simulation)
bool handleExperimentCommand(const char *c, const char *a, int n, float v);
