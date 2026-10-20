#!/usr/bin/env python3
"""Install the local Garmin scheduler; uses machine-local time (Asia/Shanghai)."""
from pathlib import Path
import os
import plistlib
import shutil
import subprocess

home = Path.home()
repo = Path(__file__).resolve().parents[1]
state = home / 'Library/Application Support/local-garmin-reports'
state.mkdir(parents=True, exist_ok=True, mode=0o700)
config = state / 'config.json'
if not config.exists():
    raise SystemExit('Create private config.json first; see docs/local-garmin-reports.md')
uv = shutil.which('uv')
if not uv:
    raise SystemExit('uv is required')
label = 'com.kazoottt.local-garmin-report'
path = home / 'Library/LaunchAgents' / (label + '.plist')
path.parent.mkdir(parents=True, exist_ok=True)
agent = {
    'Label': label,
    'ProgramArguments': [uv, 'run', '--no-project', '--python', '3.12', '--with', 'garminconnect==0.3.6',
                         'python', str(repo / 'scripts/local-garmin-report.py'), '--config', str(config), '--send'],
    'WorkingDirectory': str(repo),
    'StartCalendarInterval': [{'Hour': hour, 'Minute': 0} for hour in (9, 10, 11, 12)],
    'EnvironmentVariables': {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin', 'TZ': 'Asia/Shanghai'},
    'StandardOutPath': str(state / 'scheduler.log'),
    'StandardErrorPath': str(state / 'scheduler-error.log'),
    'ProcessType': 'Background',
}
with path.open('wb') as file:
    plistlib.dump(agent, file)
path.chmod(0o600)
domain = f'gui/{os.getuid()}'
subprocess.run(['launchctl', 'bootout', domain + '/' + label], capture_output=True)
subprocess.run(['launchctl', 'bootstrap', domain, str(path)], check=True)
print('Installed: 09:00 with retries at 10:00, 11:00, 12:00 (machine local time).')
