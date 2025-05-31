from fastapi import FastAPI, HTTPException, Response, Query, status
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
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

app = FastAPI()

scheduler = AsyncIOScheduler()
smart_hub_data = []
sensor_data = [] 
max_storage = 500
time_off = timedelta()
flag = 0
event_loop = None

LOCAL_TIME = tzlocal.get_localzone()
DEFAULT_SUNSET = "18:45"
LAT = 17.074656   # Lat location of Antigua and Barbuda
LONG = -61.817520 # Long location of Antigua and Barbuda
sunset_cache = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://simple-smart-hub-client.netlify.app"],  #Webpage
    allow_methods=["GET", "PUT", "OPTIONS"],  # allow GET, PUT and OPTIONS
    allow_headers=["*"],
)

class Settings(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_temp: int
    user_light: str 
    light_duration: str
    lat: float | None = None
    lng: float | None = None

class Graph(BaseModel):
    temperature: float 
    presence: bool 
    date_time:datetime = Field(default_factory=lambda: datetime.now(LOCAL_TIME))

class GraphResponse(BaseModel):
    temperature: float 
    presence: bool
    datetime: datetime 

@app.put("/settings")
async def user_settings(settings_request:Settings):
    global flag, time_off
    if settings_request.user_light.lower() == "sunset":
        flag = 1
        if settings_request.lat is None or settings_request.lng is None:
            settings_request.lat = LAT
            settings_request.lng = LONG
        settings_request.user_light = await get_sunset_time(settings_request.lat, settings_request.lng)
    else:
        flag = 0

    try: 
        tempo_light = get_user_light_timedelta(settings_request.user_light)
        time_off = parse_time(settings_request.light_duration)
        time_off = time_off + tempo_light
    except ValueError as e:
        raise HTTPException(status_code=400,detail=str(e))
    
    storage = {
        "id": settings_request.id,
        "user_temp": settings_request.user_temp,
        "user_light": format_timedelta(tempo_light),
        "light_time_off": format_timedelta(time_off)
    }

    report = status.HTTP_200_OK if smart_hub_data else status.HTTP_201_CREATED #check for previous settings
    smart_hub_data.clear() #replace settings
    smart_hub_data.append(storage)
    return JSONResponse(content=jsonable_encoder(storage), status_code=report)
        
@app.post("/sensors_data")
async def process_sensor_data(output_request: Graph):
    try:
        
        sensor_data.insert(0, output_request)
        if len(sensor_data) > max_storage:
            sensor_data.pop()
        
        if smart_hub_data:
            settings = smart_hub_data[-1]
            fan_status = "on" if (output_request.temperature >= settings["user_temp"] and output_request.presence) else "off"

            
            light_on_time = get_user_light_timedelta(settings["user_light"])  
            light_off_time = get_user_light_timedelta(settings["light_time_off"])
            current_time = timedelta(hours=output_request.date_time.hour, 
                                     minutes=output_request.date_time.minute, 
                                     seconds=output_request.date_time.second)
            # light_on_time = time(
            #     hour=settings.user_light.seconds // 3600,
            #     minute=(settings.user_light.seconds % 3600) // 60
            # )
            # light_off_time = time(
            #     hour=light_time_off.seconds // 3600,
            #     minute=(light_time_off.seconds % 3600) // 60
            # )
            if light_on_time <= light_off_time:
                light_on = light_on_time <= current_time <= light_off_time
            else:
                light_on = light_on_time <= current_time or current_time <= light_off_time
            
            light = "on" if (output_request.presence and light_on) else "off"
            return {"fan": fan_status, "light":light}
        else: return {"fan": "off", "light": "off", "settings":"none"}
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=jsonable_encoder(e.errors()))

regex = re.compile(r'((?P<hours>\d+?)h)?((?P<minutes>\d+?)m)?((?P<seconds>\d+?)s)?')  

def parse_time(time_str):
    """Convert duration str to time duration"""
    parts = regex.match(time_str)
    if not parts:
        raise ValueError("invalid duration format")
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

def get_user_light_timedelta(light) -> timedelta:
    """Convert user_light or other(either string or timedelta) to timedelta"""
    if isinstance(light, str):
        t = time.fromisoformat(light)
        return timedelta(
            hours=t.hour,
            minutes=t.minute,
            seconds=t.second
        )
    elif isinstance(light, timedelta):
        return light
    else:
        raise ValueError("Invalid user_light format")

async def get_sunset_time(lat: float, lng: float) -> str:
    """Get sunset time"""
    today = date.today()
    cache_key = (round(lat, 4), round(lng, 4), today)
    if cache_key in sunset_cache:
        return sunset_cache[cache_key]

    url = "https://api.sunrise-sunset.org/json"
    params = {"lat": lat, "lng": lng, "formatted": 0}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            data = response.json()
            if data["status"] == "OK":
                sunset_utc = data["results"]["sunset"]
                sunset_local = datetime.fromisoformat(sunset_utc).astimezone(LOCAL_TIME)
                sunset_str = sunset_local.strftime("%H:%M:%S")
                sunset_cache[cache_key] = sunset_str
                return sunset_str
            else:
                raise ValueError(f"Sunset API returned a bad status: {data['status']}")
    except Exception as e:
        fall_back = DEFAULT_SUNSET
        sunset_cache[cache_key] = fall_back
        print(f"Failed to fetch sunset time, default used")
        return fall_back

def daily_cache_cleaner(): 
    today = date.today()
    keys_to_delete = [key for key in sunset_cache if key[2] != today]
    for key in keys_to_delete:
        del sunset_cache[key]
        
@app.on_event("startup")
async def on_startup():
    global event_loop
    event_loop = asyncio.get_running_loop()
    daily_cache_cleaner()
    scheduler.add_job(
        lambda: asyncio.run_coroutine_threadsafe(update_sunset(), event_loop),
        CronTrigger(hour=22, minute=20)
    )
    scheduler.add_job(daily_cache_cleaner, CronTrigger(hour=3))
    scheduler.start()

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()

async def update_sunset():
    global flag, time_off
    if flag and smart_hub_data:
        new_sunset = await get_sunset_time(LAT, LONG)
        smart_hub_data[-1]["user_light"] =  format_timedelta(get_user_light_timedelta(new_sunset))
        smart_hub_data[-1]["light_time_off"] = format_timedelta(get_user_light_timedelta(new_sunset) + time_off)
        print(f"sunset updated")

@app.get("/graph", response_model=List[GraphResponse]) 
async def get_graph_data(size: int = Query(..., gt=0, le=max_storage, description="Number of objects to return (1-500)")):
    
    if not sensor_data:
        raise HTTPException(status_code=404, detail="No sensor data available")
    
    try:
        
        # Determine the slice of data to return
        data = sensor_data[:min(size, len(sensor_data))]
        
        return [
            {
                "temperature": item.temperature,
                "presence": item.presence,
                "datetime": item.date_time
            }
            for item in data
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/settings")   #For debugging purposes
async def get_settings():
    if not smart_hub_data:
        raise HTTPException(404, "No settings found")
    return smart_hub_data[-1]
