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


def get_alarm_data(database):
    """Get raw hits from specified indices in elasticsearch db"""
    es = make_connection(database)
    indices, extra_render_args = _handle_index_gathering(
        es, ES_INSTANCES[database]["index_gatherer"]
    )

    hits = []
    for index in indices:
        page = es.search(index=index, scroll="2m", size=1000)
        sid = page["_scroll_id"]
        scroll_size = len(page["hits"]["hits"])

        while scroll_size > 0:
            hits += page["hits"]["hits"]
            page = es.scroll(scroll_id=sid, scroll="2m")
            sid = page["_scroll_id"]
            scroll_size = len(page["hits"]["hits"])

    return hits, extra_render_args


def _handle_index_gathering(es, gather_cfg):
    try:
        if gather_cfg["type"] == "single_topic":
            indices = list(es.indices.get(index=topic).keys())
            extra_render_args = {}
        elif gather_cfg["type"] == "monthly":
            indices, extra_render_args = _gather_monthly_indices(
                es, gather_cfg["topic"], gather_cfg["max_indices"], gather_cfg["strptime_fmt"]
            )
    except KeyError as e:
        print(
            "Ensure index_gather is correctly configured for given type '{}'".format(
                gather_cfg["type"]
            )
        )
        raise e

    return indices, extra_render_args


def _gather_monthly_indices(es, topic, max_indices, strptime_fmt):
    """Gather indices starting with the most recent"""
    all_indices = list(es.indices.get(index=topic).keys())
    all_indices.sort(key=lambda index: datetime.strptime(index.split(topic[:-1])[1], strptime_fmt))
    selected_indices = all_indices[-max_indices:]

    utc_zone = pytz.timezone("UTC")
    fnal_zone = pytz.timezone("America/Chicago")
    
    extra_render_args = {
        "current_time" : datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "earliest_time" : _convert_timezone(
            datetime.strptime(selected_indices[0].split(topic[:-1])[1], strptime_fmt),
            utc_zone,
            fnal_zone
        ).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    }

    return selected_indices, extra_render_args


# end-----------------------------------------------------------------------------

# SBND slow control alarm specific stuff------------------------------------------

def prep_alarms(hits, source_cols, component_depth):
    """
    Categorise and convert timezone (elasticsearch uses UTC for all times).

    alarms will be a nested dictionary like:
    { system :
        { subsystem :
            { subsubsystem :
                [ { alarm hit dictionary }, ... ]
            }
        }
    }
    component_hierarchy will be a nested dictionary like
    { system : { subsystem : { subsubsystem : None } } }

    Duplicate alarms (same (pv,time,value,message)) are ignored.
    """
    alarms, component_hierarchy = {}, {}
    utc_zone = pytz.timezone("UTC")
    fnal_zone = pytz.timezone("America/Chicago")
    
    seen_hits = set()
    for hit in hits:
        hit_data = { key : hit["_source"][key] for key in source_cols }

        hit_summary = (hit_data["config"], hit_data["time"], hit_data["value"], hit_data["message"])
        if hit_summary not in seen_hits:
            seen_hits.add(hit_summary)
        else:
            continue

        components, pv = _get_pv_categs(hit["_source"]["config"], component_depth)
        hit_data["pv"] = pv
        _convert_timezones(hit_data, utc_zone, fnal_zone)
        _nested_append(alarms, components, hit_data)
        _nested_set(component_hierarchy, components, None)

    return alarms, component_hierarchy


def _get_pv_categs(pv_path, component_depth):
    """Get components of pv path assuming the pv name has a single / in it """
    pv_path = _pv_path_clean(pv_path)
    components = pv_path.split("state:/SBND/")[1].split("/")
    pv = "/".join(components[-2:])
    components = components[:-2]
    while len(components) < component_depth:
        components.append(components[-1])
    return components, pv


def _pv_path_clean(pv_path):
    """May need to be update if new pvs are added"""
    pv_path = pv_path.replace("(Gizmo/GPS)", "(Gizmo or GPS)")
    return pv_path


# end-----------------------------------------------------------------------------

# Utility functions---------------------------------------------------------------

def _convert_timezones(hit_data, original_tz, new_tz):
    for time_key in ["time", "message_time"]:
        if time_key not in hit_data:
            continue
        original_time = datetime.strptime(hit_data[time_key], "%Y-%m-%d %H:%M:%S.%f")
        new_time = _convert_timezone(original_time, original_tz, new_tz)
        hit_data[time_key] = new_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _convert_timezone(original_time, original_tz, new_tz):
    original_time = original_tz.localize(original_time)
    new_time = original_time.astimezone(new_tz)
    return new_time


def _nested_append_unique(d, keys, value, identical_checker):
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    l = d.setdefault(keys[-1], [])
    for other_value in l:
        if identical_checker(value, other_value):
            return
    l.append(value)


def _nested_append(d, keys, value):
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    l = d.setdefault(keys[-1], [])
    l.append(value)


def _nested_set(d, keys, value):
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = value


# end-----------------------------------------------------------------------------

