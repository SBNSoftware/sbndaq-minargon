from __future__ import absolute_import
from minargon import app
from flask import render_template, jsonify, request, redirect, url_for, flash, abort
import time
from os.path import join
import simplejson as json
import os
import sys
import random
from . import constants
import sys
from minargon.metrics import postgres_api, elasticsearch_api, ignition_api
from minargon.views.common.views import timeseries_view
import subprocess
import re

from minargon.tools import parseiso
# from minargon.data_config import parse
from minargon.metrics import online_metrics
from six.moves import range

@app.route('/introduction')
def introduction():
    return render_template('sbnd/introduction.html')

@app.route('/TPC_status')
def TPC_status():
    crts = [79,80]

    render_args = {
      "crts": crts,
      "eventmeta_key": False, # TODO
    }

    return render_template('sbnd/tpc_status.html', **render_args) 


# snapshot of noise (currently just correlation matrix)
@app.route('/noise_snapshot')
def noise_snapshot():
    template_args = {
        'n_channels': constants.N_CHANNELS
    }
    return render_template('sbnd/noise_snapshot.html', **template_args)



# snapshot of data on channel (fft and waveform)
@app.route('/fem_snapshot')
def fem_snapshot():
    fem = request.args.get('fem', 0, type=int)

    view_ind = {'fem': fem}
    view_ind_opts = {'fem': list(range(constants.N_FEM))}

    template_args = {
        'fem': fem,
        'view_ind_opts': view_ind_opts,
        'view_ind': view_ind,
    }
    return render_template('sbnd/fem_snapshot.html', **template_args)

# snapshot of data on channel (fft and waveform)
@app.route('/channel_snapshot')
def channel_snapshot():
    channel = request.args.get('channel', 0, type=int)

    view_ind = {'channel': channel}
    view_ind_opts = {'channel': list(range(constants.N_CHANNELS))}

    instance_name = "tpc_channel"
    config = online_metrics.get_group_config("online", instance_name, front_end_abort=True)

    template_args = {
        'channel': channel,
        'config': config,
        'view_ind': view_ind,
        'view_ind_opts': view_ind_opts,
        'extension': '',
        'dbname': "online",
    }
    return render_template('sbnd/channel_snapshot.html', **template_args)

@app.route('/channel_snapshot_dab')
def channel_snapshot_dab():
    channel = request.args.get('channel', 0, type=int)

    view_ind = {'channel': channel}
    view_ind_opts = {'channel': list(range(constants.N_CHANNELS))}

    instance_name = "tpc_channel_dab"
    config = online_metrics.get_group_config("onlineDAB", instance_name, front_end_abort=True)

    template_args = {
        'channel': channel,
        'config': config,
        'view_ind': view_ind,
        'view_ind_opts': view_ind_opts,
        'extension': '_dab',
        'dbname': "onlineDAB",
    }
    return render_template('sbnd/channel_snapshot.html', **template_args)

# view of a number of wires on a wireplane
@app.route('/wireplane_view')
def wireplane_view():
    instance_name = "tpc_channel" 
    return timeseries_view(request.args, instance_name, "wire", "wireLink", "eventmeta")

# view of a number of wires on a wireplane
@app.route('/wireplane_view_dab')
def wireplane_view_dab():
    instance_name = "tpc_channel_dab" 
    return timeseries_view(request.args, instance_name, "wire", "wireLinkDAB", "eventmeta_dab", db="onlineDAB")

# CRT
@app.route('/CRT_status')
def CRT_status():
    crts = [79,80]

    render_args = {
      "crts": crts,
      "eventmeta_key": False, # TODO
    }

    return render_template('sbnd/crt_status.html', **render_args) 

@app.route('/CRT_board')
def CRT_board():
    return timeseries_view(request.args, "CRT_board", "", "crtBoardLink")

@app.route('/CRT_board_snapshot')
def CRT_board_snapshot():
    board_no = int(request.args.get("board_no", 0))
    # get the config for this group from redis
    config_board = online_metrics.get_group_config("online", "CRT_board", front_end_abort=True)
    config_channel = online_metrics.get_group_config("online", "CRT_channel", front_end_abort=True)

    view_ind = {'board_no': board_no}
    view_ind_opts = {'board_no': list(range(20))}

    # TODO: implement real channel mapping
    board_channels = list(range(board_no*32, (board_no+1)*32))

    template_args = {
        'title': ("CRT Board %i Snapshot" % board_no),
        'board_config': config_board,
        'channel_config': config_channel,
        'board_no': board_no,
        'view_ind': view_ind,
        'view_ind_opts': view_ind_opts,
        'board_channels': board_channels
    }

    return render_template("sbnd/crt_board_snapshot.html", **template_args)

@app.route('/CRT_channel')
def CRT_channel():
    return timeseries_view(request.args, "CRT_channel", "", "crtChannelLink")
    # return timeseries_view(request.args, "CRT_channel", "")

@app.route('/CRT_channel_snapshot')
def CRT_channel_snapshot():
    channel_no = int(request.args.get("channel_no", 0))
    config_channel = online_metrics.get_group_config("online", "CRT_channel", front_end_abort=True)

    view_ind = {'channel_no': channel_no}
    view_ind_opts = {'channel_no': list(range(20))}

    template_args = {
        'title': ("CRT channel %i Snapshot" % channel_no),
        'channel_config': config_channel,
        'channel_no': channel_no,
        'view_ind': view_ind,
        'view_ind_opts': view_ind_opts,
    }

    return render_template("sbnd/crt_channel_snapshot.html", **template_args)

# PMTs
@app.route('/PMT_status')
def PMT_status():
    crts = [79,80]

    render_args = {
      "crts": crts,
      "eventmeta_key": False, # TODO
    }

    return render_template('sbnd/pmt_status.html', **render_args) 


@app.route('/PMT')
@app.route('/PMT/<hw_selector:hw_select>')
@app.route('/PMT/<PMTLOC>')
def PMT(hw_select=None, PMTLOC=None):
    if PMTLOC:
        hw_select = hardwaredb.HWSelector("pmt_placements", ["pmt_in_tpc_plane"], [PMTLOC])
   
    print(hw_select)
    args = dict(**request.args)
    args["data"] = "rms"
    args["stream"] = "fast"
    return timeseries_view(args, "PMT", "", "pmtLink", hw_select=hw_select)

@app.route('/PMT_snapshot')
def PMT_snapshot():
    channel = request.args.get("PMT", 0, type=int)
    group_name = "PMT"
    # TODO: fix hardcode
    pmt_range = list(range(360))
    config = online_metrics.get_group_config("online", group_name, front_end_abort=True)

    template_args = {
      "channel": channel,
      "config": config,
      "pmt_range": pmt_range,
      "view_ind": {"PMT": channel},
      "view_ind_opts": {"PMT": pmt_range},
    }
    return render_template("sbnd/pmt_snapshot.html", **template_args)

# Penn Trigger Board
@app.route('/PTB_status')
def PTB_status():
    crts = [79,80]

    render_args = {
      "crts": crts,
      "eventmeta_key": False, # TODO
    }

    return render_template('sbnd/trigger_status.html', **render_args) 


# @app.route('/LLT_rates')
# def LLT_rates():
#     args = dict(**request.args)
#     # args["data"] = "LLT_rate"
#     # args["stream"] = "fast"
#     # print("args")
#     return timeseries_view(request.args, "LLT_ID", "", "ptbLltLink")


@app.route('/LLT_rates')
def LLT_rates():
    initial_datum = "LLT_rate"
    instance_name = "LLT_ID"
    view_ident = ""
    link_function = "ptbLltLink"
    eventmeta_key = None
    hw_select = None
    db = "online"
    
    # get the config for this group from redis
    config = online_metrics.get_group_config(db, instance_name, front_end_abort=True)

    channels = "undefined"
    channel_map = "undefined"

    title = instance_name

    if hw_select is None:
        hw_select = "undefined"
    else:
        title = ("%s %s -- " % ("-".join(hw_select.columns), "-".join(hw_select.values))) + title
        hw_select = hw_select.to_url()

    render_args = {
        'title': "LLT Test",
        'link_function': link_function,
        'view_ident': view_ident,
        'config': config,
        'metric': initial_datum,
        'eventmeta_key': eventmeta_key,
        'channels': channels,
        'hw_select': hw_select,
        'channel_map': channel_map,
        'dbname': db
    }
    return render_template('sbnd/llt.html', **render_args)

@app.route('/HLT_rates')
def HLT_rates():
    return timeseries_view(request.args, "HLT_ID", "", "ptbHltLink")

#TODO: group the LLT_TDCs together?
@app.route('/LLT27_TDC_1')
def LLT27_TDC_1():
    render_args = {
        "stream_name": 'LLT27_TDC_1',
    }
    return render_template('common/single_stream.html', **render_args) 

@app.route('/LLT28_TDC_2')
def LLT28_TDC_2():
    render_args = {
        "stream_name": 'LLT28_TDC_2',
    }
    return render_template('common/single_stream.html', **render_args) 

@app.route('/HLT_TDC_4')
def HLT_TDC_4():
    render_args = {
        "stream_name": 'HLT_TDC_4',
    }
    return render_template('common/single_stream.html', **render_args) 

@app.route('/HLT_TDC_5')
def HLT_TDC_5():
    render_args = {
        "stream_name": 'HLT_TDC_5',
    }
    return render_template('common/single_stream.html', **render_args) 

@app.route('/HLT_diff_TDC_channel_4')
def HLT_diff_TDC_channel_4():
    render_args = {
        "stream_name": 'HLT_-_TDC_channel_4',
    }
    return render_template('common/single_stream.html', **render_args) 

@app.route('/HLT_diff_TDC_flash')
def HLT_diff_TDC_flash():
    render_args = {
        "stream_name": 'HLT_-_TDC_flash',
    }
    return render_template('common/single_stream.html', **render_args) 

@app.route('/PTB_snapshot')
def PTB_snapshot():
    trigger_no = int(request.args.get("trigger_no", 0))
    config_trigger = online_metrics.get_group_config("online", "CRT_trigger", front_end_abort=True)

    view_ind = {'trigger_no': trigger_no}
    view_ind_opts = {'trigger_no': list(range(32))}

    template_args = {
        'title': ("PTB trigger %i Snapshot" % trigger_no),
        'trigger_config': config_trigger,
        'trigger_no': trigger_no,
        'view_ind': view_ind,
        'view_ind_opts': view_ind_opts,
    }

    return render_template("sbnd/ptb_snapshot.html", **template_args)

@app.route('/PTB_TDC_diff')
def PTB_TDC_diff():
    return "PTB_TDC_diff"

@app.route('/MSUM_snapshot')
def MSUM_snapshot():
    channel = request.args.get("MSUM", 3, type=int)
    group_name = "MSUM"
    # TODO: fix hardcode
    msum_range = list(range(10))
    config = online_metrics.get_group_config("online", group_name, front_end_abort=True)

    template_args = {
      "channel": channel,
      "config": config,
      "msum_range": msum_range,
      "view_ind": {"MSUM": channel},
      "view_ind_opts": {"MSUM": msum_range},
    }
    return render_template("sbnd/msum_snapshot.html", **template_args)


@app.route('/purity')
def purity():
    config = online_metrics.get_group_config("online", "TPC", front_end_abort=True)

    render_args = {
      'config': config
    }

    return render_template('sbnd/purity.html', **render_args)

@app.route('/Impedence_Ground_Monitor')
def Impedence_Ground_Monitor():
    database = "sbnd_epics"
    IDs = [1, 3, 4, 5] 

    configs = {}
    for i in IDs:
      configs[i] = postgres_api.pv_meta_internal(database, i, front_end_abort=True)

    render_args = {
      "configs": configs,
      "database": database
    }
    return render_template('sbnd/impedence_ground_monitor.html', **render_args)

@app.route('/Impedence_Ground_Monitor_CSU')
def Impedence_Ground_Monitor_CSU():
    database = "csu_epics"
    IDs = [1, 3, 4, 5] 

    configs = {}
    for i in IDs:
      configs[i] = postgres_api.pv_meta_internal(database, i, front_end_abort=True)

    render_args = {
      "configs": configs,
      "database": database
    }
    return render_template('sbnd/impedence_ground_monitor.html', **render_args)

@app.route('/DAB_Impedence_Ground_Monitor')
def DAB_Impedence_Ground_Monitor():
    database = "sbn_epics"
    # IDs = [7, 5, 8, 9] 
    IDs = [23218, 23216, 23219, 23220]

    configs = {}
    for i in IDs:
      configs[i] = postgres_api.pv_meta_internal(database, i, front_end_abort=True)

    render_args = {
      "configs": configs,
      "database": database
    }
    return render_template('sbnd/dab_impedence_ground_monitor.html', **render_args)

@app.route('/Slow_Control_Alarms')
def es_alarms():
    database = "sbnd_alarm_logger"
    source_cols = [ "message_time", "time", "value", "message", "severity", "config" ]
    component_depth = 3

    alarm_hits, extra_render_args = elasticsearch_api.get_alarm_data(database)
    alarms, component_hierarchy = elasticsearch_api.prep_alarms(
        alarm_hits, source_cols, component_depth
    )

    render_args = {
        "alarms" : alarms, "components" : component_hierarchy
    }
    render_args.update(extra_render_args)

    return render_template('sbnd/es_alarms.html', **render_args)

@app.route('/cryo_monitor')
def cryo_monitor():
    database = "sbnd_ignition"
    pv_lists = {"east_apa": ["te-8101a", "te-8106a"],
		"west_apa": ["te-8107a", "te-8112a"],
		"cryo_wall": ["te-8035a"],
		"cryo_bottom": ["te-8062a", "te-8022a"],
		"cryo_top": ["te-8003a"]}
    dbrows = []
    for k in pv_lists.keys():
        this_list = pv_lists[k]
        for pv in this_list:
            this_dbrow = ignition_api.get_ignition_last_value_pv(database, "01", "", pv)
            dbrows = dbrows + this_dbrow
    print(dbrows)
    return render_template('sbnd/cryo_monitor.html', rows = dbrows)

    # try:
    #     return render_template('sbnd/cryo_monitor.html', row = dbrows)
    # except jinja2.exceptions.TemplateNotFound:
    #     abort(404)

