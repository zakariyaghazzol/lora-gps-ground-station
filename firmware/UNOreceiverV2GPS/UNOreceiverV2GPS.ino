#include <SPI.h>
#include <RH_RF95.h>

#define RFM95_CS   10
#define RFM95_RST  9
#define RFM95_INT  2

#define RF95_FREQ 915.0

RH_RF95 rf95(RFM95_CS, RFM95_INT);

void setup() {
  Serial.begin(9600);

  Serial.println(F("LoRa ground station starting..."));

  pinMode(RFM95_RST, OUTPUT);
  digitalWrite(RFM95_RST, HIGH);

  // Reset LoRa radio
  digitalWrite(RFM95_RST, LOW);
  delay(10);
  digitalWrite(RFM95_RST, HIGH);
  delay(10);

  if (!rf95.init()) {
    Serial.println(F("LoRa initialization failed."));
    Serial.println(F("Check the Uno LoRa wiring."));
    while (true);
  }

  if (!rf95.setFrequency(RF95_FREQ)) {
    Serial.println(F("Frequency setup failed."));
    while (true);
  }

  Serial.println(F("Ground station ready."));
  Serial.println(F("Waiting for GPS telemetry..."));
}

void loop() {
  if (rf95.available()) {
    uint8_t buffer[128];
    uint8_t length = sizeof(buffer) - 1;

    if (rf95.recv(buffer, &length)) {
      buffer[length] = '\0';

      Serial.print(F("Telemetry: "));
      Serial.println((char *)buffer);

      Serial.print(F("LoRa RSSI: "));
      Serial.print(rf95.lastRssi());
      Serial.println(F(" dBm"));

      Serial.println();
    } else {
      Serial.println(F("Packet reception failed."));
    }
  }
}