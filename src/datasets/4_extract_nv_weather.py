import os
import pandas as pd
from meteostat import Hourly
from datetime import datetime

# 2016, 2019, 2023

map_dir = "~/data/HERE-24Q2"
gnn_dir = "~/data/GNN"
state = 'NV'
year = 2016

def get_stations():
    stations = pd.read_csv(os.path.join(gnn_dir, f"{state}/STATIONS.csv"))
    return stations['station'].to_list()

def fetch_weather(start, end, timezone):
    stations = get_stations()
    data = Hourly(stations, start, end, timezone)
    data = data.fetch()

    weather = data[['temp', 'coco', 'prcp', 'wdir', 'wspd']] 
    weather.rename(index={s : i for i, s in enumerate(stations)}, inplace=True)

    weather.rename_axis(index=["station", "hour"], inplace=True)
    weather.to_csv(os.path.join(gnn_dir, f"{state}/WEATHER_{year}.csv"), date_format='%y%m%d%H')

def load_weather():
    return pd.read_csv(os.path.join(gnn_dir, f"{state}/WEATHER_{year}.csv"), index_col=[0,1], date_format='%y%m%d%H')

start = datetime(year, 1, 1)
end = datetime(year + 1, 1, 1)

fetch_weather(start, end, 'US/Pacific')
weather = load_weather()
print(weather)