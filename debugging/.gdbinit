python
import gdb
import sys
import os
sys.path.insert(0, os.path.expanduser("~/.config/gdb"))
def setup_python(event):
    import libpython
gdb.events.new_objfile.connect(setup_python)
end
