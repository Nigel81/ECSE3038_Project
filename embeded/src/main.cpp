#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include "env.h"
#include <ArduinoJson.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <DS18B20.h>

#define ONE_WIRE_BUS 4
#define LIGHT 22
#define FAN 23 
#define PIR 15

bool presence = true;

//one wire sensor
OneWire oneWire(ONE_WIRE_BUS);
DS18B20 sensor(&oneWire);

// put function declarations here:
void send_temp(float acquired_temp);

void setup() {
  // put your setup code here, to run once:
  pinMode(FAN, OUTPUT);
  digitalWrite(FAN,LOW);

  pinMode(2,OUTPUT);

  pinMode(PIR, INPUT);

  pinMode(LIGHT, OUTPUT);
  digitalWrite(LIGHT,LOW);

  digitalWrite(2,HIGH);
  delay(1000);
  digitalWrite(2,LOW);
  delay(1000);

  Serial.begin(115200);
  sensor.begin();
  sensor.setResolution(12);
  sensor.setOffset(0.25);
  Serial.println("Welcome to Smart Hub 2.0");
  Serial.println(SSID);
  Serial.println(PASS);
  WiFi.begin(SSID,PASS);

  while(WiFi.status() != WL_CONNECTED){

    delay(500);
    Serial.print(".");
  }
  Serial.print("WiFi connected. IP address is: ");
  Serial.println(WiFi.localIP());

}

void loop() {
  // put your main code here, to run repeatedly:
  presence = digitalRead(PIR); 

  if(WiFi.status()==WL_CONNECTED){
    
    sensor.requestTemperatures();
    while(!sensor.isConversionComplete()){
      delay(10);
    }

    float acquired_temp = sensor.getTempC();

    if(acquired_temp != DEVICE_DISCONNECTED_C)
      {
      Serial.print("Present Temperature: ");
      Serial.println(acquired_temp);
      send_temp(acquired_temp);
      }else {Serial.println("Temperature read failed");}
  }
  else{
    Serial.println("WiFi connection Lost");
    WiFi.reconnect();
  }
  delay(500);
}
void send_temp(float acquired_temp){
  HTTPClient http;
  http.begin(String(ENDPOINT)+"/sensors_data");
  http.addHeader("Content-Type", "application/json");

  JsonDocument object_1;
  object_1["temperature"] = acquired_temp;
  object_1["presence"] = presence;

  String request_body;
  serializeJson(object_1,request_body);
  
  int responseCode = http.POST(request_body);
  if(responseCode == HTTP_CODE_OK)
  {
    String response = http.getString();
    Serial.print("API Response: ");
    Serial.println(response);

    JsonDocument object;
    DeserializationError error = deserializeJson(object,response);
    if(error){
      Serial.println("Desrialization failed: ");
      Serial.println(error.c_str());
    }
    else{
      const char *fan_status = object["fan"];
      const char *light = object["light"];

      if(strcmp(fan_status,"on")== 0){
        digitalWrite(FAN,HIGH);
        Serial.println("Cooling the place down");
      } else {
        digitalWrite(FAN,LOW);
        Serial.println("Place is cool or no movements detected");
      }

      if(strcmp(light,"on")== 0){
        digitalWrite(LIGHT,HIGH);
        Serial.println("Light is on");
      } else {
        digitalWrite(LIGHT,LOW);
        Serial.println("Light is off");
      }
    }
  } else{
    Serial.println("HTTP POST failed. Code: ");
    Serial.println(responseCode);
  }
  http.end();
}