from datetime import datetime
import pytz

from elasticsearch import Elasticsearch
from flask import jsonify, json

from minargon import app

ES_INSTANCES = app.config["ELASTICSEARCH_INSTANCES"]


def make_connection(database):
    config = ES_INSTANCES[database]
    host, port = str(config["host"]), str(config["port"])
    es = Elasticsearch(hosts="http://" + host + ":" + port)

    return es


def get_alarm_data(es, topic):
    indices = list(es.indices.get(index=topic).keys()) # can raise elasticsearch.NotFoundError

    pvs_alarms = {}
    for index in indices:
        # can raise elasticsearch.ApiError: ApiError(503, 'search_phase_execution_exception', None)
        num_hits = es.search(index=index, size=0)["hits"]["total"]["value"]
        # res is elastic_transport.ObjectApiResponse.
        # res.body for python dict, res.meta for metadata
        res = es.search(index=index, size=num_hits)
        hits = res["hits"]["hits"]

    return hits


# ----------slow control alarms specific stuff------------------------------------

def prep_alarms(hits, source_cols):
    """Categorise and convert timezone"""
    alarms, component_hierarchy = {}, {}
    utc_zone = pytz.timezone("UTC")
    fnal_zone = pytz.timezone("America/Chicago")

    for hit in hits:
        hit_data = { key : hit["_source"][key] for key in source_cols }
        components, pv = _get_pv_categs(hit["_source"]["config"])
        hit_data["pv"] = pv
        _convert_timezones(hit_data, utc_zone, fnal_zone)
        _nested_append(alarms, components, hit_data)
        _nested_set(component_hierarchy, components, None)

    return alarms, component_hierarchy


# def _get_nested_keys(nested_dict):
#     def replace_nested_vals(d_nested, replacement):
#         for key, val in d_nested.items():
#             if isinstance(val, dict):
#                 replace_nested_vals(val, replacement)
#             else:
#                 d_nested[key] = replacement
# 
#     import copy
#     nested_dict = copy.deepcopy(nested_dict)
#     replace_nested_vals(nested_dict, None)
#     return nested_dict


def _convert_timezones(hit_data, original_tz, new_tz):
    for time_key in ["time", "message_time"]:
        if time_key not in hit_data:
            continue
        original_time = datetime.strptime(hit_data[time_key], "%Y-%m-%d %H:%M:%S.%f")
        original_time = original_tz.localize(original_time)
        new_time = original_time.astimezone(new_tz)
        hit_data[time_key] = new_time.strftime("%Y-%m-%d %H:%M:%S.%f")


def _nested_append(d, keys, value):
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    l = d.setdefault(keys[-1], [])
    l.append(value)


def _nested_set(d, keys, value):
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


def _get_pv_categs(pv_path):
    """Get components of pv path assuming the pv name has a single / in it """
    components = pv_path.split("state:/SBND/")[1].split("/")
    pv = "/".join(components[-2:])
    components = components[:-2]
    return components, pv
        

def _pack_alarm_data(es_res, pvs_alarms, source_cols):
    for hit in es_res["hits"]["hits"]:
        hit_data = { key : hit["_source"][key] for key in source_cols }

        pv_alarms = pvs_alarms.get(hit["_source"]["config"])
        if pv_alarms is None:
            pvs_alarms[hit["_source"]["config"]] = [ hit_data ]
        else:
            pv_alarms.append(hit_data)

