from minargon import app
from flask import send_file, render_template, jsonify, request, redirect, url_for, flash
from minargon.metrics import postgres_api
import numpy as np
from minargon.tools import parseiso
from minargon.metrics import online_metrics, redis_api
import os.path
from datetime import date, datetime
from matplotlib.backends.backend_agg import FigureCanvasAgg
#from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from StringIO import StringIO
from scipy.sparse import csr_matrix
from scipy.sparse import coo_matrix
import time
import seaborn as sns
"""
	Routes intented to be seen by the user	
"""
'''
Channel_downsamplefactor = 5
ADC_downsamplefactor     = 5

channeldownsample = csr_matrix((5600/Channel_downsamplefactor,5600))
adcdownsample = csr_matrix((4000000,4000000/ADC_downsamplefactor))
for i in range(5600/Channel_downsamplefactor):
	for j in range(5600):
		channeldownsample[i,j] = 1

for k in range(4000000):
	for l in range(4000000/ADC_downsamplefactor):
		adcdownsample[k,l]     = 1
'''
@app.route('/<rconnect>/<TPC>/plots.png')
@online_metrics.redis_route
def plots(rconnect,TPC):
    TPC = int(TPC)
    waveform_set0 = csr_matrix((49024, 4000000))
    offsets = [6656,18912,31168,43424]
    this_offset = offsets[TPC]
    for i in range(0,5601):
	#m,n,o,p = i+6656,i+18912,i+31168,i+43424
        waveforms, offsets, periods = redis_api.get_waveform(rconnect, "snapshot:sparse_waveform:wire:%d" % (i+this_offset))
	if len(waveforms[0])>0:
                a = 0
                for a in range(len(waveforms)):
                    b = 0
                    for b in range(len(waveforms[a])):
                        waveform_set0[i+this_offset,offsets[a]+b]=waveforms[a][b]

    waveform_set0 = waveform_set0.tocoo()
    #waveform_set0 = np.matpul(waveform_set0,adcdownsample)
    #waveform_set0 = np.matpul(channeldownsample,waveform_set0)
    fig = plt.figure(figsize=[10.0,7.0])
    canvas = FigureCanvasAgg(fig)
    
    ax0 = fig.add_subplot(111, facecolor='white')
    
    ax0.plot(waveform_set0.col, waveform_set0.row, 's', color='red', ms=1)
    ax0.set_ylim(this_offset, this_offset+5600)
    ax0.set_xlim(0,4000000)
    ax0.set_ylabel('Channel Number')
    ax0.set_xlabel('Time (ns)')
    ax0.set_title('TPC %d Event Display'%(TPC+1))
    #ax0.imshow(waveform_set0, cmap='BuPu')

    sio = StringIO()
    canvas.print_png(sio)
    sio.seek(0)

    return send_file(sio,mimetype="image/png")

@app.route('/event_display')
def event_display():

	return render_template('common/event_display.html')



@app.route('/test_error')
def test_error():
    sys.stderr.write("Flask error logging test")
    raise Exception("Flask exception logging test")

@app.route('/hellooo')
def hellooo():
    return 'Hellooooooo!'

@app.route('/')
def index():
    return redirect(url_for('introduction'))

@app.route('/introduction')
def introduction():
    template = os.path.join(app.config["FRONT_END"], 'introduction.html')
    return render_template(template)

@app.route('/<connection>/latest_gps_info')
def latest_gps_info(connection):
    dbrows = postgres_api.get_gps(connection, front_end_abort=True)     

    return render_template('common/gps_info.html',rows=dbrows)


@app.route('/online_group/<group_name>')
def online_group(group_name):
    return timeseries_view(request.args, group_name)

@app.route('/single_stream/<stream_name>/')
def single_stream(stream_name):
    render_args = {
        "stream_name": stream_name,
    }
    return render_template('common/single_stream.html', **render_args) 

# A test func for the PV Lists this translates the page made by bill to the Minargon webpage
# and also updates the script to be more compatible with python
@app.route('/<connection>/pvTree')
def pvTree(connection):
    return render_template('common/pvTree.html', data=postgres_api.pv_internal(connection, "pv_single_stream", front_end_abort=True))

def timeseries_view(args, instance_name, view_ident="", link_function="undefined"):
    # TODO: what to do with this?
    initial_datum = args.get('data', None)
    
    # get the config for this group from redis
    config = online_metrics.get_group_config("online", instance_name, front_end_abort=True)

    if initial_datum is None:
        if len(config["metric_list"]) > 0:
            initial_datum = config["metric_list"][0]
        else:
            intial_datum = "rms"

    render_args = {
        'title': instance_name,
        'link_function': link_function,
        'view_ident': view_ident,
        'config': config,
        'metric': initial_datum
    }

    return render_template('common/timeseries.html', **render_args)

@app.route('/pv_single_stream/<database>/<ID>')
def pv_single_stream(database, ID):
    # get the config
    config = postgres_api.pv_meta_internal(database, ID, front_end_abort=True)
    # get the list of other data
    # tree = postgres_api.test_pv_internal(database)

    # check the currently visited item
    checked = [("postgres", database, str(ID))]
    tree = build_data_browser_tree(checked)
    # print config
   
    #low and high thresholds given by url parameters 
    low = request.args.get('low')
    high = request.args.get('high')
    #TODO: add try and catch cases for getting timestamps
    #Use 24 hour clock for defining time in url
    #date format from URL: Month-Day-Year_Hour:Minute | mm-dd-yr hr-min
    #date format to turn back to string: Month/Day/Year Hour:Minute
    start = request.args.get('start')
    if start is not None:
	start_obj = datetime.strptime(start, '%m-%d-%Y_%H:%M')
	#start time string to be placed in date picker
        start_time = datetime.strftime(start_obj,'%m/%d/%Y %H:%M')
        #%m%d%y%H:%M format to convert string into integer|mmddyyyyHHMM

	# start timestamp to update plot
	start_timestamp_int = parseiso(start_time);

    else:
	start_obj = None
	start_time = start
        start_timestamp_int = None
 
    end = request.args.get('end')
    if end is not None:
	end_obj = datetime.strptime(end, '%m-%d-%Y_%H:%M')
	#end time string to be placed in date picker
	end_time = datetime.strftime(end_obj, '%m/%d/%Y %H:%M')
        #%m%d%y%H:%M format to convert string into integer|mmddyyyyHHMM

	#end timestamp to update plot
	end_timestamp_int = parseiso(end_time);

    else:
	end_obj = None
        end_time = end
        end_timestamp_int = None

    render_args = {
      "ID": ID,
      "config": config,
      "database": database,
      "tree": tree,
      "low": low,
      "high": high,
      "start_time": start_time,
      "end_time": end_time,
      "start_timestamp": start_timestamp_int,
      "end_timestamp": end_timestamp_int
    }
    return render_template('common/pv_single_stream.html', **render_args)

# View a variable with multiple IDs
@app.route('/pv_multiple_stream/<database>/<var>')
def pv_multiple_stream(database, var):
    
    # Get the list of IDs for the var name
    IDs = postgres_api.pv_internal(database, ret_id=var, front_end_abort=True)

    # get the configs for each ID
    configs, starts, ends, toggles, downloads = [], [], [], [], []
    for ID in IDs:
        configs.append(postgres_api.pv_meta_internal(database, ID, front_end_abort=True))
        starts.append("start-"+str(ID))
        ends.append("end-"+str(ID))
        toggles.append("toggle-"+str(ID))
        downloads.append("download-"+str(ID))

    # print config
    render_args = {
      "var": var, 
      "IDs": IDs,
      "configs": configs,
      "starts" : starts,
      "ends" : ends,
      "toggles" : toggles,
      "downloads" : downloads,
      "database": database
    }
    return render_template('common/pv_multiple_stream.html', **render_args)


def build_data_browser_tree(checked=None):
    # get the redis instance names
    redis_names = [name for name,_ in app.config["REDIS_INSTANCES"].items()]
    # and the postgres isntance names
    postgres_names = [name for name,_ in app.config["POSTGRES_INSTANCES"].items()]
    # build all of the trees
    trees = [postgres_api.pv_internal(name, front_end_abort=True) for name in postgres_names] + [online_metrics.build_link_tree(name, front_end_abort=True) for name in redis_names]
    # wrap them up at a top level
    tree_dict = {
      "text": "Data Browser",
      "expanded": True,
      "nodes": trees,
      "displayCheckbox": False,
    }
    # pre-check some instances
    if checked is None:
        checked = []
    for c in checked:
        database_type, database, ID = c
        # do a DFS down the nodes
        stack = [tree_dict]
        while len(stack) > 0:
            vertex = stack.pop()
            if "nodes" in vertex:
                stack = stack + vertex["nodes"]
            elif "ID" in vertex and "database" in vertex and "database_type" in vertex:
                if vertex["ID"] == ID and vertex["database"] == database and vertex["database_type"] == database_type:
                    vertex["state"] = {"checked": True}
                    # if we've found the vertex, we can exit the search
                    break
    return tree_dict

@app.route('/view_streams')
def view_streams():
    postgres_stream_info = {}
    redis_stream_info = {}
    # parse GET parameters
    try:
        for arg, val in request.args.items():
            # postgres streams
            if arg.startswith("postgres_"):
                database_name = arg[9:]
                database_ids = [int(x) for x in val.split(",") if x]
                postgres_stream_info[database_name] = database_ids
            # redis streams
            elif arg.startswith("redis_"):
                database_name = arg[6:]
                database_keys = val.split(",")
                redis_stream_info[database_name] = database_keys
    except:
        return abort(404)

    postgres_streams = []
    redis_streams = []
    # collect configuration for postgres streams
    for database, IDs in postgres_stream_info.items():
        for ID in IDs:
            config = postgres_api.pv_meta_internal(database, ID, front_end_abort=True)
            postgres_streams.append( (ID, database, config) )
    # TODO: collect redis stream configuration
    for database, keys in redis_stream_info.items():
        for key in keys:
            redis_streams.append( (key, database, {}) )

    checked = []
    # get the currently checked items
    for database, IDs in postgres_stream_info.items():
        for ID in IDs:
            checked.append( ("postgres", database, str(ID)) )
    for database, keys in redis_stream_info.items():
        for key in keys:
            checked.append( ("redis", database, key) )

    # build the data tree
    tree = build_data_browser_tree(checked)
    render_args = {
      "tree": tree,
      "redis_streams": redis_streams,
      "postgres_streams": postgres_streams
    }
    return render_template("common/view_streams.html", **render_args)

