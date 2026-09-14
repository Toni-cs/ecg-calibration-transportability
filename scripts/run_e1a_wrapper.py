"""Wrapper to run E1a with proper UTF-8 output redirection."""
import subprocess, os, sys

env = os.environ.copy()
env['PYTHONIOENCODING'] = 'utf-8'
env['PYTHONUTF8'] = '1'

log_path = os.path.join(os.path.dirname(__file__), '..', 'results', 'e1a_full_v3.log')
err_path = os.path.join(os.path.dirname(__file__), '..', 'results', 'e1a_full_v3_err.log')

with open(log_path, 'w', encoding='utf-8') as log_f, \
     open(err_path, 'w', encoding='utf-8') as err_f:
    proc = subprocess.Popen(
        [sys.executable, '-u', os.path.join(os.path.dirname(__file__), 'run_e1a_l2_shift_full.py')],
        cwd=os.path.join(os.path.dirname(__file__), '..'),
        stdout=log_f,
        stderr=err_f,
        env=env,
    )
    print(f'Started PID: {proc.pid}')
    proc.wait()
    print(f'Exit code: {proc.returncode}')
