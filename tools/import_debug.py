import sys
import traceback
sys.path.insert(0, r'c:\Users\user\Desktop\PFE\pfe-ai-recruitment')
try:
    import app.agents.cv_parser as m
    print('Imported cv_parser OK')
except Exception as e:
    traceback.print_exc()
    print('Exception type:', type(e))

print('\n---- File checks ----')
from pathlib import Path
files = [Path('c:\\\\Users\\\\user\\\\Desktop\\\\PFE\\\\pfe-ai-recruitment\\\\app\\\\agents\\\\cv_parser.py')]
for f in files:
    b = f.read_bytes()
    print(f, 'size', len(b), 'first100', repr(b[:100]))
    try:
        s = b.decode('utf-8')
        idx = s.find('\x00')
        print('text null index', idx)
    except Exception as ex:
        print('decode error', ex)

print('\n---- Dependency imports ----')
deps = ['os','json','pdfplumber','groq','dotenv']
for d in deps:
    try:
        __import__(d)
        print(d, 'import OK')
    except Exception as ex:
        print(d, 'import FAILED:', type(ex), ex)

print('\n---- Direct load via importlib ----')
import importlib.util
from types import ModuleType
path = 'c:\\\\Users\\\\user\\\\Desktop\\\\PFE\\\\pfe-ai-recruitment\\\\app\\\\agents\\\\cv_parser.py'
try:
    spec = importlib.util.spec_from_file_location('temp_cv', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print('Loaded via importlib.exec_module OK')
except Exception as ex:
    import traceback as tb
    tb.print_exc()
    print('Direct load failed:', type(ex), ex)

print('\n---- importlib.spec info ----')
import importlib
for name in ['app','app.agents','app.agents.cv_parser']:
    try:
        spec = importlib.util.find_spec(name)
        print(name, 'spec->', spec)
        if spec:
            print('  origin:', getattr(spec,'origin',None), 'loader:', getattr(spec,'loader',None))
    except Exception as ex:
        print('spec error for', name, ex)
