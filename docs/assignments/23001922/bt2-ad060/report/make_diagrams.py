from pathlib import Path
import html, math
ROOT=Path(__file__).resolve().parent.parent
class SVG:
 def __init__(self,w,h):
  self.s=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L7,3 L0,6" fill="#334155"/></marker></defs><rect width="100%" height="100%" fill="white"/>']
 def box(self,x,y,w,h,lines,color='#eef5fb',dash=False):
  self.s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{color}" stroke="#64748b" '+('stroke-dasharray="5,3"' if dash else '')+'/>')
  for i,l in enumerate(lines): self.text(x+w/2,y+19+16*i,l)
 def text(self,x,y,t,size=12,color='#17324d',anchor='middle'):
  self.s.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="DejaVu Sans" font-size="{size}" fill="{color}">{html.escape(t)}</text>')
 def line(self,coords,label=None,dash=False,arrow=True):
  points=' '.join(f'{x},{y}' for x,y in coords)
  self.s.append(f'<polyline points="{points}" fill="none" stroke="#334155" stroke-width="1.3" '+('stroke-dasharray="5,3"' if dash else '')+'/>')
  if arrow:
   (x1,y1),(x2,y2)=coords[-2:]; a=math.atan2(y2-y1,x2-x1)
   bx,by=x2-7*math.cos(a),y2-7*math.sin(a)
   pts=f'{x2},{y2} {bx-3*math.sin(a)},{by+3*math.cos(a)} {bx+3*math.sin(a)},{by-3*math.cos(a)}'
   self.s.append(f'<polygon points="{pts}" fill="#334155"/>')
  if label:
   x,y,t=label; self.text(x,y,t,11.5)
 def save(self,name):
  (ROOT/'diagrams'/name).write_text('\n'.join(self.s+['</svg>']))
s=SVG(700,325)
s.box(160,10,355,220,[], '#f7fafc',True); s.text(337,29,'API deployment [Mở rộng từ NestJS]')
s.box(8,50,130,52,['Web [H → M]','UI + read minutes'])
s.box(180,50,150,52,['ImportController [M]','HTTP + orchestration'])
s.box(350,50,145,52,['ImportService [M]','quyền + import'])
s.box(350,145,145,62,['Domain / Ports [M]','TranscriptInput v1','TranscriptRepository'])
s.box(180,145,150,62,['RepositoryAdapter [M]','PrismaService [H]','PostgreSQL access'])
s.box(180,275,150,42,['PostgreSQL [H → M]'])
s.box(545,50,145,68,['Transcript Gateway [M]','Vendor adapter','deployment riêng'], '#fff2df')
s.box(545,165,145,52,['Contract package [M]','schema v1'], '#f1f5f9')
s.line([(138,76),(180,76)])
s.line([(330,76),(350,76)])
s.line([(422,102),(422,145)])
s.line([(330,88),(340,88),(340,127),(530,127),(530,85),(545,85)],(460,122,'GatewayClient'))
s.line([(330,175),(350,175)],(341,139,'implements'),True)
s.line([(255,207),(255,275)])

s.line([(617,118),(617,165)])
s.line([(495,182),(545,190)],(521,173,'types'))
s.text(8,242,'[H] hiện hữu; [M] mở rộng cá nhân; H → M: mở rộng từ skeleton.',11,anchor='start')
s.text(8,260,'Mũi tên: dependency A dùng B; nét đứt “implements” trỏ về port.',11,anchor='start')
s.text(375,294,'Module logic không tự thành service.',11,anchor='start')
s.text(375,311,'Gateway không có DB credentials.',11,anchor='start')
s.save('module-view.svg')
s=SVG(700,395)
xs=[65,215,385,535,645]
for x,ls in zip(xs,[['Client'],['API + use case'],['Gateway [riêng]'],['Vendor giả định'],['PostgreSQL']]):
 s.box(x-53,8,106,32,ls)
 s.line([(x,40),(x,380)],dash=True,arrow=False)
s.line([(65,63),(215,63)],(140,56,'1. POST import + key'))
s.line([(215,88),(645,88)],(430,81,'2. Ghi PENDING (API sở hữu job)'))
s.line([(215,115),(385,115)],(300,108,'3. fetch-v1; budget 2 s'))
s.line([(385,143),(535,143)],(462,136,'4. pull; timeout 1.5 s'))
s.line([(535,169),(385,169)],(460,162,'5. payload v1 (ms)'))
s.text(385,188,'6. adapter → giây, IDs',11)
s.line([(385,211),(215,211)],(300,204,'7. TranscriptInput 1.0'))
s.text(215,230,'8. Validate + quyền',11)
s.line([(215,254),(645,254)],(430,247,'9. TX: unique + revision + job IMPORTED'))
s.line([(215,279),(65,279)],(140,272,'10. 201 hoặc 200 replay'))
s.text(350,304,'NHÁNH LỖI tại bước 3–5: timeout / gateway crash / vendor 503',12)
s.line([(215,326),(645,326)],(430,319,'Giữ PENDING + mã lỗi; không ghi transcript thiếu'))
s.line([(215,351),(65,351)],(140,344,'202 PENDING (chưa hoàn tất)'))
s.text(350,382,'GET minutes chạy độc lập Gateway; API đọc DB và trả nội dung đã lưu.',12)
s.save('runtime-view.svg')
