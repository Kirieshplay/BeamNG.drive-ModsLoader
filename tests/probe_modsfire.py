import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.resolvers import DownloadPreparer

logs = []
preparer = DownloadPreparer(lambda level, message: logs.append((level, message)))
prepared = preparer.prepare("https://modsfire.com/a1gQYQC1f2gsxDi")
print("URL", prepared.url[:160])
print("NAME", prepared.filename)
print("SIZE", prepared.total)
print("HOST", prepared.host)
print("TYPE", prepared.content_type)
print("LOGS")
for level, message in logs:
    print(level, message)
chunk = next(prepared.response.iter_content(128 * 1024))
print("CHUNK", len(chunk), chunk[:8])
prepared.response.close()
