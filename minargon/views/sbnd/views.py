from __future__ import absolute_import
from minargon import app
from flask import render_template, jsonify, request, redirect, url_for, flash, abort
import time
from datetime import datetime
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

#Alarm limits
DRIFTHV_ALARM_LIMITS = {"scheme": [-1, 2], 
                "vsp": [-0.05, 25.05], 
                "vmon": [0., 25.25], 
                "isp": [0, 25], 
                "imon": [0, 25]}
CRT_BASELINE_ALARM_MIN = 20
CRT_BASELINE_ALARM_MAX = 330

@app.route('/introduction')
def introduction():
    # drift hv
    database = "sbnd_ignition"
    pv_lists = ["scheme", "vsp", "vmon", "isp", "imon"] 
    current_time = datetime.now()
    this_month = current_time.month
    month_2digit = str(this_month).zfill(2)
    bad_drifthv_pvs = []
    for idx_pv, pv in enumerate(pv_lists):
        this_dbrow = ignition_api.get_ignition_last_value_pv(database, month_2digit, "drifthv", pv)
        if (float(this_dbrow[0][1]) > DRIFTHV_ALARM_LIMITS[pv][0]) & (float(this_dbrow[0][1]) < DRIFTHV_ALARM_LIMITS[pv][1]):
            continue
        bad_drifthv_pvs.append(pv)

    config = online_metrics.get_group_config("online", "CRT_board", front_end_abort=True)
    #crts = config['instances'] #crt board list from fcl file

    crt_maps = {
        "flat east": [82, 86, 90, 91, 99, 100],
        "flat north":  [93, 94, 95, 87, 97, 98, 77, 78],
        "flat southwest": [83, 84, 104, 103, 102, 101],
        "east wall northtop": [160, 222, 220, 81, 85, 143, 162, 133, 132],
        "east wall southbottom": [44, 147, 146, 131, 79, 206, 204, 200, 18],
        "north wall east":  [88, 152, 156, 153, 159, 134, 135, 238, 155],
        "north wall west": [151, 150, 136, 157, 158, 182, 149, 73, 181]
    }

    crts = crt_maps.keys() #crt refers to a WALL
    channels = [crt_maps[k] for k in crts]

    render_args = {
      "config": config,
      "channels": channels, #channels mean BOARD here
      "crts": crts,
      "baseline_min": CRT_BASELINE_ALARM_MIN,
      "baseline_max": CRT_BASELINE_ALARM_MAX,
      "eventmeta_key": False, #Art Event metadata
      "bad_drifthv_pvs": bad_drifthv_pvs
    }

    return render_template('sbnd/introduction.html', **render_args)

@app.route('/TPC_status')
def TPC_status():
    crts = [79,80]
    render_args = {
      "crts": crts,
      "eventmeta_key": False, # TODO
    }
    return render_template('sbnd/tpc_status.html', **render_args) 

@app.route('/TPC_rms_per_plane')
def TPC_rms_per_plane():
    group_name = "tpc_channel"
    config = online_metrics.get_group_config("online", group_name, front_end_abort=True)

    #tpc_planes = [hardwaredb.HWSelector("tpc_plane", ["tpc", "plane"], p) for p in tpc_planes]
    #channels = [hardwaredb.select(tpc_plane) for tpc_plane in tpc_planes]
    #tpc_plane_flanges = [hardwaredb.HWSelector("tpc_plane_flanges", ["tpc", "plane"], p.values) for p in tpc_planes]
    #flange_names = [["Flange: %s" % f for f in hardwaredb.channel_map(hw, channels)] for hw in tpc_plane_flanges]
    #titles = ["TPC %s-%s" % (hw.values[0], hw.values[1]) for hw in tpc_planes]

    tpc_planes = ["West-U", "West-V", "West-Y", "East-U", "East-V", "East-Y"]
    channels = [list(range(5632, 7616)),
                list(range(7616, 9600)),
                list(range(9600, 11264)),
                list(range(0, 1984)),
                list(range(1984, 3968)),
                list(range(3968, 5632))]
    titles = ["West U", "West V", "West Y", "East U", "East V", "East Y"]

    render_args = {
      "config": config,
      "channels": channels,
      "metric": "rms",
      "titles": titles,
      "tpc_planes": tpc_planes,
      "eventmeta_key": "eventmeta",
    }
    return render_template('sbnd/tpc_rms_per_plane.html', **render_args)

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
    config = online_metrics.get_group_config("online", "CRT_board", front_end_abort=True)
    #crts = config['instances'] #crt board list from fcl file

    crt_maps = {
        "flat east": [82, 86, 90, 91, 99, 100],
        "flat north":  [93, 94, 95, 87, 97, 98, 77, 78],
        "flat southwest": [83, 84, 104, 103, 102, 101],
        "east wall northtop": [160, 222, 220, 81, 85, 143, 162, 133, 132],
        "east wall southbottom": [44, 147, 146, 131, 79, 206, 204, 200, 18],
        "north wall east":  [88, 152, 156, 153, 159, 134, 135, 238, 155],
        "north wall west": [151, 150, 136, 157, 158, 182, 149, 73, 181]
    }

    crts = crt_maps.keys() #crt refers to a WALL
    channels = [crt_maps[k] for k in crts]

    render_args = {
      "config": config,
      "channels": channels, #channels mean BOARD here
      "crts": crts,
      "baseline_min": CRT_BASELINE_ALARM_MIN,
      "baseline_max": CRT_BASELINE_ALARM_MAX,
      "eventmeta_key": False, #Art Event metadata
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

@app.route('/Timing')
def Timing():
    return timeseries_view(request.args, "SPECTDC_Streams_Timing")


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
    print("render_args", render_args)
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
    current_time = datetime.now()
    this_month = current_time.month
    current_timestamp = time.mktime(current_time.timetuple())
    month_2digit = str(this_month).zfill(2)
    print(month_2digit)
    for k in pv_lists.keys():
        this_list = pv_lists[k]
        for pv in this_list:
            this_dbrow = ignition_api.get_ignition_last_value_pv(database, month_2digit, "", pv)
            try:
                formatted_time = datetime.fromtimestamp(this_dbrow[0][2]/1000) # ms since epoch
                formatted_time = datetime.strftime(formatted_time, "%Y-%m-%d %H:%M")
            except:
                formatted_time = this_dbrow[0][2]
            timestamp_diff = current_timestamp*1000 - this_dbrow[0][2]
            alarm_time = 180
            this_dbrow = [(this_dbrow[0][0], this_dbrow[0][1], formatted_time, alarm_time, timestamp_diff/1000)]
            dbrows = dbrows + this_dbrow
    print(dbrows)
    return render_template('sbnd/cryo_monitor.html', rows = dbrows)

    # try:
    #     return render_template('sbnd/cryo_monitor.html', row = dbrows)
    # except jinja2.exceptions.TemplateNotFound:
    #     abort(404)

@app.route('/ping_ignition')
def ping_ignition():
    database = "sbnd_ignition"
    pv = "te-8101a"
    current_time = datetime.now()
    this_month = current_time.month
    month_2digit = str(this_month).zfill(2)
    tstamp = 0
    this_dbrow = ignition_api.get_ignition_last_value_pv(database, month_2digit, "", pv)
    tstamp = this_dbrow[0][2]
    pong = False
    if (tstamp > 0):
        pong = True
    return jsonify(str(pong))

# @app.route('/cryo_stream')
# def cryo_stream():
@app.route('/cryo_stream/<pv>')
def cryo_stream(pv):
    # Get the list of IDs for the var name
#    IDs = postgres_api.pv_internal(database, ret_id=var, front_end_abort=True)
#
#    # get the configs for each ID
#    configs, starts, ends, toggles, downloads = [], [], [], [], []
#    for ID in IDs:
#        configs.append(postgres_api.pv_meta_internal(database, ID, front_end_abort=True))
#        starts.append("start-"+str(ID))
#        ends.append("end-"+str(ID))
#        toggles.append("toggle-"+str(ID))
#        downloads.append("download-"+str(ID))
#
#    # print config
    database = "sbnd_ignition"
    month = "02"
    # render_args = {
    #   "pv": pv, 
#      "IDs": IDs,
#      "configs": configs,
#      "starts" : starts,
#      "ends" : ends,
#      "toggles" : toggles,
#      "downloads" : downloads,
#      "database": database
    # }
    # return render_template('common/cryo_stream.html', **render_args)
    configs = ignition_api.cryo_pv_meta_internal("sbnd_ignition", pv)
    print(configs)

    render_args = {
      "configs": configs,
      "database": database,
      "month": month,
      "pv": pv
    }
    return render_template('sbnd/cryo_stream.html', **render_args)

@app.route('/DriftHV_Heinzinger')
def DriftHV_Heinzinger():
    database = "sbnd_ignition"
    pv_lists = ["scheme", "vsp", "vmon", "isp", "imon"] 
    configs = {}
    for pv in pv_lists:
        configs[pv] = {'unit': '', 'yTitle':'', 'title':'', 'warningRange': DRIFTHV_ALARM_LIMITS[pv]}

    dbrows = []
    current_time = datetime.now()
    this_month = current_time.month
    current_timestamp = time.mktime(current_time.timetuple())
    month_2digit = str(this_month).zfill(2)
    for pv in pv_lists:
        this_dbrow = ignition_api.get_ignition_last_value_pv(database, month_2digit, "drifthv", pv)
        try:
            formatted_time = datetime.fromtimestamp(this_dbrow[0][2]/1000) # ms since epoch
            formatted_time = datetime.strftime(formatted_time, "%Y-%m-%d %H:%M")
        except:
            formatted_time = this_dbrow[0][2]
        timestamp_diff = current_timestamp*1000 - this_dbrow[0][2]
        alarm_time = 180
        status = 0
        if (float(this_dbrow[0][1]) > DRIFTHV_ALARM_LIMITS[pv][0]) & (float(this_dbrow[0][1]) < DRIFTHV_ALARM_LIMITS[pv][1]):
            status = 1
        this_dbrow = [(pv, this_dbrow[0][1], formatted_time, status, alarm_time, timestamp_diff/1000)]
        dbrows = dbrows + this_dbrow

    render_args = {
      "rows": dbrows,
      "configs": configs,
      "database": database,
      "pv": pv_lists,
      "alarm_limits": DRIFTHV_ALARM_LIMITS
    }
    print("render_args", render_args)
    return render_template('sbnd/drifthv_heinzinger.html', **render_args)

