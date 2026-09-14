"""Create a synthetic, auditable review benchmark (no model call)."""
import json
from pathlib import Path
import shutil
import uuid

import build
import review_packet as review

ACCEPTED = '''# A small replication study

We recruited 120 participants from two universities.

The protocol required written consent before assignment.

| Group | N | Mean |
| --- | --- | --- |
| Control | 60 | 4.2 |
| Treatment | 60 | 5.1 |

![Figure 1. Response accuracy by group.](accuracy.png)

Results follow Smith (2020) [@smith2020].
'''


def create(visual=False):
    root = build.ROOT / '_build/review-evaluation' / uuid.uuid4().hex
    for folder in ['canonical','originals','proof-source','proofs']:
        (root/folder).mkdir(parents=True)
    canonical = ACCEPTED.replace('The protocol required written consent before assignment.\n\n','').replace('| Control | 60 | 4.2 |','| Control | 60 | 5.1 |').replace('Figure 1. Response accuracy by group.','Figure 1. Participant age by group.').replace('[@smith2020]','[@missing2020]')+'\nThe results is consistent with the hypothesis.\n'
    for name, text in [('originals/accepted.md',ACCEPTED),('canonical/article.qmd',canonical),('proof-source/article.qmd',canonical),('proofs/article.md',canonical.replace('120 participants','102 participants'))]:
        (root/name).write_text(text)
    if visual:
        from PIL import Image, ImageDraw, ImageFont
        for folder in ['originals','proof-source','proofs']:
            for path in (root/folder).iterdir(): path.unlink()
        image = Image.new('RGB',(600,240),'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=28)
        draw.text((30,45),'Accepted study record',fill='black',font=font)
        draw.text((30,115),'Participants: 120',fill='black',font=font)
        image.save(root/'originals/accepted.png')
        (root/'canonical/article.qmd').write_text('# Study record\n\nParticipants: 102\n')
    for name in ['review.py','README.md']:
        shutil.copyfile(review.TEMPLATES/name,root/name)
    (root/'prompt.md').write_text(review.PROMPT)
    (root/'schema.json').write_text(json.dumps(review.portable.SCHEMA))
    evidence = ['originals/accepted.md','canonical/article.qmd','proof-source/article.qmd','proofs/article.md']
    if visual:
        evidence = ['originals/accepted.png','canonical/article.qmd']
    (root/'packet.json').write_text(json.dumps(dict(packet_id=root.name,article_id='SYNTHETIC-EVAL',evidence=evidence,limitations=['Synthetic test; no real participant data.'],hashes=build.file_hashes(root)),indent=2))
    return root


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--visual',action='store_true',help='Image-only original versus changed canonical count')
    print(create(parser.parse_args().visual))
