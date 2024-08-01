import os
import pandas as pd

from way_graph import WayGraph

data_dir = "~/data/HERE-24Q2"
state = 'NV'

graph = WayGraph()

raw_ways = pd.read_csv(os.path.join(data_dir, f"{state}/WAYS"), delimiter='`', header=None)
for index, raw_way in raw_ways.iterrows():
    graph.append_way(raw_way)
    if index % 100000 == 0:
        print(f"parsed {index} raw ways")

raw_relations = pd.read_csv(os.path.join(data_dir, f"{state}/RELATIONS"), delimiter='`', header=None)
for index, raw_relation in raw_relations.iterrows():
    graph.append_relation(raw_relation)
    if index % 200000 == 0:
        print(f"parsed {index} raw relations")

raw_members = pd.read_csv(os.path.join(data_dir, f"{state}/RELATION_MEMBERS"), delimiter='`', header=None)
for index, raw_member in raw_members.iterrows():
    graph.add_relation_member(raw_member)
    if index % 500000 == 0:
        print(f"parsed {index} raw relation members")

graph.complete()

ways = pd.DataFrame(graph.ways, columns=['way_id', 'length', 'oneway', 'road_class', 'road_type', 'divider', 'urban', 'bipesz',
                             'lane_count', 'forward_lane_count', 'backward_lane_count', 'forward_speed', 'backward_speed',
                             'start_bearing', 'end_bearing', 'curve_left', 'curve_right', 'slope_up', 'slope_down', 
                              'from_node', 'to_node'], dtype=int) 
polylines = pd.DataFrame(graph.ways, columns=['polyline'])
nodes = pd.DataFrame(graph.nodes, columns=['node_id', 'ways'])
relations = pd.DataFrame(graph.relations, columns=['type', 'value', 'from_way', 'via_node', 'to_way'])

print(f"non road way {graph.non_road_way}; ignored leaf way {graph.ignored_road_way};") 
print(f"built {ways.shape[0]} ways, {nodes.shape[0]} nodes, {relations.shape[0]} relations")

output_dir = "~/data/GNN"

ways.to_csv(os.path.join(output_dir, f"{state}/WAYS.csv"), index=False)
polylines.to_csv(os.path.join(output_dir, f"{state}/POLYLINES.csv"), index=False)
nodes.to_csv(os.path.join(output_dir, f"{state}/NODES.csv"), index=False)
relations.to_csv(os.path.join(output_dir, f"{state}/RELATIONS.csv"), index=False)
