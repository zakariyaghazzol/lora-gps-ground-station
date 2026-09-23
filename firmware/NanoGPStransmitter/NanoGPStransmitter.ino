#include <SPI.h>
#include <RH_RF95.h>
#include <SoftwareSerial.h>
#include <TinyGPS++.h>

// ---------------- LoRa pins ----------------
#define RFM95_CS   10
#define RFM95_RST  9
#define RFM95_INT  2

#define RF95_FREQ 915.0

// ---------------- GPS pins -----------------
// GPS TX connects to Nano D4
// GPS RX is not connected
#define GPS_RX_PIN 4
#define GPS_TX_PIN 3

RH_RF95 rf95(RFM95_CS, RFM95_INT);
SoftwareSerial gpsSerial(GPS_RX_PIN, GPS_TX_PIN);
TinyGPSPlus gps;

unsigned long packetNumber = 0;
unsigned long lastTransmission = 0;

void setup() {
  Serial.begin(9600);
  gpsSerial.begin(9600);

  Serial.println(F("GPS + LoRa transmitter starting..."));

  pinMode(RFM95_RST, OUTPUT);
  digitalWrite(RFM95_RST, HIGH);

  // Reset LoRa radio
  digitalWrite(RFM95_RST, LOW);
  delay(10);
  digitalWrite(RFM95_RST, HIGH);
  delay(10);

  if (!rf95.init()) {
    Serial.println(F("LoRa initialization failed."));
    Serial.println(F("Check LoRa wiring."));
    while (true);
  }

  if (!rf95.setFrequency(RF95_FREQ)) {
    Serial.println(F("LoRa frequency setup failed."));
    while (true);
  }

  // Conservative power level for initial testing
  rf95.setTxPower(13, false);

  Serial.println(F("LoRa initialized at 915 MHz."));
  Serial.println(F("Waiting for GPS data..."));
}

void loop() {
  // Continuously process incoming GPS data
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }

  // Send one telemetry packet every second
  if (millis() - lastTransmission >= 1000) {
    lastTransmission = millis();

    char packet[125];

    if (gps.location.isValid() &&
        gps.location.age() < 3000) {

      char latitudeText[16];
      char longitudeText[16];
      char altitudeText[12];
      char speedText[10];
      char hdopText[10];

      dtostrf(gps.location.lat(), 1, 6, latitudeText);
      dtostrf(gps.location.lng(), 1, 6, longitudeText);
      dtostrf(gps.altitude.meters(), 1, 1, altitudeText);
      dtostrf(gps.speed.kmph(), 1, 1, speedText);
      dtostrf(gps.hdop.hdop(), 1, 2, hdopText);

      snprintf(
        packet,
        sizeof(packet),
        "PKT:%lu,LAT:%s,LON:%s,ALT:%s,SAT:%lu,HDOP:%s,SPD:%s",
        packetNumber,
        latitudeText,
        longitudeText,
        altitudeText,
        (unsigned long)gps.satellites.value(),
        hdopText,
        speedText
      );
    } else {
      snprintf(
        packet,
        sizeof(packet),
        "PKT:%lu,NO_FIX,SAT:%lu",
        packetNumber,
        (unsigned long)gps.satellites.value()
      );
    }

    Serial.print(F("Sending: "));
    Serial.println(packet);

    rf95.send((uint8_t *)packet, strlen(packet));
    rf95.waitPacketSent();

    packetNumber++;
  }

  // Warning if GPS serial data is not being detected
  if (millis() > 10000 && gps.charsProcessed() < 10) {
    Serial.println(F("No GPS serial data detected."));
    Serial.println(F("Check GPS TX -> Nano D4, VCC and GND."));
    delay(3000);
  }
}