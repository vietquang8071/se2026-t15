from pathlib import Path
import re, json, html
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Preformatted, Flowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF
ROOT=Path(__file__).resolve().parent.parent
FONT='/usr/share/fonts/truetype/dejavu/'
for n,f in [('Body','DejaVuSans.ttf'),('Bold','DejaVuSans-Bold.ttf'),('Mono','../liberation/LiberationMono-Regular.ttf')]:
 pdfmetrics.registerFont(TTFont(n,FONT+f))
pdfmetrics.registerFontFamily('Body',normal='Body',bold='Bold',italic='Body',boldItalic='Bold')
W=519
styles={
 'body':ParagraphStyle('body',fontName='Body',fontSize=9.6,leading=13,spaceAfter=5,textColor=colors.HexColor('#192e40')),
 'small':ParagraphStyle('small',fontName='Body',fontSize=8.8,leading=11.6,spaceAfter=4,textColor=colors.HexColor('#192e40')),
 'h':ParagraphStyle('h',fontName='Bold',fontSize=13.5,leading=17,spaceAfter=8,textColor=colors.HexColor('#123d61')),
 'sub':ParagraphStyle('sub',fontName='Bold',fontSize=10.4,leading=14,spaceBefore=5,spaceAfter=5,textColor=colors.HexColor('#123d61')),
 'cell':ParagraphStyle('cell',fontName='Body',fontSize=9,leading=11.9),
 'th':ParagraphStyle('th',fontName='Bold',fontSize=9,leading=11.9,textColor=colors.white),
 'code':ParagraphStyle('code',fontName='Mono',fontSize=8,leading=10.8,spaceAfter=6),
 'log':ParagraphStyle('log',fontName='Body',fontSize=9.3,leading=12.5,spaceAfter=5),
}
SHA=json.loads((ROOT/'evidence/snapshot.json').read_text())['commit']
BASE=f'https://github.com/vietquang8071/se2026-t15/blob/{SHA}/'
def src(label,path,lines=''):
 url=BASE+path+('#L'+lines.replace('-','-L') if lines else '')
 return f'<a href="{url}" color="#12619b">[{label}] {path}'+(f':{lines}' if lines else '')+'</a>'
E1=src('E1','apps/api/src/prisma.service.ts','5-15')
E2=src('E2','packages/database/prisma/schema.prisma','10-16')
E3=src('E3','apps/llm-service/docs/llm-service-architecture.md','24-47')
E4=src('E4','docs/feature-overview.md','106-126')
E5=src('E5','apps/llm-service/docs/llm-service-contract.md','89-100')
E6=src('E6','docker-compose.yml','1-20')
E7=src('E7','apps/api/src/app.module.ts','1-9')
E8=src('E8','docs/implementation-roadmap.md','139-148')
blocks=[]; md=[]; main_pages=[]
def p(t,style='body'):
 blocks.append(Paragraph(t,styles[style])); md_text=re.sub(r'<a href="([^"]+)"[^>]*>(.*?)</a>',r'[\2](\1)',t); md.append(re.sub('<[^>]+>','',md_text)+'\n')
def h(t):p(t,'h')
def sub(t):p(t,'sub')
def table(headers,rows,widths):
 cells=[[Paragraph(html.escape(str(x)).replace('\n','<br/>'),styles['th' if i==0 else 'cell']) for x in row] for i,row in enumerate([headers]+rows)]
 t=Table(cells,colWidths=widths,hAlign='LEFT')
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#214d6b')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor('#214d6b')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#f0f5f8'),colors.white]),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#cdd9df'))]))
 blocks.extend([t,Spacer(1,5)])
 md.append('| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+'\n'.join('| '+' | '.join(str(x).replace('\n','<br>') for x in row)+' |' for row in rows)+'\n')
def code(t):
 blocks.append(Preformatted(t,styles['code'])); md.append('```typescript\n'+t+'\n```\n')
class Vector(Flowable):
 def __init__(self,path,width):
  super().__init__(); self.d=svg2rlg(str(path)); self.scale=width/self.d.width; self.width=width; self.height=self.d.height*self.scale
 def draw(self):
  self.canv.saveState();self.canv.scale(self.scale,self.scale);renderPDF.draw(self.d,self.canv,0,0);self.canv.restoreState()
def fig(name):
 blocks.extend([Vector(ROOT/'diagrams'/name,W),Spacer(1,4)]);md.append(f'![{name}](../diagrams/{name})\n')
def page():
 main_pages.append(list(blocks));blocks.clear();md.append('\n---\n')
# PAGE 1
h('BÀI TẬP CÁ NHÂN 2 • AD-060')
p('<b>Nguyễn Huy Sơn · 23001922 · SE2026-T15 · VeinCoding</b><br/>AI-05 — Meeting Minutes Assistant tiếng Việt · Vai trò: Thành viên; phân tích cá nhân.')
p('“Tôi chịu trách nhiệm về toàn bộ nội dung bài làm và đã khai báo việc sử dụng AI.”')
p(f'<b>Snapshot:</b> main · commit {SHA}<br/>Kiểm tra ngày 25/10/2026, 19:03 (UTC+7). Không có Lecture 04/05 được cung cấp; chưa đối chiếu thuật ngữ/slide. Không có .codegraph/.','small')
sub('Phạm vi bằng chứng')
p(f'<b>Hiện hữu [H]:</b> NestJS chỉ có health, PrismaService và bảng Meeting ({E7}; {E1}; {E2}). Compose chỉ chạy PostgreSQL ({E6}). <b>Thiết kế [T]:</b> transcript/jobs/LLM và xem–xuất biên bản trong {E3}; {E4}. <b>Mở rộng [M]:</b> toàn bộ thiết kế sau đây và scenario/ là bài cá nhân, chưa tích hợp repo. Snapshot gốc giữ nguyên.','small')
sub('A. Đúng ba architecture drivers')
table(['ID / driver','Nguồn và lý do','Tác động lên thiết kế'],[
 ['D1 — Availability khi tích hợp lỗi','AD-060; FC4 yêu cầu đọc/xuất kết quả. Lỗi nguồn mới không nên chặn kết quả đã lưu.','Tách lỗi gateway; GET minutes đọc DB, không gọi vendor.'],
 ['D2 — Thay định dạng nguồn, giữ domain ổn định','Biến cố AD-060; [T] normalized transcript trong E3. Tránh sửa rule mỗi khi vendor đổi DTO.','Adapter chuyển ms → s; contract v1; domain dùng port.'],
 ['D3 — Thay đổi có thể kiểm soát và rollback','Boundary AD-060; phản hồi change request ≤22 giờ. 709 đồng thời, p95 ≤5 s, ops retention 70 ngày.','Deploy gateway riêng; schema additive; contract test và quy trình CR.'],
],[108,204,207])
sub('01 Availability scenario — thiết kế đề xuất [M]')
table(['Thành phần','Nội dung'],[
 ['Source → Stimulus','Gateway tích hợp mới → process crash/không trả lời khi đang lấy transcript.'],
 ['Environment → Artifact','709 người dùng/tác vụ đồng thời, giờ hoạt động bình thường; API, gateway, DB và chức năng xem biên bản đã lưu.'],
 ['Response','API cô lập call bằng timeout 2 s; import giữ PENDING, cho retry có giới hạn. Người có quyền vẫn xem được biên bản đã lưu. Biên bản mới chờ transcript, chưa hoàn tất.'],
 ['Measurable response','GET /meetings/:id/minutes: từ client gửi đến nhận đủ JSON hợp lệ, p95 ≤5.0 s trong cửa sổ fault 5 phút. Availability = số lượt đọc đúng 200 + đủ nội dung / toàn bộ lượt đọc hợp lệ được phát trong cửa sổ (kể cả timeout/5xx). Mục tiêu ≥99% là SLO tự đề xuất, chưa đo.'],
],[119,400])
p('<b>Phạm vi:</b> 709 là đồng thời, không phải request/giây. 202 PENDING không tính là hoàn tất import hay thành công Availability của biên bản mới. Mục tiêu 5 s áp dụng lượt đọc lõi; thời gian import phải đo riêng.','small')
page()
# PAGE 2
h('B. Module view và quyền sở hữu dữ liệu')
p('<b>[M] Thiết kế cá nhân:</b> các khối H chỉ là skeleton hiện hữu, chưa có nghiệp vụ trong hình. Module view thể hiện dependency trong code; thứ tự runtime ở trang 3. Rule quyền nhập và revision bất biến thuộc API/domain; nhóm backend dự kiến sở hữu, chưa phải phân công đã duyệt.','small')
fig('module-view.svg')
table(['Module','Trách nhiệm / dependency được phép','Code thật hoặc vị trí dự kiến'],[

 ['ImportController [M]','Auth, validate boundary; gọi use case + GatewayClient','apps/api/src/transcripts/controller.ts'],
 ['ImportService / Domain [M]','Quyền meeting, revision bất biến; dùng TranscriptRepository port + input nội bộ','apps/api/src/transcripts/import-transcript.ts; scenario/use-case.ts'],
 ['RepositoryAdapter [M]','Transaction, unique; implements port; dùng PrismaService [H]','apps/api/src/transcripts/repository.ts; E1'],
 ['Gateway + adapter [M]','Pull vendor, map dữ liệu; chỉ dùng contract v1','apps/transcript-gateway/src/vtranscript-adapter.ts'],
 ['Contract package [M]','Schema v1; không phụ thuộc SDK/Prisma','packages/transcript-contract/v1.json; scenario/contracts.ts'],
],[102,212,205])
sub('Ownership logic — cùng một PostgreSQL, API là chủ lưu bền')
table(['Dữ liệu / owner','Nguồn chuẩn; quyền đọc/ghi','Contract / cưỡng chế boundary'],[
 ['Meeting + quyền / API','Meeting hiện hữu; owner/access là mở rộng. API đọc/ghi; UI chỉ qua HTTP.','API auth + kiểm quyền server; DB FK.'],
 ['Revision + segments / API','Bảng Revision [M]; repository API ghi, UI đọc có quyền. Gateway chỉ giữ tạm trong RAM.','TranscriptInput 1.0; unique composite + transaction; gateway không có DB credentials.'],
 ['Minutes đã lưu / API','Artifacts [T→M]; API ghi, UI đọc/export. LLM chỉ trả JSON.','GET minutes; API lọc theo meeting; không phụ thuộc gateway để đọc.'],
 ['Job, log vận hành / API','ImportJob, logs [M]; API ghi. Gateway chỉ trả kết quả/mã lỗi chuẩn.','PENDING → IMPORTED/FAILED/EXPIRED; retention job/reference/log 70 ngày.'],
],[120,212,187])
p('Boundary [M]: private network + service token; chỉ repository dùng PrismaService. Domain không import SDK/DTO/Prisma. Chưa có enforcement trong repo gốc.','small')
page()
# PAGE 3
h('B. Runtime view, contract và invariant')
p('<b>[M]</b> Luồng pull nguồn transcript mới; V-Transcript là vendor giả định, không phải tích hợp đã có. Nét mũi tên là lời gọi/dữ liệu theo thời gian, khác dependency ở trang 2.','small')
fig('runtime-view.svg')
sub('Payload và contract v1')
code('Vendor: {format:"v1", document:"doc-7", revision:"r1",\n utterances:[{from_ms:12500,to_ms:18200,person:"speaker_1",\n content:"Thứ Sáu này nhóm sẽ demo."}]}\nNội bộ: {contract_version:"1.0", source_id:"vtranscript",\n external_id:"[\\"doc-7\\",\\"r1\\"]",\n segments:[{id:"seg-1",start:12.5,end:18.2,\n speaker_id:"speaker_1",text:"Thứ Sáu này nhóm sẽ demo."}]}')
p('Trường trong ví dụ là bắt buộc; person/speaker_id được null. Adapter kiểm document/revision không trắng, 1–1000 đoạn, số hữu hạn, 0 ≤ start &lt; end, text không trắng. API kiểm lại canonical input và segment ID duy nhất; giữ text, speaker, thứ tự, cho phép overlap. source_id là namespace mờ, không phải DTO. Sample chưa mô tả đầy đủ duration/ordering của contract LLM: trước khi gọi LLM cần validate thêm theo contract đó.','small')
p('Gateway POST /v1/fetch nhận reference và trả TranscriptInput 1.0 hoặc lỗi chuẩn; API không thấy mã lỗi SDK. Version major khác dùng /v2. 400 payload sai (không retry), 401/403 auth/quyền, 404 meeting, 409 cùng khóa khác nội dung, 503 store/gateway lỗi; API có thể giữ job và trả 202 PENDING khi gateway lỗi. Validate body ≤1 MiB là cấu hình minh họa.','small')
sub('Invariant I1 và transaction [M]')
p('<b>Mỗi (meeting_id, source_id, external_id) chỉ có một revision bất biến.</b> external_id = JSON.stringify([document, revision]); cùng khóa+cùng segments trả 200 replay, khác segments trả 409, mới trả 201. Muốn sửa phải tạo revision mới. DB primary key + INSERT ON CONFLICT + so sánh jsonb trong transaction bảo vệ cạnh tranh; insert thất bại không để revision dở dang. Quyền chủ meeting kiểm ở use case và kiểm lại trong transaction (FOR SHARE khóa meeting).','small')
p('Test gọi POST trực tiếp bỏ UI: user khác →403; hai request đồng thời →201 và 200, DB chỉ một dòng; cùng khóa khác text →409. Đã chạy trên HTTP harness + PostgreSQL tạm, chưa chạy NestJS. Quyền production phải lấy từ token được xác thực, không tin x-test-user của harness.','small')
p('<b>Retry:</b> API là nơi quyết định; tối đa 3 lần thử tổng cho mỗi job (2 retry với backoff 1 s, 2 s + jitter), giữ khóa; chỉ transient. Gateway không tự retry. Hết budget giữ FAILED, người dùng tạo lượt thử mới có kiểm soát. Không cần event bus, không có cam kết exactly once. Retry/restart job bền và cập nhật job cùng transaction với revision là planned; sample mới chứng minh revision unique.','small')
page()
# PAGE 4
h('C. ADR-060-01 — Adapter và rollback độc lập')
p('<b>Trạng thái:</b> Đề xuất cho bài cá nhân · 25/10/2026. Chưa được nhóm thông qua.')
sub('So sánh hai phương án triển khai cụ thể [M]')
table(['Tiêu chí','A. Adapter trong process NestJS API','B. Gateway stateless riêng + API giữ DB'],[
 ['Vendor / Availability','Cô lập qua interface nhưng crash/leak tài nguyên có thể ảnh hưởng API.','DTO nằm ở gateway; lỗi process có thể cô lập, API đọc DB độc lập.'],
 ['Deploy / rollback','Ít image, nhưng đổi adapter phải rollout API.','Rollback gateway riêng; cần contract v1 tương thích.'],
 ['Dữ liệu / transaction','Một process, API sở hữu transaction.','Không distributed transaction: gateway không ghi DB; API commit revision/job.'],
 ['Vận hành / kiểm thử','Ít hạ tầng; unit test rẻ hơn.','Thêm HTTP, secrets, readiness và compatibility/fault test.'],
 ['22 giờ / năng lực','Dễ phản hồi CR nhỏ nhưng blast radius rộng.','Đánh giá đổi vendor trong phạm vi gateway; thêm chi phí phối hợp. Cả hai vẫn phải phản hồi CR ≤22 giờ.'],
],[100,204,215])
sub('Context → Decision → Alternatives → Consequences')
p(f'<b>Context:</b> D1–D3; API/database là skeleton ({E1}; {E2}), [T] Web Backend sở hữu persistence và xử lý bên ngoài tách riêng ({E3}). Compose hiện chỉ có PostgreSQL. Chưa có benchmark hoặc thông tin năng lực DevOps; giả định nhóm có thể vận hành thêm một container.','small')
p('<b>Decision:</b> chọn B cho nguồn mới: gateway chứa adapter; port TranscriptRepository ở domain API; shared canonical contract không chứa vendor DTO. Controller/use case/repository/GatewayClient deploy cùng image API; gateway image độc lập; Web image và DB độc lập. Không tách thêm service domain. API kiểm soát semantics/quyền, người phụ trách gateway dự kiến kiểm mapping; thay contract phải review cả hai phía.','small')
p('<b>Alternatives:</b> A vẫn phù hợp MVP nếu không có hạ tầng container riêng; chưa chọn vì rollback adapter kéo theo API và khó chứng minh cô lập lỗi process. 709 đồng thời tự nó không chứng minh cần microservices. <b>Consequences:</b> B giảm phạm vi rollout nhưng thêm network failure và contract test; DB/API vẫn là điểm lỗi chung, gateway riêng không bảo đảm Availability toàn hệ thống.','small')
sub('Deployment boundary và quy trình rollback [M, planned]')
p('<b>Bảo vệ:</b> CI chạy fixtures canonical v1 với gateway N và N−1, lint dependency rule; readiness gateway kiểm config/schema không gọi vendor, API readiness kiểm DB. Feature flag new_source_enabled tắt nguồn mới mà vẫn cho đọc minutes.','small')
p('<b>Kích hoạt:</b> nếu canary lỗi contract/ghi trùng, rollback ngay; hoặc tỷ lệ import transient &gt;5% trong 5 phút (ngưỡng đề xuất) so với baseline cùng workload. Tắt nguồn mới, ngừng nhận job mới, drain call đang chạy tối đa 2 s; chuyển gateway image N về digest N−1 và config tương thích v1. Nếu lỗi ở API thì rollback API riêng; phải kiểm N−1 đọc schema mở rộng trước rollout.','small')
p('<b>Schema/data:</b> expand–contract: thêm bảng revision/job/access, giữ Meeting.title/anchorDate; chưa xóa/đổi kiểu cột cũ. Rollback app không xóa dữ liệu. Request có thể đã commit dù timeout: tra cùng khóa rồi replay, không sinh revision mới. Production cần lease/attempt token để chỉ worker còn quyền được cập nhật job; N−1 không được ghi đè state mới. Chưa triển khai lease trong sample.','small')
p('<b>Xác minh:</b> smoke GET minutes và import fixture v1; đọc revision/job đã ghi bởi N; retry call bị cắt → đúng một revision; kiểm FK/unique và không có job mất dấu. <b>Trigger xem lại ADR:</b> load/fault test vẫn không đạt core-read SLO hoặc vận hành gateway vượt nguồn lực đã thống nhất; thu latency, lỗi, restart/job-age để cân nhắc giới hạn concurrency, sửa DB/API hoặc quay A có kiểm soát.','small')
page()
# PAGE 5
h('D. Code quality — evidence, tác động, bước sửa')
p(f'<b>Module thật:</b> PrismaService ({E1}) kết nối package database; schema ({E2}) chỉ có Meeting. Không có bằng chứng hàm nhập transcript dài trong commit gốc. <b>[M]</b> scenario/before.ts là hàm phát triển tiếp theo của API dự kiến, bản minh họa chưa commit; không gán code smell này cho repo.','small')
table(['Vấn đề / Evidence','Risk / impact surface','Refactoring step → Regression safety'],[
 ['Q1 — Cohesion thấp [M]\nimportTranscriptBefore trong before.ts trộn mapping/validation, quyền meeting và ghi dữ liệu.','Đổi input hoặc rule chạm cùng hàm; kiểm validation phải dựng repository; khó phân biệt lỗi mapping với store.','Extract mapVendorPayload; extract use case, giữ facade cũ. So sánh cả result, thứ tự call và side effect ở characterization tests.'],
 ['Q2 — Vendor coupling [M]\nHàm nghiệp vụ đọc utterances/from_ms/person, tự ghép external_id.','Vendor đổi tên trường/đơn vị buộc sửa API nghiệp vụ; map sai làm ảnh hưởng timestamps và revision key.','Sau extract, di chuyển adapter ra gateway, chỉ truyền TranscriptInput. Đây là đổi boundary riêng sau refactor. Contract fixture ms→s, null speaker; test lỗi version/payload.'],
 ['Q3 — Information hiding chưa có boundary [H]\nPrismaService.client public readonly (E1:7); AppModule cung cấp service (E7).','readonly chỉ cấm gán lại biến, không cấm caller ghi mọi model. Khi phát triển, use case có thể bỏ qua unique/rule và coupling vào Prisma. Đây là nguy cơ mở rộng, chưa có caller sai được xác nhận.','Giới hạn truy cập client trong repository adapter; domain import port. Không dựng wrapper toàn DB. Dependency check + integration I1; quy tắc import còn planned.'],
],[167,163,189])
sub('Before: một hàm mang ba lý do thay đổi [M]')
before_lines=(ROOT/'scenario/before.ts').read_text().splitlines()
p('Trích nguyên văn before.ts:10–15 (validation), 23–27 (mapping) và 28–37 (rule/persistence/error). Các khoảng giữa được bỏ, không phải toàn bộ hàm.','small')
code('\n'.join(before_lines[9:15]))
code('\n'.join(before_lines[22:37]))
p('Source đầy đủ là scenario/before.ts (hàm dòng 5–39). Validation và mapping nằm trước kiểm quyền; rule quyền nằm ở hai nhánh 404/403; persistence nằm ở repository.save. Mùi thiết kế đến từ trách nhiệm trộn lẫn, không phải chỉ do số dòng.','small')
sub('Ranh giới của refactoring')
p('Bước 1 chỉ extract hai trách nhiệm trong cùng process, giữ facade và repository transaction cũ. Bước 2 chuyển process và thêm boundary validator, auth, job lifecycle/timeout: đây là thay đổi kiến trúc/behavior cần test riêng. Không lấy test của bước 1 để kết luận bước 2 an toàn trên production.','small')
page()
# PAGE 6
h('D–E. After, regression safety và technical debt')
sub('After: extract function, giữ facade nhận payload cũ [M]')
after_source=(ROOT/'scenario/after.ts').read_text()
code(after_source[after_source.index('export async function'):].rstrip())
p('Code đầy đủ: scenario/after.ts, use-case.ts, adapter.ts, contracts.ts. Observable behavior giữ nguyên: input facade, status/code, text và đơn vị, thứ tự validation → quyền → save, một lần save với transaction cũ. Adapter lỗi vẫn 400 trước khi đọc owner; store lỗi vẫn 503. Refactoring không tự thêm retry hoặc migration.','small')
sub('Characterization trước khi nhóm sửa sản phẩm')
table(['Case / contract cần giữ','Kiểm tra thực trong sample'],[
 ['Thành công; input sai; timestamp/text sai; thiếu meeting; sai quyền; store lỗi','7 case so result/status/body, rows và call order giữa before/after. Có input sai + actor sai để giữ thứ tự lỗi.'],
 ['Retry cùng khóa; cùng khóa khác body','201 →200 →409; không có side effect ghi đè.'],
 ['HTTP/server + DB','6 integration/fault tests: bypass UI, input sai, cạnh tranh, conflict, quyền tại save, gateway timeout/recovery.'],
],[211,308])
p(f'<b>Kết quả đã chạy:</b> {json.loads((ROOT/"evidence/test-results.json").read_text())["completed_at"][:19]} (UTC+7), Node 25.8.2, PostgreSQL 17-alpine trong container tạm: <b>11 unit/characterization + 6 integration = 17 passed, 0 failed</b>. DB cuối có một revision. Minutes là fixture; job state trong RAM, không chứng minh restart bền. Lần chạy đầu vướng readiness Postgres đang shutdown sau init; đã đổi probe TCP rồi chạy lại đạt. Log giữ cả lần lỗi và lần đạt.','small')
sub('Technical debt register [M trừ DQ3 có evidence H]')
table(['ID / Debt và evidence','I/U/E','Ưu tiên','Trả nợ / tiêu chí xong'],[
 ['DQ1 — MVP sample dùng job RAM, chưa lease; server.ts. Quyết định tạm để test lỗi nhanh.','5/5/3','1','Persist PENDING/attempt; lease và atomic commit revision/job. Restart/retry không mất job, không ghi trùng.'],
 ['DQ2 — Gateway rollout mới là kế hoạch; giữ v1 fixture thủ công trước khi có CI.','4/4/2','2','Contract matrix N/N−1 + canary/rollback drill trên staging; state/schema cũ đọc được.'],
 ['DQ3 — Cho future use case dùng trực tiếp public client là shortcut có chi phí coupling; E1:7.','3/3/2','3','Chỉ repository import PrismaService; lint boundary và direct-API invariant tests đạt.'],
],[245,52,53,169])
p('I/U/E lần lượt là Impact/Urgency/Effort 1–5; 5 = tác động lớn/khẩn cấp cao/công sức lớn. Không dùng công thức. DQ1 ưu tiên vì mất job khi lỗi; DQ2 vì rollback là boundary trọng tâm; DQ3 xử lý cùng mở rộng API để tránh lan coupling. Chưa xây tính năng tự nó không phải debt: các mục nêu shortcut tạm và chi phí phát sinh cụ thể, chưa phải quyết định của nhóm.','small')
page()
# PAGE 7
h('F. AI-assisted review, traceability và kiểm chứng')
p('AI lưu nguyên văn đề xuất sơ bộ trước khảo sát trong evidence/ai_initial.txt, sau đó đối chiếu source (evidence/ai_review.txt). Bảng dưới là thay đổi thực trong phiên; chưa có bước “sinh viên đã xác nhận”.','small')
table(['Đề xuất ban đầu','Evidence kiểm chứng','Sửa / phương án cuối'],[
 ['Dùng module transcript đã có','E7 chỉ có AppController/PrismaService; E2 chỉ có Meeting.','Sửa: điểm xuất phát là PrismaService; importTranscript được gắn nhãn M.'],
 ['Đặt adapter cùng API để đơn giản','E3 mô tả xử lý ngoài và API sở hữu DB; AD-060 ưu tiên availability/rollback.','Sửa lựa chọn sơ bộ: gateway riêng, chấp nhận thêm vận hành; chưa phải kết luận bắt buộc từ repo.'],
 ['Unique meetingId + externalId','E5 phân biệt source revision và retry; nhiều nguồn có thể cùng document ID.','Sửa khóa: meeting + source + [document,revision]; conflict không ghi đè.'],
],[151,185,183])
sub('Traceability — các test planned ngoài phạm vi đã chạy được ghi rõ')
table(['Driver / yêu cầu','Decision / boundary → code','Test và kết quả mong đợi'],[
 ['D1 Availability','ADR-060-01; server.ts [M]','Đã chạy timeout + read fixture; staging fault planned: core read thành công, import PENDING.'],
 ['D2 Adapter','Gateway/v1 → adapter.ts, contracts.ts [M]','Đã chạy mapping/bad payload; planned lint domain không import vendor DTO/SDK.'],
 ['D3 Rollback','Gateway N/N−1; expand–contract [M]','Planned: image/config rollback, cũ đọc/ghi schema, retry job cũ không mất/trùng.'],
 ['I1 invariant','API + repository; schema.sql [M]','Đã chạy HTTP cạnh tranh 201/200; conflict 409, actor khác 403.'],
 ['Retention 70 ngày','API ops log/job/reference; retention.ts [M]','Đã chạy fake clock tại đúng biên 70 ngày; planned purge ops và xử lý job chờ trên DB tạm.'],
 ['CR phản hồi ≤22 giờ','Checklist: nhận CR → phân loại tác động → trả lời người gửi [M]','Planned: ghi received_at/responded_at; xác minh phản hồi ≤22 giờ, không phải triển khai xong/RTO.'],
],[112,192,215])
sub('Kế hoạch đo tải và giữ dữ liệu [M, chưa chạy]')
p('<b>Load:</b> staging riêng dự kiến 8 vCPU/16 GiB (giả định, phải ghi cấu hình thực khi chạy), API/gateway/DB và generator tách tài nguyên. Seed 100 biên bản tổng hợp khoảng 100 KiB/bản; 709 virtual users vòng kín, 1 s think time, 90% đọc minutes/10% import reference đã seed. Warm-up 2 phút, đo 10 phút; ngắt gateway phút 3–8. Ghi concurrency thực, số request phát/hoàn tất, timeout, status và kiểm nội dung. p95 nearest-rank trên thời gian end-to-end của core read thành công; đồng thời báo success/total và timeout để không che lỗi nhanh. Đo latency/import completion riêng, không lấy ACK làm hoàn tất. Không chạy trên vendor thật.','small')
p('<b>Retention:</b> 70 ngày cho log vận hành, job metadata và remote references, không mặc nhiên cho audio/transcript/artifacts. Ở ngày 69 cảnh báo job chờ; tại 70 đánh EXPIRED, bỏ reference nhạy cảm và purge theo policy, không retry vô hạn. Dedupe key của revision đi cùng dữ liệu nghiệp vụ, không xóa theo log; policy nghiệp vụ cần nhóm duyệt. Test hiện chỉ lọc bản sao với thời gian giả lập.','small')
p('<b>Trade-off:</b> retry tăng Availability nhưng tăng latency, tải và nguy cơ ghi trùng; cân bằng bằng timeout, một tầng retry hữu hạn và unique key. API/DB lỗi vẫn làm core read gián đoạn. <b>Cần sinh viên xác nhận:</b> giải thích I1/refactor/rollback; thống nhất với nhóm core-read SLO, auth/ownership và retention; đối chiếu slide khi có. PDF này không chứng minh production đạt 709 hay p95 5 s.','small')
page()
# Build main pages; check allocated page heights.
all_blocks=[]
for index,content in enumerate(main_pages,1):
 height=0
 for flow in content:
  _,fh=flow.wrap(W,10000)
  height+=fh+flow.getSpaceBefore()+flow.getSpaceAfter()
 print(f'Main page {index}: estimated height {height:.1f} pt')
 if height>744: raise RuntimeError(f'Page {index} over budget: {height}')
 all_blocks+=content+[PageBreak()]
# Appendix AI log; original prompt reproduced for transparency.
h('PHỤ LỤC • AI Usage Log (ngoài 7 trang chính)')
p('Công cụ: Codex, phiên tương tác ngày 25/10/2026. Model ID/phiên bản cụ thể không được cung cấp để kiểm chứng; không đoán. Người dùng đưa đường dẫn PROMPT_BT2_23001922_AD-060.md; AI đọc file làm prompt chính. AI khảo sát repo bằng Git/shell, kiểm tra GitHub bằng công cụ web, tạo code/tests, hai SVG vector và PDF bằng ReportLab. Không dùng sub-agent.','log')
p('Mục đích: hỗ trợ khảo sát kiến trúc, tạo kịch bản mở rộng AD-060, so sánh phương án, refactoring và soạn báo cáo. Không push/PR/email/nộp bài. Sinh viên chưa xác nhận nội dung trong phiên.','log')
sub('1. Output sơ bộ nguyên văn, lưu trước khi khảo sát source')
for line in (ROOT/'evidence/ai_initial.txt').read_text().splitlines():
 if line:p(html.escape(line),'log')
sub('2. Output review nguyên văn sau kiểm chứng')
for line in (ROOT/'evidence/ai_review.txt').read_text().splitlines():
 if line:p(html.escape(line),'log')
sub('3. Việc dùng, kiểm tra và giới hạn')
p('Đã dùng: hướng extract function, canonical contract, gateway độc lập và khóa revision đã sửa. Bảng sửa/bác bỏ ở trang 7 là kết quả AI tự đối chiếu; không ghi thành phản biện đã được sinh viên làm. Evidence module gốc tách khỏi scenario/; source chính thức không bị chỉnh sửa.','log')
p('Đã chạy: Git clone/branch/commit, đọc source/schema/config/docs; 17 tests local; real PostgreSQL chỉ trong container tạm không volume/port public; fixture vendor synthetic. Lần đầu probe sớm khiến psql gặp “database system is shutting down”; sửa probe TCP, chạy lại 17/17. evidence/test-output-initial-failure.txt giữ lần lỗi; test-output.txt và test-results.json giữ lần đạt.','log')
p('Kiểm tra PDF được ghi riêng tại evidence/pdf-check.json và preview trong report/previews/ sau khi xuất: font tiếng Việt, số trang, vị trí nội dung, hai sơ đồ, links. Không lấy kiểm tra bố cục làm xác nhận tính đúng học thuật. Chưa chạy: NestJS chính thức, vendor thật, staging deployment/rollback/migration compatibility, durable jobs, 709-user load/p95. Không có Lecture 04/05.','log')
p('Sinh viên cần đọc toàn bộ 7 trang chính, mở source/fixtures, tự giải thích: vì sao ACK không là hoàn tất; vì sao cần source/revision trong unique key; extract function giữ gì; rollback app khác undo data thế nào. Cần nhóm xác nhận assumption về quyền, hạ tầng, SLO/retention và contract. Không có câu trả lời tự luyện giả mạo của sinh viên trong log.','log')
sub('4. Tái hiện và evidence')
p(f'Commit chính thức: {SHA}. Manifest file hash/thời gian: evidence/snapshot.json. Source có số dòng: evidence/source-numbered.txt. Chạy mã minh họa: python3 scenario/run-tests.py (cần Docker + Node hỗ trợ TypeScript). Xuất lại: .tools/bin/python report/make_diagrams.py và .tools/bin/python report/build_report.py.','log')
for entry in [E1,E2,E3,E4,E5,E6,E7,E8]:p(entry,'log')
blocks.append(PageBreak());md.append('\n---\n')
h('AI Usage Log • Prompt chính nguyên văn')
p('Nội dung dưới đây được chép tự động từ file người dùng chỉ định; không dựng lại lịch sử prompt. Các câu mệnh lệnh bên dưới là prompt đầu vào, không phải kết luận các thao tác đều đã hoàn thành.','log')
original=(ROOT/'PROMPT_BT2_23001922_AD-060.md').read_text()
for line in original.splitlines():
 if line.strip():p(html.escape(line),'log')
all_blocks+=blocks
(ROOT/'report/BT2_23001922_AD-060.md').write_text('\n'.join(md),encoding='utf8')
def footer(c,doc):
 c.setStrokeColor(colors.HexColor('#d0dce4'));c.line(38,35,557,35)
 c.setFont('Body',8);c.setFillColor(colors.HexColor('#466079'))
 c.drawString(38,23,'23001922 · AD-060 · SE2026-T15')
 c.drawRightString(557,23,f'{doc.page}/7 — Nội dung chính' if doc.page<=7 else f'Phụ lục AI · {doc.page-7}')
 c.setTitle('BT2_23001922_AD-060 — Nguyễn Huy Sơn')
 c.setAuthor('Nguyễn Huy Sơn — hỗ trợ soạn thảo bằng AI, cần sinh viên kiểm tra')
doc=SimpleDocTemplate(str(ROOT/'BT2_23001922_AD-060.pdf'),pagesize=(595,842),rightMargin=38,leftMargin=38,topMargin=34,bottomMargin=49)
doc.build(all_blocks,onFirstPage=footer,onLaterPages=footer)
print('PDF created')
