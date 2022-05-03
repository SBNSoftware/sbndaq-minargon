from __future__ import print_function
from __future__ import absolute_import
from datetime import datetime, tzinfo, timedelta
import calendar

from werkzeug.routing import BaseConverter, ValidationError
import pytz

LOCAL_TZ = pytz.timezone("US/Central")

class ListConverter(BaseConverter):
    def to_python(self, value):
        return [x for x in value.split(',') if len(x) > 0]
    def to_url(self, values):
        return ','.join(super(ListConverter, self).to_url(value)
                        for value in values)

class DataStream(object):
    def __init__(self, name):
        self.name = name

class RedisDataStream(DataStream):
    def __init__(self, name, key):
        super(RedisDataStream, self).__init__(name)
        self.key = key

    def to_config(self):
        dtype = "redis"
        database = self.name
        
        try:
            metric_name = self.key.split(":")[-2]
        except:
            metric_name = self.key
        config = {
          "title": self.key,
          "yTitle": metric_name
        }
        return (dtype, self.key, database, config)

class PostgresDataStream(DataStream):
    def __init__(self, name, ID):
        super(PostgresDataStream, self).__init__(name)
        self.ID = ID

    def to_config(self):
        from .metrics.postgres_api import pv_meta_internal
        dtype = "postgres"
        database = self.name
        config = pv_meta_internal(database, self.ID, front_end_abort=True)
        return (dtype, self.ID, database, config)  

class StreamConverter(BaseConverter):
    def to_python(self, value):
        database = value.split(",")[0]
        ID = value.split(",")[1]
        if database.startswith("postgres_"):
            database_name = database[9:]
            return PostgresDataStream(database_name, ID)
        elif database.startswith("redis_"):
            database_name = database[6:]
            return RedisDataStream(database_name, ID)
        else:
            raise ValueError

    def to_url(self, stream):
        if isinstance(stream, PostgresDataStream):
            return ",".join(["postgres_" + stream.name] + [str(stream.ID)])
        elif isinstance(stream, RedisDataStream):
            return ",".join(["redis_" + stream.name] + [stream.key])

def total_seconds(td):
    """Returns the total number of seconds contained in the duration."""
    return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6) / 10**6


# FROM: https://stackoverflow.com/questions/1101508/how-to-parse-dates-with-0400-timezone-string-in-python
class FixedOffset(tzinfo):
    """Fixed offset in minutes: `time = utc_time + utc_offset`."""
    def __init__(self, offset):
        self.__offset = timedelta(minutes=offset)
        hours, minutes = divmod(offset, 60)
        #NOTE: the last part is to remind about deprecated POSIX GMT+h timezones
        #  that have the opposite sign in the name;
        #  the corresponding numeric value is not used e.g., no minutes
        self.__name = '<%+03d%02d>%+d' % (hours, minutes, -hours)
    def utcoffset(self, dt=None):
        return self.__offset
    def tzname(self, dt=None):
        return self.__name
    def dst(self, dt=None):
        return timedelta(0)
    def __repr__(self):
        return 'FixedOffset(%d)' % (self.utcoffset().total_seconds() / 60)

def parseiso(timestr):
    """Convert an iso time string -> [ms] unix timestamp."""
    try: 
        naive_date_str, _, offset_str = timestr.rpartition(' ')
        dt = datetime.strptime(naive_date_str,'%Y-%m-%dT%H:%M:%S.%fZ')

        offset = int(offset_str[-4:-2])*60 + int(offset_str[-2:])
        if offset_str[0] == "-":
            offset = -offset

        dt = dt.replace(tzinfo=FixedOffset(offset))

    except:
        dt = datetime.strptime(timestr, '%m/%d/%Y %H:%M')
    return int(calendar.timegm(dt.timetuple())*1e3 + dt.microsecond/1e3)

# try parsing as int, falling back to parseiso
def parseiso_or_int(inp_str):
    try:
        return int(inp_str)
    except ValueError:
        return parseiso(str(inp_str))

def stream_args(args):
    ret = {}
    ret["start"] = args.get('start',None,type=parseiso_or_int)
    ret["stop"] = args.get('stop', None,type=parseiso_or_int)
    ret["n_data"] = args.get('n_data', None, type=int)

    return ret
    


