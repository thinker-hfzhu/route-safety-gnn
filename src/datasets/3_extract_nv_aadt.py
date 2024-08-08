import numpy as np
import pandas as pd 
import requests

raw_aadts = pd.read_csv('~/data/AADT/NV/NV_AADT.csv')

'''
http://denali.telenav.com/entity/v4/search/json?api_key=b616a547-6611-4fc4-9b2e-41b0c8f5b903
&api_signature=b616a547-6611-4fc4-9b2e-41b0c8f5b903%3A1718741482%3Ac361f33295d8715e6a4a5934ef1fcafc
&query=Sutro+St+%40+Oddie&location=39.53779639%2C-119.7986836&intent=around&locale=en-US&sort=best_match&choosemap=OSM&limit=1&match_type=fuzzy&user_id=anonymous
'''

SEARCHING_URL = 'http://denali.telenav.com/entity/v4/search/json?'
MATCHING_URL = 'http://10.230.31.156:9080/api/v2/map-match/match?'

OFFSET = 0.0002
DEVIS = [ [0, OFFSET], [-OFFSET, 0], [0, -OFFSET], [OFFSET, 0], 
         [OFFSET, OFFSET], [-OFFSET, OFFSET], [-OFFSET, -OFFSET], [OFFSET, -OFFSET]]

def match_line(points, is_ramp = False):
    coordinates = ''
    for point in points:
        coordinates += '{},{};'.format(point[0], point[1])

    matching_params = {
        'coordinate': coordinates,
        # 'sourceType': 'VEHICLE_TRACE',     
        'wayField': 'basic,names',     
        'matchingPoint':'true',
        'multiplePath':'true'    
    }
    
    response = requests.get(url = MATCHING_URL, params = matching_params)
    if not response.ok:
        return (0, 0)
    
    data = response.json()
    if 'matchingResult' not in data or len(data['matchingResult'][0]) == 0:
        return (0, 0)

    score = 0
    way_id = 0

    for matchingPath in data['matchingResult'][0]['matchingPath']:
        conf = matchingPath['confidence']
        nav_way = matchingPath['navWay'][0]
        if is_ramp:
            if nav_way['roadSubType'] != 5:
                conf -= 3
            else:
                conf += 1

        snap_distance = matchingPath['matchingPoint'][0]['snapDistance']
        conf -= snap_distance / 10

        if conf > score:
            score = conf 
            way_id = nav_way['wayId']
    
    return (score, way_id)

def match_point(from_point, is_ramp = False):
    score = 0
    way_id = 0

    for devi in DEVIS:
        to_point = (from_point[0] + devi[0], from_point[1] + devi[1])
        score_, way_id_ = match_line([from_point, to_point], is_ramp)
        
        if score_ < 70:
            continue
        elif score_ > score:
            score = score_
            way_id = way_id_

        if score > 99:
            break
        
    return (score, way_id)

def road_is_ramp(name):
    def at_start(index):
        return index >= 0 and index < 5
    if pd.isna(name):
        return False
    
    if at_start(name.find('on-ramp')):
        return True
    if at_start(name.find('off-ramp')):
        return True
    
    return False

def road_name(name):
    for i, v in enumerate(name):
        if v == '(' or v == ',':
            return name[i+1:-1].strip(')')
        
    index = name.find('Intch')
    if index > 0:
        return name[0:index-1]
    
    index = name.find('Int')
    if index > 0:
        return name[0:index-1]
    
    return name

def towards(pt, on_road, to_road):
    query = '{} @ {}'.format(on_road, to_road)
    location = '{},{}'.format(pt[0], pt[1])

    searching_params = {
        'api_key': 'b616a547-6611-4fc4-9b2e-41b0c8f5b903',     
        'api_signature': 'b616a547-6611-4fc4-9b2e-41b0c8f5b903:1718737857:ab3d2928d0d90fb349a8ef7d900faca2',     
        'query': query,
        'location': location,
        # 'choosemap':'OSM',
        'intent': 'intersection',
        'sort': 'best_match',
        'limit': 1  
    }

    response = requests.get(url = SEARCHING_URL, params = searching_params)
    if not response.ok:
        return None
    
    data = response.json()
    if 'results' not in data:
        return None

    coordinate = data['results'][0]['address']['geo_coordinates']
    return (coordinate['latitude'], coordinate['longitude'])

def start_segment_of_line(from_point, to_point, offset):
    # Convert points to NumPy arrays
    from_point = np.array(from_point)
    to_point = np.array(to_point)
    
    # Calculate the direction vector from A to B
    direction = to_point - from_point
    
    # Calculate the Euclidean norm (length) of the direction vector
    length = np.linalg.norm(direction)
    
    if length > 0.05000:
        return None

    # Normalize the direction vector
    direction_normalized = direction / length
    
    # Scale the normalized direction vector by the specified distance
    scaled_direction = offset * direction_normalized
    
    # Calculate the point C 
    mid_point = from_point + scaled_direction
    # n2 = n1 + scaled_direction
    
    return [from_point, (mid_point[0], mid_point[1])]

aadts = []

# 310447,310458,310285,310808,310311
# 12110,312310,35400,30832; 170035,190129,
# raw_aadts = raw_aadts[raw_aadts['Name'].isin([190002,30111])]

for index, raw_aadt in raw_aadts.iterrows():
    pt = (float(raw_aadt['LAT_DECIMAL']), float(raw_aadt['LON_DECIMAL']))
    is_ramp = road_is_ramp(raw_aadt['LOCATION_D'])
    on_road = road_name(raw_aadt['ROUTE_NAME'])
    pts = None

    aadt = {}

    aadt['aadt_code'] = raw_aadt['Name']
    aadt['on_road'] = on_road
    aadt['to_road'] = ''
    aadt['lat'] = round(pt[0], 5)
    aadt['lon'] = round(pt[1], 5)

    if not pd.isna(raw_aadt['STREET_TO']):
        to_road = road_name(raw_aadt['STREET_TO'])
        aadt['to_road'] = to_road
        pt2 = towards(pt, on_road, to_road)
        if pt2 is not None:
            pts = start_segment_of_line(pt, pt2, 0.00030)

    if pts:
        score, way_id = match_line(pts, is_ramp)
        aadt['score'] = int(score)
        if score >= 95:
            aadt['matched'] = 2

    if 'matched' not in aadt:
        score, way_id = match_point(pt, is_ramp)
        aadt['score'] = int(score)
        if score >= 95:
            aadt['matched'] = 1
        elif score >= 85:
            aadt['matched'] = 0
        elif score >= 70:
            aadt['matched'] = -1
        else:
            aadt['matched'] = -2

    aadt['way_id'] = way_id
    aadt['aadt_2007'] = raw_aadt['AADT_2007']
    aadt['aadt_2008'] = raw_aadt['AADT_2008']
    aadt['aadt_2009'] = raw_aadt['AADT_2009']
    aadt['aadt_2010'] = raw_aadt['AADT_2010']
    aadt['aadt_2011'] = raw_aadt['AADT_2011']
    aadt['aadt_2012'] = raw_aadt['AADT_2012']
    aadt['aadt_2013'] = raw_aadt['AADT_2013']
    aadt['aadt_2014'] = raw_aadt['AADT_2014']
    aadt['aadt_2015'] = raw_aadt['AADT_2015']
    aadt['aadt_2016'] = raw_aadt['AADT_2016']
    aadt['aadt_2017'] = raw_aadt['AADT_2017']
    aadt['aadt_2018'] = raw_aadt['AADT_2018']
    aadt['aadt_2019'] = raw_aadt['AADT_2019']
    aadt['aadt_2020'] = raw_aadt['AADT_2020']
    aadt['aadt_2021'] = raw_aadt['AADT_2021']
    aadt['aadt_2022'] = raw_aadt['AADT_2022']

    aadts.append(aadt)

    if (index + 1) % 200 == 0:
        print(f"parsed {index + 1} raw aadts")

aadts = pd.DataFrame(aadts, columns=['aadt_code', 'on_road', 'to_road', 'lat', 'lon', 'matched', 'score', 'way_id', 
                             'aadt_2007', 'aadt_2008', 'aadt_2009', 'aadt_2010', 'aadt_2011', 'aadt_2012', 'aadt_2013', 
                             'aadt_2014', 'aadt_2015', 'aadt_2016', 'aadt_2017', 'aadt_2018', 'aadt_2019', 'aadt_2020', 
                             'aadt_2021', 'aadt_2022']) 
 
aadts.to_csv("~/data/GNN/NV/AADTS.csv", index=False)


"""
# merge ways and aadts on way_id
ways = pd.read_csv(os.path.join(data_dir, f"{state}/WAYS_.csv"))
aadts = pd.read_csv(os.path.join(data_dir, "aadt_pred_train.csv"))

ways_without_aadt = []
ways_with_aadt = pd.merge(ways, aadts, how='inner', on=['way_id'])
"""
