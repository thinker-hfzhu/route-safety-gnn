import math
import numpy as np
import polyline
from geographiclib.geodesic import Geodesic
from weather import get_station_code

"""
ways																
	way_id:	
    length: 2-10000	
    one_way: 
        0: twoway
        1: forward oneway
        2: backward oneway
    road_class: highway(4), artery(3), local(2), slow(1), private and others(0)
    road_type: others(0), single(1), dual(2), connection(3), intersection(4), ramp(5), roundabout(6), tunnel(7), bridge(8)
    divider:
        0: no
        1: physical             9 in divider:lanes
        2: shaded area          7 in divider:lanes
        3: double solid line    2 in divider:lanes
        4: others
    urban: 1 if tags->'adas:urban'; tags->'adas:bua' else 0
    bipesz:
        0: default
        1: bicycle      type:lanes =>65536; traffic_sign(bicycle_crossing, yield_to_bicycles);
        2: pedestrian   highway =>residential; traffic_sign(pedestrian_crossing); connected with rt == 8
        4: school       traffic_sign(traffic_sign => school_zone) adas:maxspeed (depdendent_speed_type => school) 
    forward_lane_count(backward_lane_count): 0-6; lanes:forward =>1; lanes:backward =>1	
    lane_count: 1-12; 
        positive is from type:lanes =>0|0|65536; lanes =>1; forward_lane_count(backward_lane_count);
        negative is from lane_cat =>1
    forward_speed(backward_speed): 5-80; 
        positive is from maxspeed:forward =>40; maxspeed:backward =>30; 
        negative is from spd_kph:f =>60; spd_kph:t =>60; sc =>7
    start_bearing(end_bearing): 0-359
        positive is from geometry directly
        negative is tuned, e.g. end of digitalized dual way
    curve_left(curve_right): sum of weighted curve / length // relations   tags->'curvature'
        positive from tags->'adas:chs'; 
        negative from geometry; 
    slope_up(slope_down): sum of weighted slope / length    // tags->'adas:z_coord', relations	tags->'slope_t', relations	tags->'slope'	{Num}
        positive from tags->'adas:chs'; 
        negative from tags->'f_node_height'; tags->'t_node_height';
    from_node: node index	
    to_node: node index

nodes
    node_id:
    ways: [list of way index] 
        positive is at from_node
        negative is at to_node
        
relations: relation_type, value, from_way, via_node, to_way
    relation_type: restriction(1), barrier(2), lane_connectivity(3), traffic_control(4), traffic_sign(5), additional(6)
    restriction(1) value:
        1 (Physical)    2 of rdm_type
        2 (Legal)       1 of rdm_type 
        3 (Logical)     3 of rdm_type 
        4 (Observed)    4 of rdm_type 
        5 (Seasonal)    None rdm_type
        negative for timed: -1, -2, -3, -4, -5
    barrier(2) value:
        1 (Gated)
        2 (Toll Booth)
        negative for timed: -1, -2
    lane_connectivity(3) value:
        connected lanes
        -0.5 for bifurcation
        -1 for go straight
    traffic_control(4) value:
        1 signal
        2 stop
        3 yield
        4 railway_crossing 
    traffic_sign(5) value:
        1 animal crossing:
        2 falling rocks:
        3 hazard:               congestion_hazard, accident_hazard, truck_roll_over, 
        4 slippery(whether):    icy_conditions, slippery_road
        5 lane_merge:           lane_merge_right, lane_merge_left, lane_merge_center, road_narrows,
        6 curve:                sharp_curve_left, sharp_curve_right, winding_road_starting_left, winding_road_starting_right, lateral_wind, general_curve,
        7 hill:                 steep_hill_upwards, steep_hill_downwards, general_hill
        8 overtaking:           *overtaking*
        9 others:
    additional(6) value(other relations):
        1 blackspot 
        2 construction 
        3 no_overtaking
        4 timed_speed

joints
    from_way_index: forward is positive, backward is negative
    to_way_index: forward is positive, backward is negative
    length
    slope
    connected_lanes
    traffic_control: no_sign, signal, stop, yield, merge, branch
    traffic_conflicts: ???
"""

class WayGraph:
    '''
    ways: [{}, {'way_id': 12345678, 'length': 86, ..., 'from_node': 0, 'to_node': 1}, ...]

    nodes: [{'node_id': 22222101, 'ways': [1, -3, ...]}, 
            {'node_id': 22222102, 'ways': [-1, 2, ...]}]

    __way_idx__: {12345678:1, ...}
    __node_idx__: {22222101:0, 22222102:1, ...}
    '''
    def __init__(self):
        self.ways = [{'way_id': 0, 'length': 0}] # way index is from 1 for negative (1 != -1, 0 == -0) 
        self.nodes = []
        self.stations = []
        self.relations = []

        self.non_road_way = 0
        self.ignored_road_way = 0

        self.__leaf_ways__ = []
        self.__relations__ = []

        self.__way_idx__ = {}
        self.__node_idx__ = {}
        self.__relation_idx__ = {}
        self.__station_idx__ = {}

    def initialize(self, ways, nodes = None):
        self.ways = ways
        for index, way in ways.iterrows():
            self.__way_idx__[way['way_id']] = index

        if nodes is not None:
            self.nodes = nodes
            for index, node in nodes.iterrows():
                self.__node_idx__[node['node_id']] = index

    def get_way(self, way_id):
        return self.ways.iloc[self.__way_idx__[way_id]]
    
    def append_way(self, raw_way):
        way = {}

        tags = dict(map(str.strip, sub.split('=>', 1))
            for sub in raw_way[5].replace('"', '').split(',') if '=>' in sub)
        
        if ('rt' not in tags):
            self.non_road_way += 1
            return
        
        fc = int(tags['fc'])
        rt = int(tags['rt'])
        rst = int(tags['rst'])
        
        # road_class: highway(4), artery(3), local(2), slow(1), private and others(0)
        if rt <= 1:
            way['road_class'] = 4 
        elif fc >= 3: 
            way['road_class'] = 3 
        elif rt <= 4:
            way['road_class'] = 2
        elif rt == 6: # slow
            way['road_class'] = 1
        elif rt == 8: # walkway
            way['road_class'] = -1
        else:         # private(7) and others
            way['road_class'] = 0

        # road_type: default(0), single(1), dual(2), connection(3), intersection(4), ramp(5), roundabout(6), tunnel(7), bridge(8)
        switcher = {0:6,1:1,2:2,3:3,4:4,5:5,11:7,12:8}
        way['road_type'] = switcher.get(rst, 0)
        
        # oneway: twoway(0), forward oneway(1), backward oneway(2)
        oneway = tags.get('oneway')
        if oneway == '-1':
            way['oneway'] = 2
        elif oneway == 'yes':
            way['oneway'] = 1
        else:
            way['oneway'] = 0

        way['divider'] = _get_divider(tags)
        way['urban'] = 1 if tags.get('adas:urban') == 'yes' or tags.get('adas:bua') == 'yes' else 0
        way['bipesz'] = 0
        
        way['way_id'] = raw_way[0] // 1000

        points = _get_points(raw_way[8])
        way['polyline'] = polyline.encode(points)
        way_shape = WayShape(points)
        way['length'] = round(way_shape.length)
        way['start_bearing'] = round(way_shape.start_bearing())
        way['end_bearing'] = round(way_shape.end_bearing())

        _set_speed(way, tags)
        _set_lane(way, tags)
        _set_curve_slope(way, tags, way_shape)

        if tags.get('highway') == 'residential':
            way['bipesz'] |= 2

        nodes = raw_way[6].strip('}{').split(',')
        
        if way['road_class'] > 0:
            way['from_node'] = self.__get_node_index__(int(nodes[0]), points[0], True)
            way['to_node'] = self.__get_node_index__(int(nodes[-1]), points[-1], False)

            self.__way_idx__[way['way_id']] = len(self.ways)
            self.ways.append(way)
        else: # private, walkway, etc. will be appended into self.ways by __append_leaf_ways__
            way['from_node'] = int(nodes[0])
            way['to_node'] = int(nodes[-1])

            self.__leaf_ways__.append(way)

    def append_relation(self, raw_relation):
        '''
        record: [relation_type, value, from_way, via_node, to_way]
        relation_type: restriction(1), barrier(2), lane_connectivity(3), traffic_control(4), traffic_sign(5), additional(6)
        '''
        tags = dict(map(str.strip, sub.split('=>', 1))
            for sub in raw_relation[5].replace('"', '').split(',') if '=>' in sub)
        
        rel_id = raw_relation[0]
        rel_type = tags.get('type')
        if rel_type == 'restriction':
            value = _restriction[tags.get('rdm_type')]
            self.__append_relation__(rel_id, 1, value if tags.get('time') == None else -value)
        elif rel_type == 'barrier':
            value = _barrier[tags.get('barrier')]
            self.__append_relation__(rel_id, 2, value if tags.get('time') == None else -value)
        elif rel_type == 'lane_connectivity':
            self.__append_relation__(rel_id, 3, tags.get('lane_conn', '').count('|') + 1)
        elif rel_type == 'bifurcation':
            self.__append_relation__(rel_id, 3, -0.5)
        elif rel_type == 'go_straight':
            self.__append_relation__(rel_id, 3, -1)
        elif rel_type == 'traffic_signals':
            self.__append_relation__(rel_id, 4, 1)
        elif rel_type == 'traffic_sign':
            sign = tags.get('traffic_sign')
            if sign in _controls:
                self.__append_relation__(rel_id, 4, _controls[sign])
            elif sign in _bipesz:
                self.__append_relation__(rel_id, 7, _bipesz[sign])
            elif sign in _signs:
                self.__append_relation__(rel_id, 5, _signs[sign])
            elif sign is not None and sign.find('overtaking') >= 0:
                self.__append_relation__(rel_id, 5, 8)
            else:
                self.__append_relation__(rel_id, 5, 9)
        elif rel_type == 'railway_crossing':
            self.__append_relation__(rel_id, 4, 4)
        else:
            # rel_type in _additional
            value = _additional.get(rel_type)
            if value is not None:
                self.__append_relation__(rel_id, 6, value)

    def __append_relation__(self, relation_id, relation_type, value):
        self.__relation_idx__[relation_id] = len(self.__relations__)
        self.__relations__.append([relation_type, value, 0, -1, 0 ])

    def add_relation_member(self, raw_member):
        index = self.__relation_idx__.get(raw_member[0])
        if index is None:
            return

        if (raw_member[2] == 'W' and raw_member[3] == 'from') and raw_member[1] // 1000 in self.__way_idx__:
            self.__relations__[index][2] = self.__way_idx__[raw_member[1] // 1000]
        elif (raw_member[2] == 'N' and raw_member[3] == 'via') and raw_member[1] in self.__node_idx__:
            self.__relations__[index][3] = self.__node_idx__[raw_member[1]]
        elif (raw_member[2] == 'W' and raw_member[3] == 'to') and raw_member[1] // 1000 in self.__way_idx__:
            self.__relations__[index][4] = self.__way_idx__[raw_member[1] // 1000]

    def complete(self):
        for way in self.__leaf_ways__:
            self.__append_leaf_ways__(way)

        for node in self.nodes:
            self.__dual_way_at_end__(node)

        for relation in self.__relations__:
            self.__settle_relation(relation)

    def __get_node_index__(self, node_id, point, from_node):
        way_index = len(self.ways)
        node_index = self.__node_idx__.get(node_id)
        if node_index == None:
            node_index = len(self.nodes)
            self.__node_idx__[node_id] = node_index

            station_index = self.__get_station_index__(get_station_code(point[0], point[1]))
            self.nodes.append({'node_id': node_id, 'station': station_index, 'ways': [way_index if from_node else -way_index]})
        else:
            self.nodes[node_index]['ways'].append(way_index if from_node else -way_index)
            
        return node_index

    def __get_station_index__(self, station_code):
        station_index = self.__station_idx__.get(station_code)
        if station_index == None:
            station_index = len(self.stations)
            self.__station_idx__[station_code] = station_index
            self.stations.append({'station': station_code, 'nodes': 1})
        else:
            self.stations[station_index]['nodes'] += 1
        
        return station_index

    def __append_leaf_ways__(self, way):
        from_index = self.__node_idx__.get(way['from_node'])
        if from_index is None:
            way['from_node'] = -1
        elif way['road_class'] == -1:
            # set bipesz of ways at node
            self.__walkway_at_node__(self.nodes[from_index])
            way['from_node'] = -1
        else: 
            way['from_node'] = from_index
            self.nodes[from_index]['ways'].append(len(self.ways))

        to_index = self.__node_idx__.get(way['to_node'])
        if to_index is None:
            way['to_node'] = -1
        elif way['road_class'] == -1:
            # set bipesz of ways at node
            self.__walkway_at_node__(self.nodes[to_index])
            way['to_node'] = -1
        else: 
            way['to_node'] = to_index
            self.nodes[to_index]['ways'].append(-len(self.ways))

        if way['from_node'] != -1 or way['to_node'] != -1:
            self.__way_idx__[way['way_id']] = len(self.ways)
            self.ways.append(way)
        else:
            self.ignored_road_way += 1

    def __walkway_at_node__(self, node):
        for index in node['ways']:
            way = self.ways[index if index > 0 else -index]
            way['bipesz'] |= 2

    def __dual_way_at_end__(self, node):
        '''
        'ways': [29973, 164000, -179117, -183249, -234607]

        forward from   start_bearing          end
        forward to     end_bearing            start
        backward from  reverse start_bearing  start   
        backward to    reverse end_bearing    end

        start: [(way, heading)]
        end: [(way, heading)]
        '''
        if len(node['ways']) < 3:
            return

        start = []
        end = []

        for index in node['ways']:
            way = self.ways[index if index > 0 else -index]
            if way['road_type'] != 2:
                continue

            if index > 0: # from node of way
                if way['oneway'] == 1:
                    end.append((way, way['start_bearing']))
                elif way['oneway'] == 2:
                    start.append((way, (way['start_bearing'] + 180) % 360))
            else:         # to node of way
                if way['oneway'] == 1:
                    start.append((way, way['end_bearing']))
                elif way['oneway'] == 2:
                    end.append((way, (way['end_bearing'] + 180) % 360))

        if not start or not end:
            return
        
        for from_way, from_bearing in start:
            for to_way, to_bearing in end:
                _tune_shape(from_way, to_way, (to_bearing + 360 - from_bearing) % 360)

    def __settle_relation(self, relation):
        if relation[2] == 0 or relation[3] == -1:
            return
        
        if relation[0] == 7:
            self.ways[relation[2]]['bipesz'] |= relation[1]
        else:
            self.relations.append(relation)

class WayShape:

    def __init__(self, points, skip_head = False, skip_tail = False):
        # assert len(self.points) >= 2
        self.points = points
        self.__segment_size = len(self.points) - 1

        self.__bearings = []
        self.__lengths = []
        self.length = 0

        for i in range(self.__segment_size):
            pt1 = self.points[i]
            pt2 = self.points[i + 1]
            
            geo = Geodesic.WGS84.Inverse(pt1[0], pt1[1], pt2[0], pt2[1])
            bearing = geo['azi1']
            length = geo['s12']
            self.__bearings.append(bearing if bearing >= 0 else 360 + bearing)
            self.__lengths.append(length)
            self.length += length

        if skip_head:
            while self.__segment_size > 1 and self.__lengths[0] < 25:
                self.__lengths[1] += self.__lengths[0]
                del self.__lengths[0]
                del self.__bearings[0]
                self.__segment_size -= 1

        if skip_tail:
            while self.__segment_size > 1 and self.__lengths[-1] < 25:
                self.__lengths[-2] += self.__lengths[-1]
                del self.__lengths[-1]
                del self.__bearings[-1]
                self.__segment_size -= 1

    def start_bearing(self):
        return round(self.__bearings[0]) % 360

    def end_bearing(self):
        return round(self.__bearings[-1]) % 360
    
    def mid_point(self):
        i = np.argmax(self.__lengths)
        lat = round((self.points[i][0] + self.points[i+1][0]) / 2, 5)
        lon = round((self.points[i][1] + self.points[i+1][1]) / 2, 5)
        return (lat, lon)
        
    def arc(self, i):
        return (self.__lengths[i] + self.__lengths[i + 1]) / 2
    
    def curve(self):
        if (self.__segment_size == 1):
            return (0, 0)
        
        curve_left = 0
        left_length = 0
        curve_right = 0
        right_length = 0
        for i in range(self.__segment_size - 1):
            arc = self.arc(i)
            angle = (self.__bearings[i + 1] + 360 - self.__bearings[i]) % 360

            if angle < 2 or angle > 358:
                right_length += arc / 2
                left_length += arc / 2
            elif angle < 180:
                curve_right += _weighted_curve(_encode_curvature(angle, min(arc, 25)), arc)
                right_length += arc
            else: 
                curve_left += _weighted_curve(_encode_curvature(360 - angle, min(arc, 25)), arc)
                left_length += arc

        # calucated as negative sign
        return (-round(curve_left / left_length) if left_length else 0,
                -round(curve_right / right_length) if right_length else 0)

_restriction = {'2':1, '1':2, '3':3, '4':4, None:5}
_barrier = {'gate':1, 'toll_booth':2}
_additional = {'blackspot':1, 'construction':2, 'no_overtaking':3, 'timed_speed':-1}
_controls = {'stop':2, 'yield':3}
_bipesz = {'school_zone':4, 'pedestrian_crossing':2, 'bicycle_crossing':1, 'yield_to_bicycles': 1}
_signs = {'animal_crossing':1, 'falling_rocks':2, 'congestion_hazard':3, 'accident_hazard':3, 'truck_roll_over': 3,
            'icy_conditions':4, 'slippery_road':4, 'lane_merge_left':5, 'lane_merge_right':5, 'lane_merge_center':5, 
            'road_narrows':5, 'sharp_curve_left':6, 'sharp_curve_right':6, 'general_curve':6, 'lateral_wind':6, 
            'winding_road_starting_left':6, 'winding_road_starting_right':6, 'steep_hill_upwards':7, 
            'steep_hill_downwards':7, 'general_hill':7, }

def _get_divider(tags):
    dividers = tags.get('divider:lanes')
    if dividers == None:
        return 0
    elif '9' in dividers: # physical
        return 1
    elif '7' in dividers: # shaded area
        return 2
    elif '2' in dividers: # double solid line
        return 3
    else:
        return 4

def _get_points(linestr):
    points = []
    for ptstr in linestr[linestr.find("(") + 1 : linestr.find(")")].split(','):
        lat_lon = ptstr.split(' ')
        points.append(tuple([float(lat_lon[1]), float(lat_lon[0])]))
    
    return points

def _set_speed(way, tags):
    way['forward_speed'] = int(tags.get('maxspeed:forward', 0))
    if way['forward_speed'] == 0 and way['oneway'] != 2:
        way['forward_speed'] = -int(float(tags.get('spd_kph:f', 0)) * 0.6214)

    way['backward_speed'] = int(tags.get('maxspeed:backward', 0)) 
    if way['backward_speed'] == 0 and way['oneway'] != 1:
        way['backward_speed'] = -int(float(tags.get('spd_kph:t', 0)) * 0.6214) 

def _set_lane(way, tags):
    way['forward_lane_count'] = int(tags.get('lanes:forward', 0))
    way['backward_lane_count'] = int(tags.get('lanes:backward', 0)) 

    type_lanes = tags.get('type:lanes')
    if type_lanes != None:
        count = 0
        lane_types = type_lanes.split('|')
        for lt in lane_types:
            if lt == '65536': # 65536: Bicycle Lane
                way['bipesz'] |= 1
            else:
                count += 1
        way['lane_count'] = count
    else:
        way['lane_count'] = int(tags.get('lanes', 0))
    
    if way['lane_count'] == 0:
        way['lane_count'] = way['forward_lane_count'] + way['backward_lane_count'] 
        if way['lane_count'] == 0:
            way['lane_count'] = -int(tags.get('lane_cat', 0))

def _encode_curvature(angle, arc):
    '''
    curvature  delta  1 / radius    radius     
        0        1                       
        64       2      0.00064     1562.5      
        128      4      0.00192     520.833     
        192      8      0.00448     223.214     
        256      16     0.00960     104.167     
        320      32     0.01984     50.403      
        384      64     0.04032     24.802      
        448      128    0.08128     12.303      
        512             0.16320     6.127
    '''
    if angle < 1:
        return 0
    
    radius = (360 / angle) * arc / (math.pi * 2)
    curve_num = int(100000 / radius)

    if (curve_num > 16320):
        return 512
    
    delta = 1
    scale = 64
    base = 0
    floor = 0
    for _ in range(8):
        ceil = floor + delta * scale 
        if (curve_num < ceil):
            return int(base + (curve_num - floor) / delta)
        
        floor = ceil
        base += scale
        delta *= 2
    
    return 512

def _weighted_curve(curve, arc):
    # curve / 16 -> 0-32
    return np.power(curve / 16, 1.2) * arc
    
def _weighted_slope(slope, arc):
    # slope / 100 -> 0-25 degree
    return np.power(slope / 100, 1.3) * arc

def _set_curve_slope(way, tags, shape):
    '''
    -9000 < SLOPE < 9000 up   
    0     < CURVE < 1023 left 
    '''
    adas_chs = tags.get('adas:chs')
    if adas_chs != None:
        curve_left = 0
        left_length = 0
        curve_right = 0
        right_length = 0

        slope_up = 0
        up_length = 0
        slope_down = 0
        down_length = 0

        for i, chs in enumerate(adas_chs.split('|')):
            values = chs.split(';')
            arc = shape.arc(i)
            if values[0] != '':
                curve = int(values[0])
                if curve > 511:
                    curve_left += _weighted_curve(curve - 511, arc)
                    left_length += arc
                else:
                    curve_right += _weighted_curve(511 - curve, arc)
                    right_length += arc
            if values[2] != '':
                slope = int(values[2])
                if slope > 0:
                    slope_up += _weighted_slope(slope, arc)
                    up_length += arc
                else:
                    slope_down += _weighted_slope(-slope, arc)
                    down_length += arc

        if left_length or right_length:
            way['curve_left'] = round(curve_left / left_length) if left_length else 0
            way['curve_right'] = round(curve_right / right_length) if right_length else 0
        
        if up_length or down_length:
            way['slope_up'] = round(slope_up / up_length) if up_length else 0
            way['slope_down'] = round(slope_down / down_length) if down_length else 0

    if 'slope_up' not in way: # also 'slope_down' not in way 
        f_node_height = tags.get('f_node_height')
        t_node_height = tags.get('t_node_height')
        if f_node_height and t_node_height:
            slope = np.rad2deg(np.arctan((float(t_node_height) - float(f_node_height)) / shape.length)) * 100
            # calucated as negative sign
            way['slope_up'] = -round(_weighted_slope(slope, shape.length) / shape.length) if slope > 0 else 0
            way['slope_down'] = -round(_weighted_slope(-slope, shape.length) / shape.length) if slope < 0 else 0

    if 'curve_left' not in way: # also 'curve_right' not in way
        # calucated as negative sign
        way['curve_left'], way['curve_right'] = shape.curve()

def _tune_shape(from_way, to_way, bearing_change):
    # find two dual way heading change [200, 260] or angle [20, 80]
    if bearing_change < 200 or bearing_change > 260:
        return
    
    from_shape = WayShape(polyline.decode(from_way['polyline']), from_way['oneway'] == 2, from_way['oneway'] == 1)
    to_shape = WayShape(polyline.decode(to_way['polyline']), to_way['oneway'] == 1, to_way['oneway'] == 2)

    from_bearing = from_shape.end_bearing() if from_way['oneway'] == 1 else (from_shape.start_bearing() + 180) % 360
    to_bearing = to_shape.start_bearing() if to_way['oneway'] == 1 else (to_shape.end_bearing() + 180) % 360
    bearing_skip_change = (to_bearing + 360 - from_bearing) % 360 

    # skip end heading change [160, 200]
    if bearing_skip_change < 200 and bearing_skip_change > 160:
        if from_way['oneway'] == 1:
            from_way['end_bearing'] = -from_shape.end_bearing()
        else:
            from_way['start_bearing'] = -from_shape.start_bearing()

        if to_way['oneway'] == 1:
            to_way['start_bearing'] = -to_shape.start_bearing()
        else:
            to_way['end_bearing'] = -to_shape.end_bearing()

        if from_way['curve_left'] < 0 or from_way['curve_right'] < 0:
            # calucated as negative sign
            from_way['curve_left'], from_way['curve_right'] = from_shape.curve()
        
        if to_way['curve_left'] < 0 or to_way['curve_right'] < 0:
            # calucated as negative sign
            to_way['curve_left'], to_way['curve_right'] = to_shape.curve()

# points = polyline.decode("abkyGntl`KIg@KB") 
# shape = WayShape(points, False, False)
# print(shape.curve())

# way = {}
# tags = {'adas:chs':'313;1;-25|304;6;-40'}
# _set_curve_slope(way, tags, shape)
# print(way)

# way = {}
# tags = {'f_node_height': 506.5, 't_node_height': 497.93}
# _set_curve_slope(way, tags, shape)
# print(way)