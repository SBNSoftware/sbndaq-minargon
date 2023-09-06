from elasticsearch import Elasticsearch
from flask import jsonify, json

from minargon import app

ES_INSTANCES = app.config["ELASTICSEARCH_INSTANCES"]


def make_connection(database):
    config = ES_INSTANCES[database]
    host, port = str(config["host"]), str(config["port"])
    es = Elasticsearch(hosts="http://" + host + ":" + port)

    return es


def get_alarm_data(es, topic, source_cols):
    indices = list(es.indices.get(index=topic).keys()) # can raise elasticsearch.NotFoundError

    pvs_alarms = {}
    for index in indices:
        # can raise elasticsearch.ApiError: ApiError(503, 'search_phase_execution_exception', None)
        num_hits = es.search(index=index, size=0)["hits"]["total"]["value"]
        # res is elastic_transport.ObjectApiResponse.
        # res.body for python dict, res.meta for metadata
        res = es.search(index=index, size=num_hits)
        _pack_alarm_data(res, pvs_alarms, source_cols)

    # return json.dumps(pvs_alarms, indent=2)
    return pvs_alarms
        
def _pack_alarm_data(es_res, pvs_alarms, source_cols):
    for hit in es_res["hits"]["hits"]:
        hit_data = { key : hit["_source"][key] for key in source_cols }

        pv_alarms = pvs_alarms.get(hit["_source"]["config"])
        if pv_alarms is None:
            pvs_alarms[hit["_source"]["config"]] = [ hit_data ]
        else:
            pv_alarms.append(hit_data)

