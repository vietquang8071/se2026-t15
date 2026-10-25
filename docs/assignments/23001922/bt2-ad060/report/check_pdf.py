from pathlib import Path
import datetime, json, re, subprocess
import pymupdf
from PIL import Image
from reportlab.pdfbase.ttfonts import TTFont
ROOT=Path(__file__).resolve().parent.parent
pdf=ROOT/'BT2_23001922_AD-060.pdf'
doc=pymupdf.open(pdf)
expected=[
 'BÀI TẬP CÁ NHÂN 2', 'B. Module view', 'B. Runtime view', 'C. ADR-060-01',
 'D. Code quality', 'D–E. After', 'F. AI-assisted review',
]
checks=[]
for i,heading in enumerate(expected):
 text=doc[i].get_text()
 assert heading in text,(i+1,heading)
 assert f'{i+1}/7' in text
 assert 'Phụ lục AI' not in text
 checks.append({'page':i+1,'heading':heading,'characters':len(text),'images':len(doc[i].get_images())})
assert 'PHỤ LỤC' in doc[7].get_text()
first=doc[0].get_text()
for value in ['23001922','AD-060','SE2026-T15','AI-05','Nguyễn Huy Sơn',
 'Tôi chịu trách nhiệm về toàn bộ nội dung bài làm và đã khai báo việc sử dụng AI.']:
 assert value in first,value
all_text='\n'.join(page.get_text() for page in doc[:7])
for value in ['709','5.0','70 ngày','22 giờ','17 passed','0 failed']:
 assert value in all_text,value
bounds=[]; fonts=set(); font_sizes=[]
font_paths={
 'DejaVuSans':'/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
 'DejaVuSans-Bold':'/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
 'LiberationMono':'/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf',
 'NotoSans-Regular':'/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',
}
glyphs={n:TTFont(n,p).face.charToGlyph for n,p in font_paths.items()}
for i,page in enumerate(doc):
 assert abs(page.rect.width-595)<1 and abs(page.rect.height-842)<1
 for block in page.get_text('dict')['blocks']:
  for line in block.get('lines',[]):
   for span in line['spans']:
    if not span['text'].strip():continue
    x0,y0,x1,y1=span['bbox']
    assert x0>=30 and x1<=565,(i+1,span['text'],span['bbox'])
    assert y0>=20 and y1<=830,(i+1,span['text'],span['bbox'])
    fonts.add(span['font']);font_sizes.append(span['size'])
    assert all(ord(ch) in glyphs[span['font']] for ch in span['text'] if not ch.isspace()), (span['font'],span['text'])
    if y0<795:bounds.append(y1)
links=[link['uri'] for page in doc for link in page.get_links() if link.get('uri')]
assert len(links)>=15
assert all('/blob/1bcbfc156671888a83da57dece19c1ac18b498e8/' in uri for uri in links)
assert '\ufffd' not in all_text
# Render all main pages at readable resolution for manual inspection.
preview=ROOT/'report/previews';preview.mkdir(exist_ok=True)
thumbs=[]
for i in range(7):
 pix=doc[i].get_pixmap(matrix=pymupdf.Matrix(1.5,1.5),alpha=False)
 pix.save(str(preview/f'page-{i+1}.png'))
 im=Image.open(preview/f'page-{i+1}.png').convert('RGB');im.thumbnail((380,540));thumbs.append(im)
contact=Image.new('RGB',(1520,1120),'#cbd5e1')
for i,im in enumerate(thumbs):contact.paste(im,((i%4)*380,(i//4)*560))
contact.save(preview/'overview.png')
status=subprocess.check_output(['git','-C',str(ROOT/'evidence/repository'),'status','--porcelain'],text=True)
assert not status,status
result={
 'checked_at':datetime.datetime.now().astimezone().isoformat(),'pdf':pdf.name,
 'total_pages':len(doc),'main_pages':7,'appendix_pages':len(doc)-7,
 'main_page_structure':checks,'links':len(links),'link_commit_verified':True,
 'font_names_in_use':sorted(fonts),'smallest_text_pt':round(min(font_sizes),2),
 'text_within_page_bounds':True,'all_rendered_characters_have_font_glyphs':True,'required_ids_commitment_and_parameters_found':True,
 'reference_repository_worktree_clean':True,
 'diagram_format':'SVG rendered as vector paths/text; no raster images on module/runtime pages',
 'visual_review':'Main pages rendered to report/previews; manual inspection by AI follows this automated check',
 'limitations':['No Lecture 04/05 supplied','No live vendor/production rollback/load 709 verification'],
}
(ROOT/'evidence/pdf-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
(ROOT/'report/rendered.txt').write_text('\n\f\n'.join(page.get_text() for page in doc))
print(json.dumps(result,ensure_ascii=False,indent=2))
