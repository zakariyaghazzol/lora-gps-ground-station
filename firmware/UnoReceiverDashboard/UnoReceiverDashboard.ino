#include <SPI.h>
#include <RH_RF95.h>

#define RFM95_CS   10
#define RFM95_RST  9
#define RFM95_INT  2
#define RF95_FREQ  915.0

RH_RF95 rf95(RFM95_CS, RFM95_INT);

void setup() {
  Serial.begin(9600);
  pinMode(RFM95_RST, OUTPUT);
  digitalWrite(RFM95_RST, HIGH);
  digitalWrite(RFM95_RST, LOW);
  delay(10);
  digitalWrite(RFM95_RST, HIGH);
  delay(10);

  if (!rf95.init()) {
    Serial.println(F("ERROR: LoRa initialization failed"));
    while (true);
  }

  if (!rf95.setFrequency(RF95_FREQ)) {
    Serial.println(F("ERROR: Frequency setup failed"));
    while (true);
  }

  Serial.println(F("Ground station ready"));
}

void loop() {
  if (!rf95.available()) return;

  uint8_t buffer[RH_RF95_MAX_MESSAGE_LEN + 1];
  uint8_t length = RH_RF95_MAX_MESSAGE_LEN;

  if (!rf95.recv(buffer, &length)) {
    Serial.println(F("ERROR: Packet reception failed"));
    return;
  }

  buffer[length] = '\0';
  Serial.print(F("DATA,"));
  Serial.print((char *)buffer);
  Serial.print(F(",RSSI:"));
  Serial.println(rf95.lastRssi());
}
