/*
 * THERMAL CONTROLLER FIRMWARE - v5.0 (Lógica Rígida de Modos)
 * - Modo 1 (Heat): Fan = 0V (Travado). PID controla Lâmpada.
 * - Modo 2 (Cool): Lamp = Base% (Travado). PID controla Fan.
 * - Watchdog: 3s sem sinal = Desliga tudo.
 */

#include <math.h>
#include <DHT.h>

// --- PINOUT ---
#define PIN_SENSOR A1     
#define PIN_LAMP   3      
#define PIN_FAN    6      
#define PIN_RPM    2      

#define DHTTYPE DHT11
DHT dht(PIN_SENSOR, DHTTYPE);

// --- ESTADO ---
bool systemActive = false; 

// --- VARIÁVEIS DO PROCESSO ---
double rawTemp = 0.0;     
double disturbance = 0.0; 
double pidInput = 0.0;    
double setpoint = 0.0;
int controlMode = 0;      // 0=Auto, 1=Heat, 2=Cool

// Carga Base da Lâmpada (0-255) para modo Ventilação
int baseHeatPWM = 255; 

// --- SEGURANÇA ---
unsigned long lastCommandTime = 0;
const long WATCHDOG_TIMEOUT = 3000;

// --- PID ---
double kp = 40.0;
double ki = 1.0;
double kd = 10.0;

double error = 0, lastError = 0, integral = 0, derivative = 0;
unsigned long lastPIDTime = 0;
const int PID_INTERVAL = 200;

// --- ATUAÇÃO ---
int lampPWM = 0;
int fanPWM = 0;

// --- RPM ---
volatile int rpmPulses = 0;
unsigned long lastRPMTime = 0;
int rpm = 0;

void countRPM() { rpmPulses++; }

void setup() {
  Serial.begin(115200);
  dht.begin();
  
  pinMode(PIN_LAMP, OUTPUT);
  pinMode(PIN_FAN, OUTPUT);
  pinMode(PIN_RPM, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_RPM), countRPM, RISING);
  
  analogWrite(PIN_LAMP, 0);
  analogWrite(PIN_FAN, 0);
  
  lastCommandTime = millis(); 
}

void loop() {
  unsigned long currentMillis = millis();

  // 1. LEITURA DE COMANDOS
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    parseCommand(command);
    lastCommandTime = currentMillis; 
  }

  // 2. WATCHDOG
  if (currentMillis - lastCommandTime > WATCHDOG_TIMEOUT) {
    systemActive = false;
    analogWrite(PIN_LAMP, 0);
    analogWrite(PIN_FAN, 0);
  }

  // 3. SENSOR
  static unsigned long lastDHTRead = 0;
  if (currentMillis - lastDHTRead > 500) {
    float t = dht.readTemperature();
    if (!isnan(t)) rawTemp = t;
    lastDHTRead = currentMillis;
  }
  
  pidInput = rawTemp + disturbance;

  // 4. RPM
  if (currentMillis - lastRPMTime >= 1000) {
    detachInterrupt(digitalPinToInterrupt(PIN_RPM));
    rpm = (rpmPulses * 60) / 2; 
    rpmPulses = 0;
    lastRPMTime = currentMillis;
    attachInterrupt(digitalPinToInterrupt(PIN_RPM), countRPM, RISING);
  }

  // 5. PID
  if (systemActive && (currentMillis - lastPIDTime >= PID_INTERVAL)) {
    computePID(currentMillis - lastPIDTime);
    lastPIDTime = currentMillis;
  } else if (!systemActive) {
    analogWrite(PIN_LAMP, 0);
    analogWrite(PIN_FAN, 0);
  }

  // 6. TELEMETRIA
  if (currentMillis % 500 == 0) { 
      sendTelemetry();
  }
}

void computePID(int deltaTimeMs) {
  // 1. Cálculos PID
  error = setpoint - pidInput;
  
  integral += error * (deltaTimeMs / 1000.0);
  
  // Anti-windup
  if (integral > 255) integral = 255;
  if (integral < -255) integral = -255;

  derivative = (error - lastError) / (deltaTimeMs / 1000.0);
  lastError = error;

  double rawOutput = (kp * error) + (ki * integral) + (kd * derivative);

  // 2. Limpeza inicial
  lampPWM = 0;
  fanPWM = 0;

  // --- LÓGICA DE MODOS ---

  // MODO 0: AUTO
  if (controlMode == 0) { 
    if (rawOutput > 0) {
      lampPWM = (int)rawOutput;
      fanPWM = 0;
    } else {
      lampPWM = 0;
      fanPWM = abs((int)rawOutput);
    }
  }
  
  // MODO 1: SÓ AQUECIMENTO
  else if (controlMode == 1) { 
    if (rawOutput > 0) lampPWM = (int)rawOutput;
    else lampPWM = 0;
    
    fanPWM = 0; // Trava Fan
  }
  
  // MODO 2: SÓ VENTILAÇÃO (Correção Aqui)
  else if (controlMode == 2) { 
    // PID controla APENAS a ventoinha (Resfriamento/Valores Negativos)
    if (rawOutput < 0) {
      fanPWM = abs((int)rawOutput);
    } else {
      fanPWM = 0; // Se PID pedir calor, Fan desliga
    }

    // A Lâmpada deve ser CONSTANTE.
    // O valor 'baseHeatPWM' foi recebido pelo comando "BASE:XX"
    lampPWM = baseHeatPWM; 
  }

  // 3. Restrições (0-255)
  if (lampPWM > 255) lampPWM = 255; if (lampPWM < 0) lampPWM = 0;
  if (fanPWM > 255) fanPWM = 255;   if (fanPWM < 0) fanPWM = 0;

  // --- TRAVAS FINAIS DE SEGURANÇA ---
  
  // Garante Fan desligado no Modo 1
  if (controlMode == 1) {
    fanPWM = 0;
    analogWrite(PIN_FAN, 0);
  } else {
    analogWrite(PIN_FAN, fanPWM);
  }

  // Garante Lâmpada Constante no Modo 2
  if (controlMode == 2) {
    // Sobrescreve forçadamente com a base, ignorando qualquer erro de cálculo anterior
    lampPWM = baseHeatPWM; 
    analogWrite(PIN_LAMP, lampPWM);
  } else {
    analogWrite(PIN_LAMP, lampPWM);
  }
}

void sendTelemetry() {
  Serial.print("DADOS,");
  Serial.print(pidInput, 1); 
  Serial.print(",");
  Serial.print(setpoint, 1);
  Serial.print(",");
  Serial.print(lampPWM);
  Serial.print(",");
  Serial.print(fanPWM);
  Serial.print(",");
  Serial.print(millis());
  Serial.print(",");
  Serial.println(rpm);
}

void parseCommand(String cmd) {
  cmd.trim();
  if (cmd.equals("PING")) return;

  if (cmd.equals("STOP")) {
    systemActive = false;
    analogWrite(PIN_LAMP, 0);
    analogWrite(PIN_FAN, 0);
    return;
  }

  if (cmd.startsWith("SET:")) {
    setpoint = cmd.substring(4).toFloat();
    systemActive = true; 
  }
  else if (cmd.startsWith("DIST:")) {
    disturbance = cmd.substring(5).toFloat();
  }
  else if (cmd.startsWith("MODE:")) {
    controlMode = cmd.substring(5).toInt();
    integral = 0;
  }
  else if (cmd.startsWith("BASE:")) {
    baseHeatPWM = cmd.substring(5).toInt();
  }
  else if (cmd.startsWith("PID:")) {
    int first = cmd.indexOf(':');
    int second = cmd.indexOf(':', first + 1);
    int third = cmd.indexOf(':', second + 1);
    if (second > 0 && third > 0) {
        kp = cmd.substring(first+1, second).toFloat();
        ki = cmd.substring(second+1, third).toFloat();
        kd = cmd.substring(third+1).toFloat();
        integral = 0;
    }
  }
}
