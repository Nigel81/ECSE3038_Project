from fastapi import FastAPI, HTTPException, Response, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ValidationError
from datetime import datetime, timedelta, time, timezone, date
from fastapi.responses import JSONResponse
from typing import List
from uuid import UUID, uuid4
import re
import tzlocal
import asyncio
import httpx
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

smart_hub_data = []
sensor_data = [] 
max_storage = 500

LOCAL_TIME = tzlocal.get_localzone()
#UTC = timezone.utc
DEFAULT_SUNSET = "18:45"
LAT = 17.074656
LONG = -61.817520 # location of Antigua and Barbuda
sunset_cache = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://simple-smart-hub-client.netlify.app"],  # Your frontend URL
    allow_methods=["GET", "PUT", "OPTIONS"],  # Explicitly allow GET and OPTIONS
    allow_headers=["*"],
)

class Settings(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_temp: int
    user_light: str 
    #light_time_off: timedelta
    light_duration: str
    lat: float | None = None
    lng: float | None = None

class Graph(BaseModel):
    temperature: float 
    presence: bool 
    #date_time:datetime = Field(default_factory=datetime.utcnow)
    date_time:datetime = Field(default_factory=lambda: datetime.now(LOCAL_TIME))
class GraphResponse(BaseModel):
    temperature: float 
    presence: bool
    datetime: datetime 

@app.put("/settings")
async def user_settings(settings_request:Settings):
    if settings_request.user_light.lower() == "sunset":
        if settings_request.lat is None or settings_request.lng is None:
            settings_request.lat = LAT
            settings_request.lng = LONG
        settings_request.user_light = await get_sunset_time(settings_request.lat, settings_request.lng)

    tempo_light = get_user_light_timedelta(settings_request.user_light)
    tempo_duration = settings_request.light_duration

    time_off = parse_time(tempo_duration)
    time_off = time_off + tempo_light
    # storage = {"settings":settings_request,"light_time_off":time_off}
    # time_off1 = format_timedelta(time_off)
    # storage1 = settings_request.dict()
    # storage1 ["light_time_off"] = time_off1 #time_off
    # del storage1["light_duration"]
    # storage1["user_light"] = format_timedelta(tempo_light)
    storage = {
        "id": settings_request.id,
        "user_temp": settings_request.user_temp,
        "user_light": format_timedelta(tempo_light),
        "light_time_off": format_timedelta(time_off)
    }

    smart_hub_data.clear() #make room for new user settings
    smart_hub_data.append(storage)
    return storage
        #"message": "Settings stored successfully"

@app.post("/sensors_data")
async def process_sensor_data(output_request: Graph):
    # if not smart_hub_data:
    #         raise HTTPException(status_code=400, detail="Settings not found")
    try:
        
        sensor_data.insert(0, output_request)
        if len(sensor_data) > max_storage:
            sensor_data.pop()
        #settings = smart_hub_data[-1]
        if smart_hub_data:
            settings = smart_hub_data[-1]
            #light_time_off = settings["light_time_off"]
            fan_status = "on" if (output_request.temperature >= settings["user_temp"] and output_request.presence) else "off"

            #current_time = output_request.date_time.time()
            light_on_time = time.fromisoformat(settings["user_light"])  
            light_off_time = time.fromisoformat(settings["light_time_off"])
            # light_on_time = time(
            #     hour=settings.user_light.seconds // 3600,
            #     minute=(settings.user_light.seconds % 3600) // 60
            # )
            # light_off_time = time(
            #     hour=light_time_off.seconds // 3600,
            #     minute=(light_time_off.seconds % 3600) // 60
            # )
            # if light_on_time <= light_off_time:
            #     light_on = light_on_time <= current_time <= light_off_time
            # else:
            #     light_on = light_on_time <= current_time or current_time <= light_off_time
            light_on_datetime = datetime.combine(
                output_request.date_time.date(), 
                light_on_time,
                tzinfo=LOCAL_TIME
                )
            light_off_datetime = datetime.combine(
                output_request.date_time.date(),
                light_off_time,
                tzinfo=LOCAL_TIME
            )
            if light_on_time > light_off_time:
                light_off_datetime += timedelta(days=1)

            if light_on_datetime <= output_request.date_time <= light_off_datetime:
                light_on = True
            else:
                light_on = False
            light = "on" if (output_request.presence and light_on) else "off"
            return {"fan": fan_status, "light":light}
        else: return {"fan": "off", "light": "off", "settings":"none"}
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=jsonable_encoder(e.errors()))

regex = re.compile(r'((?P<hours>\d+?)h)?((?P<minutes>\d+?)m)?((?P<seconds>\d+?)s)?')  

# def parse_time(time_str):
#     parts = regex.match(time_str)
#     if not parts:
#         return
#     parts = parts.groupdict()
#     time_params = {}
#     for name, param in parts.items():
#         if param:
#             time_params[name] = int(param)
#     return timedelta(**time_params)

def parse_time(time_str):
    parts = regex.match(time_str)
    if not parts:
        raise ValueError("Invalid duration format")
    parts = parts.groupdict()
    time_params = {}
    for name, param in parts.items():
        if param:
            time_params[name] = int(param)
    return timedelta(**time_params)

def format_timedelta(td: timedelta) -> str:
    """Convert timedelta to HH:MM:SS format"""
    
    if td < timedelta(0):
        raise ValueError("Timedelta must be non-negative")
    
    total_seconds = int(td.total_seconds()) % 86400
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def get_user_light_timedelta(user_light) -> timedelta:
    """Convert user_light (either string or timedelta) to timedelta"""
    if isinstance(user_light, str):
        t = time.fromisoformat(user_light)
        return timedelta(
            hours=t.hour,
            minutes=t.minute,
            seconds=t.second
        )
    elif isinstance(user_light, timedelta):
        return user_light
    else:
        raise ValueError("Invalid user_light format")

async def get_sunset_time(lat: float, lng: float) -> str:
    today = date.today()
    cache_key = (round(lat, 4), round(lng, 4), today)
    if cache_key in sunset_cache:
        return sunset_cache[cache_key]

    url = "https://api.sunrise-sunset.org/json"
    params = {"lat": lat, "lng": lng, "formatted": 0}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            if data["status"] == "OK":
                sunset_utc = data["results"]["sunset"]
                sunset_local = datetime.fromisoformat(sunset_utc).astimezone(LOCAL_TIME)
                sunset_str = sunset_local.strftime("%H:%M:%S")
                sunset_cache[cache_key] = sunset_str
                return sunset_str
            else:
                raise HTTPException(500, detail=f"Sunset API error: {data['status']}")
        else:
            raise HTTPException(response.status_code, detail="Failed to fetch sunset time")

async def daily_cache_cleaner():
    while True:
        await asyncio.sleep(86400)  
        today = date.today()
        keys_to_delete = [key for key in sunset_cache if key[2] != today]
        for key in keys_to_delete:
            del sunset_cache[key]
        
@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(daily_cache_cleaner())

@app.get("/graph", response_model=List[GraphResponse])
async def get_graph_data(size: int = Query(..., gt=0, le=max_storage, description="Number of objects to return (1-500)")):
    
    if not sensor_data:
        raise HTTPException(status_code=404, detail="No sensor data available")
    
    try:
        
        # Determine the slice of data to return
        data = sensor_data[:min(size, len(sensor_data))]
        
        #if not latest_first:
        #    data = reversed(data)
        return [
            {
                # "temperature": round(random.uniform(15.0, 35.0), 1),
                # "presence": random.choice([True, False]),
                # "datetime": datetime.utcnow()
                "temperature": item.temperature,
                "presence": item.presence,
                "datetime": item.date_time
            }
            for item in data
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/settings")   #for debugging purposes
async def get_settings():
    if not smart_hub_data:
        raise HTTPException(404, "No settings found")
    return smart_hub_data[-1]
