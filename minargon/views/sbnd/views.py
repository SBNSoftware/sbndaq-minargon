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
from minargon.metrics import postgres_api
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
        'extension': ''
    }
    return render_template('sbnd/channel_snapshot.html', **template_args)

@app.route('/channel_snapshot_dab')
def channel_snapshot_dab():
    channel = request.args.get('channel', 0, type=int)

    view_ind = {'channel': channel}
    view_ind_opts = {'channel': list(range(constants.N_CHANNELS))}

    instance_name = "tpc_channel_dab"
    config = online_metrics.get_group_config("online", instance_name, front_end_abort=True)

    template_args = {
        'channel': channel,
        'config': config,
        'view_ind': view_ind,
        'view_ind_opts': view_ind_opts,
        'extension': '_dab',
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
    return timeseries_view(request.args, instance_name, "wire", "wireLinkDAB", "eventmeta_dab")

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

