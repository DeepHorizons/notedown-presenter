from .presenter import *

# avoid having to require the notebook to install notedown
try:
    from .presenter import NotedownPresenterContentsManager
except ImportError:
    err = 'You need to install the jupyter notebook.'
    NotedownContentsManager = err
    NotedownContentsManagerStripped = err
    raise
