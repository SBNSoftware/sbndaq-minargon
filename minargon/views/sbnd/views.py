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
from minargon.metrics import postgres_api, elasticsearch_api
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
@app.route('/CRT_board')
def CRT_board():
    return timeseries_view(request.args, "CRT_board", "", "crtBoardLink")

@app.route('/CRT_channel')
def CRT_channel():
    return timeseries_view(request.args, "CRT_channel", "", "crtChannelLink")

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

@app.route('/LLT_rates')
def LLT_rates():
    return "LLT_rates"

@app.route('/HLT_rates')
def HLT_rates():
    return "HLT_rates"

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

