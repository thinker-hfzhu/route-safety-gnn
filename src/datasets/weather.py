from meteostat import Stations, Hourly
from datetime import datetime

def get_station_code(lat, lon):
    stations = Stations()
    station = stations.nearby(lat,lon).fetch(1)
    return station.index[0]

def get_hourly_weather(station_code, start, end):
    # get the weather data for the specified station
    data = Hourly(station_code, start, end)
    return data.fetch()

# code = get_station_code(39.53560, -119.80807)
# print(get_hourly_weather(code, datetime(2024, 2, 15), datetime(2024, 2, 16)))
