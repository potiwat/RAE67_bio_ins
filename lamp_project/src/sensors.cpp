// sensors.cpp - ToF pipeline (Week 02 slides): sensor contract -> low-pass -> hysteresis + dwell
#include "lamp.h"

// ================= ToF sensors - processed as in the Week 02 slides =================
// 2x VL53L0X (GY-VL53L0X V1), one I2C bus each (no XSHUT):
//   BASE ToF: Wire  SDA 21 / SCL 22   -> OBJECT on the table (10-20 cm)   (people: camera only)
//   HEAD ToF: Wire1 SDA 32 / SCL 33   -> AFRAID (< 30 cm, < 10 cm = fast full recoil "jolt") / collision guard
// Pipeline per sample (slides p.10, 13, 14):
//   1) sensor contract: sample FRESH (< STALE_MS old) and FINITE and IN RANGE, else INVALID -> safe (no event)
//   2) low-pass filter  d_f[k] = BETA * d_raw[k] + (1 - BETA) * d_f[k-1]      (BETA = 0.25, course model)
//   3) hysteresis T_enter / T_exit per event  +  dwell time t_enter / t_exit (our addition, Lab06-style
//      debounce) so something only passing by does not trigger anything.

Senses sense;
bool cameraConnected = false;   // true while CAM lines arrive from the laptop (webcam), see cameraLine()
// An object to look at (-> interested: bow down and look).
// OBJ_NEED_BASE true: it STARTS only when the BASE ToF sees something within OBJ_ENTER_CM (the camera alone - e.g. a
// bottle seen far away while standing up - is not enough; before, the lamp bowed, found nothing and came back up).
// Once started it stays while the base ToF OR the camera still sees it (so a lifted object can still be followed).
// With the camera connected a person in view does not block the base ToF (the user is in front while placing it);
// without the camera something near the base counts as an object only while no person is detected (old rule).
static bool objLatch = false;
bool thingThere() {
  bool baseStart = baseNear() && (cameraConnected || !personThere());
  if (!OBJ_NEED_BASE) return sense.object || baseStart;
  objLatch = baseStart || (objLatch && (baseNear() || sense.object));
  return objLatch;
}

Tof tofBase{"base", VL53L0X(), &Wire, 21, 22};
Tof tofHead{"head", VL53L0X(), &Wire1, 32, 33};
bool tofLive = false;
bool tofEnabled = TOF_ON_AT_BOOT;      // 'tof on' / 'tof off' 

//                      name        lo  T_enter T_exit  t_enter t_exit
Hyst hObject  {"object",  0, OBJ_ENTER_CM,     OBJ_EXIT_CM,     OBJ_T_IN,     OBJ_T_OUT};      // base ToF
Hyst hAfraid    {"afraid",    0, AFRAID_ENTER_CM,    AFRAID_EXIT_CM,    AFRAID_T_IN,    AFRAID_T_OUT};     // head ToF
Hyst hStartle {"startle", 0, STARTLE_ENTER_CM, STARTLE_EXIT_CM, STARTLE_T_IN, STARTLE_T_OUT};  // head ToF
Hyst hPerson  {"person",  PERSON_LO_CM, PERSON_ENTER_CM, PERSON_EXIT_CM, PERSON_T_IN, PERSON_T_OUT};  // base ToF fallback


bool tofInit(Tof &t) {
  t.bus->begin(t.sda, t.scl, 100000);  // 100 kHz: tolerant of the long cable to the head
  t.dev.setBus(t.bus);
  t.dev.setTimeout(30);
  t.bus->beginTransmission(0x29);                       // quick probe first: a missing chip costs ~1 ms, not
  t.ok = t.bus->endTransmission() == 0 && t.dev.init(); // a full init (~100 ms loop stall -> STS "no reply")
  if (t.ok) { t.dev.setMeasurementTimingBudget(33000); t.dev.startContinuous(40); t.lastSample = millis(); }
  t.lastTry = millis();
  if (t.ok) { Serial.printf("ToF %s (SDA %d SCL %d): OK\n", t.name, t.sda, t.scl); t.warned = false; }
  else if (!t.warned) {
    Serial.printf("ToF %s (SDA %d SCL %d): NOT CONNECTED (keeps retrying quietly; 's %s <cm>' simulates it)\n",
                  t.name, t.sda, t.scl, &t == &tofHead ? "near" : "base");
    t.warned = true;
  }
  return t.ok;
}

// 'tof scan': wiring check for both ToF buses. (1) idle level of SDA / SCL with the bus released:
// both must read HIGH (pull-up on the ToF board). LOW = shorted to GND / no pull-up / board unpowered.
// (2) scan every I2C address: the VL53L0X answers at 0x29.
void tofScan() {
  for (Tof *t : {&tofBase, &tofHead}) {
    t->bus->end();
    pinMode(t->sda, INPUT); pinMode(t->scl, INPUT); delay(2);
    int sda = digitalRead(t->sda), scl = digitalRead(t->scl);
    Serial.printf("ToF %s bus (SDA %d SCL %d): idle SDA %s, SCL %s%s\n", t->name, t->sda, t->scl,
                  sda ? "HIGH ok" : "LOW", scl ? "HIGH ok" : "LOW",
                  sda && scl ? "" : "  -> line pulled LOW: board unpowered, no pull-up, or wire shorted / broken");
    t->bus->begin(t->sda, t->scl, 100000);
    int found = 0;
    for (uint8_t a = 1; a < 127; a++) {
      t->bus->beginTransmission(a);
      if (t->bus->endTransmission() == 0) { Serial.printf("   device at 0x%02X%s\n", a, a == 0x29 ? " (VL53L0X)" : ""); found++; }
    }
    if (!found) Serial.println("   no device answers -> check VIN / GND / SDA / SCL of this board");
    else { t->dev.setBus(t->bus);
           Serial.printf("   model id 0x%02X (0xEE = VL53L0X)\n", t->dev.readReg(0xC0)); }
  }
  for (Tof *t : {&tofBase, &tofHead}) if (tofEnabled) tofInit(*t);
}

// one tick: get a raw sample (non-blocking), apply the sensor contract, then the low-pass filter
void tofStep(Tof &t) {
  bool fresh = false;
  if (!isnan(t.simCm)) { t.raw = t.simCm; t.lastSample = millis(); fresh = true; }
  else if (!tofEnabled) { /* real sensors switched off ('tof on' to start) */ }
  else if (t.ok) {
    if ((t.dev.readReg(VL53L0X::RESULT_INTERRUPT_STATUS) & 0x07) != 0) {   // new measurement ready
      uint16_t mm = t.dev.readReg16Bit(VL53L0X::RESULT_RANGE_STATUS + 10);
      t.dev.writeReg(VL53L0X::SYSTEM_INTERRUPT_CLEAR, 0x01);
      t.raw = (mm == 0 || mm >= 8000) ? NAN : mm / 10.0f;   // 0 / 8190 = no target -> not a number
      t.lastSample = millis(); fresh = true;
    } else if (millis() - t.lastSample > 1000) {           // silent for 1 s -> sensor lost
      uint8_t id = t.dev.readReg(0xC0);                    // model id: 0xEE when the chip still answers on I2C
      t.ok = false;
      Serial.printf("WARN ToF %s stopped answering (model id 0x%02X: %s)\n", t.name, id,
                    id == 0xEE ? "chip answers but gives no data" : "no I2C answer - check wires / 3V3");
    }
  } else if (millis() - t.lastTry > 5000) tofInit(t);       // not connected: retry every 5 s

  // 1) sensor contract (slides p.10): fresh? finite and in range?
  bool stale = millis() - t.lastSample > TOF_STALE_MS;
  bool inRange = isfinite(t.raw) && t.raw >= TOF_MIN_CM && t.raw <= TOF_MAX_CM;
  t.valid = !stale && inRange;
  if (!t.valid) { if (fresh) t.invalidCount++; return; }     // keep the last filtered value, no event
  // 2) low-pass filter (slides p.14)
  t.filt = isnan(t.filt) ? t.raw : TOF_BETA * t.raw + (1 - TOF_BETA) * t.filt;
}

float tofCm(const Tof &t) { return t.valid ? t.filt : 999; }   // 999 = nothing usable
bool baseNear() { return hObject.on; }
// PERSON rule (2026-11-09): the camera is trusted whenever it sees someone (even if the base ToF does not).
// The base ToF seeing someone only WAKES the robot to look; it counts as a person only while no camera exists.
// SLEEPY (also while bowing down to sleep): the CAMERA is ignored - the bowed head camera would see the user
// sitting there and wake it at once (2026-11-12 user). Only the BASE ToF wakes it (object or someone near the base,
// see lastActivityMs in brain.cpp); once awake the camera counts again (person still there -> excited greeting).
bool personThere() { return (sense.person && emo != SLEEPY) || (!cameraConnected && hPerson.on); }
bool someoneMaybe() { return hPerson.on && !personThere(); }   // base ToF says "someone?" -> wake up and look

// ================= CAMERA (USB webcam -> laptop lamp_camera.py -> this USB serial) =================
//   CAM,<seq>,<person 0/1>,<object 0/1>,<object_id 0-9>,<x -1..1>,<y -1..1>   >= 10 per second
//   WAVE,<seq>,<x>                                                           when a wave is seen
// x: -1 left .. +1 right of the image, y: -1 top .. +1 bottom (object centre, or the person's face if no object).
// The laptop sends RAW per-frame detections; filtering (dwell) is done HERE so C0/C1 applies to the camera too.
int camRawPerson = 0, camRawObject = 0, camRawId = 0, camSeq = -1;
uint32_t camLastMs = 0, camLines = 0, camLost = 0;   // camLost = seq numbers that never arrived
Dwell dCamPerson{"cam_person", CAM_T_IN, CAM_PERSON_T_OUT};
Dwell dCamObject{"cam_object", CAM_T_IN, CAM_T_OUT};
static int camIdCand = 0;          // object id must stay the same CAM_ID_T s before it counts as a new object
static float camIdTimer = 0;
static float camX = 0, camY = 0;
static float holdX = 0, holdY = 0, holdT = 0;      // object jumped: where to, and for how long it stayed there

void cameraLine(const char *line) {          // called by handleLine() for lines starting with "cam,"
  int seq, p, o, id; float x, y;
  if (sscanf(line, "cam,%d,%d,%d,%d,%f,%f", &seq, &p, &o, &id, &x, &y) != 6) return;   // malformed -> ignored
  if (!isfinite(x) || !isfinite(y) || id < 0 || id > 9) return;
  if (camSeq >= 0 && seq != camSeq) {
    int gap = (seq - camSeq + 65536) % 65536;
    if (gap > 1 && gap < 1000) camLost += gap - 1;
  }
  camSeq = seq;
  camRawPerson = p ? 1 : 0; camRawObject = o ? 1 : 0; camRawId = camRawObject ? id : 0;
  camX = constrain(x, -1.0f, 1.0f); camY = constrain(y, -1.0f, 1.0f);
  camLastMs = millis(); camLines++;
}

void waveLine(const char *line) {            // "wave,<seq>,<x>"
  int seq; float x;
  if (sscanf(line, "wave,%d,%f", &seq, &x) != 2 || !isfinite(x)) return;
  if (cameraConnected) cameraWave(constrain(x, -1.0f, 1.0f));
}

static void cameraStep() {
  // a scripted scenario is a pure ToF simulation (written for "no camera"): a real person in front of the
  // webcam must not change its result -> the camera counts as not connected while 'scen' runs
  bool conn = camLastMs && millis() - camLastMs < CAM_TIMEOUT_MS && !scenarioRunning();
  if (conn != cameraConnected) {
    cameraConnected = conn;
    Serial.printf("camera %s\n", conn ? "CONNECTED (camera decides person / object)" : "LOST -> ToF only");
    noteInput("camera", conn, millis());
    if (!conn) {                             // forget everything the camera said
      sense.person = sense.object = false; sense.color = 0;
      dCamPerson.on = dCamObject.on = false; dCamPerson.timer = dCamObject.timer = 0;
      camRawPerson = camRawObject = camRawId = 0;
    }
  }
  if (!cameraConnected) return;              // 's person' / 's object' simulation works while no camera
  dCamPerson.update(camRawPerson);
  dCamObject.update(camRawObject);
  for (Dwell *d : {&dCamPerson, &dCamObject})
    if (d->changed) { d->changed = false; noteInput(d->name, d->on, d->srcMs); }
  // object identity: once an object is there its id is LOCKED; only a different id seen for CAM_ID_T s (2 s,
  // a really different object) replaces it -> one thing never flips id, so the boredom can build up
  if (camRawObject && camRawId != sense.color) {
    if (camRawId != camIdCand) { camIdCand = camRawId; camIdTimer = 0; }
    camIdTimer += DT;
    if (cond == 0 || camIdTimer >= CAM_ID_T || sense.color == 0) { sense.color = camRawId; camIdTimer = 0; }
  } else camIdTimer = 0;
  sense.person = dCamPerson.on;
  sense.object = dCamObject.on;
  if (!sense.object) sense.color = 0;
  // CAM x,y = the object's centre if one is seen in that frame, else the person's face. While an object counts as
  // there, use ONLY frames that really show it (a missed frame would make the head jump to the person and back).
  bool usePos = sense.object ? camRawObject : (camRawPerson && !camRawObject);
  sense.posFresh = usePos;
  // Slid / placed off-centre = moves SMOOTHLY -> follow. Lifted / carried away = JUMPS -> hold (do not chase);
  // if it then stays at the new place for OBJ_SETTLE_S it was just moved -> accept the new place and follow.
  if (usePos) {
    float jump = fabsf(camX - sense.objX) + fabsf(camY - sense.objY);
    if (sense.object && jump > OBJ_JUMP) {
      if (!sense.posHold || fabsf(camX - holdX) + fabsf(camY - holdY) > 0.15f) { holdX = camX; holdY = camY; holdT = 0; }
      if (!sense.posHold) noteInput("obj_jump_hold", true, millis());
      sense.posHold = true;
      holdT += DT;
      if (holdT >= OBJ_SETTLE_S) { sense.objX = camX; sense.objY = camY; sense.posHold = false; }
    } else {                                 // light smoothing of the target position
      sense.objX += 0.5f * (camX - sense.objX);
      sense.objY += 0.5f * (camY - sense.objY);
      sense.posHold = false; holdT = 0;
    }
  }
  if (!sense.object) { sense.posHold = false; holdT = 0; }   // taken away: nothing to follow
}

void sensorsStep() {
  cameraStep();
  tofStep(tofBase);
  tofStep(tofHead);
  // 3) hysteresis + dwell (slides p.13)
  hObject.update(tofBase.valid, tofBase.filt);
  hPerson.update(tofBase.valid, tofBase.filt);
  hAfraid.update(tofHead.valid, tofHead.filt);
  hStartle.update(tofHead.valid, tofHead.filt);
  for (Hyst *h : {&hObject, &hPerson, &hAfraid, &hStartle})        // every switch = one logged input
    if (h->changed) { h->changed = false; noteInput(h->name, h->on, h->srcMs); }
  sense.baseCm = tofCm(tofBase);
  sense.headCm = tofCm(tofHead);

  static uint32_t lastLive = 0;
  if (tofLive && millis() - lastLive > 200) {
    lastLive = millis();
    Serial.printf("BASE raw %5.1f filt %5.1f %-7s obj %d person %d | HEAD raw %5.1f filt %5.1f %-7s afraid %d startle %d\n",
                  tofBase.raw, tofBase.filt, tofBase.valid ? "ok" : "INVALID", hObject.on, hPerson.on,
                  tofHead.raw, tofHead.filt, tofHead.valid ? "ok" : "INVALID", hAfraid.on, hStartle.on);
  }
}

