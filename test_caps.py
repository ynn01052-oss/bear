import subprocess
from auto import open_caps, ADB_PATH, ADB_DEVICE

subprocess.run([ADB_PATH, "connect", ADB_DEVICE], capture_output=True)
open_caps()