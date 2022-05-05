from __future__ import absolute_import
from minargon import app
from flask import render_template, jsonify, request, redirect, url_for, flash
import simplejson as json
from minargon.metrics import postgres_api

from minargon.tools import parseiso
from minargon.metrics import online_metrics
from minargon.views.common.views import timeseries_view

from minargon import hardwaredb

# load template injectors
from . import inject
from six.moves import range
from six.moves import zip

TPC_RMS_ALARM_MIN = 1.5
TPC_RMS_ALARM_MAX = 20.

PMT_RMS_ALARM_MIN = 0.5
PMT_RMS_ALARM_MAX = 7.

PMT_BASELINE_ALARM_MIN = 14500
PMT_BASELINE_ALARM_MAX = 15500

@app.route('/test/<int:chan>')
def test(chan):
    channels =  hardwaredb.icarus_tpc.tpc_channel_list("readout_board_id", str(chan))
    return str(channels)

@app.route('/TPC_Flange_Overview/<TPC>')
def TPC_Flange_Overview(TPC):
    flanges = hardwaredb.select(hardwaredb.HWSelector("flanges_flanges", ["tpc_id"], [TPC]))
    return flange_page(flanges)

@app.route('/Flange_Overview')
def Flange_Overview():
    flanges = ["WE05", "WE06", "WE07", "WE09", "WE18", "WE19"]
    return flange_page(flanges)

def flange_page(flanges):
    group_name = "tpc_channel"

    config = online_metrics.get_group_config("online", group_name, front_end_abort=True)

    # turn the flange positions to hw_selects
    hw_selects = [hardwaredb.HWSelector("flanges", ["flange_pos_at_chimney"], [f]) for f in flanges]

    channels = [hardwaredb.select(hw_select) for hw_select in hw_selects]
    channel_map = [hardwaredb.channel_map(hw_select, c) for hw_select,c in zip(hw_selects, channels)]

    # setup the plot titles
    titles = ["flange_pos_at_chimney %s -- tpc_channel" % f for f in flanges]
     
    render_args = {
      "config": config,
      "channels": channels,
      "channel_maps": channel_map,
      "flanges": flanges,
      "metric": "rms",
      "titles": titles,
      "hw_selects": [h for h in hw_selects],
      "eventmeta_key": "eventmetaTPC",
    }

    return render_template('icarus/flange_overview.html', **render_args)

@app.route('/CRT_status')
def CRT_status():
    crts = [hw for _,hw in hardwaredb.icarus.crt.CRTLOCs()]
    channels = [hardwaredb.select(crt) for crt in crts]
    config = online_metrics.get_group_config("online", "CRT_board", front_end_abort=True)

    #print(channels)
    render_args = {
      "config": config,
      "channels": channels,
      "crts": crts,
      "baseline_min": 20,
      "baseline_max": 400,
      "eventmeta_key": False, # TODO
    }

    return render_template('icarus/crt_status_overview.html', **render_args) 

@app.route('/introduction')
def introduction():
    pmt_config = online_metrics.get_group_config("online", "PMT", front_end_abort=True)
    pmts = [hw for _,hw in hardwaredb.icarus.pmt.PMTLOCs()]
    pmt_channels = [hardwaredb.select(pmt) for pmt in pmts]

    # filter out disconnected channels
    disconnected_pmt_channels = [15, 63, 111, 207, 255, 303, 351]
    for i in range(len(pmt_channels)):
      dc = [channel for channel in pmt_channels[i] if channel in disconnected_pmt_channels]
      for j in dc:
        pmt_channels[i].remove(j)

    tpc_config = online_metrics.get_group_config("online", "tpc_channel", front_end_abort=True)
    allflanges = hardwaredb.icarus.tpc.TPCFlanges()
    # TODO: these should be in a database. But for now, hard-code the bad flanges
    badflanges = ["WW01B", "EW20T"]
    flanges = [f for f in allflanges if f.values[0] not in badflanges]
    tpc_channels = [hardwaredb.select(tpc_flange.where("channel_type", "wired")) for tpc_flange in flanges]

    render_args = {
      "tpc_config": tpc_config,
      "tpc_channels": tpc_channels,
      "tpc_rms_min": TPC_RMS_ALARM_MIN,
      "tpc_rms_max": TPC_RMS_ALARM_MAX,
      "flanges": flanges,
      "pmt_config": pmt_config,
      "pmt_channels": pmt_channels,
      "disconnected_pmt_channels": disconnected_pmt_channels,
      "pmt_rms_min": PMT_RMS_ALARM_MIN,
      "pmt_rms_max": PMT_RMS_ALARM_MAX,
      "baseline_min": PMT_BASELINE_ALARM_MIN,
      "baseline_max": PMT_BASELINE_ALARM_MAX,
      "pmts": pmts
    }

    return render_template('icarus/introduction.html', **render_args)

@app.route('/PMT_status')
def PMT_status():
    pmts = [hw for _,hw in hardwaredb.icarus.pmt.PMTLOCs()]
    channels = [hardwaredb.select(pmt) for pmt in pmts]
    config = online_metrics.get_group_config("online", "PMT", front_end_abort=True)

    # filter out disconnected channels
    disconnected_pmt_channels = [15, 63, 111, 207, 255, 303, 351]
    for i in range(len(channels)):
      dc = [channel for channel in channels[i] if channel in disconnected_pmt_channels]
      for j in dc:
        channels[i].remove(j)

    render_args = {
      "config": config,
      "channels": channels,
      "pmts": pmts,
      "rms_min": PMT_RMS_ALARM_MIN,
      "rms_max": PMT_RMS_ALARM_MAX,
      "baseline_min": PMT_BASELINE_ALARM_MIN,
      "baseline_max": PMT_BASELINE_ALARM_MAX,
      "eventmeta_key": "eventmetaPMT",
    }

    return render_template('icarus/pmt_status_overview.html', **render_args)

@app.route('/TPC_status')
def TPC_status():
    TPCs = ["EE", "EW", "WE", "WW"]
    # Lookup the planes in each TPC
    tpc_planes_all = [p for TPC in TPCs for p in hardwaredb.select(hardwaredb.HWSelector("tpc_plane_planes", ["tpc_id"], [TPC]))]

    # Build the "HWSelector" object to map the planes to channels
    tpc_planes_all_hw = [hardwaredb.HWSelector("tpc_plane", ["tpc", "plane"], p).where("channel_type", "wired") for p in tpc_planes_all]
    # Lookup the channels
    channels = [hardwaredb.select(tpc_plane) for tpc_plane in tpc_planes_all_hw]

    config = online_metrics.get_group_config("online", "tpc_channel", front_end_abort=True)

    render_args = {
      "config": config,
      "channels": channels,
      "tpc_planes": tpc_planes_all_hw,
      "eventmeta_key": "eventmetaTPC",
      "rms_min": TPC_RMS_ALARM_MIN,
      "rms_max": TPC_RMS_ALARM_MAX,
      "baseline_min": -2200,
      "baseline_max": -1000,
    }

    return render_template('icarus/tpc_status_overview.html', **render_args)

@app.route('/TPC_Plane_Overview/<TPC>')
def TPC_Plane_Overview(TPC):
    tpc_planes = hardwaredb.select(hardwaredb.HWSelector("tpc_plane_planes", ["tpc_id"], [TPC]))
    return plane_page(tpc_planes)

def plane_page(tpc_planes):
    tpc_planes = [hardwaredb.HWSelector("tpc_plane", ["tpc", "plane"], p) for p in tpc_planes]
    print(tpc_planes)

    group_name = "tpc_channel"
    config = online_metrics.get_group_config("online", group_name, front_end_abort=True)

    channels = [hardwaredb.select(tpc_plane) for tpc_plane in tpc_planes]
    tpc_plane_flanges = [hardwaredb.HWSelector("tpc_plane_flanges", ["tpc", "plane"], p.values) for p in tpc_planes]
    flange_names = [["Flange: %s" % f for f in hardwaredb.channel_map(hw, channels)] for hw in tpc_plane_flanges]
    titles = ["TPC %s-%s" % (hw.values[0], hw.values[1]) for hw in tpc_planes]

    render_args = {
      "config": config,
      "channels": channels,
      "metric": "rms",
      "titles": titles,
      "tpc_planes": tpc_planes,
      "eventmeta_key": "eventmetaTPC",
      "flange_names": flange_names,
    }

    return render_template('icarus/plane_overview.html', **render_args);

@app.route('/CRT_board/')
@app.route('/CRT_board/<hw_selector:hw_select>')
def CRT_board(hw_select=None):
    return timeseries_view(request.args, "CRT_board", "", "crtBoardLink", hw_select=hw_select)


@app.route('/TPC')
@app.route('/TPC/<hw_selector:hw_select>')
def TPC(hw_select=None):
    args = dict(**request.args)
    args["data"] = "rms"
    args["stream"] = "fast"

    return timeseries_view(args, "tpc_channel", "", "wireLink", eventmeta_key="eventmetaTPC", hw_select=hw_select)

@app.route('/CRT_group_select')
def CRT_group_select():
    pydict = { 
        "text" : ["Select CRT Grouping"],
        "expanded": "true",
        "color" : "#000000",
        "selectable" : "false",
        "displayCheckbox": False,
        "nodes" : []
    }

    for table, cols in hardwaredb.icarus.crt.available_selectors().items():
        col_nodes = []
        for col, values in cols.items():
            child_nodes = []
            for opt in values:
                node = {
                    "text" : [opt.display_values()],
                    "selectable" : "true",
                    "displayCheckbox": "false",
                    "href":  url_for("CRT_board", hw_select=opt)
                }
                child_nodes.append(node)

            col_node = {
                "text" : [col],
                "selectable" : "false",
                "displayCheckbox": False,
                "nodes" : child_nodes 
            }
            col_nodes.append(col_node)

        table_node = {
            "text": [table],
            "selectable" : "false",
            "displayCheckbox": False,
            "nodes" : col_nodes 
        }

        pydict["nodes"].append(table_node)

    return render_template('icarus/hw_grouping_select.html', data=pydict, title="CRT")

@app.route('/TPC_group_select')
def TPC_group_select():
    pydict = { 
        "text" : ["Select TPC Grouping"],
        "expanded": "true",
        "color" : "#000000",
        "selectable" : "false",
        "displayCheckbox": False,
        "nodes" : []
    }

    for table, cols in hardwaredb.icarus.tpc.available_selectors().items():
        col_nodes = []
        for col, values in cols.items():
            child_nodes = []
            for opt in values:
                node = {
                    "text" : [opt.display_values()],
                    "selectable" : "true",
                    "displayCheckbox": "false",
                    "href":  url_for("TPC", hw_select=opt)
                }
                child_nodes.append(node)

            col_node = {
                "text" : [col],
                "selectable" : "false",
                "displayCheckbox": False,
                "nodes" : child_nodes 
            }
            col_nodes.append(col_node)

        table_node = {
            "text": [table],
            "selectable" : "false",
            "displayCheckbox": False,
            "nodes" : col_nodes 
        }

        pydict["nodes"].append(table_node)

    return render_template('icarus/hw_grouping_select.html', data=pydict, title="TPC")

@app.route('/NoiseCorr')
def NoiseCorr():
    return render_template("icarus/noise_snapshot.html")

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
    return render_template("icarus/pmt_snapshot.html", **template_args)

@app.route('/CRT_board_snapshot/')
def CRT_board_snapshot():
    board_no = int(request.args.get("board_no", 0))
    # get the config for this group from redis
    config_board = online_metrics.get_group_config("online", "CRT_board", front_end_abort=True)
    config_channel = online_metrics.get_group_config("online", "CRT_channel", front_end_abort=True)

    view_ind = {'board_no': board_no}
    # TODOL fix..... all of this
    view_ind_opts = {'board_no': list(range(8))}

    # TODO: implement real channel mapping
    board_channels = list(range(board_no*32, (board_no+1)*32))

    render_args = {
        'title': ("CRT Board %i Snapshot" % board_no),
        'board_config': config_board,
        'channel_config': config_channel,
        'board_no': board_no,
        'view_ind': view_ind,
        'view_ind_opts': view_ind_opts,
        'board_channels': board_channels
    }

    return render_template("icarus/crt_board_snapshot.html", **render_args)

# snapshot of data on channel (fft and waveform)
@app.route('/channel_snapshot')
def channel_snapshot():
    channel = request.args.get('channel', 0, type=int)

    view_ind = {'channel': channel}
    # TODOL fix..... all of this
    view_ind_opts = {'channel': list(range(2304))}

    group_name = "tpc_channel"
    config = online_metrics.get_group_config("online", group_name, front_end_abort=True)

    template_args = {
        'channel': channel,
        'config': config,
        'view_ind': view_ind,
        'view_ind_opts': view_ind_opts,
    }
    return render_template('icarus/channel_snapshot.html', **template_args)


@app.route('/Purity')
def Purity():
    group_name = "tpc_purity"

    # get the config for this group from redis
    config = online_metrics.get_group_config("online", group_name, front_end_abort=True)

    render_args = {
        'title': "Purity Display",
        'config': config,
    }

    return render_template('icarus/purity_timeseries.html', **render_args)
  
@app.route('/TPCPS')
def tpcps():
    channel = reqeust.args.get('tpcps', 0, type=int)
    config = online_metrics.get_group_config("online", "tpcps", front_end_abort=True)
    
    render_args = {
        'channel': channel,
        'config': config,
    }

    return render_template('icarus/tpcps.html', **render_args)

@app.route('/Impedance_Ground_Monitor')
def Impedance_Ground_Monitor():
    database = "epics"
    IDs = [44, 46, 47, 48, 49, 51, 52, 53] 

    configs = {}
    for i in IDs:
      configs[i] = postgres_api.pv_meta_internal(database, i, front_end_abort=True)

    render_args = {
      "configs": configs,
      "database": database
    }
    return render_template('icarus/impedance_ground_monitor.html', **render_args)

@app.route('/Level_Monitor')
def Level_Monitor():
    database = "epics"
    IDmap = {
      "een": list(range(78, 83)),
      "ewn": list(range(83, 88)),
      "ees": [88, 89, 56, 90, 91], # lol
      "ews": list(range(92, 97)),
      "wen": [57, 59, 60, 61, 62],
      "wwn": list(range(63, 68)),
      "wes": list(range(68, 73)),
      "wws": list(range(73, 78)),
      "wes": list(range(68, 73)),
    }

    configs = {}
    for _,IDs in IDmap.items():
        for i in IDs:
            configs[i] = postgres_api.pv_meta_internal(database, i, front_end_abort=True)

    render_args = {
      "configs": configs,
      "database": database,
      "IDmap": IDmap,
    }

    return render_template('icarus/level_monitor.html', **render_args)



