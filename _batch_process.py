from pathlib import Path
from processor import AvatarProcessor

root = Path(r'C:\Users\zs\Desktop\7-4\20260703-11907582624846')
out_root = Path(r'C:\Users\zs\Desktop\7-4-avatar-outputs\20260703-11907582624846')
out_root.mkdir(parents=True, exist_ok=True)
processor = AvatarProcessor()
count = 0
for p in root.iterdir():
    if not p.is_file():
        continue
    if p.suffix.lower() not in {'.png', '.jpg', '.jpeg'}:
        continue
    data = p.read_bytes()
    out = processor.process(data)
    target = (out_root / p.name).with_suffix('.png')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(out)
    count += 1
    print(target)
print('done', count)
