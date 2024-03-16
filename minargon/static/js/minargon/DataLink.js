// all the datalinks...

// DataLink which connects a epics stream given the ID

// Arguments to constructor:
// root: the root path wehre all of the API endpoints are defined
// ID: the epics channel ID
export class EpicsStreamLink {
  constructor(root, database, ID) {
    this.root = root;
    this.database = database;
    this.ID = String(ID);
  }

  step_link() {
    return this.root + "/" + this.database + "/ps_step/" + this.ID;
  }

  data_link(start, stop, n_data) {
    return this.root + "/" + this.database + "/ps_series/" + this.ID + '?' + $.param(timeArgs(start, stop, n_data));
  }

  config_link() {
    return this.root + "/" + this.database + "/pv_meta/" + this.ID;
  }

  accessors() {
    return [[this.ID]];
  }

  name() {
    return this.ID;
  }

}

export class CryoStreamLink {
  constructor(root, database, month, pv) {
    this.root = root;
    this.database = database;
//    this.pv = String(pv);
//    this.month = String(month);
    this.pv = pv;
    this.month = month;
  }

  step_link() {
    return this.root + "/" + this.database + "/cryo_ps_step/" + this.month + "/" + this.pv;
  }

  data_link(start, stop, n_data) {
    return this.root + "/" + this.database + "/cryo_ps_series/" + this.month + "/" + this.pv + '?' + $.param(timeArgs(start, stop, n_data));
  }

  config_link() {
    return this.root + "/" + this.database + "/cryo_pv_meta/" + this.pv;
  }

  accessors() {
    return [[this.pv]];
  }

  name() {
    return this.pv;
  }

}

export class DriftHVStreamLink {
  constructor(root, database, pv) {
    this.root = root;
    this.database = database;
//    this.pv = String(pv);
//    this.month = String(month);
    this.pv = pv;
  }

  step_link() {
    return this.root + "/" + this.database + "/drifthv_ps_step/" + this.pv;
  }

  data_link(start, stop, n_data) {
    return this.root + "/" + this.database + "/drifthv_ps_series/" + this.pv + '?' + $.param(timeArgs(start, stop, n_data));
  }

  config_link() {
    return this.root + "/" + this.database + "/drifthv_pv_meta/" + this.pv;
  }

  accessors() {
    return [[this.pv]];
  }

  name() {
    return this.pv;
  }

}


// DataLink which connects a raw stream name with the backend API for online metrics

// Arguments to constructor:
// root: the root path where all of the API endpoints are defined
// stream: the full name of the stream 
export class SingleStreamLink {
  constructor(root, stream) {
    this.stream = stream;
    this.root = root;
  }

  step_link() {
    return this.root + '/infer_step_size/' + this.stream;
  }
 
  data_link(start, stop, n_data) {
    return this.root + '/stream/' + this.stream + '?' + $.param(timeArgs(start, stop, n_data));
  }

  event_source_link(start) {
    return this.root + '/stream_subscribe/' + this.stream + '?' + $.param(timeArgs(start));
  }

  accessors() {
    return [[this.stream]];
  }

  name() {
    return this.stream;
  }
}

export class HWGroupMetricLink {
  constructor(root, stream, group, metric, hw_selects, downsample) {
    this.root = root;
    this.stream = stream;
    this.group = group;
    this.metric = metric;
    this.hw_selects = hw_selects;
    this.downsample = downsample;
  }

  data_link(start, stop, n_data) {
    var hw_selects = this.hw_selects.join(",");
    var downsample = "";
    if (this.downsample)  downsample = "/" + this.downsample;
    return this.root + "/stream_group_hw_avg/" + this.stream + "/" + this.metric + "/" + this.group + "/" + hw_selects + downsample + "?" + $.param(timeArgs(start, stop, n_data));
  }

  step_link() {
    return this.root + "/stream_group_hw_step/" + this.stream + "/" + this.metric + "/" + this.group + "/" + this.hw_selects[0];
  }

  accessors() {
    var ret = [];
    for (var i = 0; i < this.hw_selects.length; i++) {
      ret.push([this.metric, this.hw_selects[i]]);
    }
    return ret;
  };

  name() {
    return this.group;
  }
}

export class HwMetricStreamLink {
  constructor(root, stream, group, instances, metrics, hw_select) {
    this.root = root;
    this.stream = stream;
    this.group = group;
    this.metrics = metrics;
    this.hw_select = hw_select;
    this.instances = instances;
  }

  step_link() {
    var metric_list = "";
    for (var i = 0; i < this.metrics.length; i++) {
      metric_list = metric_list + this.metrics[i] + ",";
    }
    var link = this.root + '/infer_step_size/' + this.stream + '/' + metric_list + '/' + this.group + '/' + this.instances[0];
    return link;
  }

  data_link_internal(base, start, stop, n_data) {
    var metrics = "";
    for (var i = 0; i < this.metrics.length; i++) {
      metrics = metrics + this.metrics[i] + ',';
    }

    var ret = this.root + base + this.stream + '/' + metrics + '/' + this.group + '/hw_select/' + this.hw_select;
    var args = timeArgs(start, stop, n_data);
    if (!(args === null)) {
      ret = ret + '?' + $.param(args);
    }
    return ret;
  }

  data_link(start, stop, n_data) {
    return this.data_link_internal('/stream_group/', start, stop, n_data);
  }

  ref_link() {
    return this.data_link_internal('/stream_group_ref/');
  }

  event_source_link(start) {
    return this.data_link_internal('/stream_group_subscribe/', start, null);
  }

  accessors() {
    var ret = [];
    // iterate first over each metric
    for (var i = 0; i < this.metrics.length; i++) {
      // iterate over the instances
      for (var j = 0; j < this.instances.length; j++) {
        ret.push( [this.metrics[i], this.instances[j]] );
      }
    }
    return ret;

  }

  name() {
    return this.hw_select;
  }

}

// DataLink which connects configured timeseries with the backend API for online metrics

// Arguments to constructor:
// root: the root path where all of the API endpoints are defined
// stream: the name of the stream
// group: the group object provided by the configuration backend
// instances: a list of instances provided by the configuration backend 
// metrics: a list of metrics
// sequence: you should set this to false unless you know what you are doing
export class MetricStreamLink {
  constructor(root, stream, group, instances, metrics, sequence) {
    this.root = root;
    this.stream = stream;
    this.group = group;
    this.metrics = metrics;
    if (sequence === true) {
      this.sequence = true;
      this.field_start = String(instances[0]);
      this.field_end = String(instances[1]);
    }
    else {
      this.sequence = false;
      this.instances = instances;
    }

  }
 
  step_link() {
    var metric_list = "";
    for (var i = 0; i < this.metrics.length; i++) {
      metric_list = metric_list + this.metrics[i] + ",";
    }
    var link = this.root + '/infer_step_size/' + this.stream + '/' + metric_list + '/' + this.group + '/' + this.instances[0];
    return link;
  }
  
  data_link_internal(base, start, stop, n_data) {
    if (this.sequence) {
      var instances = this.field_start + '/' + this.field_end; 
    }
    else if (this.instances.length == 1) {
      var instances = this.instances[0] + ","; 
    }
    else {
      var instances = "";

      // check if sequential
      var is_sequential = true;
      for (var i = 1; i < this.instances.length; i++) {
        if (Number(this.instances[i]) - 1 != Number(this.instances[i-1])) {
          is_sequential = false;
          break;
        }
      }

      if (!is_sequential) {
        for (var i = 0; i < this.instances.length; i++) {
          instances = instances + this.instances[i] + ',';
        }
      }
      else {
        instances = this.instances[0] + "/" + (Number(this.instances[this.instances.length-1])+1);
      }
    }
    var metrics = "";
    for (var i = 0; i < this.metrics.length; i++) {
      metrics = metrics + this.metrics[i] + ',';
    }

    var ret = this.root + base + this.stream + '/' + metrics + '/' + this.group + '/' + instances;
    var args = timeArgs(start, stop, n_data);
    if (!(args === null)) {
      ret = ret + '?' + $.param(args);
    }
    return ret;
  }

  data_link(start, stop, n_data) {
    return this.data_link_internal('/stream_group/', start, stop, n_data);
  }

  ref_link() {
    return this.data_link_internal('/stream_group_ref/');
  }

  event_source_link(start) {
    return this.data_link_internal('/stream_group_subscribe/', start, null);
  }

  accessors() {
    var ret = [];
    // iterate first over each metric
    for (var i = 0; i < this.metrics.length; i++) {
      // iterate over the instances
    
      // sequence
      if (this.sequence) {
        for (var field = this.field_start; field < this.field_start + this.field_end; field++) {
          ret.push( [this.metrics[i], String(field)] );
        }
      }
      // not a sequence -- iterate over the provided instances
      for (var j = 0; j < this.instances.length; j++) {
        ret.push( [this.metrics[i], this.instances[j]] );
      }
    }
    return ret;

  }

  name() {
    if (this.metrics.length == 1) return this.metrics[0];
    if (!this.sequence && this.instances.length == 1)  return String(this.instances[0]);
    return this.group;
  }

}

function flatten(arr) {
    return arr[0];
}

// start/stop can be a date or an integer
function timeArgs(start, stop, n_data) {
  var now = new Date();
  var ret = {
    now: now.toISOString() + " " + now.getTimezoneOffset(),
  };

  if (n_data !== undefined) {
    ret.n_data = n_data;
  }

  if (start instanceof Date) {
    // alert(start);
    ret.start = start.toISOString() + " " + start.getTimezoneOffset();
  }
  else if (start !== undefined) {
    ret.start = start;
  }
  // stop doesn't have to be set
  if (!(stop === undefined)) {
    if (stop instanceof Date) {
      ret.stop = stop.toISOString() + " " + stop.getTimezoneOffset();
    }
    else {
       ret.stop = stop;
    }
  }
  return ret;

}



