**Api**
- POST request:
  When the api receive the this request, the data is stored in list with a max storage of 500 with the cureent time. When the max storage is reached, the oldest data is removed.
  The API then compares the settings with the data received. If there is no settings, the API replies to the ESP32 with fan and light off, with the accompanied message of settings: none. If there is settings, the API determines whether to turn on or off the fan and light based on comparison logic with user settings.

- GET request for settings
  Returns the current user settings for troubleshooting

- GET request for graph
  This request returns values to plot a graph on the Webpage. If there is no values, the response back to the web page is 404 - No sensor data found

- Put request for user settings


**ESP32**
- The ESP32 collects temperature reading of the room and presence reading and send it to the API.
- The ESP32 reads the response of the API and turns on or off the light and fan based on the response of the API