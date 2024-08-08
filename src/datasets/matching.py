import pandas as pd
import requests

DIRS = ['S', 'E', 'N', 'W']
OFFSET = 0.0002
DEVIS = [ [0, OFFSET], [-OFFSET, 0], [0, -OFFSET], [OFFSET, 0], 
         [OFFSET, OFFSET], [-OFFSET, OFFSET], [-OFFSET, -OFFSET], [OFFSET, -OFFSET]]

def point_from_dir(dir, to_point):
    if dir == 'N':
        return (to_point[0] - OFFSET, to_point[1])
    elif dir == 'S':
        return (to_point[0] + OFFSET, to_point[1])
    elif dir == 'W':
        return (to_point[0], to_point[1] + OFFSET)
    elif dir == 'E':
        return (to_point[0], to_point[1] - OFFSET)

    return to_point

# MATCHING_URL = 'http://graph-service-here-na.stg.k8s.mypna.com:9080/api/v2/map-match/match?'

# MATCHING_URL = 'http://10.230.31.153:9080/api/v2/map-match/match?'

MATCHING_URL = 'http://10.230.31.156:9080/api/v2/map-match/match?'

def get_route_dir(road_names):
    for road_name in road_names:
       if road_name['type'] == 'ROUTE_NUMBER':
           if road_name['name'][-1] in DIRS:
               return road_name['name'][-1]
           
    return 0

def match_line(points, dir = False):
    coordinates = ''
    for point in points:
        coordinates += '{},{};'.format(point[0], point[1])

    matching_params = {
        'coordinate': coordinates,
        # 'sourceType': 'VEHICLE_TRACE',     
        'wayField': 'basic,names',     
        # 'matchingPoint':'true',
        # 'multiplePath':'true'    
    }
    
    response = requests.get(url = MATCHING_URL, params = matching_params)
    if not response.ok:
        return (0, 0, 0)
    
    data = response.json()
    if data['matched'] == 0:
        return (0, 0, 0)

    matchingPath = data['matchingResult'][0]['matchingPath'][0]
    
    way_ids = []
    dirs = []
    for nav_way in matchingPath['navWay']:
        if way_ids and nav_way['roadSubType'] == 4:
            break
            
        way_ids.append(nav_way['wayId'])
        dirs.append(get_route_dir(matchingPath['roadName']) if 'roadName' in matchingPath and dir else 0)

    return (matchingPath['confidence'], way_ids[-1], dirs[-1])

def match_point(to_point, dir = None):
    if dir:
        from_point = point_from_dir(dir, to_point)
        score, way_id, _ = match_line([from_point, to_point])
    else:
        score = 0
        
    if score < 99:
        for devi in DEVIS:
            from_point = (to_point[0] + devi[0], to_point[1] + devi[1])
            score_, way_id_, dir_ = match_line([from_point, to_point], True)
            if dir_ == dir:
                score_ += 1.5
            
            if score_ < 90:
                continue
            elif abs(score - score_) < 1:
                score = 0
            elif score_ > score:
                score = score_
                way_id = way_id_

            if score > 99:
                break
        
    if score >= 98:
        return way_id
    else:
        return 0

def match_maneuver(crash):
    to_point = (crash['lat'], crash['lon'])
    road = crash['primary_road']

    dir = crash['v1_dir']
    if dir not in DIRS:
        crash['v1_dir'] = None
        dir = None

    way_id = match_point(to_point, dir)
    if way_id:
        crash['v1_way'] = way_id
        #     print(f"{dir} : {way_id}")
        # else:
        #     print(f"{dir} : {crash['v1_maneuver']}")
        # print(dir) # TODO rotate
        # dir = 'N'

    if 'v2_maneuver' not in crash:
        return 
    
    dir = crash['v2_dir']
    if dir not in DIRS:
        crash['vs_dir'] = None
        dir = None

    way_id = match_point(to_point, dir)
    if way_id:
        crash['v2_way'] = way_id
        #     print(f"{dir} : {way_id}")
        # else:
        #     print(f"{dir} : {crash['v2_maneuver']}")

# crashes = pd.read_csv('~/data/GNN/NV/CRASHES.csv')

# for index, crash in crashes.iterrows():
#     if index < 151:
#         continue

#     match_maneuver(crash)
    
# print(patterns)
