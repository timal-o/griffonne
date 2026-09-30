import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fontcreator import project, build
project.reset_pages()
for p in sorted(Path("work/fake").glob("scan_*.jpg")):
    print(p.name, project.ingest(p.read_bytes()))
t = time.time()
r = project.build(build.Settings(family="TestHand"))
print(r, f"{time.time()-t:.1f}s")
