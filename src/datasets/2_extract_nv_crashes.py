import pandas as pd
import pyproj
from matching import match_maneuver

severities = {'FATAL CRASH':3, 'INJURY CRASH':2, 'PROPERTY DAMAGE ONLY':1}

action_to_maneuvers = {'GOING STRAIGHT':'going-straight', 'TURNING LEFT':'turning-left', 'TURNING RIGHT':'turning-right', 
                       'MAKING U-TURN':'making-u-turn', 'BACKING UP':'backing-up', 'STOPPED':'stopped', 'PARKED':'stopped',  
                       'CHANGING LANES':'changing-lanes', 'PASSING OTHER VEHICLE':'changing-lanes', 
                       'LEAVING LANE':'leaving-lane', 'NEGOTIATING A CURVE':'leaving-lane', 'ENTERING LANE':'entering-lane', 
                       'LEAVING PARK POSITION':'starting', 'ENTERING PARK POSITION':'slowing', 'RACING':'speeding',
                       'TRAVELING WRONG WAY':'wrong-way', 'DRIVERLESS-MOVING VEHICLE':'driverless'} 

leaving_lane_in_factor = ['FAILURE TO KEEP IN PROPER LANE', 'RAN OFF ROAD', 'DROVE LEFT OF CENTER']

leaving_lane_in_event = ['RAN OFF ROAD', 'FENCE/WALL', 'MEDIAN BARRIER', 'CROSS MEDIAN', 'POST', 'POLE',
                'TREE/SHRUB', 'DITCH', 'EMBANKMENT', 'GUARDRAIL', 'MAILBOX', 'CURB', 'BRIDGE RAIL', 'FIXED OBJECTS']

speeding_in_factor = ['FOLLOWED TOO CLOSELY', 'DRIVING TOO FAST FOR CONDITIONS', 'EXCEEDED AUTHORIZED SPEED LIMIT']

driver_faults = [
    ('impaired-driving', ['HAD BEEN DRINKING', 'DRUG INVOLVEMENT']), 
    ('attention', ['INATTENTION/DISTRACTED',  'FELL ASLEEP, FAINTED, FATIGUED, ETC.', 'OBSTRUCTED VIEW']),
    ('patient', ['ILLNESS', 'PHYSICAL IMPAIRMENT'])
    # ('others', ['OTHER IMPROPER DRIVING'])   # 'UNKNOWN'
]

vehicle_faults = [
    ('right-of-way', ['FAILED TO YIELD RIGHT OF WAY']),
    ('traffic-sign', ['DISREGARDED TRAFFIC SIGNS, SIGNALS, ROAD MARKINGS', 'WRONG SIDE OR WRONG WAY']),
    ('spacing', ['FOLLOWED TOO CLOSELY']),
    ('speeding', ['DRIVING TOO FAST FOR CONDITIONS', 'EXCEEDED AUTHORIZED SPEED LIMIT']),
    ('lane-departure', ['UNSAFE LANE CHANGE', 'FAILURE TO KEEP IN PROPER LANE OR RUNNING OFF ROAD', 'RAN OFF ROAD', 'DROVE LEFT OF CENTER']),
    ('operating', ['OPERATING VEHICLE IN ERRATIC, RECKLESS, CARELESS, NEGLIGENT OR  AGGRESSIVE MANNER', 'OVER-CORRECTING/OVER-STEERING', 
           'OTHER IMPROPER DRIVING', 'MADE AN IMPROPER TURN', 'UNSAFE BACKING']),
    ('hit-and-run', ['HIT AND RUN']),
    ('attention', ['VISIBILITY OBSTRUCTED']),
    ('others', ['OBJECT AVOIDANCE', 'MECHANICAL DEFECTS', 'ROAD DEFECT', 'OTHER', 'DRIVERLESS VEHICLE']) # 'UNKNOWN'
]

def has_words(text, words, inc_na = False):
    if pd.isna(text):
        return inc_na

    for word in words:
        if text.find(word) >= 0:
            return True
        
    return False

def as_fault(raw_crash, v):
    fault = None

    factors = raw_crash[f'{v} Driver Factors']
    for driver_fault in driver_faults:
        if has_words(factors, driver_fault[1]):
            fault = driver_fault[0]
            break

    if fault == 'impaired-driving':
        return fault
    
    factors = raw_crash[f'{v} Vehicle Factors']
    for index, vehicle_fault in enumerate(vehicle_faults):
        if (index < 5 or not fault) and has_words(factors, vehicle_fault[1]):
            fault = vehicle_fault[0]
            break

    return fault 

def at_fault(raw_crash, v):
    if (has_words(raw_crash[f'{v} Driver Factors'], driver_without_faults, True) and 
            has_words(raw_crash[f'{v} Vehicle Factors'], vehicle_without_faults, True)):
        return False

    return True

def is_leaving_lane(raw_crash, v):
    if has_words(raw_crash[f'{v} Vehicle Factors'], leaving_lane_in_factor):
        return True
    
    if pd.isna(raw_crash['V2 Action']) and has_words(raw_crash[f'{v} All Events'], leaving_lane_in_event):
        return True

    return False

def is_passing_intersection(raw_crash):
    if raw_crash['Dir'] == 'AT INT':
        return True 
    
    return False

def is_changing_lanes(raw_crash, v):
    if has_words(raw_crash[f'{v} Vehicle Factors'], ['UNSAFE LANE CHANGE']):
        return True
    
    return False
    
def is_speeding(raw_crash, v):
    if has_words(raw_crash[f'{v} Vehicle Factors'], speeding_in_factor):
        return True
    
    return False

def as_maneuver(raw_crash, v):
    maneuver = action_to_maneuvers.get(raw_crash[f'{v} Action'], 'going-straight')
    if maneuver not in ['going-straight', 'changing-lanes']:
        return maneuver
    
    if is_passing_intersection(raw_crash):
        return 'passing-intersection'
    elif is_leaving_lane(raw_crash, v):
        return 'leaving-lane'
    elif is_changing_lanes(raw_crash, v):
        return 'changing-lanes'
    elif is_speeding(raw_crash, v):
        return 'speeding'
    else:
        return maneuver # if maneuver else 'TBD'

def nad83_to_gps(x, y):
    proj = pyproj.Proj(proj='utm', zone=11, datum='NAD83', ellps='WGS84')
    lon, lat = proj(x, y, inverse=True)
    return (round(lat, 5), round(lon, 5))

def st_date(raw_date):
    subs = raw_date.split(' ')[0].split('/')
    return f'{subs[2]}-{subs[0]}-{subs[1]}'

def st_time(raw_time):
    raw_time = raw_time.split(' ')
    is_pm = raw_time[1] == 'PM'
    subs = raw_time[0].split(':')
    if subs[0] == '12':
        subs[0] = '0'
    if is_pm:
        subs[0] = int(subs[0]) + 12

    return f'{subs[0]}:{subs[1]}:{subs[2]}'
    
def convert(raw_crash):
    '''
    crash_id, crash_date, crash_time, crash_severity, v1_maneuver, v1_dir, v1_fault, v2_maneuver, v2_dir, v2_fault, mbpa, primary_road, lat, lon
    MBPA: Motorcyclist, Bicyclist, Pedestrian, AnimalType
        Motorcyclist    5,154	2.17%
        Bicyclist       2,301	0.97% Pedalcyclist
        Pedestrian      4,964	2.09%
        AnimalType      4,108	1.73%
    '''
    crash = {}

    crash['crash_id'] = raw_crash['OBJECTID']
    crash['crash_date'] = st_date(raw_crash['Crash Date'])
    crash['crash_time'] = st_time(raw_crash['Crash Time'])
    crash['crash_severity'] = severities[raw_crash['Crash Severity']]
    crash['intersection'] = 1 if raw_crash['Dir'] == 'AT INT' else 0

    crash['v1_maneuver'] = as_maneuver(raw_crash, 'V1')
    crash['v1_dir'] = raw_crash['V1 Dir']
    crash['v1_fault'] = as_fault(raw_crash, 'V1')
    
    count(crash['v1_maneuver'], maneuvers)
    
    if not pd.isna(raw_crash['V2 Action']):
        crash['v2_maneuver'] = as_maneuver(raw_crash, 'V2')
        crash['v2_dir'] = raw_crash['V2 Dir']
        crash['v2_fault'] = as_fault(raw_crash, 'V2')

        count(crash['v2_maneuver'], maneuvers)  

    crash['mbpa'] = 'M' if raw_crash['Motorcyclist'] == 'YES' else ''
    crash['mbpa'] += 'B' if raw_crash['Pedalcyclist'] == 'YES' else ''
    crash['mbpa'] += 'P' if raw_crash['Pedestrian'] == 'YES' else ''
    crash['mbpa'] += 'A' if not pd.isna(raw_crash['AnimalType']) else ''

    crash['primary_road'] = raw_crash['Primary Street']
    lat_lon = nad83_to_gps(raw_crash['x'], raw_crash['y'])
    crash['lat'] = lat_lon[0]
    crash['lon'] = lat_lon[1]

    return crash

actions = {'LEAVING LANE':0, 'OTHER':0, 'ENTERING LANE':0, 'PASSING OTHER VEHICLE':0, 'NEGOTIATING A CURVE':0,  
    'TRAVELING WRONG WAY':0, 'PARKED':0, 'LEAVING PARK POSITION':0, 'DRIVERLESS-MOVING VEHICLE':0, 
    'OTHER TURNING MOVEMENT':0, 'RACING':0, 'ENTERING PARK POSITION':0, 'U-TURN':0, 'LANE CHANGE':0}

driver_without_faults = ['APPARENTLY NORMAL']

vehicle_without_faults = ['MECHANICAL DEFECTS', 'ROAD DEFECT', 'VISIBILITY OBSTRUCTED', 'NO IMPROPER DRIVING', 'UNKNOWN']

def is_special(raw_crash, v):
    action = raw_crash[f'{v} Action']
    if action in actions and actions[action] < 2:
        actions[action] += 1
        return True
    
    # if has_words(raw_crash[f'{v} Driver Factors'], ['UNKNOWN']):
    #     return True

    # if has_words(raw_crash[f'{v} Vehicle Factors'], [
    #             #'UNKNOWN', 'DRIVERLESS VEHICLE', 'OTHER', 'NO IMPROPER DRIVING', 'OBJECT AVOIDANCE', 'MECHANICAL DEFECTS', 'ROAD DEFECT', 
    #             'WRONG SIDE OR WRONG WAY', 'VISIBILITY OBSTRUCTED'                                          
    #             ]):
    #     return True
    
    if has_words(raw_crash[f'{v} All Events'], [
            # 'CARGO/EQUIPMENT LOSS OR SHIFT', 'MOVABLE OBJECT', 'IMMERSION', 
            'BRIDGE OVERHEAD STRUCTURE', 'OVERHEAD SIGN SUPPORT', 'BRIDGE PIER OR ABUTMENT', 'UNKNOWN FIXED OBJECT', 'OTHER TRAFFIC BARRIER'
        ]):
        return True
    
    return False

def count(text, counts):
    if pd.isna(text):
        return
    
    tokens = list(map(str.strip, text.split(':')))
    for token in tokens:
        value = counts.get(token)
        counts[token] = value + 1 if value else 1

def print_crash(raw_crash, crash):
    print(f"{crash['crash_id']} | {crash['crash_date']} | {crash['crash_time']} | {crash['crash_severity']} | {crash['mbpa']}")
    print(f"{crash['lat']},{crash['lon']} at {crash['primary_road']}" )
    
    print(str(raw_crash['V1 Action']) + ' | ' + str(raw_crash['V1 Driver Factors']) + ' | ' + str(raw_crash['V1 Vehicle Factors']) + ' | ' + str(raw_crash['V1 All Events']))
    print(f"=> {crash['v1_maneuver']} | {crash['v1_dir']} | {crash['v1_fault']} " + ('$' if at_fault(raw_crash, 'V1') else ''))

    if not pd.isna(raw_crash['V2 Action']):
        print(str(raw_crash['V2 Action']) + ' | ' + str(raw_crash['V2 Driver Factors']) + ' | ' + str(raw_crash['V2 Vehicle Factors']) + ' | ' + str(raw_crash['V2 All Events']))
        print(f"=> {crash['v2_maneuver']} | {crash['v2_dir']} | {crash['v2_fault']} " + ('$' if at_fault(raw_crash, 'V2') else ''))

raw_crashes = pd.read_csv('~/data/CRASH/NV/Crash_2016-2020.csv')

maneuvers = {}
crashes = []
num = 0

raw_crashes = raw_crashes[raw_crashes['Crash Year'] == 2019]
print(raw_crashes.shape)

for index, raw_crash in raw_crashes.iterrows():
    crash = convert(raw_crash)

    match_maneuver(crash)
    crashes.append(crash)
    num += 1

    if num % 200 == 0:
        print(f"parsed {index} raw crashes, matched {num} crashes")
        # break

    # if is_special(raw_crash, 'V1'):
    #     print_crash(raw_crash, crash)
    #     print('***')

crashes = pd.DataFrame(crashes, columns=['crash_id', 'crash_date', 'crash_time', 'crash_severity', 'intersection', 
                             'v1_maneuver', 'v1_dir', 'v1_fault', 'v1_way', 'v2_maneuver', 'v2_dir', 'v2_fault', 'v2_way',
                             'mbpa', 'primary_road', 'lat', 'lon']) 
 
crashes.to_csv("~/data/GNN/NV/CRASHES.csv", index=False)

'''  
dfactors = {}
vfactors = {}
events = {}

dfactors2 = {}
vfactors2 = {}
events2 = {}

count(crash['V1 Driver Factors'], dfactors)
count(crash['V1 Vehicle Factors'], vfactors)
count(crash['V1 All Events'], events)
count(crash['V2 Driver Factors'], dfactors2)
count(crash['V2 Vehicle Factors'], vfactors2)
count(crash['V2 All Events'], events2)

print(sorted(dfactors.items(), key=lambda x: x[1], reverse=True))
print(sorted(vfactors.items(), key=lambda x: x[1], reverse=True))
print(sorted(events.items(), key=lambda x: x[1], reverse=True))
print(sorted(dfactors2.items(), key=lambda x: x[1], reverse=True))
print(sorted(vfactors2.items(), key=lambda x: x[1], reverse=True))
print(sorted(events2.items(), key=lambda x: x[1], reverse=True))

print(sorted(maneuvers.items(), key=lambda x: x[1], reverse=True))

data_dir = "~/data/CRASH/NV/"

crashes = gpd.read_file(data_dir + '2020.gdb', layer='Crash_Data_2020')
print(crashes.shape)
crashes.to_csv(data_dir + '2020/Crash_Data')
vehicles = gpd.read_file(data_dir + '2020.gdb', layer='Vehicle_Table_2020')
print(vehicles.shape)
vehicles.to_csv(data_dir + '2020/Vehicle_Table')
persons = gpd.read_file(data_dir + '2020.gdb', layer='Person_Table_2020')
print(persons.shape)
persons.to_csv(data_dir + '2020/Person_Table')
'''