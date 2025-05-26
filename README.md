**Api**
- POST request:
  When the api receive the this request, the data is stored in list with a max storage of 500 with the curent time. When the max storage is reached, the oldest data is removed.
  The API then compares the settings in smart hub data array with the data received. If there is no settings, the API replies to the ESP32 with fan and light off, with the accompanied message of settings: none. If there is settings, the API determines whether to turn on or off the fan and light based on comparison logic with user settings.

- GET request for settings
  Returns the current user settings for troubleshooting

- GET request for graph
  This request returns values to plot a graph on the Webpage. If there is no values, the response back to the web page is 404 - No sensor data found

- Put request for user settings
  <user_light> The Api receives a str of either the on time or "sunset". If the on time is received, it is convert to timedelta for internal use. When it is "sunset", a function calculates the sunset time using the default location of Antigua and Barbuda or received location while sending the settings. This is then converted to timedelta for internal use.
  <user_temp> There not calculation
  <light_duration> The Api receives a str of either hours, minutes or seconds. It is then converted to timedelta using the parse_time function. The light off time is calculated by adding user_light with the light duration. The user_temp, user_light and light off time is stored in smart hub data array. Additionally, the data stored is returned for view.

**ESP32**
- The ESP32 collects temperature reading of the room and presence reading and send it to the API.
- The ESP32 reads the response of the API and turns on or off the light and fan based on the response of the API

**Purpose of project**
To control simple appliances using the internet and an api