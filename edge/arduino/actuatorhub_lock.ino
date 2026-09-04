/*
 * ActuatorHub — Arduino / ESP32 edge sketch (MQTT over WiFi)
 *
 * Controls a lock relay on LOCK_PIN and reports ACKs.
 * Library: PubSubClient + ArduinoJson (ESP32) or compatible WiFi board.
 *
 * Topics:
 *   subscribe  actuators/<SITE>/lock/<NAME>/cmd
 *   publish    actuators/<SITE>/lock/<NAME>/ack
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

const char* WIFI_SSID = "YOUR_SSID";
const char* WIFI_PASS = "YOUR_PASSWORD";
const char* MQTT_HOST = "192.168.1.10";
const int   MQTT_PORT = 1883;

const char* SITE = "hq-dc1";
const char* NAME = "cage-b";
const int   LOCK_PIN = 5;   // HIGH = locked

WiFiClient wifi;
PubSubClient mqtt(wifi);

String cmdTopic;
String ackTopic;

void publishAck(const char* action, bool ok) {
  StaticJsonDocument<192> doc;
  doc["ok"] = ok;
  doc["edge"] = "arduino-gate-01";
  doc["action"] = action;
  char buf[192];
  serializeJson(doc, buf);
  mqtt.publish(ackTopic.c_str(), buf);
}

void applyAction(const char* action) {
  if (strcmp(action, "lock") == 0 || strcmp(action, "e_stop") == 0) {
    digitalWrite(LOCK_PIN, HIGH);
    publishAck(action, true);
  } else if (strcmp(action, "unlock") == 0) {
    digitalWrite(LOCK_PIN, LOW);
    publishAck(action, true);
  } else {
    publishAck(action, false);
  }
}

void onMessage(char* topic, byte* payload, unsigned int length) {
  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) return;
  const char* action = doc["action"] | "";
  applyAction(action);
}

void reconnect() {
  while (!mqtt.connected()) {
    if (mqtt.connect("arduino-gate-01")) {
      mqtt.subscribe(cmdTopic.c_str());
    } else {
      delay(2000);
    }
  }
}

void setup() {
  pinMode(LOCK_PIN, OUTPUT);
  digitalWrite(LOCK_PIN, HIGH); // fail-secure: locked

  cmdTopic = String("actuators/") + SITE + "/lock/" + NAME + "/cmd";
  ackTopic = String("actuators/") + SITE + "/lock/" + NAME + "/ack";

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) delay(400);

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
}

void loop() {
  if (!mqtt.connected()) reconnect();
  mqtt.loop();
}
