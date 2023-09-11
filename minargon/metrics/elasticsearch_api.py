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
    print(indices)

    hits = []
    for index in indices:
        try:
            num_hits = es.search(index=index, size=0)["hits"]["total"]["value"]
            res = es.search(index=index, size=num_hits)
        except Exception as e: # XXX Temporary, need to figure out why some shards are corrupted
            continue
        hits += res["hits"]["hits"]

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
        "current_time" : datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
        "earliest_time" : _convert_timezone(
            datetime.strptime(selected_indices[0].split(topic[:-1])[1], strptime_fmt),
            utc_zone,
            fnal_zone
        ).strftime("%Y-%m-%d %H:%M:%S.%f")
    }

    return selected_indices, extra_render_args


# end-----------------------------------------------------------------------------

# slow control alarm specific stuff-----------------------------------------------

def prep_alarms(hits, source_cols):
    """Categorise and convert timezone (elasticsearch uses UTC for all times)"""
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


def _get_pv_categs(pv_path):
    """Get components of pv path assuming the pv name has a single / in it """
    components = pv_path.split("state:/SBND/")[1].split("/")
    pv = "/".join(components[-2:])
    components = components[:-2]
    return components, pv


# end-----------------------------------------------------------------------------

# Utility functions---------------------------------------------------------------

def _convert_timezones(hit_data, original_tz, new_tz):
    for time_key in ["time", "message_time"]:
        if time_key not in hit_data:
            continue
        original_time = datetime.strptime(hit_data[time_key], "%Y-%m-%d %H:%M:%S.%f")
        new_time = _convert_timezone(original_time, original_tz, new_tz)
        hit_data[time_key] = new_time.strftime("%Y-%m-%d %H:%M:%S.%f")


def _convert_timezone(original_time, original_tz, new_tz):
    original_time = original_tz.localize(original_time)
    new_time = original_time.astimezone(new_tz)
    return new_time


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


# end-----------------------------------------------------------------------------

