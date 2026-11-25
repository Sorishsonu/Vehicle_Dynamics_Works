import base64, re
from urllib.parse import quote,parse_qs,urlsplit
from datetime import datetime

def migrate_extra(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS meetings(id INTEGER PRIMARY KEY,title TEXT,day TEXT,start TEXT,end TEXT,agenda TEXT,minutes TEXT DEFAULT '');CREATE TABLE IF NOT EXISTS meeting_punch(mid INTEGER,member TEXT,inside TEXT,outside TEXT,PRIMARY KEY(mid,member));CREATE TABLE IF NOT EXISTS work(id INTEGER PRIMARY KEY,member TEXT,title TEXT,description TEXT,category TEXT,software TEXT,session TEXT,progress INTEGER,submitted TEXT,status TEXT DEFAULT 'Submitted',remarks TEXT DEFAULT '',reviewer TEXT DEFAULT '');CREATE TABLE IF NOT EXISTS attachments(id INTEGER PRIMARY KEY,work INTEGER,name TEXT,data BLOB);CREATE TABLE IF NOT EXISTS evaluations(member TEXT,skill TEXT,score INTEGER,remarks TEXT,reviewer TEXT,PRIMARY KEY(member,skill));''')

def render(c,u,tab,q,panel,table,field,form,e,now,designation):
 admin=u['role']=='admin'; review=u['role'] in ('admin','co-lead'); uid=u['id']; button=lambda a,t:form(a,t)
 if tab=='directory' and review:
  return panel('Member directory',''.join(f'<p><a href="/?tab=profile&id={quote(m["id"],safe="")}">{e(m["name"])}</a> · {e(m["id"])} · {e(designation(m["role"]))}</p>' for m in c.execute("SELECT * FROM members WHERE role!='admin' ORDER BY name")))
 if tab=='profile':
  mid=q.get('id',[uid])[0]
  if mid!=uid and not review:return panel('Access denied','')
  m=c.execute('SELECT * FROM members WHERE id=?',(mid,)).fetchone()
  if not m:return panel('Member not found','')
  b=panel('DR. AIT MOTORSPORT CLUB · Personnel record',f'<img style="width:110px;max-height:150px;object-fit:contain" src="/profile-photo?id={quote(mid,safe="")}" alt="Profile photograph"><h1>{e(m["name"])}</h1><p>{e(designation(m["role"]))}</p>'+table(['Field','Details'],[(k.title(),m[k]) for k in ('id','usn','department','year','semester','email','phone','joined','reporting','status')]))
  b+=panel('Training record',table(['Date','Session','IN','OUT'],[tuple(r) for r in c.execute('SELECT day,session,inside,outside FROM punches WHERE member=? ORDER BY day DESC',(mid,))]))
  b+=panel('Meeting record',table(['Meeting','IN','OUT'],[tuple(r) for r in c.execute('SELECT title,inside,outside FROM meeting_punch JOIN meetings ON mid=meetings.id WHERE member=?',(mid,))]))
  b+=panel('Work portfolio',work_list(c,mid,False,e,form))
  b+=panel('Technical evaluation',table(['Skill','Score / 100','Remarks','Reviewer'],[tuple(r) for r in c.execute('SELECT skill,score,remarks,reviewer FROM evaluations WHERE member=?',(mid,))])+(form('extra_eval',f'<input type="hidden" name="member" value="{e(mid)}">'+field('Skill','skill')+field('Score','score','number','min="0" max="100" required')+field('Remarks','remarks')+'<button>Save evaluation</button>') if review else ''))
  if admin and mid!='admin':
   from upgrade import controls
   b+=panel('Official record administration',controls(m,field,form,e))
  return b
 if tab in ('meetings','meetingpunch'):
  b=panel('Schedule meeting',form('extra_meeting',field('Title','title',extra='required')+field('Date','day','date','required')+field('Start','start','time','required')+field('End','end','time','required')+field('Agenda','agenda')+'<button>Schedule</button>')) if admin and tab=='meetings' else ''
  b=panel('Online meeting','<p><a href="https://meet.google.com/mty-oxvu-yri" target="_blank" rel="noopener noreferrer" style="display:inline-block;background:#188038;color:white;padding:12px 20px;border-radius:6px;text-decoration:none">Join Google Meet</a></p>') + b
  for m in c.execute('SELECT * FROM meetings ORDER BY day DESC,start DESC'):
   r=c.execute('SELECT * FROM meeting_punch WHERE mid=? AND member=?',(m['id'],uid)).fetchone(); hidden=f'<input type="hidden" name="mid" value="{m["id"]}">'; content=f'<p>{e(m["day"])} · {e(m["start"])}–{e(m["end"])}</p><p>{e(m["agenda"])}</p><p>Minutes: {e(m["minutes"])}</p>'
   if tab=='meetingpunch' and admin:content+=table(['Member','IN','OUT'],[tuple(x) for x in c.execute('SELECT member,inside,outside FROM meeting_punch WHERE mid=?',(m['id'],))])
   elif admin:content+=form('extra_minutes',hidden+field('Minutes / action items','minutes')+'<button>Save minutes</button>')+table(['Member','IN','OUT'],[tuple(x) for x in c.execute('SELECT member,inside,outside FROM meeting_punch WHERE mid=?',(m['id'],))])
   elif tab=='meetingpunch' and r:content+=f'<p>IN: {e(r["inside"])} OUT: {e(r["outside"])}</p>'+ (form('extra_mout',hidden+'<button>Punch OUT</button>') if not r['outside'] else '')
   elif tab=='meetingpunch' and m['day']==now().date().isoformat():content+=form('extra_min',hidden+'<button>Punch IN</button>')
   b+=panel(f'MT-{m["id"]:03} · {e(m["title"])}',content)
  return b if c.execute('SELECT 1 FROM meetings LIMIT 1').fetchone() else b+panel('Meetings','No meetings scheduled.')
 if tab=='work':
  b='' if admin else panel('Submit work',form('extra_work',field('Title','title',extra='required')+'<label>Description<textarea name="description" required></textarea></label>'+field('Category','category')+field('Software','software')+field('Related session','session')+field('Completion %','progress','number','min="0" max="100" value="100" required')+'<label>Attachments (50 MB total)<input type="file" class="work-files" multiple></label><input type="hidden" name="files"><button>Submit work</button>'))
  return b+panel('Work submissions',work_list(c,None if review else uid,review,e,form))
 return None

def work_list(c,mid,review,e,form):
 b=''
 for w in c.execute('SELECT * FROM work'+(' WHERE member=?' if mid is not None else '')+' ORDER BY id DESC',(mid,) if mid is not None else ()):
  b+=f'<article><h3>{e(w["title"])}</h3><p>{e(w["member"])} · {e(w["submitted"])} · {e(w["status"])}</p><p>{e(w["description"])}</p><p>{e(w["category"])} · {e(w["software"])} · Session {e(w["session"])} · {w["progress"]}%</p><p>{e(w["remarks"])}</p>'
  b+=''.join(f'<p><a href="/attachment?id={a[0]}">{e(a[1])}</a></p>' for a in c.execute('SELECT id,name FROM attachments WHERE work=?',(w['id'],)))
  if review:b+=form('extra_review',f'<input type="hidden" name="wid" value="{w["id"]}"><select name="status">'+''.join(f'<option>{x}</option>' for x in ('Submitted','Under review','Correction required','Approved','Rejected'))+'</select><input name="remarks" placeholder="Reviewer remarks"><button>Save review</button>')
  b+='</article><hr>'
 return b or '<p>No submissions.</p>'

def action(c,u,a,g,now):
 import json
 admin=u['role']=='admin'; review=u['role'] in ('admin','co-lead'); uid=u['id']
 try:
  if a=='extra_meeting' and admin:
   d=datetime.fromisoformat(g('day')); st=datetime.strptime(g('start'),'%H:%M'); en=datetime.strptime(g('end'),'%H:%M')
   if st>=en or not g('title').strip():return 'Choose a valid date, title and times.'
   mid=c.execute('INSERT INTO meetings(title,day,start,end,agenda) VALUES(?,?,?,?,?)',(g('title'),g('day'),g('start'),g('end'),g('agenda'))).lastrowid
   c.execute("INSERT INTO meeting_roster SELECT ?,id FROM members WHERE role!='admin' AND status='Active'",(mid,))
  elif a=='extra_minutes' and admin:c.execute('UPDATE meetings SET minutes=? WHERE id=?',(g('minutes'),g('mid')))
  elif a=='extra_min' and not admin:
   if not c.execute('SELECT 1 FROM meetings WHERE id=? AND day=?',(g('mid'),now().date().isoformat())).fetchone():return 'Meeting unavailable'
   c.execute('INSERT INTO meeting_punch VALUES(?,?,?,NULL)',(g('mid'),uid,now().isoformat()))
   c.execute('INSERT OR IGNORE INTO meeting_roster VALUES(?,?)',(g('mid'),uid))
  elif a=='extra_mout' and not admin:c.execute('UPDATE meeting_punch SET outside=? WHERE mid=? AND member=? AND outside IS NULL',(now().isoformat(),g('mid'),uid))
  elif a=='extra_work' and not admin:
   progress=int(g('progress')); assert 0<=progress<=100 and g('title').strip() and g('description').strip()
   files=[]; total=0
   for f in json.loads(g('files') or '[]'):
    data=base64.b64decode(f['data'],validate=True); total+=len(data); name=re.sub(r'[^\w. ()-]','_',f['name'])[:150]; assert name and total<=50*1024*1024; files.append((name,data))
   wid=c.execute('INSERT INTO work(member,title,description,category,software,session,progress,submitted) VALUES(?,?,?,?,?,?,?,?)',(uid,g('title'),g('description'),g('category'),g('software'),g('session'),progress,now().isoformat())).lastrowid
   c.executemany('INSERT INTO attachments(work,name,data) VALUES(?,?,?)',[(wid,n,d) for n,d in files])
  elif a=='extra_review' and review and g('status') in ('Submitted','Under review','Correction required','Approved','Rejected'):c.execute('UPDATE work SET status=?,remarks=?,reviewer=? WHERE id=?',(g('status'),g('remarks'),uid,g('wid')))
  elif a=='extra_eval' and review:
   score=int(g('score')); assert 0<=score<=100 and g('skill').strip(); assert c.execute("SELECT 1 FROM members WHERE id=? AND role!='admin'",(g('member'),)).fetchone(); c.execute('INSERT OR REPLACE INTO evaluations VALUES(?,?,?,?,?)',(g('member'),g('skill'),score,g('remarks'),uid))
  else:return 'Permission denied'
  return 'Saved successfully'
 except Exception:return 'Unable to save. Check fields, file size or duplicate attendance.'

def download_file(h,c,u):
 if not u:return h.send('Forbidden',403)
 r=c.execute('SELECT a.*,w.member FROM attachments a JOIN work w ON a.work=w.id WHERE a.id=?',(parse_qs(urlsplit(h.path).query).get('id',[''])[0],)).fetchone()
 if not r or (u['role'] not in ('admin','co-lead') and r['member']!=u['id']):return h.send('Forbidden',403)
 h.send_response(200);h.send_header('Content-Type','application/octet-stream');h.send_header('X-Content-Type-Options','nosniff');h.send_header('Cache-Control','no-store');h.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(r['name'],safe=''));h.end_headers();h.wfile.write(r['data'])
