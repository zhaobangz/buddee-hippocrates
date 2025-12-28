"""Startup check for Buddi: verifies optional dependencies and device availability.

Run this script to get a quick report of what's installed and whether GPU
or other optional features look usable.
"""
import sys
import platform
import shutil
import importlib


def check_import(name):
    try:
        mod = importlib.import_module(name)
        return True, mod
    except Exception as e:
        return False, str(e)


def check_tesseract():
    t = shutil.which('tesseract')
    return t is not None, t


def check_sounddevice():
    ok, mod = check_import('sounddevice')
    if not ok:
        return False, str(mod)
    try:
        sd = mod
        # try to query devices (may raise if no permission)
        devices = sd.query_devices()
        input_devs = [d for d in devices if d.get('max_input_channels', 0) > 0]
        return True, len(input_devs)
    except Exception as e:
        return False, str(e)


def check_pytorch_transformers():
    ok_torch, torch_res = check_import('torch')
    ok_trans, trans_res = check_import('transformers')
    info = {
        'torch': ok_torch,
        'transformers': ok_trans,
    }
    if ok_torch:
        try:
            import torch
            cuda = torch.cuda.is_available()
            try:
                mps = getattr(torch.backends, 'mps', None) is not None and torch.backends.mps.is_available()
            except Exception:
                mps = False
            info.update({'cuda': cuda, 'mps': mps, 'cuda_count': torch.cuda.device_count() if cuda else 0})
        except Exception as e:
            info['torch_error'] = str(e)
    else:
        info['torch_error'] = torch_res
    if not ok_trans:
        info['transformers_error'] = trans_res
    return info


def main():
    print('Buddi startup check')
    print('Platform:', platform.platform())
    print('Python:', sys.version.splitlines()[0])
    print()

    # PIL / ImageGrab
    pil_ok, pil_res = check_import('PIL')
    print('* Pillow installed:', pil_ok)
    if not pil_ok:
        print('  ', pil_res)

    # pytesseract + tesseract executable
    pt_ok, pt_res = check_import('pytesseract')
    tess_ok, tess_path = check_tesseract()
    print('* pytesseract installed:', pt_ok)
    print('* tesseract executable found:', tess_ok, tess_path)

    # sounddevice
    sd_ok, sd_res = check_sounddevice()
    print('* sounddevice usable:', sd_ok)
    if sd_ok and isinstance(sd_res, int):
        print('  input devices found:', sd_res)
    else:
        print('  ', sd_res)

    # torch/transformers
    info = check_pytorch_transformers()
    print('* torch installed:', info.get('torch', False))
    if info.get('torch'):
        print('  cuda available:', info.get('cuda'), 'count:', info.get('cuda_count'))
        print('  mps available:', info.get('mps'))
    else:
        print('  torch error:', info.get('torch_error'))
    print('* transformers installed:', info.get('transformers', False))
    if not info.get('transformers', False):
        print('  transformers error:', info.get('transformers_error'))

    # tkinter available
    tk_ok, tk_res = check_import('tkinter')
    print('* tkinter available (for UI):', tk_ok)

    # macOS specific notes
    if sys.platform == 'darwin':
        print('\nmacOS detected:')
        print(' - Screen Recording and Microphone permissions may be required for screen/audio capture.')
        print(' - If you see permission errors when running the app, open System Settings -> Privacy & Security -> Screen Recording / Microphone and add your terminal or Python interpreter.')

    print('\nSummary: install missing optional packages (Pillow, pytesseract, sounddevice, numpy, torch, transformers) as needed and ensure OS permissions for capture features.')

if __name__ == '__main__':
    main()
