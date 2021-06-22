from __future__ import absolute_import
from minargon import app

from minargon.hardwaredb.icarus.tpc import TPCs
from minargon.hardwaredb.icarus.crt import CRTLOCs
from minargon.hardwaredb.icarus.pmt import PMTLOCs

@app.context_processor
def inject_hw_info():
    return dict(TPCs=TPCs(), CRTLOCs=CRTLOCs(), PMTLOCs=PMTLOCs())


